"""Anonymous API boundaries; real model execution is checked separately."""
import asyncio
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest

from online_api.serve import Service, clean, public_inputs


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


if __name__ == '__main__': unittest.main()
