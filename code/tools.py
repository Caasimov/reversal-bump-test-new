import os
import pandas as pd
import numpy as np
from scipy.fftpack import fft, fftfreq
import matplotlib
import matplotlib.pyplot as plt
import h5py
from typing import Callable, List, Tuple, Any, Union, Optional
from __future__ import annotations
from tqdm import tqdm
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
                for col, path in colpaths.items():
                    self[col] = f[path][()]
            else:
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
                    fragments.append(self[l_bound:u_bound])
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
            fragments.append(group)

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
        
        """
        if isinstance(col, str):
            col = [col]
            
        N = len(self.shape[1])
        T = 1.0 / sampling_rate
        X_f = fftfreq(N, T)[:N//2]
        
        output = {"f": X_f}
        output.update({key: None for key in col}) 
        
        for c in col:
            Y_f = fft(self[c]).to_numpy()
            output[c] = Y_f[0:N//2]
        
        return DataFramePlus(output)
                  
            
    def _lag(self, col1: str, col2: str) -> None:
        """ Calculate the lag between two columns
        
        Parameters
        __________
        col1: str
            Column name for the first column
        col2: str
            Column name for the second column
        
        Returns
        __________
        None
        """
        cross_corr = np.correlate(self[col1], self[col2], mode='full')
        
        lag_idx = abs(cross_corr.argmax() - len(self[col2]))
        
        return lag_idx
        
    def _offset(self, col1: str, col2: str) -> None:
        """ Calculate the offset in mean between two columns
        
        Parameters
        __________
        col1: str
            Column name for the first column
        col2: str
            Column name for the second column
        
        Returns
        __________
        None
        """
        return np.mean(self[col1]) - np.mean(self[col2])

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
        
    fpath = f"{paths_plots[fig_type]}/{fname}"
    
    if os.path.exists(fpath):
            check = input("File already exists. Overwrite? [y/n]: ")
            if check.lower() == 'n':
                return
        
    fig.savefig(fpath)
    

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
    fig, ax = plt.subplots(1, 1, figsize=figsize)
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

def plot_IO(x_b: list, y_b: list, x_t: Optional[List[float]]=None, y_t: Optional[List[float]]=None, trend: Optional[bool]=True, save_check: Optional[bool]=True, fname: Optional[str]=None) -> None:
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
    save: bool
        Flag to save the plot
    fname: str
        File name to save the plot
    
    Returns
    __________
    None
    """
    fig, ax = plt.subplots(1, 1, figsize=figsize)
    if x_t is not None or y_t is not None:
        ax.scatter(x_t, y_t, color=c1, label='Positive Acceleration', marker=marker)
        ax.scatter(x_b, y_b, color=c2, label='Negative Acceleration', marker=marker)
        ax.set_xlabel('Input Amplitude [$m/s^2$]')
        ax.set_ylabel('Bump Magnitude [$m/s^2$]')
    
        if trend:
            # Add dashed trendline
            z_t = np.polyfit(x_t, y_t, 1)
            p_t = np.poly1d(z_t)
            z_b = np.polyfit(x_b, y_b, 1)
            p_b = np.poly1d(z_b)

            ax.plot(x_t, p_t(x_t), ls=linestyle1, color=c1)
            ax.plot(x_b, p_b(x_b), ls=linestyle1, color=c2)
    else:
        ax.scatter(x_b, y_b, color=c1, label='Acceleration', marker=marker)
        ax.set_xlabel('Input Amplitude [$m/s^2$]')
        ax.set_ylabel('Bump Magnitude [$m/s^2$]')
        
        if trend:
            z_b = np.polyfit(x_b, y_b, 1)
            p_b = np.poly1d(z_b)
            ax.plot(x_b, p_b(x_b), ls=linestyle1, color=c1)
        
    ax.legend()
    ax.grid(True)
    if not save_check:
        plt.show()
    else:
        save(fig, "I/O", fname)