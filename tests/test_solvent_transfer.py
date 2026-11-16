import copy
import unittest
from openmolspec_bench.solvent_transfer import ReferenceTransfer, solvent


def pair(smiles, identifier, before, after):
    return {'smiles':smiles,'molecule_id':identifier,'atom_id':'1','nucleus':'13C',
            'source_solvent':'CDCl3','target_solvent':'DMSO-d6',
            'source':{'shift_ppm':before,'spectrum_ids':[identifier+'-A']},
            'target':{'shift_ppm':after,'spectrum_ids':[identifier+'-B']}}


class TransferTests(unittest.TestCase):
    def test_query_target_and_stereoisomers_cannot_leak_into_prediction(self):
        library={'pairs':[pair('C[C@H](O)F','q',20.,999.),pair('C[C@@H](O)F','stereo',20.,-999.),pair('CCO','ref',18.,19.)]}
        out=ReferenceTransfer(library).predict('C[C@H](O)F','13C','CDCl3','DMSO-d6',20.)
        self.assertEqual(out['predicted_target_ppm'],21.)
        self.assertEqual(out['reference']['molecule_id'],'ref')
        modified=copy.deepcopy(library);modified['pairs'][0]['target']['shift_ppm']=100000.
        self.assertEqual(out,ReferenceTransfer(modified).predict('C[C@H](O)F','13C','CDCl3','DMSO-d6',20.))

    def test_reverse_solvent_direction_reverses_delta(self):
        model=ReferenceTransfer({'pairs':[pair('CCO','ref',18.,20.)]})
        self.assertEqual(model.predict('CCCO','13C','DMSO-d6','CDCl3',30.)['predicted_target_ppm'],28.)

    def test_no_independent_reference_is_not_zero_correction(self):
        model=ReferenceTransfer({'pairs':[pair('CCO','query',18.,20.)]})
        with self.assertRaises(ValueError):model.predict('OCC','13C','CDCl3','DMSO-d6',18.)

    def test_unknown_or_mixed_solvents_rejected(self):
        with self.assertRaises(ValueError):solvent('CDCl3 + CD3OD')
        self.assertEqual(solvent('Chloroform-D1 (CDCl3)'),'CDCl3')

    def test_nearest_source_peak_breaks_same_molecule_tie(self):
        model=ReferenceTransfer({'pairs':[pair('CCO','ref',18.,20.),pair('CCO','ref',58.,57.)]})
        self.assertEqual(model.predict('CCCO','13C','CDCl3','DMSO-d6',60.)['predicted_target_ppm'],59.)


if __name__=='__main__':unittest.main()
