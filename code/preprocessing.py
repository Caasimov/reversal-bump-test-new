import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from filterpy.kalman import ExtendedKalmanFilter
import h5py
import os
import json

def kalman_filter():
    rk = ExtendedKalmanFilter(dim_x=3, dim_z=1)
    dt = 0.05

def hdf5_to_df(fname, dof):
    '''
    Load a hdf5 file into a pandas dataframe
    '''
    paths_cmd = [
        'data/commanded/tick',
        f'data/commanded/data/{dof}',
        f'data/commanded/data/{dof}dot',
        f'data/commanded/data/{dof}dotdot'
        ]
    paths_mes = [
        'data/measured/tick',
        'data/measured/data/actual_pos'
        ]
    
    index_match = {"x": 0, "y": 1, "z": 2, "phi": 3, "theta": 4, "psi": 5}
    column_names_cmd = ['t', 'pos_cmd', 'vel_cmd', 'acc_cmd']
    column_names_mes = ['t', 'pos_mes']
    
    with h5py.File(fname, 'r') as f:
        # Create a list of dataframes from the paths
        dfs_cmd = [pd.DataFrame(f[path][()], dtype=np.float64) for path in paths_cmd]
        dfs_mes = [
            pd.DataFrame(f[paths_mes[0]][()], dtype=np.float64),
            pd.DataFrame(f[paths_mes[1]][()][:, index_match[dof]], dtype=np.float64)
            ]
    
    # Concatenate the dataframes along the columns axis
    df_cmd = pd.concat(dfs_cmd, axis=1)
    df_mes = pd.concat(dfs_mes, axis=1)
    
    # Rename the columns
    df_cmd.columns = column_names_cmd
    df_mes.columns = column_names_mes
    
    # Merge the dataframes on the time column
    merged_df = pd.merge(df_cmd, df_mes, on='t', how='inner')
    
    # Adjust for inverted z-axis
    if dof == 'z':
        merged_df['pos_mes'] = merged_df['pos_mes'] * -1
    
    return merged_df

def clean_data(df):
    '''
    Remove rows with NaN values and reset index.
    '''
    df.dropna(inplace=True)
    df.reset_index(drop=True, inplace=True)
    
def find_derivatives(df):
    '''
    Compute derivatives of a specified DoF using central difference formula.
    '''
    df['vel_mes'] = (df['pos_mes'].shift(-1) - df['pos_mes'].shift(1)) / (df['t'].shift(-1) - df['t'].shift(1))
    df['acc_mes'] = (df['vel_mes'].shift(-1) - df['vel_mes'].shift(1)) / (df['t'].shift(-1) - df['t'].shift(1))
    
    # Remove rows with NaN values and reset index
    clean_data(df)

def find_offset(df):
    '''
    Determine positional/rotational system offset for a specified DoF between commanded and measured data.
    '''
    return np.mean(df['pos_mes']) - np.mean(df['pos_cmd'])

def find_lag(df):
    '''
    Determine the fixed delay between input and output signals using the commanded and measured positions using cross-correlation.
    '''    
    # Determine cross correlation
    cross_corr = np.correlate(df['pos_cmd'], df['pos_mes'], mode='full')
    
    idx_lag = abs(cross_corr.argmax() - len(df['pos_mes']) + 1) 
    time_lag = df.loc[idx_lag, 't'] - df.loc[0, 't']
    
    # Actual lag value in terms of time returned along with the position of the zero on the cmd and mes columns
    return time_lag, idx_lag

def find_zero(df):
    idx = 0
    vel_0=[]
    previous = 0
    for element in df['vel_cmd']:
        if previous * element < 0:
            vel_0.append(idx)
        idx += 1
        previous = element
    return vel_0

def createinterval(df):
    zeros = find_zero(df)
    freqlist = []
    for zero in range(len(zeros)-2):
        listdf = []
        for element in range(zeros[zero], zeros[zero+2]):
            listdf.append(element)
        freqlist.append(listdf)
    return freqlist

def preprocess(df, freq_sample=100):
    '''
    Clean the dataframe for direct analysis.
    '''
    
    # Determine time scaling factor
    delta_t = np.float64(1/freq_sample)
    scaling_factor = np.float64(delta_t/(df.loc[1, 't']-df.loc[0, 't']))
    
    # Adjust time column to be in seconds
    df['t'] = df['t']*scaling_factor

    # Add measured velocity and acceleration using forward difference formula
    find_derivatives(df)
    
    # Adjust for amplitude offset between cmd and mes signals
    df['pos_mes'] = df['pos_mes'] - find_offset(df)
    
    # Adjust for lag between cmd and mes signals
    _, idx_lag = find_lag(df)
    df['pos_mes'] = df['pos_mes'].shift(-idx_lag)
    df['vel_mes'] = df['vel_mes'].shift(-idx_lag)
    df['acc_mes'] = df['acc_mes'].shift(-idx_lag)
    clean_data(df)
    
    # Set t_0 to 0
    df['t'] = df['t'] - df.loc[0, 't']

def plot_dof(df, dof, file_type, interval=None):
    '''
    Plot position, velocity & acceleration corresponding to a specified DoF for both commanded and measured data. 
    '''
    if interval == None:
        interval = list(range(0, df.shape[0]))

    # Numerical derivatives of var_1
    vel_1 = df.loc[interval, 'vel_cmd']
    acc_1 = df.loc[interval, 'acc_cmd']
    
    # Numerical derivatives of var_2
    vel_2 = df.loc[interval, 'vel_mes']
    acc_2 = df.loc[interval, 'acc_mes']
    
    fig, axs = plt.subplots(3, 1, figsize=(10,10))

    # Position subplot
    axs[0].plot(df.loc[interval, 't'], df.loc[interval, 'pos_cmd'], label="CMD pos", color='blue')
    axs[0].plot(df.loc[interval, 't'], df.loc[interval, 'pos_mes'], label="MES pos", color='red')
    axs[0].set_title('Position')
    axs[0].legend()

    # Velocity subplot
    axs[1].plot(df.loc[interval, 't'], vel_1, label="CMD vel", color='blue')
    axs[1].plot(df.loc[interval, 't'], vel_2, label="MES vel", color='red')
    axs[1].set_title('Velocity')
    axs[1].legend()

    # Acceleration subplot
    axs[2].plot(df.loc[interval, 't'], acc_1, label="CMD acc", color='blue')
    axs[2].plot(df.loc[interval, 't'], acc_2, label="MES acc", color='red')
    axs[2].set_title('Acceleration')
    axs[2].legend()

    # Adding a xlabel for the whole figure
    for ax in axs:
        ax.set_xlabel('Time')

    # Adjust the layout
    plt.tight_layout()
    
    # Create the plots directory if it doesn't exist
    os.makedirs(f'plots/{dof}', exist_ok=True)
    
    # Save the figure
    plt.savefig(f'plots/{dof}/{file_type}.png', dpi=300)
    
    # Show the figure
    plt.show()

def extract_data_function(file_path):
    with open(file_path, 'r') as f:
    # Load the JSON data
        data = json.load(f)
    extracted_data = [
        [move["time"],
        move["move"]["profile"]["Tfade"],
        move["move"]["profile"]["Ttotal"],
        move["move"]["profile"]["omg"],
        move["move"]["profile"]["gain"],
        move["move"]["profile"]["phi0"],
        move["move"]["axis"]]
        for move in data["moves"] if "profile" in move["move"] and "FadedSineProfile" in move["move"]["profile"]["type"]
    ]
    return extracted_data

def time_conversion(extracted_data):
    time_stamps = []
    for i in range(0, len(extracted_data)):
        if len(extracted_data[i][3]) == 1:
            time_stamps.append([extracted_data[i][1]+extracted_data[i][0], extracted_data[i][2]+extracted_data[i][0]- extracted_data[i][1]])     
        else:   
            time_stamps.append([extracted_data[i][1]+extracted_data[i][0], extracted_data[i][2]+extracted_data[i][0]- extracted_data[i][1]])
    time_stamps =  [[round(entry * 10**-4, 6) for entry in sublist] for sublist in time_stamps]
    return time_stamps

file_direct = {
    "AGARD-AR-144-A" : 'data/json/srs-agard144a.json',
    "AGARD-AR-144-B": 'data/json/srs-agard144b.json',
    "AGARD-AR-144-D" : 'data/json/srs-agard144d.json', 
    "AGARD-AR-144-E" : 'data/json/srs-agard144e.json',
    "MULTI-SINE-1" : 'data/json/srs-test-motion-sines1.json',
    "MULTI-SINE-2" : 'data/json/srs-test-motion-sines2.json',
    "MULTI-SINE-3" : 'data/json/srs-test-motion-sines3.json'
}

file_type1 = 'MULTI-SINE-1'

extracted_data = extract_data_function(file_direct[file_type1])
if file_type1 == 'MULTI-SINE-1':
    extracted_data2 = extract_data_function(file_direct["MULTI-SINE-2"]) 
    for i in range(len(extracted_data2)):
        extracted_data2[i][0] = extracted_data[i][0] + extracted_data[-1][0] + extracted_data[-1][2]
    extracted_data.extend(extracted_data2)
    extracted_data2 = extract_data_function(file_direct["MULTI-SINE-3"]) 
    for i in range(len(extracted_data2)):
        extracted_data2[i][0] = extracted_data[i][0] + extracted_data[-1][0] + extracted_data[-1][2]
    extracted_data.extend(extracted_data2)

if file_type1 == "AGARD-AR-144-B":
    extracted_data2 = extract_data_function(file_direct["AGARD-AR-144-E"]) 
    for i in range(len(extracted_data2)):
        extracted_data2[i][0] = extracted_data[i][0] + extracted_data[-1][0] + extracted_data[-1][2]
    extracted_data.extend(extracted_data2)
    
file_dir = {
    "AGARD-AR-144_A": "data/hdf5/motionlog-20240301_133202.hdf5",
    "AGARD-AR-144_B+E": "data/hdf5/motionlog-20240301_141239.hdf5",
    "MULTI-SINE": "data/hdf5/motionlog-20240301_144109.hdf5",
    "BUMP": "C:/Users/Olafe/studie/project/motionlog-20240301_150040.hdf5",
    "PMD": "C:/Users/Olafe/studie/project/motionlog-20240301_150320.hdf5",
}

if __name__ == "__main__":
    dof = 'z'
    file_type = 'BUMP'
    df_z = hdf5_to_df(file_dir[file_type], dof)
    preprocess(df_z)
    zero = createinterval(df_z)
    print(zero)
    plot_dof(df_z, dof, file_type)
   

    time_stamps = time_conversion(extracted_data)
    filtered_rows = []

    # Iterate through each nested list
    for time_range in time_stamps:
        start_time, end_time = time_range
        
        # Filter the DataFrame based on the time range
        filtered_df = df_z[(df_z['t'] >= start_time) & (df_z['t'] <= end_time)]
        print(filtered_df)
        
        # Append the filtered rows to the list
        filtered_rows.append(filtered_df)
