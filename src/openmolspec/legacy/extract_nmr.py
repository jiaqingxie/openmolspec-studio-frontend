import pickle
import argparse
import numpy as np
import re
import os
import json
import multiprocessing as mp
import sys
from pathlib import Path
from tqdm import tqdm, trange
from rdkit import Chem
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from openmolspec.core.processing import (
    classify_exception,
    record_quality_metadata,
    report_row,
    write_processing_reports,
)

# Frequency unit conversion: centimetres to hertz
cm_hz = 2.99792458e10
# Angstrom to meter Unit factor
A_m = 1e-10
# Boltzmann constant
Kb = 1.380649 * 10e-23  # J/K
# Planck constant
hp = 6.62606896*10e-34  # J/S
# Speed of light
c = 299792458  # m/s

def Lorenz_broadening(x0, y0, c, sigma=12):
    '''Lorenz broadening for Vibration and NMR spectroscopies
    x0 y0:Position of the horizontal and vertical axes to be broadening

    c:Position of the broadening horizontal axis and number of points

    sigma:spread half width

    The position of the vertical axis after the output has been broadened.
    '''
    lx = x0[:, None]-c[None, :]
    ly = (sigma/(2*3.1415926))/(lx**2 + 0.25*(sigma**2))
    y = np.sum(y0[:, None]*ly, axis=0)
    return y.flatten()

def get_nmr_spectrum(shifts, sigma=0.05):
    """Construct an NMR spectrum from the supplied peak positions and weights."""
    return Lorenz_broadening(shifts, np.ones_like(shifts), np.linspace(0, 12, 1024), sigma=sigma)

class LogParser:
    """
    Class for calculating and parsing properties from Gaussian log files.
    """
    def __init__(self, file_path):
        
        with open(file_path, 'r') as f:
            self.text = f.read()
        
        self.properties = {'filename':file_path}
        self.error_type = None
        self.error_message = None
        try:
            self.log2nmr()
            
        except Exception as e:
            self.error_type = classify_exception(e)
            self.error_message = str(e)
        else:
            self.properties['smiles'] = label_dict[file_path.split('.log')[0].split('/')[-1]]
    
    def log2nmr(self):
        """Extract NMR quantities from the loaded Gaussian log."""
        element_list = []
        isotropic_list = []
        anisotropy_list = []
        shielding_tensor = []
        
        shielding_pattern = r'\d+\s+([A-Za-z]+)\s+Isotropic =\s+([-]?\d+[.]\d+)\s+Anisotropy =\s+([-]?\d+[.]\d+)'
        chemical_shifts = re.findall(shielding_pattern, self.text)

        for item in chemical_shifts:
            element, isotropic, anisotropy = item
            element_list.append(element)
            isotropic_list.append(isotropic)
            anisotropy_list.append(anisotropy)
            
        tensor_pattern = ''.join([
            r'XX=\s+([-]?\d+[.]\d+)\s+YX=\s+([-]?\d+[.]\d+)\s+ZX=\s+([-]?\d+[.]\d+)\s+',
            r'XY=\s+([-]?\d+[.]\d+)\s+YY=\s+([-]?\d+[.]\d+)\s+ZY=\s+([-]?\d+[.]\d+)\s+',
            r'XZ=\s+([-]?\d+[.]\d+)\s+YZ=\s+([-]?\d+[.]\d+)\s+ZZ=\s+([-]?\d+[.]\d+)\s+',])
        
        shielding_tensor = re.findall(tensor_pattern, self.text)
        shielding_tensor = np.array([[float(item) for item in tensor] for tensor in shielding_tensor])

        atoms = np.array([Chem.Atom(item).GetAtomicNum() for item in element_list])
        isotropic_list = np.array([float(item) for item in isotropic_list])
        anisotropy_list = np.array([float(item) for item in anisotropy_list])
        
        out_dict = {'atom': atoms,
                    'isotropic': isotropic_list,
                    'anisotropy': anisotropy_list,
                    'shielding_tensor':shielding_tensor.flatten()
                    }
        
        self.properties.update(out_dict)



def get_args_parser():
    """Construct the argument parser for the extraction command."""
    parser = argparse.ArgumentParser(description='Extract legacy NMR records')

    # basic params
    parser.add_argument('--log-path', default='',
                        help="Choose dataset")
    parser.add_argument('--json-path', default='',
                        help="Choose label json")
    parser.add_argument('--save-path', default='',
                        help="path to save processed data")
    parser.add_argument('--report-path', default=None,
                        help='Directory for processing_report.parquet and summary JSON')
    args = parser.parse_args()
    return args

# Define a top-level function to process a single log file
# This function is pickleable.
def process_log_file_wrapper(args_tuple):
    """Unpack one extraction job and process its source log."""
    file_id, log_path = args_tuple
    log_file_path = os.path.join(log_path, f'{file_id}.log')
    try:
        log = LogParser(log_file_path)
        return log.properties if len(log.properties) > 0 else None
    except Exception as e:
        print(f"Error processing {log_file_path}: {e}")
        return None


def process_log_file_with_report(args_tuple):
    """Process a molecular log and return its processing-report entry."""
    file_id, log_path = args_tuple
    log_file_path = os.path.join(log_path, f'{file_id}.log')
    try:
        log = LogParser(log_file_path)
    except Exception as exc:
        return None, report_row(
            file_id,
            log_file_path,
            status='failed',
            error_type=classify_exception(exc),
            error_message=str(exc),
        )
    if log.error_type is None and 'atom' in log.properties:
        missing, flags = record_quality_metadata(log.properties, modality='nmr')
        if 'smiles' not in log.properties:
            missing.append('smiles')
        return log.properties, report_row(
            file_id, log_file_path, status='success', missing_fields=missing,
            quality_flags=flags,
        )
    return None, report_row(
        file_id, log_file_path, status='failed',
        error_type=log.error_type or 'UNKNOWN_ERROR',
        error_message=log.error_message or 'Parser produced no atom field',
    )

    
if __name__ == "__main__":
        
    args = get_args_parser()
    log_path = args.log_path
    label_file = args.json_path
    save_path = args.save_path
    
    valid_ids = [item.split('.')[0] for item in os.listdir(log_path) if item.endswith('.log')]

    with open(label_file, 'r') as f:
        label_dict = json.load(f)

    num_processes = mp.cpu_count()
    print(f"Using {num_processes} processes to accelerate data processing.")

    results = []
    report_rows = []

    # Prepare arguments for the wrapper function to avoid pickling lambda
    task_args = [(file_id, log_path) for file_id in valid_ids]

    with mp.Pool(processes=num_processes) as pool:
        # Use imap_unordered and pass the wrapper function with its arguments
        for result, report in tqdm(
            pool.imap_unordered(process_log_file_with_report, task_args),
            total=len(valid_ids),
        ):
            report_rows.append(report)
            if result is not None:
                results.append(result)

    if save_path:
        df = pd.DataFrame(results)
        df = df[~df.smiles.isna()]
        df.to_pickle(save_path)
        report_path = args.report_path or f'{save_path}.report'
        write_processing_reports(report_rows, report_path)
        print(f"Number of processed files:\t{len(results)}")
        print(f"Number of valid files:\t{len(df)}")
        print(f"Saving files in {save_path}")
