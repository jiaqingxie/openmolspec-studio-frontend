"""Scientific figures for the reader-facing documentation and notebooks.

Every plotted value comes from the supplied evidence. RDKit structure drawings
are aligned for comparison and embedded as native vector paths in SVG exports.
"""
import copy
import io
import json
from pathlib import Path
import sys
import textwrap
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np

INK = '#20334B'
MUTED = '#6A7889'
BLUE = '#397BA6'
TEAL = '#178F88'
ORANGE = '#D47A42'
RED = '#BB5D4E'
GREY = '#A8B3BF'
LIGHT = '#E9EEF2'
SVG = 'http://www.w3.org/2000/svg'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


class ScientificFigure(Figure):
    def savefig(self, fname, *args, **kwargs):
        fmt = kwargs.get('format') or (Path(fname).suffix.lstrip('.') if isinstance(fname, (str, Path)) else '')
        molecules = getattr(self, '_vector_molecules', [])
        if fmt != 'svg' or not molecules:
            return super().savefig(fname, *args, **kwargs)
        stream = io.StringIO()
        super().savefig(stream, *args, **{**kwargs, 'format': 'svg'})
        document = ET.fromstring(stream.getvalue())
        width, height = self.get_size_inches()*72
        for axis, vector in molecules:
            group = next((g for g in document.iter(f'{{{SVG}}}g') if g.get('id') == axis.get_gid()), None)
            if group is None:
                raise ValueError('Missing molecular SVG panel')
            for parent in list(group.iter()):
                for node in list(parent):
                    if node.tag == f'{{{SVG}}}image': parent.remove(node)
            box = axis.images[0].get_window_extent().transformed(self.transFigure.inverted()) if axis.images else axis.get_position()
            native = ET.fromstring(vector)
            native_width, native_height = map(float, native.get('viewBox').split()[2:])
            transform = f'translate({box.x0*width} {(1-box.y1)*height}) scale({box.width*width/native_width} {box.height*height/native_height})'
            embedded = ET.SubElement(group, f'{{{SVG}}}g', {'transform': transform})
            for child in native:
                embedded.append(copy.deepcopy(child))
        ET.register_namespace('', SVG)
        ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')
        rendered = ET.tostring(document, encoding='unicode')
        if hasattr(fname, 'write'):
            fname.write(rendered)
        else:
            Path(fname).write_text(rendered)


def style():
    from openmolspec.plotting import figure_style
    figure_style()
    plt.rcParams.update({'font.family':'Arial','font.size':8,'axes.titlesize':9,
        'axes.titleweight':'normal','axes.labelsize':9,'axes.labelcolor':'#222222',
        'text.color':INK,'xtick.color':MUTED,'ytick.color':MUTED,
        'xtick.labelsize':8,'ytick.labelsize':8,'axes.edgecolor':'#222222',
        'axes.linewidth':.6,'axes.spines.top':False,'axes.spines.right':False,
        'axes.titlepad':8,'axes.labelpad':5,'figure.facecolor':'white',
        'savefig.facecolor':'white','legend.frameon':False,'legend.fontsize':8,
        'svg.hashsalt':'openmolspec-figures-v2','svg.fonttype':'none','pdf.fonttype':42})


def canvas(title, kicker, subtitle, widths=(1,1), height=6.4, left=.09):
    style()
    fig = plt.figure(figsize=(7.1,max(2.8,height/2)), FigureClass=ScientificFigure)
    grid = fig.add_gridspec(1,len(widths),width_ratios=widths,left=left,right=.98,
                           top=.84,bottom=.19,wspace=.38)
    axes = [fig.add_subplot(grid[0,i]) for i in range(len(widths))]
    fig._description={'title':title,'topic':kicker,'description':subtitle}
    return fig, axes


def footer(fig, text, status='Recorded results'):
    fig._source_caption=text


def clean(axis, grid='y'):
    axis.set_axisbelow(True)
    axis.grid(False)
    axis.tick_params(length=3,pad=5)


def panel(axis, letter, title):
    axis.set_title(textwrap.fill(title,31),loc='left',fontsize=9)
    axis.text(-.15,1.10,letter,transform=axis.transAxes,weight='bold',fontsize=9,color='#111111')


def molecule(axis, smiles, reference=None, atom_indices=False):
    from rdkit import Chem
    from rdkit.Chem import rdDepictor, rdFMCS
    from rdkit.Chem.Draw import rdMolDraw2D
    from PIL import Image
    mol = Chem.MolFromSmiles(smiles) if smiles else None
    axis.axis('off')
    if mol is None:
        axis.text(.5,.5,'No valid structure returned',ha='center',va='center',color=RED,transform=axis.transAxes)
        return None
    # Canonicalize unlabelled depictions so equivalent SMILES share an orientation.
    if not atom_indices:
        mol = Chem.MolFromSmiles(Chem.MolToSmiles(mol,isomericSmiles=True))
    rdDepictor.Compute2DCoords(mol)
    if reference is not None:
        match=rdFMCS.FindMCS([reference,mol],timeout=2,ringMatchesRingOnly=True)
        if not match.canceled and match.numAtoms >= 3:
            params=rdDepictor.ConstrainedDepictionParams();params.alignOnly=True;params.acceptFailure=True
            rdDepictor.GenerateDepictionMatching2DStructure(mol,reference,refPatt=Chem.MolFromSmarts(match.smartsString),params=params)
    width,height=840,470
    drawings=[]
    for cls in (rdMolDraw2D.MolDraw2DCairo,rdMolDraw2D.MolDraw2DSVG):
        draw=cls(width,height);options=draw.drawOptions()
        options.bondLineWidth=3.2;options.padding=.08;options.minFontSize=40;options.maxFontSize=44
        from openmolspec.plotting import arial_path
        options.fontFile=arial_path()
        options.addAtomIndices=atom_indices
        options.annotationFontScale=.8
        draw.DrawMolecule(mol);draw.FinishDrawing();drawings.append(draw.GetDrawingText())
    axis.imshow(Image.open(io.BytesIO(drawings[0])))
    axis.set_aspect('equal',adjustable='datalim')
    vector=getattr(axis.figure,'_vector_molecules',[])
    axis.set_gid('oms-molecule-'+str(len(vector)))
    vector.append((axis,drawings[1]));axis.figure._vector_molecules=vector
    return mol


def metrics_box(axis, text, color=TEAL):
    axis.text(.04,.96,text,transform=axis.transAxes,va='top',ha='left',fontsize=8,color='#333333')


def render_task(task_id, evidence):
    b=evidence;p=b['plot'];kind=p['kind'];first=b['examples'][0]
    scope=p['label']
    if kind=='hsqc':
        fig,(structure,ax)=canvas('Butanenitrile in CDCl₃','HSQC',scope)
        molecule(structure,first['input']['smiles'],atom_indices=True)
        panel(structure,'a','Butanenitrile')
        for peaks,marker,color,label in [(first['reference']['peaks_c_h_ppm'],'o',TEAL,'Observed'),
                                         (first['output']['peaks_c_h_ppm'],'x',ORANGE,'Predicted')]:
            c,h=np.array(peaks).T
            ax.scatter(h,c,marker=marker,color=color,label=label)
        ax.set(xlabel='¹H (ppm)',ylabel='¹³C (ppm)')
        ax.invert_xaxis()
        ax.invert_yaxis()
        ax.legend()
        panel(ax,'b','HSQC cross-peaks')
    elif kind=='parity':
        x,y=np.asarray(p['x']),np.asarray(p['y']);error=y-x
        gap='.gap.' in task_id
        title='Predicting the HOMO–LUMO gap' if gap else task_id.rsplit('.',1)[-1]+' chemical-shift diagnostic'
        subtitle='Prediction and reference for every recorded pair · '+str(len(x))+' paired values'
        fig,axes=canvas(title,'Multimodal property prediction' if gap else 'NMR · model assessment',subtitle)
        ax,dist=axes;low,high=min(x.min(),y.min()),max(x.max(),y.max());margin=max((high-low)*.08,.01)
        ax.plot([low-margin,high+margin],[low-margin,high+margin],ls=(0,(4,4)),color=GREY,lw=1.2,zorder=1)
        ax.scatter(x,y,s=35,facecolors=BLUE,edgecolors='white',linewidth=.6,alpha=.85,zorder=3)
        ax.set(xlim=(low-margin,high+margin),ylim=(low-margin,high+margin),xlabel=f'Reference ({p["unit"]})',ylabel=f'Prediction ({p["unit"]})')
        clean(ax,'both');panel(ax,'a','Prediction versus reference')
        dist.hist(error,bins=min(18,max(6,int(np.sqrt(len(x))))),color=TEAL,alpha=.82,rwidth=.9)
        dist.axvline(0,color=INK,lw=1,ls=(0,(4,3)))
        dist.set(xlabel=f'Prediction − reference ({p["unit"]})',ylabel='Paired values')
        dist.yaxis.set_major_locator(MaxNLocator(integer=True));clean(dist);panel(dist,'b','Error distribution')
        footer(fig,scope+' · The dashed diagonal denotes exact agreement.', 'Diagnostic only' if not gap else 'Frozen-model evaluation')
    elif kind=='vibrational':
        fig,axes=canvas('Vibrational spectra from a molecular geometry','IR / Raman · openSpec',
                        'Predicted Hessian and response tensors · reference and prediction use the same geometry')
        for i,(ax,channel) in enumerate(zip(axes,('ir','raman'))):
            ref=np.asarray(p['reference_'+channel]);pred=np.asarray(p['predicted_'+channel]);x=p['wavenumber_cm1']
            ax.fill_between(x,0,ref,color=BLUE,alpha=.09)
            ax.plot(x,ref,color=BLUE,lw=1.5,label='Gaussian reference')
            ax.plot(x,pred,color=ORANGE,lw=1.35,alpha=.95,label='Model prediction')
            ax.set(xlabel='Wavenumber (cm$^{-1}$)',ylabel='Normalized intensity',xlim=(400,4000),ylim=(-.03,1.13))
            ax.set_xticks([500,1500,2500,3500]);clean(ax);panel(ax,chr(97+i),'Infrared' if channel=='ir' else 'Raman')
            ax.legend(loc='upper right',fontsize=9)
        footer(fig,scope+' · Normalized line shapes; two examples establish execution, not independent accuracy.')
    elif kind=='nmr_peaks':
        nucleus=task_id.rsplit('.',1)[-1]
        fig,axes=canvas('Molecular structure to '+nucleus+' chemical shifts','NMR · frozen forward prediction',
                        'Known structure → atomwise predictions · experimental peaks are shown only for comparison',widths=(.82,1.5))
        molecule(axes[0],p['smiles']);panel(axes[0],'a','Input structure')
        ax=axes[1];ref=p['reference_ppm'];pred=p['prediction_ppm']
        ax.vlines(ref,0,1,color=BLUE,lw=1.7,label=f'Experimental · {len(ref)} peaks')
        ax.vlines(pred,0,-1,color=ORANGE,lw=1.5,label=f'Predicted · {len(pred)} atom shifts')
        ax.axhline(0,color=GREY,lw=.8);ax.set(ylim=(-1.35,1.65),xlabel='Chemical shift (ppm)',yticks=[])
        ax.invert_xaxis();ax.spines['left'].set_visible(False);ax.legend(loc='upper right',fontsize=9)
        panel(ax,'b','Experimental and predicted peak positions')
        footer(fig,scope+' · Stick heights mark positions, not measured intensities. Peak matching does not establish atom assignments.')
    elif kind=='ms':
        fig,axes=canvas('Molecular structure to an MS/MS spectrum','Mass spectrometry · '+task_id.rsplit('.',1)[-1].upper(),
                        'Frozen prediction under recorded acquisition conditions',widths=(.8,1.5))
        molecule(axes[0],first['input']['smiles']);panel(axes[0],'a','Input structure')
        ax=axes[1]
        for key,sign,color,label in [('reference',1,BLUE,'Observed'),('predicted',-1,ORANGE,'Predicted')]:
            values=np.asarray(p[key],dtype=float).copy();values[:,1]/=max(values[:,1].max(),1e-12)
            ax.vlines(values[:,0],0,sign*values[:,1],color=color,lw=1.1,label=label)
        ax.axhline(0,color=GREY,lw=.8);ax.set(xlabel='m/z',ylabel='Relative intensity',ylim=(-1.18,1.4))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v,pos:f'{abs(v):g}'));clean(ax);ax.legend(loc='upper left',fontsize=8)
        panel(ax,'b','MS/MS spectrum')
        fields=first['input'];footer(fig,f'{fields["adduct"]} · collision energy {fields["collision_energy"]} · {fields["instrument"]}. '+scope)
    elif kind=='ranking':
        style();candidates=p['candidates'];columns=3;rows=int(np.ceil(len(candidates)/columns))
        fig=plt.figure(figsize=(7.1,.6+1.85*rows),FigureClass=ScientificFigure)
        grid=fig.add_gridspec(rows,columns,left=.045,right=.98,top=.93,bottom=.07,wspace=.22,hspace=.62)
        for index,candidate in enumerate(candidates):
            ax=fig.add_subplot(grid[index//columns,index%columns]);molecule(ax,candidate['smiles'])
            color=TEAL if candidate['reference_match'] else INK
            ax.set_title(f'Rank {index+1}'+(' · Reference' if candidate['reference_match'] else ''),loc='left',color=color,fontsize=8,pad=7)
            ax.text(.5,-.14,f'Score {candidate["score"]:.3f}',transform=ax.transAxes,ha='center',fontsize=8,color=color)
        footer(fig,scope+' · All candidates retained in the recorded ranking are drawn. Reference labels are for evaluation; scores are not calibrated probabilities.')
    elif kind=='molecules':
        from rdkit import Chem
        candidates=first.get('candidates')
        if candidates and len(candidates)>1:
            structures=[('Reference',p['reference'],None)]+[(f'Rank {i+1}',c.get('canonical_smiles') or c.get('smiles'),c.get('score')) for i,c in enumerate(candidates)]
            style();columns=3;rows=int(np.ceil(len(structures)/columns))
            fig=plt.figure(figsize=(7.1,.65+1.95*rows),FigureClass=ScientificFigure)
            grid=fig.add_gridspec(rows,columns,left=.04,right=.98,top=.92,bottom=.09,wspace=.24,hspace=.65)
            reference=None
            for index,(label,smiles,score) in enumerate(structures):
                ax=fig.add_subplot(grid[index//columns,index%columns]);mol=molecule(ax,smiles,reference=reference)
                if index==0:reference=mol
                match=reference is not None and mol is not None and Chem.MolToSmiles(reference)==Chem.MolToSmiles(mol)
                ax.set_title(label+(' · Match' if index and match else ''),loc='left',fontsize=8,color=TEAL if match else INK,pad=7)
                if score is not None:ax.text(.5,-.14,f'Score {score:.3f}',transform=ax.transAxes,ha='center',fontsize=8,color=MUTED)
            footer(fig,scope+' · Every saved candidate is shown, including incorrect structures. Scores retain the original decoding convention.')
            return fig
        modality='NMR + supplied molecular formula' if task_id.startswith('nmr.') else 'Spectral inputs · no molecular formula supplied'
        fig,axes=canvas('From spectra to a molecular structure','Structure generation',modality+' · first recorded example')
        reference=molecule(axes[0],p['reference']);predicted=molecule(axes[1],p['predicted'],reference=reference)
        panel(axes[0],'a','Reference structure');panel(axes[1],'b','Actual top-1 prediction')
        matched=reference is not None and predicted is not None and Chem.MolToSmiles(reference)==Chem.MolToSmiles(predicted)
        footer(fig,scope+' · 2D drawings are aligned for readability. The reference structure is not a model input.')
    elif kind=='assignment':
        r=p['record'];entries=r['assignments'];x=np.array([e['observed_ppm'] for e in entries]);y=np.array([e['predicted_ppm'] for e in entries])
        fig,axes=canvas('Assigning observed peaks to candidate atoms','NMR · known-structure assignment',
                        'Frozen atomwise prediction followed by minimum-cost peak matching',widths=(1.15,1))
        molecule(axes[0],r['smiles'],atom_indices=True);panel(axes[0],'a','Structure with zero-based atom indices')
        ax=axes[1];limits=[min(x.min(),y.min())-5,max(x.max(),y.max())+5]
        ax.plot(limits,limits,color=GREY,ls=(0,(4,3)),lw=1.2);ax.scatter(x,y,color=TEAL,s=45,edgecolors='white',zorder=3)
        ax.set(xlabel='Observed ¹³C peak (ppm)',ylabel='Matched site prediction (ppm)',xlim=limits,ylim=limits)
        clean(ax,'both');panel(ax,'b','Matched peaks');metrics_box(ax,f'{len(entries)} matched peaks\nResidual MAE  {np.mean(abs(y-x)):.2f} ppm')
        footer(fig,'Candidate assignments only. Residual error is not experimental assignment accuracy; independent atom-assignment labels are unavailable.', 'Assignment accuracy not measured')
    elif kind=='solvent':
        fig,axes=canvas('Transferring chemical shifts between solvents','NMR · experimental-reference baseline',
                        'Paired experimental atoms · comparison with leaving the source shift unchanged',left=.145)
        for i,(ax,nucleus) in enumerate(zip(axes,('1H','13C'))):
            m=p['metrics'][nucleus];values=[m['unchanged_shift_mae_ppm'],m['mae_ppm']]
            ax.barh([1,0],values,height=.5,color=[GREY,TEAL]);ax.set_yticks([1,0],['Unchanged','Transfer'])
            ax.set(xlabel='Mean absolute error (ppm)',xlim=(0,max(values)*1.38),ylim=(-.7,1.7));clean(ax,'x')
            for y,value in zip([1,0],values):ax.text(value+max(values)*.035,y,f'{value:.3f}',va='center',fontsize=8)
            panel(ax,chr(97+i),('¹H' if nucleus=='1H' else '¹³C')+f' · {m["atoms"]} paired atoms')
        footer(fig,scope+' · Lower is better. This reference-retrieval algorithm is not a pretrained solvent-conditioned neural model.')
    elif kind=='magma':
        fig,axes=canvas('Explaining MS/MS peaks with candidate fragments','Mass spectrometry · MAGMa',
                        'Known structure and observed peaks → algorithmic fragment matches',widths=(1,1))
        molecule(axes[0],first['output']['engine_smiles']);panel(axes[0],'a','Structure used by the annotation engine')
        records=p['records'];ax=axes[1];pos=np.arange(len(records));matched=np.array([r['n_matched'] for r in records]);total=np.array([r['n_peaks'] for r in records])
        ax.barh(pos,matched,color=TEAL,height=.48,label='Matched');ax.barh(pos,total-matched,left=matched,color=LIGHT,height=.48,label='Unmatched')
        ax.set_yticks(pos,[f'Spectrum {i+1}' for i in pos]);ax.invert_yaxis();ax.set_xlabel('Observed peaks');clean(ax,'x');ax.legend(loc='lower right',fontsize=8)
        for y,m,n in zip(pos,matched,total):ax.text(n+.02*max(total),y,f'{m}/{n}',va='center',fontsize=11)
        ax.set_xlim(0,max(total)*1.25);panel(ax,'b','Peak-matching coverage')
        footer(fig,scope+' · Fragment matches are candidate explanations, not experimental proof of a unique fragmentation pathway.')
    else:
        raise ValueError(kind)
    return fig


def short_count(value, position=None):
    return f'{value/1e6:g}M' if abs(value)>=1e6 else f'{value/1e3:g}k' if abs(value)>=1000 else f'{value:g}'


def count_bars(axis, labels, values, colors=BLUE):
    pos=np.arange(len(values));axis.barh(pos,values,color=colors,height=.56);axis.set_yticks(pos,labels);axis.invert_yaxis()
    axis.set_xlim(0,max(values)*1.32);axis.xaxis.set_major_formatter(FuncFormatter(short_count));clean(axis,'x')
    for y,v in zip(pos,values):axis.text(v+max(values)*.025,y,f'{v:,}',va='center',fontsize=10,color=INK)


def render_datasets(data):
    figures={}
    rows=data['datasets'][:4]
    fig,(ax,)=canvas('What is available in the NMR evaluation files','Data · experimental evaluation views',
                    'Complete local-file census · molecular records grouped by available H/C modalities',widths=(1,),height=6)
    ax.set_position([.21,.205,.745,.53])
    labels={'nmrspec_test':'NMRSpec','patent_test_10k':'OpenDataLab patent','nmrexp_exp_10k':'NMRexp','nmrgym_test':'NMRGym'}
    positions=np.arange(len(rows));left=np.zeros(len(rows))
    for modality,color in [('H only',BLUE),('H+C',TEAL),('C only',ORANGE)]:
        counts=np.array([r['modality_records'].get(modality,0) for r in rows])
        ax.barh(positions,counts,left=left,label=modality,color=color,height=.52);left+=counts
    ax.set_yticks(positions,[labels[r['id']] for r in rows]);ax.invert_yaxis();ax.set(xlabel='Molecular records',xlim=(0,max(left)*1.14))
    ax.xaxis.set_major_formatter(FuncFormatter(short_count));clean(ax,'x');ax.legend(loc='lower right',ncol=3,bbox_to_anchor=(1,1.02))
    for y,n in zip(positions,left):ax.text(n+max(left)*.015,y,f'{int(n):,}',va='center',fontsize=11)
    footer(fig,'Prepared evaluation views overlap other data and model-training files. These counts are not additive measures of new molecules.')
    figures['dataset-nmr-views']=fig
    row=next(r for r in data['datasets'] if r['id']=='openspec_test')
    fig,axes=canvas('The computed-spectrum test view','Data · OpenMolSpec computed observables',
                    '20,390 records · 16,728 unique canonical isomeric structures',widths=(1.1,1))
    axes[0].set_position([.19,.205,.29,.53])
    pairs=sorted(row['source_records'].items(),key=lambda item:-item[1]);count_bars(axes[0],[k for k,v in pairs],[v for k,v in pairs]);axes[0].set_xlabel('Test records');panel(axes[0],'a','Origins of the molecular structures')
    hist=row['heavy_atom_histogram'];axes[1].bar([int(k) for k in hist],list(hist.values()),color=TEAL,width=.85);axes[1].set(xlabel='Heavy atoms per molecule',ylabel='Test records');clean(axes[1]);panel(axes[1],'b','Molecular size')
    footer(fig,'Spectra in this view are calculated. Source-library names describe where the molecular structures originated.')
    figures['dataset-openspec-test']=fig
    counts=data['patent_corpus']['summary']['counts']
    fig,axes=canvas('Experimental NMR curated from patent records','Data · OpenDataLab / WanJuan',
                    f'{counts["examples"]:,} standard-InChI identities · counts from the existing complete-corpus report')
    count_bars(axes[0],['Train','Validation','Test'],[counts[k] for k in ('train','val','test')],[BLUE,GREY,TEAL]);axes[0].set_xlabel('Structure identities');panel(axes[0],'a','Prepared data splits')
    count_bars(axes[1],['H only','H + C','C only'],[counts[k] for k in ('h_only','h_and_c','c_only')],[BLUE,TEAL,ORANGE]);axes[1].set_xlabel('Structure identities');panel(axes[1],'b','Available spectral modalities')
    footer(fig,'Team-curated external experimental measurements. Molecular identities and spectral-record counts are distinct units.')
    figures['dataset-patent-corpus']=fig
    rows=[r for r in data['external_local_views'] if r['id'].startswith('nmrexp')]
    fig,(ax,)=canvas('Six nuclei in the local NMRexp views','Data · external experimental NMR',
                    'Locally filtered per-nucleus files · not a recount of the complete original release',widths=(1,),height=6.2)
    labels=[r['id'].split('_')[1] for r in rows];values=[r['records'] for r in rows];pos=np.arange(len(rows))
    ax.barh(pos,values,color=[BLUE if x in ('1H','13C') else TEAL for x in labels],height=.55)
    ax.set_yticks(pos,labels);ax.invert_yaxis();ax.set_xscale('log');ax.set(xlabel='Spectral records · logarithmic scale',xlim=(1,max(values)*5));clean(ax,'x')
    for y,n in zip(pos,values):ax.text(n*1.12,y,f'{n:,}',va='center',fontsize=10)
    footer(fig,'External authors retain credit for the measurements and original curation. Nucleus-specific spectral records are not unique-molecule counts.')
    figures['dataset-nmrexp-nuclei']=fig
    return figures
