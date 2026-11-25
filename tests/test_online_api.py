"""Anonymous API boundaries; real model execution is checked separately."""
import asyncio
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest

from online_api.serve import Service, clean, public_inputs, model_tool_message


class PublicAPIContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = Service(SimpleNamespace(database=Path(self.tmp.name) / 'runs.sqlite',
            model='test', models_root=Path('/server/nmr'), portable_root=Path('/server/vib'),
            model_python='/server/python'), 'test-only-secret')
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever)
        self.thread.start()
        self.service.loop = self.loop
        self.service.queue = asyncio.Queue()
        self.service.ready = True

    def tearDown(self):
        asyncio.run_coroutine_threadsafe(asyncio.sleep(0), self.loop).result(timeout=2)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()
        self.loop.close()
        self.service.db.close()
        self.tmp.cleanup()

    def test_browser_cannot_override_model_paths(self):
        run = self.service.submit({'kind': 'tool', 'task': 'nmr.forward.13C',
            'inputs': {'smiles': 'CCO', 'root': '/attacker', 'python': 'bad',
                       'model_settings': {'root': '/attacker'}}}, 'client')
        payload = self.service.db.execute('SELECT payload FROM runs WHERE id=?', (run['id'],)).fetchone()[0]
        self.assertNotIn('attacker', payload)
        self.assertEqual(self.service.settings('nmr.forward.13C')['root'], '/server/nmr')

    def test_unknown_tasks_and_malformed_requests_are_rejected(self):
        for payload in [[], {'kind': 'tool', 'task': 'shell', 'inputs': {}},
                        {'kind': 'agent', 'prompt': ' '}, {'kind': 'agent', 'prompt': 'x' * 4001}]:
            with self.assertRaises(ValueError): self.service.submit(payload, 'client')

    def test_public_candidate_and_peak_limits(self):
        for inputs in [{'smiles': 'C' * 257}, {'candidates': ['CCO'] * 33},
                       {'candidates': ['CCO', {'python': 'bad'}]}, {'nmr_h': [1.] * 257}]:
            with self.assertRaises(ValueError): public_inputs(inputs)

    def test_concurrent_queue_is_bounded(self):
        payload = {'kind': 'tool', 'task': 'nmr.forward.13C', 'inputs': {'smiles': 'CCO'}}
        for _ in range(4): self.service.submit(payload, 'client')
        with self.assertRaisesRegex(ValueError, 'queue is full'): self.service.submit(payload, 'client')

    def test_global_agent_budget_precedes_provider_calls(self):
        import time
        self.service.db.execute('INSERT INTO budgets VALUES (?,30)', ('daily:' + str(int(time.time() // 86400)) + ':agent',))
        self.service.db.commit()
        with self.assertRaisesRegex(ValueError, 'daily'):
            self.service.submit({'kind': 'agent', 'prompt': 'Predict CCO'}, 'new-client')
        self.assertEqual(self.service.db.execute('SELECT count(*) FROM runs').fetchone()[0], 0)

    def test_private_paths_are_removed_without_changing_scientific_values(self):
        value = clean({'result': {'prediction_ppm': [17.774, 57.774]},
                       'python': '/mnt/private/python', 'checkpoint': '/mnt/private/weights.pt'})
        self.assertEqual(value['result']['prediction_ppm'], [17.774, 57.774])
        self.assertNotIn('/mnt', str(value))
        self.assertNotIn('python', value)

    def test_dense_ms_output_remains_valid_json_with_actual_highest_peaks(self):
        import json
        peaks = [[float(i), i / 10000.] for i in range(4000)]
        result = {'completed': True, 'task': 'ms.forward.glacier',
                  'result': {'predicted_peaks': peaks, 'instrument': 'QTOF', 'adduct': '[M+H]+'}}
        shown = json.loads(model_tool_message(result))['prediction_summary']
        self.assertEqual(shown['predicted_peak_count'], 4000)
        self.assertEqual(shown['top20_predicted_peaks_by_intensity'], list(reversed(peaks[-20:])))
        self.assertEqual(len(result['result']['predicted_peaks']), 4000)

    def test_agent_reads_assignment_alternatives_as_atom_indices(self):
        import json
        from online_api.serve import ROOT
        case = json.loads((ROOT / 'website/assets/harness/quercetin-agent.json').read_text())
        result = next(e['data']['result'] for e in case['events']
                      if e['type'] == 'tool_end' and e['data']['name'] == 'spectra_predict')
        raw = next(row for row in result['result']['assignments'] if row['observed_ppm'] == 115.0)
        shown = json.loads(model_tool_message(result))['result']
        peak = next(row for row in shown['assignments'] if row['observed_ppm'] == 115.0)
        self.assertEqual(shown['observed_peaks'], 14)
        self.assertEqual(raw['other_sites_within_tolerance'], [3, 8])
        self.assertEqual(peak['alternative_atom_index_groups'],
                         [result['result']['sites'][i]['atom_indices'] for i in (3, 8)])
        self.assertNotIn('other_sites_within_tolerance', peak)


if __name__ == '__main__': unittest.main()
