"""Arial data-availability figures from the complete recorded census reports."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'documentation/assets/gallery');args=parser.parse_args()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.ticker import FuncFormatter
    from openmolspec.plotting import figure_style
    figure_style();blue='#397BA6';teal='#178F88';grey='#A8B3BF'
    raw=json.loads((ROOT/'results/opendatalab_all_modalities_20261117.json').read_text())
    external=json.loads((ROOT/'results/external_data_census_20261117.json').read_text())['datasets']
    corpus=json.loads((ROOT/'results/corpus_comparison_20261117.json').read_text())
    figures={}
    def canvas():
        fig,axes=plt.subplots(1,2,figsize=(7.1,3.0));fig.subplots_adjust(left=.17,right=.97,bottom=.24,top=.84,wspace=.65)
        for i,ax in enumerate(axes):
            ax.text(-.14,1.10,chr(97+i),transform=ax.transAxes,weight='bold',fontsize=9)
            ax.tick_params(length=3,width=.6);ax.spines[['top','right']].set_visible(False)
        return fig,axes
    def horizontal(ax,labels,values,*,color=blue,log=False):
        pos=np.arange(len(values));ax.barh(pos,values,color=color,height=.6);ax.set_yticks(pos,labels);ax.invert_yaxis()
        if log:ax.set_xscale('log');ax.set_xlim(.8,max(values)*3)
        else:ax.set_xlim(0,max(values)*1.16);ax.xaxis.set_major_formatter(FuncFormatter(lambda v,p:f'{v/1e6:g}M' if v>=1e6 else f'{v/1e3:g}k' if v>=1000 else f'{v:g}'))
    fig,(a,b)=canvas();counts=raw['counts']
    horizontal(a,['NMR','MS','IR','Raman'],[counts['entries:'+k] for k in ['NMR','MS','IR','Raman']],log=True)
    a.set(xlabel='Spectral entries · log scale',title='OpenDataLab raw collection')
    n=corpus['patent']['counts'];horizontal(b,['H only','H + C','C only'],[n['H_only'],n['H+C'],n['C_only']],color=[blue,teal,grey],log=True)
    b.set(xlabel='Molecular records · log scale',title='Curated experimental NMR')
    figures['data-nmr-availability']=fig
    if 'nmr_nucleus_labels' in raw:
        fig,(a,b)=canvas();nuclei=['1H','13C','19F','31P','11B','29Si'];n=raw['nmr_nucleus_labels']
        horizontal(a,[label.replace('Other / multiple nuclei','Other / multiple') for label in n],list(n.values()),log=True);a.set(xlabel='NMR entries · log scale',title='OpenDataLab nucleus labels')
        c=corpus['nmrexp']['counts'];values=[c.get('nucleus:'+key,0) for key in nuclei];other=c['records']-sum(values)
        horizontal(b,nuclei+['Other labels'],values+[other],color=teal,log=True);b.set(xlabel='Spectral records · log scale',title='NMRexp v2 local release')
        figures['data-nmr-nuclei']=fig
    fig,(a,b)=canvas();q=raw['quality']
    horizontal(a,['MS entries','≥2 peak positions','m/z + intensity'],[counts['entries:MS'],q['MS:at_least_two_numeric_peaks'],q['MS:numeric_position_intensity_pairs']],log=True)
    a.set(xlabel='Entries · overlapping tiers',title='OpenDataLab MS forms')
    m=external['massspecgym_1_5'];horizontal(b,['Train','Validation','Test'],[m['fold_spectra'][k] for k in ['train','val','test']],color=[blue,grey,teal])
    b.set(xlabel='MS/MS spectra',title='MassSpecGym v1.5')
    figures['data-ms-availability']=fig
    fig,(a,b)=canvas();kinds=['IR','Raman'];pos=np.arange(2)
    a.bar(pos-.18,[counts['entries:'+k] for k in kinds],.35,color=grey,label='All entries')
    a.bar(pos+.18,[counts['entries_with_structure_text:'+k] for k in kinds],.35,color=blue,label='With structure text')
    a.set_xticks(pos,kinds);a.set(yscale='log',ylabel='Experimental entries',title='OpenDataLab · experimental');a.legend(loc='upper center',bbox_to_anchor=(.5,-.22),fontsize=7,ncol=1)
    arrays=external['qme14s']['channels'];vals=[arrays[k]['records'] for k in ['ir','raman']];usable=[arrays[k]['records']-arrays[k]['constant_rows'] for k in ['ir','raman']]
    b.bar(pos,vals,color=grey,width=.55,label='Array rows');b.bar(pos,usable,color=teal,width=.55,label='Nonconstant rows')
    b.set_xticks(pos,kinds);b.set(ylabel='Computed array rows',title='QMe14S local arrays');b.yaxis.set_major_formatter(FuncFormatter(lambda v,p:f'{v/1000:g}k'))
    b.legend(loc='upper center',bbox_to_anchor=(.5,-.22),fontsize=7,ncol=1)
    fig.subplots_adjust(bottom=.32)
    figures['data-vibrational-availability']=fig
    fig,(a,b)=canvas();comb=raw['combinations'];buckets={'NMR only':0,'MS only':0,'NMR + MS':0,'Includes IR':0,'Includes Raman':0,'Other':0}
    for name,value in comb.items():
        tokens=set(name.split('+'));tokens.discard('Other')
        key='Includes Raman' if 'Raman' in tokens else 'Includes IR' if 'IR' in tokens else 'NMR + MS' if tokens=={'NMR','MS'} else 'NMR only' if tokens=={'NMR'} else 'MS only' if tokens=={'MS'} else 'Other'
        buckets[key]+=value
    assert sum(buckets.values())==counts['compound_records']
    horizontal(a,list(buckets),list(buckets.values()),log=True);a.set(xlabel='Compound records · log scale',title='Mutually exclusive groups')
    nmr_ms=sum(value for key,value in comb.items() if {'NMR','MS'}<=set(key.split('+')))
    allfour=sum(value for key,value in comb.items() if {'NMR','MS','IR','Raman'}<=set(key.split('+')))
    horizontal(b,['Any NMR + MS','NMR + MS + IR','All four'],[nmr_ms,sum(value for key,value in comb.items() if {'NMR','MS','IR'}<=set(key.split('+'))),allfour],color=teal,log=True)
    b.set(xlabel='Compound records · overlapping subsets',title='Co-occurrence of modalities')
    figures['data-multimodal-availability']=fig
    massbank_path=ROOT/'results/massbank_spectrum_qualification_20261117.json'
    if massbank_path.exists():
        massbank=json.loads(massbank_path.read_text())
        fig,(a,b)=canvas()
        for dataset,hist,color in [('MassSpecGym v1.5',external['massspecgym_1_5']['heavy_atom_histogram_spectral_records'],blue),('MassBank snapshot',massbank['heavy_atom_histogram_spectral_records'],teal)]:
            pairs=sorted((int(k),v) for k,v in hist.items());x=np.array([k for k,v in pairs]);n=np.array([v for k,v in pairs])
            a.step(x,np.cumsum(n)/n.sum(),where='post',color=color,label=dataset,lw=1.4)
        a.set(xlabel='Heavy atoms · log scale',ylabel='Fraction of spectra',xscale='log',ylim=(0,1.03),title='Valid-structure spectral records');a.legend(loc='lower right',fontsize=6.7)
        adducts=external['massspecgym_1_5']['adducts'];pairs=sorted(adducts.items(),key=lambda item:-item[1])
        horizontal(b,[k for k,v in pairs],[v for k,v in pairs],log=True)
        b.set(xlabel='Spectra · log scale',title='MassSpecGym v1.5 adducts')
        figures['data-ms-distributions']=fig
    qme_path=ROOT/'results/qme14s_alignment_20261117.json'
    if qme_path.exists():
        qme=json.loads(qme_path.read_text())
        fig,(a,b)=canvas();fig.subplots_adjust(left=.11,wspace=.57)
        for dataset,hist,color in [('QM9S local view',external['qm9s']['heavy_atom_histogram_mapping_records'],blue),('QMe14S local view',qme['heavy_atom_histogram_molecular_records'],teal)]:
            pairs=sorted((int(k),v) for k,v in hist.items());x=np.array([k for k,v in pairs]);n=np.array([v for k,v in pairs])
            a.step(x,np.cumsum(n)/n.sum(),where='post',color=color,label=dataset,lw=1.4)
        a.set(xlabel='Heavy atoms',ylabel='Fraction of molecular records',ylim=(0,1.03),title='Computed collection coverage');a.legend(loc='lower right',fontsize=6.7)
        elements=qme['element_presence_molecular_records'];pairs=sorted(elements.items(),key=lambda item:-item[1]);pos=np.arange(len(pairs))
        b.bar(pos,[v/qme['counts']['rows']*100 for k,v in pairs],color=teal,width=.7);b.set_xticks(pos,[k for k,v in pairs],rotation=90)
        b.set(xlabel='Element',ylabel='Molecular records (%)',title='QMe14S element occurrence')
        figures['data-vibrational-distributions']=fig
    qualified_path=ROOT/'results/opendatalab_structure_qualification_20261117.json'
    if qualified_path.exists():
        qualified=json.loads(qualified_path.read_text());distribution=qualified['modality_distributions']
        fig,(a,b)=canvas();fig.subplots_adjust(left=.12,wspace=.45)
        for key,label,color in [('nmr','NMR',blue),('ms','MS',teal),('ir','IR','#D47A42'),('raman','Raman','#7D6BA4')]:
            for ax,field,offset in [(a,'heavy_atom_histogram_unique_identities',0),(b,'molecular_weight_50Da_histogram_unique_identities',50)]:
                pairs=sorted((int(k)+offset,n) for k,n in distribution[key][field].items())
                x=np.array([k for k,n in pairs]);y=np.array([n for k,n in pairs])
                ax.step(x,np.cumsum(y)/y.sum(),where='post',lw=1.3,label=label,color=color)
        a.set_xscale('symlog',linthresh=1);b.set_xscale('log')
        a.set(xlabel='Heavy atoms · symlog scale',ylabel='Fraction of unique identities',title='OpenDataLab molecular size',ylim=(0,1.03))
        b.set(xlabel='Mass-bin upper edge (Da) · log',title='OpenDataLab mass · 50 Da bins',ylim=(0,1.03));b.legend(loc='lower right',fontsize=7)
        figures['data-opendatalab-chemistry']=fig
        fig,(a,b)=canvas();splits=qualified['fixed_scaffold_split']
        horizontal(a,['Train','Validation','Test'],[splits[k]['identities'] for k in ['train','val','test']],color=[blue,grey,teal])
        a.set(xlabel='Unique molecular identities',title='Fixed OpenMolSpec v1 partition')
        horizontal(b,['NMR','MS','IR','Raman'],[distribution[k]['unique_identities'] for k in ['nmr','ms','ir','raman']],log=True)
        b.set(xlabel='Identities · overlapping groups',title='At least one source entry')
        figures['data-opendatalab-splits']=fig
    args.output.mkdir(parents=True,exist_ok=True)
    qa=ROOT/'.runtime/figure-qa-v1';qa.mkdir(exist_ok=True)
    contracts={}
    for name,fig in figures.items():
        boxes=[ax.get_position() for ax in fig.axes]
        deviations=[abs(getattr(box,edge)-getattr(boxes[0],edge))*fig.get_figheight()*72 for box in boxes[1:] for edge in ['y0','y1']]
        alignment={'passed':bool(max(deviations,default=0)<=1.5),'tolerance_pt':1.5,'maximum_edge_deviation_pt':float(max(deviations,default=0))}
        (qa/f'{name}.alignment.json').write_text(json.dumps(alignment,indent=2)+'\n')
        if not alignment['passed']:raise ValueError('Panel alignment failed: '+name)
        for ext in ['svg','pdf','png']:
            fig.savefig(args.output/f'{name}.{ext}',dpi=300,metadata={'Date':None} if ext=='svg' else {'CreationDate':None} if ext=='pdf' else None)
        sources=['opendatalab_all_modalities_20261117.json','external_data_census_20261117.json','corpus_comparison_20261117.json']
        if name=='data-ms-distributions':sources=['external_data_census_20261117.json','massbank_spectrum_qualification_20261117.json']
        if name=='data-vibrational-distributions':sources=['external_data_census_20261117.json','qme14s_alignment_20261117.json']
        if name.startswith('data-opendatalab-'):sources=['opendatalab_structure_qualification_20261117.json']
        contracts[name]={'backend':'Python / Matplotlib','font':'Arial','dimensions_mm':[180.34,76.2],'source_reports':sources,'exclusions':'none; category aggregation specified in plotting source','statistics':'whole-file counts, no sampling or error bars','alignment_report':str(qa/f'{name}.alignment.json')}
        plt.close(fig);print('Exported',name,flush=True)
    (qa/'contracts.json').write_text(json.dumps(contracts,indent=2)+'\n')


if __name__=='__main__':main()
