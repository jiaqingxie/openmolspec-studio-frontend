"""Run the author's 2-ethyl-1-indanone workbook through simpleNMR's carbon assignment workflow."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
import tempfile
from xml.etree import ElementTree


def run(source, java_executable):
    from rdkit import Chem

    name = '2-ethyl-1-indanone'
    workbook = source / 'exampleProblems' / name / (name + '.xlsx')
    inputs = ['molecule', 'H1_1D', 'H1_pureshift', 'C13_1D', 'HSQC', 'COSY', 'HMBC']
    previous = Path.cwd()
    sys.path.insert(0, str(source))
    search_path = os.environ.get('PATH', '')
    os.environ['PATH'] = str(java_executable.parent) + os.pathsep + search_path
    try:
        import java
        import nmrProblem

        # The upstream Linux launcher builds a Windows classpath. Use the same
        # NewTest and JARs with this platform's separator in an isolated run.
        classpath = os.pathsep.join(str(source / p) for p in ('predictorc.jar', 'cdk-2.7.1.jar', '.'))
        command = shlex.join([str(java_executable), '-classpath', classpath, 'NewTest', 'mol.mol'])
        java.JAVA_AVAILABLE = True
        java.JAVA_COMMAND = command + ' > mol.csv'
        with tempfile.TemporaryDirectory(prefix='simplenmr-') as scratch:
            work = Path(scratch)
            os.chdir(work)
            (work / 'csTables').symlink_to(source / 'csTables', target_is_directory=True)
            case = work / name
            case.mkdir()
            shutil.copyfile(workbook, case / workbook.name)
            info = nmrProblem.parse_argv(['simpleNMR.py', str(case)], qtstarted=False)
            problem = nmrProblem.NMRproblem(info, qtstarted=False, java_available=True,
                                            xy3_calc_method='c13ppm', java_command=java.JAVA_COMMAND,
                                            expts_available=inputs)
            if not problem.data_complete:
                raise ValueError('The author workbook could not be initialized')
            # Normal startup path for this workbook with measured C13 and H1 integrals.
            if problem.c13_from_hsqc or problem.h1_df_integral_added:
                raise ValueError('Expected the author workbook with measured C13 and integrated H1')
            problem.define_hsqc_f2integral()
            problem.define_c13_attached_protons()
            nmrProblem.build_model(problem)
            nmrProblem.build_molecule_graph_network(problem)
            problem.build_xy3()
            shifts = problem.c13[['label', 'ppm', 'expected_idx', 'expected_ppm']]
            if shifts.isna().any().any() or not shifts.expected_idx.is_unique:
                raise ValueError('Incomplete or duplicate carbon assignment in the author example')
            mol = Chem.MolFromSmiles(problem.smiles)
            carbon_ids = {a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 6}
            if set(shifts.expected_idx) != carbon_ids:
                raise ValueError('Carbon indices disagree with the input structure')
            atoms = {r.label: int(r.expected_idx) for r in shifts.itertuples()}
            # Read the author's saved HTML only after the model has returned its assignments.
            reference = workbook.parent / 'html' / (name + '.html')
            table = re.search(r'<table\b[^>]*\bid="summary_table"[^>]*>.*?</table>',
                              reference.read_text(), re.DOTALL)
            if table is None:
                raise ValueError('Missing author summary table')
            html_table = ElementTree.fromstring(table[0])
            fields = [cell.text for cell in html_table.findall('thead/tr/th')]
            reference_atoms = {}
            for row in html_table.findall('tbody/tr'):
                values = dict(zip(fields, [cell.text for cell in row.findall('td')]))
                reference_atoms['C' + values['carbon atom']] = int(values['atom idx'])
            if set(atoms) != set(reference_atoms):
                raise ValueError('Signal IDs differ from the author summary table')
            return {'method': 'simpleNMR c13ppm initialization with NMRShiftDB HOSE predictions',
                    'source': 'https://github.com/EricHughesABC/simpleNMR/tree/685b819a54fb49ccba63290cd1b493a00ae33ebd',
                    'workbook': str(workbook.relative_to(source)),
                    'workbook_sha256': hashlib.sha256(workbook.read_bytes()).hexdigest(),
                    'implementation_sha256': hashlib.sha256((source / 'nmrProblem.py').read_bytes()).hexdigest(),
                    'experiments': inputs, 'smiles': problem.smiles,
                    'atom_index_basis': 'Zero-based RDKit atom index in the workbook SMILES.',
                    'carbon_candidates': [{'signal': r.label, 'carbon_ppm': float(r.ppm),
                                           'candidate_atom': int(r.expected_idx), 'predicted_ppm': float(r.expected_ppm)}
                                          for r in shifts.itertuples()],
                    'hsqc': [{'carbon_ppm': float(r.f1_ppm), 'proton_ppm': float(r.f2_ppm),
                              'candidate_carbon_atom': atoms[r.f1C_i]} for r in problem.hsqc.itertuples()],
                    'cosy_rows': len(problem.cosy), 'hmbc_rows': len(problem.hmbc),
                    'author_comparison': {'source': str(reference.relative_to(source)),
                                          'sha256': hashlib.sha256(reference.read_bytes()).hexdigest(),
                                          'carbon_signals': len(atoms),
                                          'same_atom_index': sum(atoms[k] == v for k,v in reference_atoms.items())},
                    'assignment_accuracy': None, 'validation': 'Candidate coverage and carbon index integrity.'}
    finally:
        os.chdir(previous)
        os.environ['PATH'] = search_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--java', default=shutil.which('java'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.java:
        parser.error('Set --java to a Java 11 or newer executable')
    result = run(args.source.resolve(), Path(args.java).resolve())
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
