"""Spectra Harness: validated, observable model calls by spectroscopy family.

Inspired by the replaceable tool/service boundaries in DeepSeek Harness:
https://github.com/deepseek-ai/deepseek-harness . No DSH runtime is required.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import time


def _finite_vector(value, name, length=None):
    if not isinstance(value,(list,tuple)) or not value or (length is not None and len(value)!=length):
        raise ValueError(f'{name} requires '+(f'{length} finite values' if length else 'a nonempty numeric list'))
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in value):
        raise ValueError(f'{name} contains nonfinite or nonnumeric values')


@dataclass
class HarnessPlugin:
    name: str
    task_ids: tuple
    validate: object
    execute: object


class SpectraHarness:
    """A tool registry shared by Python, CLI, MCP and the web application."""
    def __init__(self,plugins=None):
        self.plugins={}
        for plugin in plugins or default_plugins():
            for task_id in plugin.task_ids:
                if task_id in self.plugins:raise ValueError('Task already registered: '+task_id)
                self.plugins[task_id]=plugin

    def catalog(self):
        from openmolspec_bench.catalog import records
        return [{'task':r['id'],'title':r['title'],'modalities':r['modalities'],'domain':r['domain'],
                 'harness':self.plugins[r['id']].name} for r in records() if r['id'] in self.plugins]

    def validate(self,task,inputs,model_config):
        if task not in self.plugins:raise ValueError('No direct-call harness registered for '+task)
        if not isinstance(inputs,dict) or not isinstance(model_config,dict):raise ValueError('inputs and model_config must be objects')
        self.plugins[task].validate(task,inputs,model_config)
        return {'valid':True,'task':task,'harness':self.plugins[task].name}

    def run(self,task,inputs,model_config,*,repeats=1):
        """Run identical requests and retain per-call elapsed time and output hashes."""
        self.validate(task,inputs,model_config)
        if isinstance(repeats,bool) or not isinstance(repeats,int) or not 1<=repeats<=5:raise ValueError('repeats must be 1–5')
        request_hash=hashlib.sha256(json.dumps({'task':task,'inputs':inputs,'model_config':model_config},sort_keys=True,allow_nan=False).encode()).hexdigest()
        calls=[];outputs=[];prediction_hashes=[]
        for index in range(repeats):
            start=time.monotonic()
            try:
                result=self.plugins[task].execute(task,inputs,model_config)
                digest=hashlib.sha256(json.dumps(result,sort_keys=True,allow_nan=False).encode()).hexdigest()
                # Runtime provenance can include fresh temporary input paths.
                # Keep its raw digest and compare the prediction fields separately.
                prediction={k:v for k,v in result.items() if k!='provenance'}
                prediction_hash=hashlib.sha256(json.dumps(prediction,sort_keys=True,allow_nan=False).encode()).hexdigest()
                prediction_hashes.append(prediction_hash)
                outputs.append(result);calls.append({'index':index,'status':'passed','elapsed_seconds':time.monotonic()-start,'output_sha256':digest,'prediction_sha256':prediction_hash})
            except Exception as error:
                calls.append({'index':index,'status':'failed','elapsed_seconds':time.monotonic()-start,'error_type':type(error).__name__,'error':str(error)})
                break
        passed=len(outputs)==repeats
        return {'version':'1.0','task':task,'harness':self.plugins[task].name,'request_sha256':request_hash,
                'completed':passed,'calls':calls,'result':outputs[-1] if outputs else None,
                'repeat_outputs_equal':len({x['output_sha256'] for x in calls if x['status']=='passed'})==1 if passed and repeats>1 else None,
                'repeat_predictions_equal':len(set(prediction_hashes))==1 if passed and repeats>1 else None,
                'repeat_results':outputs if repeats>1 else [],
                'validation_scope':'request contract, execution and repeated serialized outputs; scientific accuracy requires reference data'}


def _nmr_validate(task,x,config):
    if task.startswith('nmr.forward.') or task=='nmr.assignment':
        if not isinstance(x.get('smiles'),str) or not x['smiles'].strip():raise ValueError('Supply a SMILES structure')
        nucleus=task.rsplit('.',1)[-1] if task.startswith('nmr.forward.') else x.get('nucleus','13C')
        if nucleus not in ('1H','13C'):raise ValueError('Direct NMRNet SDK supports 1H/13C')
        if task=='nmr.assignment':_finite_vector(x.get('peaks_ppm'),'peaks_ppm')
        if not config.get('root'):raise ValueError('Supply the NMRNet model root')
    else:
        if not config.get('checkpoint'):raise ValueError('Supply a compatible NMR Transformer checkpoint')
        query=x.get('query')
        if not isinstance(query,dict):raise ValueError('Supply query with H/C NMR records')
        view=task.split('.')[2]
        for field in (['h_nmr'] if view=='h' else ['c_nmr'] if view=='c' else ['h_nmr','c_nmr']):
            if not query.get(field):raise ValueError('Required modality missing: '+field)
        if '.generation.' in task and not query.get('formula'):raise ValueError('Generation requires an explicitly supplied formula')
        if '.retrieval.' in task:
            if not isinstance(x.get('candidates'),list) or not x['candidates'] or any(not isinstance(s,str) or not s for s in x['candidates']):raise ValueError('Supply candidate SMILES')
            if task.endswith('.m2s'):raise ValueError('Use the benchmark API for molecule-to-spectrum retrieval')


def _nmr_execute(task,x,config):
    from .model import NMRNet,NMRTransformer
    settings={k:v for k,v in config.items() if k in ('python','device')}
    if task.startswith('nmr.forward.') or task=='nmr.assignment':
        nucleus=task.rsplit('.',1)[-1] if task.startswith('nmr.forward.') else x.get('nucleus','13C')
        model=NMRNet.from_pretrained(config['root'],nucleus=nucleus,**settings)
        return model.assign(x['smiles'],x['peaks_ppm'],tolerance_ppm=x.get('tolerance_ppm')) if task=='nmr.assignment' else model.predict(x['smiles'])
    generation='.generation.' in task;query=dict(x['query']);view=task.split('.')[2]
    query['modality_mask']={'h':[1,0],'c':[0,1],'hc':[1,1]}[view]
    model=NMRTransformer.from_pretrained(config['checkpoint'],stage='generate' if generation else 'align',**settings)
    return model.predict(query,beam_size=x.get('beam_size',5)) if generation else model.retrieve(query,x['candidates'],top_k=x.get('top_k',10))


def _ms_validate(task,x,config):
    for key in ('smiles','adduct','instrument'):
        if not isinstance(x.get(key),str) or not x[key].strip():raise ValueError('Supply '+key)
    energy=x.get('collision_energy')
    try:value=float(energy)
    except (TypeError,ValueError):raise ValueError('Supply finite nonnegative collision_energy') from None
    if isinstance(energy,bool) or not math.isfinite(value) or value<0:raise ValueError('Supply finite nonnegative collision_energy')
    for key in ('source','weights'):
        if not config.get(key):raise ValueError('Supply MS '+key)


def _ms_execute(task,x,config):
    from .model import MSPredictor
    return MSPredictor(model=task.rsplit('.',1)[-1],**config).predict(**x)


def _vibrational_validate(task,x,config):
    if not config.get('root'):raise ValueError('Supply the vibrational checkpoint root')
    allow=x.get('allow_missing_modalities',False)
    for key,size in [('ir',1024),('raman',1024),('nmr_h',None),('nmr_c',None)]:
        if x.get(key) is None and allow:continue
        _finite_vector(x.get(key),key,size)
    if '.retrieval' in task or '.reranking' in task:
        if not isinstance(x.get('candidates'),list) or len(x['candidates'])<2:raise ValueError('Supply at least two candidate structures')


def _vibrational_execute(task,x,config):
    from .model import GapModel,Vib2Mol
    values={k:x[k] for k in ('ir','raman','nmr_h','nmr_c') if x.get(k) is not None}
    allow=x.get('allow_missing_modalities',False)
    if '.gap.' in task:return GapModel(**config).predict(values,allow_missing_modalities=allow)
    model=Vib2Mol(**config)
    if '.retrieval' in task or '.reranking' in task:
        return model.retrieve(values,x['candidates'],top_k=x.get('top_k',10),rerank='reranking' in task,allow_missing_modalities=allow)
    return model.predict(values,top_k=x.get('top_k',10),allow_missing_modalities=allow)


def default_plugins():
    from openmolspec_bench.catalog import TASKS
    nmr=tuple(t.id for t in TASKS if t.enabled and (t.id in ('nmr.forward.1H','nmr.forward.13C','nmr.assignment') or t.id.startswith('nmr.generation.') or t.id.startswith('nmr.retrieval.') and t.id.endswith('.s2m')))
    ms=tuple(t.id for t in TASKS if t.id.startswith('ms.forward.'))
    vib=tuple(t.id for t in TASKS if t.enabled and (t.id.startswith('vibrational.') and t.id!='vibrational.forward' or t.id.startswith('spectroscopy.reranking')))
    return [HarnessPlugin('NMR Spectra Harness',nmr,_nmr_validate,_nmr_execute),
            HarnessPlugin('MS Spectra Harness',ms,_ms_validate,_ms_execute),
            HarnessPlugin('Vibrational Spectra Harness',vib,_vibrational_validate,_vibrational_execute)]


def main():
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('catalog','validate','run'))
    parser.add_argument('--request',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args();harness=SpectraHarness()
    if args.command=='catalog':result=harness.catalog()
    else:
        if not args.request:parser.error('--request is required')
        x=json.loads(args.request.read_text());method=harness.validate if args.command=='validate' else harness.run
        result=method(x['task'],x['inputs'],x['model_config'],**({'repeats':x.get('repeats',1)} if args.command=='run' else {}))
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:
        with args.output.open('x') as stream:stream.write(text)
    else:print(text)


if __name__=='__main__':main()
