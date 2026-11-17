import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from openmolspec.split import split_records,molecular_group


class DatasetSplitTests(unittest.TestCase):
    def test_conflicting_connectivity_roles_rejected_without_publishing(self):
        # Model two normalized structural forms that share connectivity but
        # acquire distinct scaffolds. An export must fail before publication.
        identity='LFQSCWFLJHTTHZ-UHFFFAOYSA-N'
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'split'
            with patch('openmolspec.split.molecular_group',side_effect=[(identity,'a',None),(identity,'group7',None)]):
                with self.assertRaisesRegex(ValueError,'conflicting scaffold'):
                    split_records([{'smiles':'CCO'},{'smiles':'OCC'}],dest)
            self.assertFalse(dest.exists())

    def test_mobile_h_representations_of_one_standard_identity_share_scaffold(self):
        for first,second in [('O=c1cccc[nH]1','Oc1ccccn1'),('N=c1cccc[nH]1','Nc1ccccn1')]:
            a=molecular_group(first);b=molecular_group(second)
            self.assertEqual(a[:2],b[:2])
        with tempfile.TemporaryDirectory() as tmp:
            report=split_records([{'smiles':s} for s in ['O=c1cccc[nH]1','Oc1ccccn1']],Path(tmp)/'split')
            self.assertEqual(max(v['records'] for v in report['files'].values()),2)

    def test_scaffold_groups_ignore_isotope_and_protonation_variants(self):
        groups=[molecular_group(s)[1] for s in ['c1ccncc1','c1cc[nH+]cc1','[13cH]1ccncc1']]
        self.assertEqual(len(set(groups)),1)

    def test_reordered_stereoisomers_and_modalities_stay_in_one_group(self):
        rows=[{'smiles':s,'channel':channel} for s in ['C[C@H](O)F','C[C@@H](O)F','CCO','CCC','c1ccccc1','Cc1ccccc1'] for channel in ['NMR','MS']]
        with tempfile.TemporaryDirectory() as tmp:
            mappings=[]
            for i,items in enumerate([rows,list(reversed(rows))]):
                dest=Path(tmp)/str(i);report=split_records(items,dest,method='random')
                self.assertTrue(report['groups_disjoint']);seen={}
                for role in ['train','val','test']:
                    for line in (dest/f'{role}.jsonl').read_text().splitlines():
                        row=json.loads(line);group=row['_openmolspec_split']['connectivity']
                        self.assertEqual(seen.setdefault(group,role),role)
                mappings.append(seen)
            self.assertEqual(*mappings)

    def test_same_scaffold_is_grouped_and_original_role_is_preserved(self):
        rows=[{'smiles':s,'_openmolspec':{'split':'test'}} for s in ['c1ccccc1','Cc1ccccc1','Oc1ccccc1']]
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'split';r=split_records(rows,dest)
            self.assertEqual(r['original_split_record_counts'],{'test':3})
            counts=[v['records'] for v in r['files'].values()];self.assertEqual(max(counts),3)
            with self.assertRaises(FileExistsError):split_records(rows,dest)


if __name__=='__main__':unittest.main()
