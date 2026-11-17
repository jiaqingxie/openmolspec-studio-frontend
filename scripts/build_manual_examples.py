"""Build real gap examples, molecular conformers and cleaned NMR distributions."""
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src'),str(ROOT/'scripts')]
ASSETS=ROOT/'documentation/assets'


def refresh_examples():
    """Publish the first three saved molecular examples for NMR and MS."""
    path=ROOT/'results/nmr_documented_examples_20261117_v2.json'
    payload=json.loads(path.read_text());seen=set()
    for row in payload['results']:
        task=row['task']
        if task not in ['nmr.forward.1H','nmr.forward.13C'] or task in seen:continue
        seen.add(task);model=row['models'][0]
        destination=ASSETS/'examples'/(task.replace('.','-')+'.json');bundle=json.loads(destination.read_text())
        bundle['examples']=[{'input':{'smiles':ex['smiles']},'output':{'prediction_ppm':ex['prediction_ppm'],'model':model['model']},'reference':{'peaks_ppm':ex['reference_ppm']}} for ex in model['examples'][:3]]
        destination.write_text(json.dumps(bundle,ensure_ascii=False,indent=2)+'\n')
    for model in ['glacier','iceberg']:
        path=ROOT/'results'/f'ms_{model}_32_molecules_20261116.json';report=json.loads(path.read_text())
        rows=[row for row in report['records'] if row['status']=='passed'][:3]
        destination=ASSETS/'examples'/f'ms-forward-{model}.json';bundle=json.loads(destination.read_text())
        bundle['examples']=[{'input':{key:row[key] for key in ['smiles','adduct','collision_energy','instrument','precursor_mz']},'sample_id':row['spec_id'],
            'output':{'predicted_peaks_top100':sorted(sorted(row['predicted_peaks'],key=lambda peak:peak[1],reverse=True)[:100])},
            'reference':{'observed_peaks':row['reference_peaks']},'metrics':row['metrics']} for row in rows]
        destination.write_text(json.dumps(bundle,ensure_ascii=False,indent=2)+'\n')
    path=ASSETS/'evidence_index.json';index=json.loads(path.read_text())
    for task,entry in index.items():
        bundle=json.loads((ASSETS/'examples'/(task.replace('.','-')+'.json')).read_text())
        entry['example_count']=len(bundle['examples'])
    path.write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')


def conformers():
    """Attach reproducible RDKit conformers to the recorded gap predictions."""
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from audit_documentation_data import read_lmdb
    evidence=json.loads((ASSETS/'examples/vibrational-gap-ir_raman_hc.json').read_text())
    wanted={row['sample_id']:row for row in evidence['examples']}
    path=ROOT.parents[1]/'openmolspec-studio-portable/benchmark_data/release_v1_ks200k_hc_nmr_minmax/vib2mol/openspec_test.lmdb'
    examples=[]
    for row in read_lmdb(path):
        sid=row['sample_id']
        if sid not in wanted:continue
        ref=wanted[sid]['reference']['gap_ev']
        factor=27.211386245988
        assert abs(row['gap']*factor-ref)<1e-6
        molecule=Chem.AddHs(Chem.MolFromSmiles(row['kekule_smiles']))
        parameters=AllChem.ETKDGv3();parameters.randomSeed=42
        if AllChem.EmbedMolecule(molecule,parameters)!=0:
            raise RuntimeError(f'Could not embed the structure for {sid}')
        method='RDKit ETKDGv3; seed 42'
        if AllChem.MMFFHasAllMoleculeParams(molecule):
            AllChem.MMFFOptimizeMolecule(molecule,maxIters=1000)
            method+='; MMFF94'
        examples.append({'sample_id':sid,'smiles':row['kekule_smiles'],
            'molblock':Chem.MolToMolBlock(molecule),'coordinate_method':method,
            'predicted_gap_ev':wanted[sid]['output']['gap_ev'],'reference_gap_ev':ref,
            'reference_homo_ev':row['homo']*factor,'reference_lumo_ev':row['lumo']*factor,
            'model':'openSpec shared spectroscopy Transformer',
            'model_input':['IR','Raman','1H NMR','13C NMR']})
    assert len(examples)==len(wanted)
    examples.sort(key=lambda row:list(wanted).index(row['sample_id']))
    destination=ASSETS/'viewer';destination.mkdir(exist_ok=True)
    (destination/'gap-conformers.json').write_text(json.dumps({'examples':examples},indent=2)+'\n')
    library=ROOT/'.runtime/frontend-v1/node_modules/3dmol'
    shutil.copyfile(library/'build/3Dmol-min.js',destination/'3Dmol-min.js')
    shutil.copyfile(library/'LICENSE',destination/'3Dmol-LICENSE.txt')
    return examples


def distributions():
    """Plot all cleaned molecular records, including explicit overflow bins."""
    import numpy as np
    from matplotlib.ticker import FuncFormatter
    from documentation_figures import canvas,clean,panel,BLUE,TEAL,ORANGE
    summary=json.loads((ASSETS/'cleaned-data-summary.json').read_text())
    report=summary['nmr'];experimental=summary['experimental']
    assert report['completed']
    hist=report['histograms'];fig,axes=canvas('','','')
    for ax,key,maximum,width,label,color,letter in [
        (axes[0],'heavy_atoms',100,5,'Heavy atoms',BLUE,'a'),
        (axes[1],'molecular_weight_10Da',1500,50,'Molecular weight (Da)',TEAL,'b')]:
        edges=np.arange(0,maximum+width,width);values=np.zeros(len(edges),dtype=int)
        for value,count in hist[key].items():
            values[min(int(float(value)//width),len(values)-1)]+=count
        assert int(values.sum())==report['molecular_identities']
        ax.bar(edges,values,width=width*.88,color=color,align='edge',linewidth=0)
        ax.set(xlim=(0,maximum+width),xlabel=label,ylabel='Molecules')
        ticks=[0,maximum//2,maximum]
        ax.set_xticks(ticks,[str(ticks[0]),str(ticks[1]),f'≥{maximum}'])
        ax.yaxis.set_major_formatter(FuncFormatter(lambda n,p:f'{n/1000:g}k'))
        clean(ax);panel(ax,letter,'Molecular size' if key=='heavy_atoms' else 'Molecular weight')
    fig._source_caption=f'{report["molecular_identities"]:,} cleaned molecular identities. Last bins include every larger molecule.'
    figures={'data-cleaned-nmr':fig}
    fig,axes=canvas('','','')
    for ax,key,low,high,width,label,color,letter in [
        (axes[0],'h_shift_0.1ppm',-2,16,.2,'¹H chemical shift (ppm)',BLUE,'a'),
        (axes[1],'c_shift_0.1ppm',-20,250,3,'¹³C chemical shift (ppm)',TEAL,'b')]:
        edges=np.r_[low-width,np.arange(low,high+width/2,width)];values=np.zeros(len(edges),dtype=int)
        for value,count in hist[key].items():
            values[min(max(int(np.floor((float(value)-low)/width+1e-9))+1,0),len(values)-1)]+=count
        ax.bar(edges,values,width=width*.94,color=color,align='edge',linewidth=0)
        ax.set(xlim=(low-width,edges[-1]+width),xlabel=label,ylabel='Observed peaks')
        ticks=[low-width,0,8,high] if key.startswith('h_') else [low-width,50,150,high]
        ax.set_xticks(ticks,[f'<{low:g}' if i==0 else f'≥{value:g}' if i==len(ticks)-1 else f'{value:g}' for i,value in enumerate(ticks)])
        ax.yaxis.set_major_formatter(FuncFormatter(lambda n,p:f'{n/1e6:g}M' if n>=1e6 else f'{n/1000:g}k'))
        clean(ax);panel(ax,letter,'Proton shifts' if key.startswith('h_') else 'Carbon shifts')
    fig._source_caption='All parsed shifts in the cleaned H/C collection. First and last bins include values outside the displayed central range.'
    figures['data-cleaned-nmr-shifts']=fig

    fig,axes=canvas('','','',left=.12)
    nuclei=['1H','13C','19F','31P','11B','29Si']
    counts=[report['counts']['h_spectra'],report['counts']['c_spectra']]+[experimental['views'][n]['spectra'] for n in nuclei[2:]]
    for ax,labels,values,letter,title in [
        (axes[0],nuclei,counts,'a','Experimental NMR'),
        (axes[1],['IR','MS','Raman'],[experimental['views'][m]['spectra'] for m in ['IR','MS','Raman']],'b','Experimental optical and mass spectra')]:
        y=np.arange(len(labels));ax.barh(y,values,height=.55,color=BLUE if letter=='a' else TEAL)
        ax.set_yticks(y,labels);ax.invert_yaxis();ax.set_xscale('log')
        ax.set(xlim=(1,max(values)*8),xlabel='Spectra (log scale)')
        for position,value in zip(y,values):ax.text(value*1.15,position,f'{value:,}',va='center',fontsize=8)
        clean(ax);panel(ax,letter,title)
    figures['data-cleaned-experimental']=fig

    fig,axes=canvas('','','')
    for ax,key,width,maximum,xlabel,ylabel,letter in [
        (axes[0],'MS:heavy_atoms',5,100,'Heavy atoms','Spectral records','a'),
        (axes[1],'MS:positions',10,1200,'m/z','Observed peaks','b')]:
        values=np.zeros(maximum//width+1,dtype=int)
        for value,count in experimental['histograms'][key].items():values[min(max(int(float(value)//width),0),len(values)-1)]+=count
        ax.bar(np.arange(len(values))*width,values,width=width*.92,color=BLUE if letter=='a' else TEAL,align='edge',linewidth=0)
        ax.set(xlim=(0,maximum+width),xlabel=xlabel,ylabel=ylabel)
        ax.set_xticks([0,maximum//2,maximum],['0',str(maximum//2),f'≥{maximum}'])
        clean(ax);panel(ax,letter,'MS molecular size' if letter=='a' else 'Mass-spectral peak positions')
    figures['data-cleaned-ms']=fig

    fig,axes=canvas('','','')
    for ax,modality,letter,color in [(axes[0],'IR','a',BLUE),(axes[1],'Raman','b',ORANGE)]:
        width=50;maximum=4000;values=np.zeros(maximum//width+1,dtype=int)
        for value,count in experimental['histograms'][modality+':positions'].items():values[min(max(int(float(value)//width),0),len(values)-1)]+=count
        ax.bar(np.arange(len(values))*width,values,width=width*.94,color=color,align='edge',linewidth=0)
        ax.set(xlim=(0,maximum+width),xlabel='Wavenumber (cm$^{-1}$)',ylabel='Observed peaks')
        ax.set_xticks([0,1000,2000,3000,4000],['0','1000','2000','3000','≥4000'])
        clean(ax);panel(ax,letter,modality+' peak positions')
    figures['data-cleaned-vibrational']=fig
    return figures


def export(qa_directory=None):
    """Export model figures and cleaned data plots; optionally run Nature QA."""
    import matplotlib.pyplot as plt
    from openmolspec_bench.catalog import TASKS
    from documentation_evidence import load_evidence,render
    destination=ASSETS/'gallery';destination.mkdir(exist_ok=True)
    alignment=None
    if qa_directory:
        sys.path.insert(0,str(qa_directory))
        from audit_panel_alignment import require_matplotlib_panel_alignment
        alignment=require_matplotlib_panel_alignment
    items=[(t.id.replace('.','-'),lambda task=t:render(task.id,load_evidence(task.id))) for t in TASKS if t.enabled]
    for task in ['nmr.generation.hc','ms.forward.glacier','ms.forward.iceberg']:
        for index in [1,2]:
            items.append((task.replace('.','-')+f'-example-{index+1}',lambda task=task,index=index:render(task,example_index=index)))
    items.extend((name,lambda value=fig:value) for name,fig in distributions().items())
    for name,make in items:
        fig=make()
        if alignment:
            alignment(fig,json_out=ROOT/'.runtime/manual-figure-qa'/f'{name}-alignment.json')
        for extension in ('png','svg','pdf'):
            fig.savefig(destination/f'{name}.{extension}',dpi=220,
                metadata={'Date':None} if extension=='svg' else None)
        svg=destination/f'{name}.svg'
        svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
        plt.close(fig);print(name,flush=True)


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qa-scripts',type=Path)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--conformers-only',action='store_true')
    mode.add_argument('--figures-only',action='store_true')
    mode.add_argument('--examples-only',action='store_true')
    args=parser.parse_args()
    if args.examples_only or not (args.conformers_only or args.figures_only):refresh_examples()
    if args.examples_only:return
    if not args.figures_only:
        examples=conformers();print(f'3D examples: {len(examples)}',flush=True)
    if not args.conformers_only:export(args.qa_scripts)


if __name__=='__main__':main()
