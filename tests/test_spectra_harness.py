import unittest
from openmolspec.harness import SpectraHarness,HarnessPlugin


class SpectraHarnessTests(unittest.TestCase):
    def test_missing_experiment_conditions_rejected_before_execution(self):
        with self.assertRaisesRegex(ValueError,'collision_energy'):
            SpectraHarness().validate('ms.forward.glacier',{'smiles':'CCO','adduct':'[M+H]+','instrument':'Orbitrap'},{'source':'source','weights':'weights'})
        with self.assertRaisesRegex(ValueError,'1024'):
            SpectraHarness().validate('vibrational.gap.ir_raman_hc',{'ir':[1,2]},{'root':'models'})

    def test_plugin_repeated_outputs_and_failure_trace(self):
        plugin=HarnessPlugin('test',('test',),lambda *args:None,lambda *args:{'shifts':[1.2]})
        r=SpectraHarness([plugin]).run('test',{}, {},repeats=2)
        self.assertTrue(r['completed']);self.assertTrue(r['repeat_outputs_equal']);self.assertEqual(len(r['calls']),2)
        def fail(*args):raise ValueError('wrong checkpoint')
        plugin.execute=fail;r=SpectraHarness([plugin]).run('test',{}, {},repeats=2)
        self.assertFalse(r['completed']);self.assertEqual(len(r['calls']),1);self.assertEqual(r['calls'][0]['error_type'],'ValueError')


if __name__=='__main__':unittest.main()
