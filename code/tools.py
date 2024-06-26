from __future__ import annotations
import os
import pandas as pd # All data is stored in pandas DataFrames
import numpy as np
from scipy.fftpack import fft, fftfreq
from scipy.signal import find_peaks
from scipy.optimize import curve_fit
import matplotlib
import matplotlib.pyplot as plt
import h5py 
from typing import Callable, List, Tuple, Any, Union, Optional
from tqdm import tqdm # Progress bar
from config import *

class DataFramePlus(pd.DataFrame):
    """ Custom DataFrame class with additional functionality """
    
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
    
    def read_hdf5(self, fpath: str, colpaths: dict, colidx: Optional[int]=None) -> None:
        """ HDF5 file to pandas DataFrame
        
        Parameters
        __________
        fpath: str
            File path to the HDF5 file
        colpaths: dict
            Dictionary of column paths in the HDF5 file
        colidx: int
            Index of the column to read (optional)
        
        Returns
        __________
        None
        """
        
        with h5py.File(fpath, 'r') as f:
            if colidx is None:
                # For command data
                for col, path in colpaths.items():
                    self[col] = f[path][()]
            else:
                # For measured data
                for col, path in colpaths.items():
                    self[col] = f[path][()][:, colidx]
        
    def read_csv(self, fpath: str, **kwargs) -> None:
        """ CSV file to pandas DataFrame
        
        Parameters
        __________
        fpath: str
            File path to the CSV file
        
        Returns
        __________
        None
        """
        
        df = pd.read_csv(fpath, **kwargs)
        self.__init__(df)
                
    def smart_save(self, fpath: str, **kwargs) -> None:
        """ Save DataFrame to file and check for overwrite
        
        Parameters
        __________
        fpath: str
            File path to save the DataFrame
        kwargs: dict
            Additional keyword arguments for pd.DataFrame.to_csv
            
        Returns
        __________
        None
        """
        if os.path.exists(fpath):
            check = input(f'File {fpath} exists. Overwrite? [y/n]: ')
            if check.lower() == 'n':
                return
            
        self.to_csv(fpath, **kwargs)
    
    def clean(self) -> None:
        """ Drop NaN values and reset DataFrame index
        
        Parameters
        __________
        None
        
        Returns
        __________
        None
        """
        self.dropna(inplace=True)
        self.reset_index(drop=True, inplace=True)
    
    def fragment_by_iteration(self, func: Callable[[pd.DataFrame, int, Any], Tuple[int, bool]], *args, **kwargs) -> List[DataFramePlus]:
        """ Fragment DataFrame into a list of smaller DataFrames
        
        Parameters
        __________
        func: Callable
            Interval-based logic to fragment the DataFrame, returns True on split and starting index
            
        Returns
        __________
        List[pandas.DataFrame]
            List of DataFrames
        """
        l_bound = self.index[0]
        MAX = self.index[-1]
        u_bound = l_bound + 1
        fragments = []
        prev_l_bound = l_bound

        with tqdm(total=MAX, desc="Fragmenting DataFrame", bar_format="{desc}: |{bar}| {percentage:.1f}%") as pbar:
            while u_bound <= MAX:
                l_bound, flag = func(self[l_bound:u_bound], l_bound, *args, **kwargs)
                if flag:
                    fragments.append(DataFramePlus(self[l_bound:u_bound]))
                    l_bound = u_bound
                u_bound += 1
                pbar.update(l_bound - prev_l_bound)
                prev_l_bound = l_bound
        tqdm.write(f"Fragmentation complete. {len(fragments)} fragments found.")
        return fragments
    
    def fragment_by_mask(self, func: Callable[[pd.DataFrame, Any], pd.Series], *args, **kwargs) -> List[DataFramePlus]:
        """ Fragment DataFrame into a list of smaller DataFrames
        
        Parameters
        __________
        func: Callable
            Mask-based logic to fragment the DataFrame, True for inclusion
        
        Returns
        __________
        List[pandas.DataFrame]
            List of DataFrames
        """
        mask = func(self, *args, **kwargs)
        fragments = []        

        for _, group in self[mask].groupby((~mask).cumsum()):
            fragments.append(DataFramePlus(group))

        print(f"Fragmentation complete. {len(fragments)} fragments found.")
        return fragments
    
    def dydx(self, xcol: str, ycol: str, deriv_name: str) -> None:
        """ Calculate the derivative of column y with respect to column x
        
        Parameters
        __________
        xcol: str
            Column name for x
        ycol: str
            Column name for y
        
        Returns
        __________
        None
        """

        self[deriv_name] = (self[ycol].shift(-1) - self[ycol].shift(1)) / (self[xcol].shift(-1) - self[xcol].shift(1))
        
        self.clean()
            
    def align(self, col_names: List[str], idx_shift: int) -> None:
        """ Align two columns through cross-correlation
        -> col2 will be shifted to match col1
        
        Parameters
        __________
        col_names: List[str]
            List of column names to align
        idx_shift: int
            Index shift for the alignment
        
        Returns
        __________
        None
        
        """
        for col in col_names:
            self[col] = self[col].shift(-idx_shift)
        self.clean()
    
    def FFT(self, col: Union[str, List[str]], sampling_rate: float) -> DataFramePlus:
        """ Generate FFT of selected columns of DataFrame
        
        Parameters
        __________
        col: Union[str, List[str]]
            Column name or list of column names to perform FFT on
        sampling_rate: float
            Sampling rate of the data
        
        Returns
        __________
        DataFramePlus
            DataFrame containing the FFT results
        """
        if isinstance(col, str):
            col = [col]
            
        N = self.shape[0]
        T = 1.0 / sampling_rate
        X_f = fftfreq(N, T)[:N//2]
        
        output = {"f": X_f}
        output.update({key: None for key in col}) 
        
        for c in col:
            Y_f = fft(np.array(self[c]))
            output[c] = Y_f[0:N//2]
        
        return DataFramePlus(output)
                  
            
    def _lag(self, col1: str, col2: str) -> int:
        """ Calculate the lag between two columns
        
        Parameters
        __________
        col1: str
            Column name for the first column
        col2: str
            Column name for the second column
        
        Returns
        __________
        int
            Lag index
        """
        cross_corr = np.correlate(self[col1], self[col2], mode='full')
        
        lag_idx = abs(cross_corr.argmax() - len(self[col2]))
        
        return lag_idx
        
    def _offset(self, col1: str, col2: str) -> float:
        """ Calculate the offset in mean between two columns
        
        Parameters
        __________
        col1: str
            Column name for the first column
        col2: str
            Column name for the second column
        
        Returns
        __________
        float
            Offset value
        """
        return np.mean(self[col1]) - np.mean(self[col2])

def linear_func(x: float, m: float) -> float:
    """ Linear function
    
    Parameters
    __________
    x: float
        Independent variable
    m: float
        Slope of the line
    
    Returns
    __________
    float
        Dependent variable
    """
    return m * x

def save(fig: matplotlib.figure.Figure, fig_type: str, fname: Optional[str]=None) -> None:
    """ Save the figure
    
    Parameters
    __________
    fig: matplotlib.figure.Figure
        Figure to save
    fig_type: str
        Type of figure to save
    fname: str
        File name to save the figure
    
    Returns
    __________
    None
    """
    if not fname:
        fname = input("Enter file name: ")
        
    fpath = f"{paths_plots[fig_type]}/{fname}.pdf"
    
    if os.path.exists(fpath):
            check = input(f'File {fpath} exists. Overwrite? [y/n]: ')
            if check.lower() == 'n':
                return
        
    fig.savefig(fpath, format="pdf", bbox_inches='tight')
    

def plot_signal(df: pd.DataFrame, type: Optional[str]='acceleration', save_check: Optional[bool]=False, fname: Optional[str]=None) -> None:
    """ Plot the full signal
    
    Parameters
    __________
    df: pd.DataFrame
        DataFrame to plot
    type: str
        Type of data to plot
    save_check: bool
        Flag to save the plot
    fname: str
        File name to save the plot
    
    Returns
    __________
    None
    """
    fig, ax = plt.subplots(1, 1, figsize=figsize_default)
    ax.plot(df['t'], df[f'{type[:3]}_mes'], label=f'Measured {type.capitalize()}', color=c2)
    ax.plot(df['t'], df[f'{type[:3]}_cmd'], label=f'Commanded {type.capitalize()}', color=c1)
    ax.set_xlabel('Time [s]')
    ax.set_ylabel(f'{type.capitalize()} [$m/s^2$]')
    
    ax.legend()
    ax.grid(True)
    
    if not save_check:
        plt.show()
    else:
        save(fig, "signal", fname)

def plot_IO(x_b: list, y_b: list, x_t: Optional[List[float]]=None, y_t: Optional[List[float]]=None,
            trend: Optional[bool]=True, fix_trend: Optional[bool]=False, freq_dep: Optional[bool]=True,
            save_check: Optional[bool]=True, fname: Optional[str]=None) -> list:
    """ Plot the input-output data
    
    Parameters
    __________
    x_b: list
        List of input data for the bottom sine
    y_b: list
        List of output data for the bottom sine
    x_t: list (optional)
        List of input data for the top sine
    y_t: list (optional)
        List of output data for the top sine
    trend: bool
        Flag to plot the trendline
    fix_trend: bool
        Set y-intercept to 0
    freq_dep: bool
        Flag to include/exclude frequency-dependent points on the I/O plot
    save: bool
        Flag to save the plot
    fname: str
        File name to save the plot
    
    Returns
    __________
    None
    """
    
    trend_data = []
    
    fig, ax = plt.subplots(1, 1, figsize=figsize_default)
    if x_t is not None or y_t is not None:
        x_t = np.array(x_t)
        y_t = np.array(y_t)
        x_b = np.array(x_b)
        y_b = np.array(y_b)

        if not freq_dep:
            mask_t = np.logical_or(np.logical_and(y_t>0.8, np.isclose(x_t, 3.00, atol=0.4)), np.logical_and(y_t>0.23, np.isclose(x_t, 0.3, atol=0.05)))
            mask_b = np.logical_or(np.logical_and(y_b>0.8, np.isclose(x_b, 3.00, atol=0.4)), np.logical_and(y_b>0.23, np.isclose(x_b, 0.3, atol=0.05)))
            x_t = x_t[~mask_t]
            y_t = y_t[~mask_t]
            x_b = x_b[~mask_b]
            y_b = y_b[~mask_b]
        
        ax.scatter(x_t, y_t, color=c1, label='Positive Acceleration', marker=marker1)
        ax.scatter(x_b, y_b, color=c2, label='Negative Acceleration', marker=marker2)
        ax.set_xlabel('Input Amplitude [$m/s^2$]')
        ax.set_ylabel('Bump Magnitude [$m/s^2$]')
        ax.legend()
            
        if trend:
            if fix_trend:
                z_t, _ = curve_fit(linear_func, x_t, y_t)
                z_b, _ = curve_fit(linear_func, x_b, y_b)
                y_t_pred = linear_func(x_t, z_t[0])
                y_b_pred = linear_func(x_b, z_b[0])
                residuals_t = [np.sum(np.power(y_t - y_t_pred, 2))]
                residuals_b = [np.sum(np.power(y_b - y_b_pred, 2))]
                z_t  = np.array([z_t[0], 0])
                z_b  = np.array([z_b[0], 0])

            else:
                z_t, residuals_t, _, _, _ = np.polyfit(x_t, y_t, 1, full=True)
                z_b, residuals_b, _, _, _ = np.polyfit(x_b, y_b, 1, full=True)
                
            p_t = np.poly1d(z_t)
            p_b = np.poly1d(z_b)

            # Calculate R^2
            ss_res_t = residuals_t[0]
            ss_tot_t = np.sum((y_t - np.mean(y_t))**2)
            r_squared_t = 1 - (ss_res_t / ss_tot_t)
            
            ss_res_b = residuals_b[0]
            ss_tot_b = np.sum((y_b - np.mean(y_b))**2)
            r_squared_b = 1 - (ss_res_b / ss_tot_b)
            

            trend_data.extend([[z_t[1], z_t[0], r_squared_t], [z_b[1], z_b[0], r_squared_b]])

            x_t = np.sort(x_t)
            x_b = np.sort(x_b)
            
            ax.plot(x_t, p_t(x_t), ls=linestyle1, color=c1)
            ax.plot(x_b, p_b(x_b), ls=linestyle1, color=c2)
            
    else:
        x_b = np.array(x_b)
        y_b = np.array(y_b)

        if not freq_dep:
            mask = np.logical_or(np.logical_and(y_b>0.8, np.isclose(x_b, 3.00, atol=0.4)), np.logical_and(y_b>0.23, np.isclose(x_b, 0.3, atol=0.05)))
            x_b = x_b[~mask]
            y_b = y_b[~mask]

        ax.scatter(x_b, y_b, color=c1, marker=marker1)
        ax.set_xlabel('Input Amplitude [$m/s^2$]')
        ax.set_ylabel('Bump Magnitude [$m/s^2$]')

        if trend:
            if fix_trend:
                z_b, _ = curve_fit(linear_func, x_b, y_b)
                y_b_pred = linear_func(x_b, z_b[0])
                residuals_b = [np.sum(np.power(y_b - y_b_pred, 2))]
                z_b  = np.array([z_b[0], 0])
            else:
                z_b, residuals_b, _, _, _ = np.polyfit(x_b, y_b, 1, full=True)

            ss_res_b = residuals_b[0]
            ss_tot_b = np.sum((y_b - np.mean(y_b))**2)
            r_squared_b = 1 - (ss_res_b / ss_tot_b)

            trend_data.extend([z_b[1], z_b[0], r_squared_b])
            p_b = np.poly1d(z_b)
            x_b = np.sort(x_b)
            ax.plot(x_b, p_b(x_b), ls=linestyle1, color=c1)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.grid(True)
    if not save_check:
        plt.show()
    else:
        save(fig, "I/O", fname)
        return trend_data

def plot_deBode(df_list: List[pd.DataFrame], cols: List[str], height: Optional[float]=0.2, save_check: Optional[bool]=True, fname: Optional[str]=None, cutoff: Optional[float]=float('inf')) -> None:
    """ Plot the deBode diagram for a given signal seperated into its consituent wavelengths (post FFT)
    
    Parameters
    __________
    df_list: List[pd.DataFrame]
        List of DataFrames containing the FFT results
    cols: List[str]
        cols[0] = X_f, cols[1] = Y_f
    height: float
        Height threshold for the peaks
    save_check: bool
        Flag to save the plot
    fname: str
        File name to save the plot
    
    Returns
    __________
    None
    """
    
    magnitudes = []
    phases = []
    freqs = []
    
    # Data pre-processing
    for wl in df_list:
        fft_mag = np.abs(wl[cols[0]])
        peaks, _ = find_peaks(fft_mag, height=height)
        
        # Calculate transfer function
        H_s = wl[cols[1]][peaks] / wl[cols[0]][peaks]
        mag_temp = []
        phases_temp = []
        freq_temp = []
        # Decompose transfer function
        for i, h in enumerate(H_s):
            if np.abs(h) < cutoff:
                mag_temp.append(20*np.log10(np.abs(h)))
                phases_temp.append(np.angle(h, deg=True))
                freq_temp.append(wl['f'][peaks[i]])
            
        magnitudes.extend(mag_temp)
        phases.extend(phases_temp)
        freqs.extend(freq_temp)
    
    # Plotting
    fig, ax = plt.subplots(2, 1, figsize=figsize_deBode)
    ax[0].scatter(freqs, magnitudes, color=c1, marker=marker1)
    ax[0].set_xlabel('Frequency [Hz]')
    ax[0].set_ylabel('Magnitude [dB]')
    ax[0].set_xscale('log')
    ax[0].grid(True)
    
    ax[1].scatter(freqs, phases, color=c1, marker=marker1)
    ax[1].set_xlabel('Frequency [Hz]')
    ax[1].set_ylabel('Phase [deg]')
    ax[1].set_xscale('log')
    ax[1].grid(True)
    
    plt.tight_layout()
    
    if not save_check:
        plt.show()
    else:
        save(fig, "deBode", fname)

def plot_IO_full(x: List[list], y: List[list], plt_names: List[str], freq_dep: Optional[bool]=True, bump_isol: Optional[bool]=False, save_check: Optional[bool]=True, fname: Optional[str]=None) -> None:
    """ Plot all input-output test data on the same plot
    
    Parameters
    __________
    x: List[list]
        List of input data
    y: List[list]
        List of output data
    plt_names: List[str]
        List of plot names
    freq_dep: bool
        Flag to include/exclude frequency-dependent points on the I/O plot
    bump_isol: bool
        Flag to exclude/include points only for the bump on the I/O plot
    save_check: bool
        Flag to save the plot
    fname: str
        File name to save the plot
    
    Returns
    __________
    None
    """
    fig, ax = plt.subplots(1, 1, figsize=figsize_default)

    for i, (xi, yi) in enumerate(zip(x, y)):
        if bump_isol and i == 0:
            continue

        xi = np.array(xi)
        yi = np.array(yi)

        if not freq_dep and i==0:
            mask = np.logical_or(np.logical_and(yi>0.8, np.isclose(xi, 3.00, atol=0.4)), np.logical_and(yi>0.23, np.isclose(xi, 0.3, atol=0.05)))
            xi = xi[~mask]
            yi = yi[~mask]

        ax.scatter(xi, yi, color=colors_all[i], marker=markers_all[i], label=plt_names[i])
        z, _, _, _, _ = np.polyfit(xi, yi, 1, full=True)
        p = np.poly1d(z)
        if not bump_isol:
            xi = np.append(xi, 3.0)
        xi = np.sort(xi)
        ax.plot(xi, p(xi), ls=linestyle1, color=colors_all[i])

    ax.set_xlabel('Input Amplitude [$m/s^2$]')
    ax.set_ylabel('Bump Magnitude [$m/s^2$]')
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.legend()
    ax.grid(True)

    if not save_check:
        plt.show()
    else:
        save(fig, "I/O", fname)