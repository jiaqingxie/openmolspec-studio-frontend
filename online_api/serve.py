"""Serve the public tool UI with server-held credentials and real MCP calls.

The API is intentionally independent of the GitHub Pages frontend. Agent event
names follow the Luffy202 frontend branch's tool_start/tool_end/status pattern.
No provider key is stored in the source tree, run database or browser response.
"""
import argparse
import asyncio
import copy
import getpass
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
ORIGINS = {'https://jiaqingxie.github.io', 'http://127.0.0.1:8769', 'http://localhost:8769'}
TASKS = {'nmr.forward.1H', 'nmr.forward.13C', 'nmr.assignment', 'vibrational.forward',
         'vibrational.gap.ir_raman_hc', 'vibrational.generation.hc', 'vibrational.retrieval.hc', 'ms.forward.glacier'}
SYSTEM = """You are the OpenMolSpec spectroscopy assistant. Answer in the user's language.
Use the MCP tools to discover capabilities, validate a request, and run models.
All numerical predictions must come from spectra_predict. Do not invent values.
For prediction, always call spectra_validate first and check valid=true.
For NMR use SMILES and 1H/13C. Assignment additionally needs measured ppm peaks.
For MS/MS use ms.forward.glacier with smiles, adduct, collision_energy and instrument.
Ask for missing acquisition conditions; do not invent them.
The exact task IDs are nmr.forward.13C, nmr.forward.1H and nmr.assignment.
NMR prediction inputs have the form {"smiles":"CCO"}.
Report atom indices and ppm units. No hidden model paths or configuration are needed.
For spectra-to-property/generation use full supplied IR/Raman/H/C arrays, not invented arrays.
If inputs are missing, ask concisely for them. A formula alone is not a structure.
Explain the visible tool results concisely. Do not reveal internal reasoning or credentials.
"""


def clean(value):
    """Keep scientific outputs while removing local runtime paths."""
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()
                if key not in {'model_settings', 'model_config', 'python', 'root', 'models_root'}}
    if isinstance(value, (list, tuple)): return [clean(item) for item in value]
    if isinstance(value, str):
        return re.sub(r'/(?:mnt|tmp|root|home)/[^\s"\']+', lambda m: '<server>/' + Path(m.group()).name, value)
    return value


def public_inputs(inputs):
    """Limit anonymous work and keep runtime settings under server control."""
    if not isinstance(inputs, dict): raise ValueError('Model inputs must be an object')
    fields = {'smiles', 'nucleus', 'peaks_ppm', 'ir', 'raman', 'nmr_h', 'nmr_c', 'candidates',
              'adduct', 'collision_energy', 'instrument', 'precursor_mz'}
    result = {key: value for key, value in inputs.items() if key in fields}
    if 'smiles' in result and (not isinstance(result['smiles'], str) or len(result['smiles']) > 256):
        raise ValueError('SMILES may contain at most 256 characters')
    for key in ('peaks_ppm', 'nmr_h', 'nmr_c'):
        if key in result and (not isinstance(result[key], list) or len(result[key]) > 256):
            raise ValueError(key + ' supports at most 256 values')
    if 'candidates' in result:
        values = result['candidates']
        if not isinstance(values, list) or not 2 <= len(values) <= 32 or any(
                not isinstance(value, str) or not value or len(value) > 256 for value in values):
            raise ValueError('Supply 2–32 candidate SMILES, each at most 256 characters')
    for key in ('adduct', 'instrument'):
        if key in result and (not isinstance(result[key], str) or len(result[key]) > 64):
            raise ValueError(key + ' must be a short acquisition condition')
    return result


class Service:
    def __init__(self, args, key):
        self.args, self.key = args, key
        self.db = sqlite3.connect(args.database, check_same_thread=False)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS runs(
          id TEXT PRIMARY KEY,payload TEXT,status TEXT,created REAL,result TEXT,error TEXT);
          CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,type TEXT,data TEXT,created REAL);
          CREATE TABLE IF NOT EXISTS budgets(key TEXT PRIMARY KEY,used INTEGER);''')
        self.db.commit(); self.lock = threading.RLock(); self.ready = False
        self.db.execute("UPDATE runs SET status='failed',error='The worker restarted. Submit the request again.' WHERE status IN ('queued','running')")
        self.db.commit()
        self.loop = None; self.queue = None; self.tools = []

    def status(self):
        return {'service': 'OpenMolSpec tools', 'version': '1.0', 'connected': self.ready,
                'model': self.args.model, 'transport': 'MCP stdio', 'tools': sorted(TASKS)}

    def submit(self, payload, client):
        if not self.ready: raise ValueError('The tool service is connecting. Try again shortly.')
        if not isinstance(payload, dict): raise ValueError('The request must be an object')
        if payload.get('kind') == 'agent':
            prompt = payload.get('prompt')
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
                raise ValueError('Enter a question of 1–4,000 characters')
            payload = {'kind': 'agent', 'prompt': prompt.strip()}
        else:
            task, inputs = payload.get('task'), payload.get('inputs')
            if payload.get('kind') != 'tool' or task not in TASKS or not isinstance(inputs, dict):
                raise ValueError('Choose a supported tool and supply its inputs')
            payload = {'kind': 'tool', 'task': task, 'inputs': public_inputs(inputs)}
        with self.lock:
            waiting = self.db.execute("SELECT count(*) FROM runs WHERE status IN ('queued','running')").fetchone()[0]
            if waiting >= 4: raise ValueError('The computation queue is full. Please try again shortly.')
            bucket = hashlib.sha256(client.encode()).hexdigest() + ':' + str(int(time.time() // 3600))
            used = self.db.execute('SELECT used FROM budgets WHERE key=?', (bucket,)).fetchone()
            if used and used[0] >= 12: raise ValueError('The public demonstration limit has been reached. Please try again later.')
            daily = 'daily:' + str(int(time.time() // 86400))
            budgets = [(daily, 120)] + ([(daily + ':agent', 30)] if payload['kind'] == 'agent' else [])
            for key, limit in budgets:
                count = self.db.execute('SELECT used FROM budgets WHERE key=?', (key,)).fetchone()
                if count and count[0] >= limit: raise ValueError('The daily demonstration limit has been reached. Please try again tomorrow.')
            for key, _ in budgets:
                self.db.execute('INSERT INTO budgets VALUES (?,1) ON CONFLICT(key) DO UPDATE SET used=used+1', (key,))
            self.db.execute('INSERT INTO budgets VALUES (?,1) ON CONFLICT(key) DO UPDATE SET used=used+1', (bucket,))
            run_id = str(uuid.uuid4())
            self.db.execute('INSERT INTO runs VALUES (?,?,\'queued\',?,NULL,NULL)', (run_id, json.dumps(payload), time.time()))
            self.db.execute('DELETE FROM runs WHERE created<?', (time.time() - 86400,))
            self.db.commit()
        asyncio.run_coroutine_threadsafe(self.queue.put((run_id, payload)), self.loop)
        return {'id': run_id, 'status': 'queued'}

    def event(self, run_id, kind, data):
        with self.lock:
            self.db.execute('INSERT INTO events(run_id,type,data,created) VALUES (?,?,?,?)',
                            (run_id, kind, json.dumps(clean(data), ensure_ascii=False, allow_nan=False), time.time()))
            self.db.commit()

    def get(self, run_id, after=0):
        with self.lock:
            row = self.db.execute('SELECT status,created,result,error FROM runs WHERE id=?', (run_id,)).fetchone()
            if not row: return None
            events = self.db.execute('SELECT id,type,data,created FROM events WHERE run_id=? AND id>? ORDER BY id', (run_id, after)).fetchall()
        return {'id': run_id, 'status': row[0], 'created_at': row[1], 'result': json.loads(row[2]) if row[2] else None,
                'error': row[3], 'events': [{'id': i, 'type': kind, 'data': json.loads(data), 'created_at': created} for i, kind, data, created in events]}

    def settings(self, task):
        if task not in TASKS or task == 'vibrational.forward': raise ValueError('Choose an available MCP model task')
        if task == 'ms.forward.glacier':
            return {'source': str(self.args.ms_source), 'weights': str(self.args.ms_weights),
                    'python': self.args.model_python, 'device': 'cpu'}
        return {'root': str(self.args.models_root if task.startswith('nmr.') else self.args.portable_root),
                'python': self.args.model_python if task.startswith('nmr.') else self.args.vibrational_python,
                'device': 'cpu'}

    @staticmethod
    def unpack(result):
        if result.structured_content is not None: return result.structured_content
        return json.loads(next(block.text for block in result.content if block.type == 'text'))

    async def call(self, session, run_id, name, arguments):
        if name not in {'spectra_tasks', 'spectra_datasets', 'spectra_validate', 'spectra_predict'}:
            raise ValueError('Unknown MCP tool')
        fields = {'spectra_tasks': set(), 'spectra_datasets': {'name'},
                  'spectra_validate': {'task', 'inputs'}, 'spectra_predict': {'task', 'inputs', 'repeats'}}
        arguments = {key: value for key, value in arguments.items() if key in fields[name]}
        task = arguments.get('task')
        visible = {k: v for k, v in arguments.items() if k != 'model_settings'}
        token = str(uuid.uuid4())
        self.event(run_id, 'tool_start', {'id': token, 'name': name, 'args': visible})
        start = time.monotonic()
        if name in {'spectra_validate', 'spectra_predict'}:
            arguments['inputs'] = public_inputs(arguments.get('inputs'))
            arguments['model_settings'] = self.settings(task)
            if name == 'spectra_predict': arguments['repeats'] = 1
        result = self.unpack(await session.call_tool(name, arguments))
        if name in {'spectra_tasks', 'spectra_datasets'} and isinstance(result, dict) and isinstance(result.get('result'), list):
            result = result['result']
        if name == 'spectra_tasks': result = [row for row in result if row['task'] in TASKS]
        if name == 'spectra_predict' and not result.get('completed'):
            raise ValueError(result.get('calls', [{}])[-1].get('error', 'Model execution failed'))
        result = clean(result)
        self.event(run_id, 'tool_end', {'id': token, 'name': name, 'result': result, 'elapsed_seconds': time.monotonic() - start})
        return result

    def completion(self, messages, tools):
        body = {'model': self.args.model, 'messages': messages, 'tools': tools,
                'max_tokens': 1400, 'temperature': 0.1, 'stream': False}
        request = urllib.request.Request(self.args.base_url.rstrip('/') + '/chat/completions',
            data=json.dumps(body).encode(), headers={'Authorization': 'Bearer ' + self.key,
                'Content-Type': 'application/json', 'User-Agent': 'OpenMolSpec/1.0'})
        with urllib.request.urlopen(request, timeout=120) as response: return json.load(response)

    async def agent(self, session, run_id, payload):
        self.event(run_id, 'status', {'stage': 'connecting', 'label': 'Connecting the model API and MCP tools'})
        listing = await session.list_tools()
        definitions = []
        for tool in listing.tools:
            schema = copy.deepcopy(tool.input_schema)
            schema.get('properties', {}).pop('model_settings', None)
            schema['required'] = [name for name in schema.get('required', []) if name != 'model_settings']
            if 'task' in schema.get('properties', {}):
                schema['properties']['task']['enum'] = sorted(TASKS - {'vibrational.forward'})
            definitions.append({'type': 'function', 'function': {'name': tool.name,
                'description': tool.description, 'parameters': schema}})
        self.event(run_id, 'discovery', {'transport': 'MCP stdio', 'tools': [row['function']['name'] for row in definitions]})
        messages = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': payload['prompt']}]
        catalog = await self.call(session, run_id, 'spectra_tasks', {})
        messages.insert(1, {'role': 'system', 'content': 'Currently available tool tasks: ' + json.dumps(catalog, ensure_ascii=False)})
        usage = []
        for step in range(6):
            self.event(run_id, 'status', {'stage': 'model', 'label': 'The agent is selecting its next action', 'step': step + 1})
            answer = await asyncio.to_thread(self.completion, messages, definitions)
            usage.append(answer.get('usage', {}))
            message = answer['choices'][0]['message']
            calls = message.get('tool_calls') or []
            # Only public answer text and tool requests are retained, never reasoning fields.
            public = {'role': 'assistant', 'content': message.get('content') or ''}
            if calls: public['tool_calls'] = calls
            messages.append(public)
            if not calls:
                text = public['content'].strip()
                if not text: raise ValueError('The model did not return an answer')
                self.event(run_id, 'answer', {'content': text})
                return {'answer': text, 'model': self.args.model, 'usage': usage, 'transport': 'MCP stdio'}
            if len(calls) > 4: raise ValueError('Too many tool requests in one step')
            for part in calls:
                name = part['function']['name']
                arguments = json.loads(part['function']['arguments'])
                try:
                    result = await self.call(session, run_id, name, arguments)
                except (ValueError, KeyError, TypeError) as error:
                    result = {'error': str(error), 'available_tasks': sorted(TASKS - {'vibrational.forward'})}
                    self.event(run_id, 'tool_error', {'name': name, 'error': str(error)})
                encoded = json.dumps(result, ensure_ascii=False)
                if len(encoded) > 20000: encoded = json.dumps({'summary': 'A full numerical result is available in the tool trace', 'result': {k: v for k, v in result.items() if k in {'completed', 'task', 'result', 'unit'}}}, ensure_ascii=False)[:20000]
                messages.append({'role': 'tool', 'tool_call_id': part['id'], 'content': encoded})
        raise ValueError('The agent reached its step limit. Try a smaller question.')

    async def tool(self, session, run_id, payload):
        task, inputs = payload['task'], payload['inputs']
        if task == 'vibrational.forward':
            self.event(run_id, 'tool_start', {'id': run_id, 'name': 'geometry_to_spectra', 'args': inputs})
            start = time.monotonic()
            result = await asyncio.to_thread(self.geometry, inputs)
            self.event(run_id, 'tool_end', {'id': run_id, 'name': 'geometry_to_spectra', 'result': result, 'elapsed_seconds': time.monotonic() - start})
            return result
        valid = await self.call(session, run_id, 'spectra_validate', {'task': task, 'inputs': inputs})
        if not valid.get('valid'): raise ValueError(valid.get('error', 'Invalid model input'))
        return await self.call(session, run_id, 'spectra_predict', {'task': task, 'inputs': inputs})

    def geometry(self, inputs):
        process = subprocess.run([self.args.vibrational_python, '-m', 'online_api.geometry'],
            input=json.dumps({'smiles': inputs['smiles'], 'root': str(self.args.portable_root)}),
            capture_output=True, text=True, cwd=ROOT, timeout=600,
            env={**os.environ, 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'})
        if process.returncode: raise ValueError('Geometry prediction failed: ' + process.stderr[-1000:])
        line = next(line[14:] for line in reversed(process.stdout.splitlines()) if line.startswith('OMS_RESULT_V1:'))
        return clean(json.loads(line))

    async def run(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        self.loop = asyncio.get_running_loop(); self.queue = asyncio.Queue()
        parameters = StdioServerParameters(command=sys.executable, args=['-m', 'openmolspec.mcp'],
            env={**os.environ, 'PYTHONPATH': str(ROOT / 'src') + os.pathsep + str(ROOT),
                 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'})
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=600) as session:
                await session.initialize(); self.ready = True
                print('OpenMolSpec MCP connected; model API configured; tool service ready.', flush=True)
                while True:
                    run_id, payload = await self.queue.get()
                    with self.lock:
                        self.db.execute("UPDATE runs SET status='running' WHERE id=?", (run_id,)); self.db.commit()
                    try:
                        result = await (self.agent(session, run_id, payload) if payload['kind'] == 'agent' else self.tool(session, run_id, payload))
                        with self.lock:
                            self.db.execute("UPDATE runs SET status='completed',result=? WHERE id=?", (json.dumps(clean(result), ensure_ascii=False, allow_nan=False), run_id)); self.db.commit()
                    except Exception as error:
                        message = clean(str(error)).replace(self.key, '[redacted]')[:1000]
                        self.event(run_id, 'error', {'message': message})
                        with self.lock:
                            self.db.execute("UPDATE runs SET status='failed',error=? WHERE id=?", (message, run_id)); self.db.commit()


def handler(service):
    class API(BaseHTTPRequestHandler):
        def reply(self, value, status=200):
            data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status); self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data))); self.send_header('Cache-Control', 'no-store')
            origin = self.headers.get('Origin', '')
            if origin in ORIGINS: self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type,X-OMS-Client')
            self.end_headers(); self.wfile.write(data)

        def do_OPTIONS(self): self.reply({}, 200)

        def do_GET(self):
            path = self.path.split('?', 1)[0]
            if path in {'/', '/api/status', '/api/health'}: return self.reply(service.status())
            match = re.fullmatch(r'/api/runs/([a-f0-9-]{36})', path)
            if match:
                result = service.get(match[1])
                return self.reply(result if result else {'error': 'Run not found'}, 200 if result else 404)
            self.reply({'error': 'Route not found'}, 404)

        def do_POST(self):
            if self.path != '/api/runs': return self.reply({'error': 'Route not found'}, 404)
            if self.headers.get('Origin') not in ORIGINS: return self.reply({'error': 'Open this tool from the OpenMolSpec website'}, 403)
            try: length = int(self.headers.get('Content-Length', '0'))
            except ValueError: return self.reply({'error': 'Invalid request length'}, 400)
            if not 0 < length <= 180000: return self.reply({'error': 'Request is too large'}, 413)
            try:
                payload = json.loads(self.rfile.read(length))
                result = service.submit(payload, self.headers.get('CF-Connecting-IP') or self.client_address[0])
                self.reply(result, 202)
            except (ValueError, TypeError) as error: self.reply({'error': str(error)}, 400)

        def log_message(self, format, *args): pass
    return API


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8721)
    parser.add_argument('--database', type=Path, default=ROOT / '.runtime/online-runs.sqlite')
    parser.add_argument('--base-url', default='https://hapiopen.cc/v1')
    parser.add_argument('--model', default='deepseek-v4.1-flash')
    parser.add_argument('--models-root', type=Path, default=ROOT.parents[1] / 'models')
    parser.add_argument('--portable-root', type=Path, default=ROOT.parents[1] / 'openmolspec-studio-portable')
    parser.add_argument('--model-python', default=os.environ.get('OPENMOLSPEC_NMR_PYTHON', sys.executable))
    parser.add_argument('--vibrational-python', default=str(ROOT.parents[1] / 'openmolspec-studio-portable/.venv/bin/python'))
    parser.add_argument('--ms-source', type=Path, default=ROOT.parents[1] / 'mspred/ms-pred-main')
    parser.add_argument('--ms-weights', type=Path, default=ROOT.parents[1] / 'mspred')
    args = parser.parse_args()
    key = os.environ.get('OPENAI_API_KEY') or getpass.getpass('Provider API key (hidden): ')
    args.database.parent.mkdir(parents=True, exist_ok=True)
    service = Service(args, key)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(service))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    asyncio.run(service.run())


if __name__ == '__main__': main()
