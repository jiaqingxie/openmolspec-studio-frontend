import hashlib
import json
from pathlib import Path
import pickle
import re
import tempfile
import unittest
from unittest.mock import patch

import h5py
import lmdb
import numpy as np
import pandas as pd
from torch_geometric.data import Batch

from benchmarks.data.prepare_nmr_shifts import parse_assigned_geometry, shift_graph, run


REFERENCE = {'id': 'test-tms', 'sigma_ref_ppm': {'H': 31., 'C': 191.}}
LOG = ''' Charge = 0 Multiplicity = 1
 Input orientation:
 ---------------------------------------------------------------------
 Center Atomic Atomic Coordinates (Angstroms)
 Number Number Type X Y Z
 ---------------------------------------------------------------------
 1 6 0 0.0 0.0 0.0
 2 1 0 1.0 0.0 0.0
 3 8 0 0.0 1.0 0.0
 4 1 0 0.0 0.0 1.0
 ---------------------------------------------------------------------
 1 C Isotropic = 151.0000 Anisotropy = 1.
 2 H Isotropic = 2.7000D+01 Anisotropy = 1.
 3 O Isotropic = 100.0000 Anisotropy = 1.
 4 H Isotropic = 29.0000 Anisotropy = 1.
 Normal termination of Gaussian 16
'''


class StructureNMRTests(unittest.TestCase):
    def test_mixed_prefix_requires_independent_archive(self):
        tensor = '\n XX= 1 YX= 0 ZX= 0\n XY= 0 YY= 2 ZY= 0\n XZ= 0 YZ= 0 ZZ= 3'
        text = LOG.replace(' Input orientation:', ' Error termination via Lnk1e\n Input orientation:')
        text = text.replace(' 1 C Isotropic', ' SCF Done: E = -1\n SCF GIAO Magnetic shielding tensor (ppm):\n 1 C Isotropic')
        text = re.sub(r'(^.*Isotropic[^\n]*)', lambda m: m[0]+tensor, text, flags=re.M)
        archive = r' 1\1\GINC\SP\ROPBE\\# NMR\\title\\0,1\C,0,0,0,0\H,0,1,0,0\O,0,0,1,0\H,0,0,0,1\\Version=test\\@'
        text = text.replace(' Normal termination',
            ' Leave Link 601 at test\n (Enter /gaussian/l9999.exe)\n'+archive+'\n Normal termination')
        *_, metadata = parse_assigned_geometry(text, with_metadata=True)
        self.assertEqual(metadata['nmr_completion'], 'verified_normal_suffix_with_mixed_failed_prefix')
        for bad in (text.replace(archive, ''), text.replace('C,0,0,0,0', 'N,0,0,0,0'),
                    text.replace('H,0,1,0,0', 'H,0,2,0,0'),
                    text.replace('H,0,1,0,0', 'H,0,-1,0,0'),
                    text.replace('ZZ= 3', 'ZZ= ', 1)):
            with self.assertRaises(ValueError):
                parse_assigned_geometry(bad)
        recovered = text.replace(' Input orientation:', ' Lost orientation:')
        recovered = recovered.replace(' Leave Link 601', ' Leave Link 1002 at test\n Leave Link 601')
        recovered = recovered.replace('Version=test', 'Version=test\\HF=-1\\RMSD=1e-9')
        recovered = recovered.replace('SCF Done:', 'Lost SCF line:')
        z, pos, sigma, charge, meta = parse_assigned_geometry(recovered, with_metadata=True)
        self.assertEqual(meta['nmr_geometry_source'], 'NMR terminal SP archive')
        np.testing.assert_allclose(pos, [[0,0,0],[1,0,0],[0,1,0],[0,0,1]])
        for bad in (recovered.replace('RMSD=1e-9', 'RMSD=1e-2'),
                    recovered.replace('\\SP\\', '\\FOpt\\'),
                    recovered.replace('C,0,0,0,0', 'N,0,0,0,0'),
                    recovered.replace('Leave Link 1002', 'Leave Link 1001'),
                    recovered.replace('ZZ= 3', 'ZZ= ', 1)):
            with self.assertRaises(ValueError):
                parse_assigned_geometry(bad)

    def test_recover_only_completed_nmr_final_write_failure(self):
        tensor = '\n XX= 1 YX= 0 ZX= 0\n XY= 0 YY= 2 ZY= 0\n XZ= 0 YZ= 0 ZZ= 3'
        text = LOG.replace(' 1 C Isotropic', ' SCF Done: E = -1\n SCF GIAO Magnetic shielding tensor (ppm):\n 1 C Isotropic')
        text = re.sub(r'(^.*Isotropic[^\n]*)', lambda m: m[0]+tensor, text, flags=re.M)
        text = text.replace(' Normal termination of Gaussian 16',
            ' Leave Link  601 at test\n (Enter /gaussian/l9999.exe)\nErroneous write. Write -1 instead of 16777216.')
        *_, metadata = parse_assigned_geometry(text, with_metadata=True)
        self.assertFalse(metadata['normal_termination'])
        self.assertIn('l9999_write_failure', metadata['nmr_completion'])
        final_error = text.replace('Erroneous write. Write -1 instead of 16777216.',
            'NInts<0 in InToWP.\n Error termination via Lnk1e in /gaussian/l9999.exe at test.')
        *_, metadata = parse_assigned_geometry(final_error, with_metadata=True)
        self.assertEqual(metadata['nmr_completion'], 'complete_shielding_post_nmr_l9999_error')
        for bad in (final_error.replace('in /gaussian/l9999.exe', 'in /gaussian/l502.exe'),
                    final_error.replace('Leave Link  601', 'Leave Link  602'),
                    final_error + '\n (Enter /gaussian/l502.exe)',
                    final_error.replace('ZZ= 3', 'ZZ= ', 1)):
            with self.assertRaises(ValueError):
                parse_assigned_geometry(bad)
        deleted = text[:text.index(' Leave Link')] + (
            ' Leave Link 1002 at test\n Internal input file was deleted!\n'
            ' Error termination via Lnk1e at test.\n')
        *_, metadata = parse_assigned_geometry(deleted, with_metadata=True)
        self.assertFalse(metadata['normal_termination'])
        self.assertIn('internal_input_deleted', metadata['nmr_completion'])
        for bad in (deleted.replace('1002', '1001'),
                    deleted.replace('ZZ= 3', 'ZZ= ', 1),
                    deleted.replace('SCF Done:', 'SCF failed:'),
                    deleted.replace('Leave Link 1002', 'Error termination\nLeave Link 1002'),
                    deleted + ' (Enter /gaussian/l502.exe)\n',
                    deleted.replace('Internal input file was deleted!', 'Killed')):
            with self.assertRaises(ValueError):
                parse_assigned_geometry(bad)
        truncated = text[:text.index(' Leave Link')] + (
            ' Leave Link 1002 at test\n (Enter /gaussian/l601.exe)\n'
            ' Population analysis using the SCF Density.\n'
            ' Calculating spin-rotation constants.\n')
        *_, metadata = parse_assigned_geometry(truncated, with_metadata=True)
        self.assertFalse(metadata['normal_termination'])
        self.assertEqual(
            metadata['nmr_completion'],
            'complete_shielding_post_nmr_link601_spin_rotation_truncation')
        for bad in (truncated.replace('Leave Link 1002', 'Leave Link 1001'),
                    truncated.replace('l601.exe', 'l602.exe'),
                    truncated.replace('Calculating spin-rotation constants.', 'Killed'),
                    truncated + 'unexpected trailing output\n',
                    truncated.replace('Calculating spin-rotation constants.',
                                      'Calculating spin-rotation constants.\nError termination'),
                    truncated.replace('SCF Done:', 'SCF failed:'),
                    truncated.replace('ZZ= 3', 'ZZ= ', 1)):
            with self.assertRaises(ValueError):
                parse_assigned_geometry(bad)
        link601_io = text[:text.index(' Leave Link')] + (
            ' Leave Link 1002 at test\n (Enter /gaussian/l601.exe)\n'
            ' Population analysis using the SCF Density.\n'
            ' FileIO operation on non-existent file.\n'
            ' Error termination in NtrErr:\n NtrErr Called from FileIO.\n')
        *_, metadata = parse_assigned_geometry(link601_io, with_metadata=True)
        self.assertEqual(
            metadata['nmr_completion'],
            'complete_shielding_post_nmr_link601_io_failure')
        rwf_failure = link601_io.replace(
            'FileIO operation on non-existent file.', 'RdWrB1 read garbage pointers.')
        *_, metadata = parse_assigned_geometry(rwf_failure, with_metadata=True)
        self.assertEqual(
            metadata['nmr_completion'],
            'complete_shielding_post_nmr_link601_io_failure')
        for bad in (link601_io.replace('l601.exe', 'l502.exe'),
                    link601_io.replace('Leave Link 1002', 'Leave Link 1001'),
                    link601_io.replace('FileIO operation on non-existent file.', 'Killed'),
                    link601_io.replace('Error termination in NtrErr:', 'No error:'),
                    link601_io + ' (Enter /gaussian/l9999.exe)\n',
                    link601_io.replace('ZZ= 3', 'ZZ= ', 1)):
            with self.assertRaises(ValueError):
                parse_assigned_geometry(bad)
        l9999_truncated = text[:text.index(' Leave Link')] + (
            ' Leave Link 1002 at test\n (Enter /gaussian/l601.exe)\n'
            ' Calculating spin-rotation constants.\n Leave Link 601 at test\n'
            ' (Enter /gaussian/l9999.exe)\n Cartesian Nonad. Coup.: Max 1 RMS 0.1\n')
        *_, metadata = parse_assigned_geometry(l9999_truncated, with_metadata=True)
        self.assertEqual(
            metadata['nmr_completion'],
            'complete_shielding_post_nmr_l9999_incomplete_finalization')
        l9999_fileio = l9999_truncated + (
            ' FileIO operation on non-existent file.\n'
            ' Error termination in NtrErr:\n NtrErr Called from FileIO.\n')
        *_, metadata = parse_assigned_geometry(l9999_fileio, with_metadata=True)
        self.assertEqual(
            metadata['nmr_completion'],
            'complete_shielding_post_nmr_l9999_incomplete_finalization')
        killed_in_finalizer = text.replace(
            'Erroneous write. Write -1 instead of 16777216.', 'Killed')
        *_, metadata = parse_assigned_geometry(killed_in_finalizer, with_metadata=True)
        self.assertEqual(
            metadata['nmr_completion'],
            'complete_shielding_post_nmr_l9999_incomplete_finalization')
        for bad in (l9999_truncated.replace('Leave Link 601', 'Leave Link 602'),
                    l9999_truncated.replace('l9999.exe', 'l502.exe'),
                    l9999_truncated + ' (Enter /gaussian/l502.exe)\n',
                    l9999_truncated.replace('(Enter /gaussian/l9999.exe)',
                                             'Error termination\n (Enter /gaussian/l9999.exe)'),
                    l9999_truncated.replace('ZZ= 3', 'ZZ= ', 1)):
            with self.assertRaises(ValueError):
                parse_assigned_geometry(bad)
        for bad in (text.replace('ZZ= 3', 'ZZ= ', 1),
                    text.replace('SCF Done:', 'SCF failed:'),
                    text.replace('Leave Link  601', 'Leave Link  602'),
                    text.replace('l9999.exe', 'l601.exe'),
                    text.replace(' 1 C Isotropic', ' Error termination\n 1 C Isotropic')):
            with self.assertRaises(ValueError):
                parse_assigned_geometry(bad)

    def test_assignment_masks_batch_and_invariance(self):
        z, pos, sigma, charge = parse_assigned_geometry(LOG)
        self.assertEqual(charge, (0, 1))
        d = shift_graph(z, pos, sigma, REFERENCE, 'a', 5.)
        np.testing.assert_equal(d.nmr_shift.numpy().ravel(), [40, 4, 0, 2])
        np.testing.assert_equal(d.nmr_mask.numpy(), [True, True, False, True])
        self.assertEqual(d.num_nodes, 4)  # oxygen context is not removed
        b = Batch.from_data_list([d, d])
        self.assertEqual(tuple(b.nmr_shift.shape), (8, 1))
        np.testing.assert_equal(b.atom_id.numpy(), [0, 1, 2, 3]*2)
        perm = [3, 2, 0, 1]
        other = shift_graph(z[perm], pos[perm]+10, sigma[perm], REFERENCE, 'b', 5.)
        np.testing.assert_equal(other.nmr_shift.numpy(), d.nmr_shift.numpy()[perm])
        c_only = shift_graph([6], [[0, 0, 0]], [150.], REFERENCE, 'c', 5.)
        self.assertFalse(c_only.nmr_h_mask.any())
        self.assertEqual(tuple(c_only.edge_index.shape), (2, 0))
        no_hc = shift_graph([7, 15, 17], [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                            [100., 330., 550.], REFERENCE, 'no_hc', 5.)
        self.assertFalse(no_hc.has_nmr_target.item())
        self.assertFalse(no_hc.nmr_mask.any())
        self.assertFalse(no_hc.nmr_h_mask.any())
        self.assertFalse(no_hc.nmr_c_mask.any())
        self.assertEqual(float(no_hc.nmr_shift.sum()), 0.)

    def test_reject_ambiguous_sources(self):
        for bad in [LOG.replace('1 C Isotropic', '2 C Isotropic'),
                    LOG+LOG, LOG.replace('Normal termination', 'Error termination'),
                    LOG.replace('3 O Isotropic', '3 C Isotropic'),
                    LOG.replace('Input orientation:', 'No coordinates:')]:
            with self.assertRaises(ValueError):
                parse_assigned_geometry(bad)
        with self.assertRaises(ValueError):
            shift_graph([6, 1], [[0, 0, 0]]*2, [150., 30.], REFERENCE, 'x', 5.)

    def test_export_hash_identity_and_train_statistics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root/'payload'
            payload.mkdir()
            log = root/'source.log'
            log.write_text(LOG)
            sha = hashlib.sha256(log.read_bytes()).hexdigest()
            z, _, sigma, _ = parse_assigned_geometry(LOG)
            with h5py.File(payload/'shard-00000.h5', 'w') as f:
                for name, arr in [('atomic_numbers', z), ('nmr_isotropic', sigma)]:
                    g = f.create_group('arrays/'+name)
                    g['values'] = np.tile(arr, 3)
                    g['offsets'] = np.arange(4)*len(arr)
                    g['shapes'] = [[len(arr)]]*3
                    g['present'] = [True]*3
            pd.DataFrame(dict(sample_id=list('abc'), shard=['shard-00000']*3,
                              row_in_shard=range(3))).to_parquet(payload/'index.parquet')
            manifest = root/'manifest.parquet'
            pd.DataFrame(dict(sample_id=list('abc'), nmr_log_path=[str(log)]*3,
                              nmr_file_hash=[sha]*3)).to_parquet(manifest)
            split = root/'split.parquet'
            pd.DataFrame(dict(align_sample_id=list('abc'), inchikey=list('ABC'),
                              align_source=['TEST']*3, split_scaffold=list('xyz'),
                              split=['train', 'validation', 'test'])).to_parquet(split)
            with patch('benchmarks.data.prepare_nmr_shifts.load_tms_reference', return_value=REFERENCE):
                out = root/'out'
                result = run(payload, manifest, split, out, log, workers=2)
                self.assertEqual(result['counts'], dict(train=1, eval=1, test=1))
                self.assertEqual(result['no_hc_target_counts'], dict(train=0, eval=0, test=0))
                self.assertEqual(result['supervised_counts'], result['counts'])
                self.assertEqual(result['train_target_statistics']['h']['mean_ppm'], 3.)
                self.assertEqual(result['train_target_statistics']['h']['std_ppm'], 1.)
                from benchmarks.data.verify_nmr_shifts import verify
                self.assertEqual(verify(out)['status'], 'verified')
                with lmdb.open(str(out/'equiformer_v3/train.lmdb'), subdir=False, readonly=True, lock=False) as env:
                    with env.begin() as tx:
                        data = pickle.loads(tx.get(b'a'))
                        self.assertEqual(data.inchikey, 'A')
                        self.assertEqual(data.nmr_file_hash, sha)
                with self.assertRaises(FileExistsError):
                    run(payload, manifest, split, out, log)
                log.write_text(LOG+'\n')
                with self.assertRaisesRegex(ValueError, 'hash differs'):
                    run(payload, manifest, split, root/'bad', log, workers=1)
                self.assertEqual(json.loads((root/'bad/summary.json').read_text())['state'], 'failed')
                self.assertEqual(len(pd.read_parquet(root/'bad/excluded_records.parquet')), 1)
                with self.assertRaisesRegex(ValueError, '3 invalid records'):
                    run(payload, manifest, split, root/'all_bad', log, workers=1, collect_errors=True)
                failed = json.loads((root/'all_bad/summary.json').read_text())
                self.assertEqual(failed['state'], 'failed')
                self.assertEqual(failed['counts'], dict(train=0, eval=0, test=0))
                self.assertEqual(len(pd.read_parquet(root/'all_bad/excluded_records.parquet')), 3)
                self.assertFalse((root/'all_bad/benchmark_split.parquet').exists())


if __name__ == '__main__':
    unittest.main()
