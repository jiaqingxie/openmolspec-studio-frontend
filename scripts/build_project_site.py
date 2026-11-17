"""Build the GitHub Pages project portal from real documentation evidence.

No server or frontend build dependency is required. Relative asset paths support
the requested /openmolspec.github.io/ project URL and local preview prefixes.
"""
import argparse
from html import escape
import json
from pathlib import Path
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from openmolspec_bench.catalog import TASKS
from documentation_content import group
from manual_profiles import profile
from manual_citations import REFERENCES

DOCS='docs/'
DATA_FIGURES=[
    ('data-cleaned-nmr','Cleaned H/C NMR molecular distributions'),
    ('data-cleaned-nmr-shifts','Experimental proton and carbon chemical shifts'),
    ('data-cleaned-experimental','Cleaned experimental spectra by nucleus and modality'),
    ('data-cleaned-ms','Experimental mass spectra and molecular distributions'),
    ('data-cleaned-vibrational','Experimental IR and Raman peak distributions'),
]


def contract(task):
    name=task.id
    if name.startswith('nmr.forward.'):return 'Molecular structure; nucleus','Atom-indexed shifts (ppm)'
    if name=='nmr.assignment':return 'Known structure; observed H/C peaks','Candidate peak-to-atom assignments'
    if name=='nmr.solvent_transfer':return 'Structure; source shifts; solvent pair','Target shifts and reference provenance'
    if name.startswith('nmr.retrieval.'):
        return ('Molecular structure; candidate spectra','Ranked spectra') if name.endswith('.m2s') else ('NMR peaks; candidate structures','Ranked molecular structures')
    if name.startswith('nmr.generation.'):return 'NMR peaks; supplied molecular formula','SMILES candidates'
    if name.startswith('ms.forward.'):return 'Structure; adduct; collision energy; instrument','MS/MS m/z–intensity peaks'
    if name=='ms.annotation.magma':return 'Structure; MS/MS peaks; precursor conditions','Candidate fragment annotations'
    if name=='vibrational.forward':return 'Elements and 3D Cartesian coordinates','IR and Raman spectra'
    modalities=', '.join(task.modalities)
    if '.gap.' in name:return modalities,'HOMO–LUMO gap (eV)'
    if '.generation' in name:return modalities,'SMILES candidates'
    return modalities+'; candidate structures','Ranked molecular structures'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--manual',type=Path,required=True,help='Verified bilingual Sphinx HTML directory to include at docs/')
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    manual=args.manual.resolve()
    manifest=json.loads((manual/'build-manifest.json').read_text())
    if not manifest.get('completed') or not manifest.get('internal_links_verified'):
        raise ValueError('Build and verify the bilingual manual before packaging the project site')
    shutil.copytree(manual,output/'docs',dirs_exist_ok=True)
    assets=ROOT/'documentation/assets';gallery=assets/'gallery'
    extra={f'{slug}-example-{number}' for slug in ['nmr-generation-hc','ms-forward-glacier','ms-forward-iceberg'] for number in [2,3]}
    allowed={task.id.replace('.','-') for task in TASKS if task.enabled}|{slug for slug,_ in DATA_FIGURES}|extra
    shutil.copytree(assets/'brand',output/'assets/brand',dirs_exist_ok=True)
    (output/'assets/gallery').mkdir(parents=True,exist_ok=True)
    for path in (output/'assets/gallery').iterdir():
        if path.is_file() and path.stem not in allowed:path.unlink()
    for path in gallery.iterdir():
        if path.stem in allowed and path.suffix in ['.png','.svg','.pdf']:shutil.copyfile(path,output/'assets/gallery'/path.name)
    for name in ['site.css','site.js']:shutil.copyfile(ROOT/'website'/name,output/name)
    text=(ROOT/'website/index.html').read_text()
    tasks=[task for task in TASKS if task.enabled]
    proof=json.loads((ROOT/'results/doc_notebook_execution.json').read_text())
    summary=json.loads((assets/'cleaned-data-summary.json').read_text())
    cleaned=summary['nmr']
    if not cleaned['completed']:
        raise ValueError('The project site requires the completed cleaned NMR collection')
    text=text.replace('__INTRO_COUNTS__',f'The cleaned H/C NMR collection contains {cleaned["molecular_identities"]:,} molecular identities. Explore {len(tasks)} tasks and {proof["executed_notebooks"]} tutorials covering prediction, structure elucidation, training and spectroscopy.')
    qme=json.loads((ROOT/'results/qme14s_alignment_20261117.json').read_text())
    massbank=json.loads((ROOT/'results/massbank_spectrum_qualification_20261117.json').read_text())
    rows=[('OpenDataLab · cleaned H/C NMR','Experimental · OpenMolSpec collection','Proton and carbon chemical shifts, molecular structures, formulas and experimental conditions; predefined train/validation/test files.',f'{cleaned["molecular_identities"]:,} molecules; {cleaned["counts"]["h_spectra"]:,} H spectra; {cleaned["counts"]["c_spectra"]:,} C spectra',DOCS+'data/nmr.html'),
          ('NMRexp v2 · H/C view','Experimental · external','Literature-derived proton and carbon NMR spectra, accessed through the filtered per-nucleus Parquet views.','1,651,821 H spectra; 1,439,344 C spectra','https://zenodo.org/records/17296666'),
          ('OpenMolSpec · computed test view','Computed · OpenMolSpec benchmark','Paired IR/Raman arrays, H/C shifts, structures and electronic properties for molecular retrieval, generation and gap prediction.','20,390 records; 16,728 canonical molecular structures',DOCS+'data/vibrational.html'),
          ('MassSpecGym v1.5 · prediction view','Experimental · external','Tandem mass spectra paired with molecular structures and the acquisition conditions used for forward spectrum prediction.','119,029 prediction-ready spectra','https://huggingface.co/datasets/roman-bushuiev/MassSpecGym'),
          ('MassBank · MS2 view','Experimental · external','Numerical tandem mass spectra with parseable molecular structures and repository acquisition metadata.',f'{massbank["counts"]["valid_numeric_ms2_with_valid_structure"]:,} spectra','https://github.com/MassBank/MassBank-data'),
          ('QMe14S · paired IR/Raman view','Computed · external','Small molecules with 14-element coverage and finite, nonconstant paired infrared and Raman arrays.',f'{qme["paired_array_quality"]["both_finite_nonconstant_rows"]:,} IR/Raman pairs','https://arxiv.org/abs/2501.18876')]
    if 'experimental' in summary:
        report=summary['experimental']
        if report.get('completed'):
            descriptions={'IR':'Measured infrared peak positions in cm⁻¹, paired with standardized molecular structures.',
                'Raman':'Measured Raman peak positions in cm⁻¹ and source experimental metadata.',
                'MS':'Measured m/z–intensity peak lists paired with standardized molecular structures.',
                '11B':'Boron chemical shifts in ppm with boron-containing molecular structures.',
                '19F':'Fluorine chemical shifts in ppm with fluorine-containing molecular structures.',
                '29Si':'Silicon chemical shifts in ppm with silicon-containing molecular structures.',
                '31P':'Phosphorus chemical shifts in ppm with phosphorus-containing molecular structures.'}
            for modality,counts in report.get('views',{}).items():
                count=counts['spectra']
                if count: rows.insert(1,(f'OpenDataLab · {modality}','Experimental · OpenMolSpec collection',descriptions[modality],f'{count:,} spectra; {counts["molecules"]:,} molecules',DOCS+'data/index.html'))
    text=text.replace('__DATA_ROWS__',''.join(f'<tr><td><a href="{url}">{escape(name)}</a></td><td>{escape(domain)}</td><td>{escape(description)}</td><td>{escape(count)}</td></tr>' for name,domain,description,count,url in rows))
    text=text.replace('__REFERENCES__',''.join(f'<li>{escape(reference)} <a href="{url}">Source ↗</a></li>' for reference,url in REFERENCES.values()))
    example_rows=[]
    for slug,title,description in [
        ('nmr-generation-hc','Structure elucidation from NMR','Input H/C NMR peaks and a molecular formula; compare the generated candidate structures.'),
        ('ms-forward-glacier','Predicting tandem mass spectra','Input a molecular structure and acquisition conditions; compare predicted and observed fragment peaks.'),
        ('vibrational-forward','IR and Raman from a molecular geometry','Use the openSpec model to predict IR and Raman spectra from atomic coordinates.'),
        ('vibrational-gap-ir_raman_hc','Predicting the HOMO–LUMO gap','Combine IR, Raman and NMR spectra to predict the energy gap in eV.')]:
        guide=DOCS+'tasks/'+slug+'.html'
        example_rows.append(f'<figure><h3><a href="{guide}">{title}</a></h3><a href="assets/gallery/{slug}.png" data-figure data-guide="{guide}"><img src="assets/gallery/{slug}.png" alt="{title}" loading="lazy"></a><figcaption>{description}</figcaption></figure>')
    text=text.replace('__EXAMPLES__',''.join(example_rows))
    shutil.copytree(assets/'viewer',output/'assets/viewer',dirs_exist_ok=True)
    figures=[]
    for slug,label in DATA_FIGURES:
        if (gallery/(slug+'.png')).exists():figures.append(f'<figure><a href="assets/gallery/{slug}.png" data-figure data-guide="{DOCS}data/index.html"><img src="assets/gallery/{slug}.png" alt="{label}" loading="lazy"></a><figcaption>{label}</figcaption></figure>')
    text=text.replace('__DATA_FIGURES__',''.join(figures))
    task_rows=[];task_names={};task_families={}
    for task in tasks:
        slug=task.id.replace('.','-');title=profile(task)[0];family=group(task);inputs,outputs=contract(task)
        task_names[slug]=title;task_families[slug]=family
        task_rows.append(f'<tr data-family="{family}"><td><a href="{DOCS}tasks/{slug}.html">{escape(title)}</a><small>{task.id}</small></td><td>{escape(inputs)}</td><td>{escape(outputs)}</td></tr>')
    text=text.replace('__TASK_ROWS__',''.join(task_rows))
    tutorials=[('SDK inference','sdk-inference','Call NMRNet on a real molecular input and compare measured peaks.'),('Training workflow','sdk-training-preflight','Prepare train/validation data and inspect an explicit training plan.'),('NMR Fourier transform','theory-nmr-fourier','Simulate an FID and recover its frequencies.'),('NMR inversion','theory-nmr-inversion','Recover a relaxation distribution from simulated noisy signals.'),('IR / Raman broadening','theory-vibrational-broadening','Connect normal-mode activities to continuous spectra.'),('MS isotope envelopes','theory-ms-isotopes','Explore isotope probabilities and resolving power.')]
    text=text.replace('__TUTORIALS__',''.join(f'<a class="tutorial-card" href="{DOCS}notebooks/{slug}.html"><h3>{title}</h3><p>{desc}</p><span>Open executed tutorial →</span></a>' for title,slug,desc in tutorials))
    cards=[]
    for path in sorted(gallery.glob('*.png')):
        if path.stem not in allowed:continue
        slug=path.stem;base=re.sub(r'-example-[23]$','',slug);family=task_families.get(base,'data')
        title=task_names.get(base,dict(DATA_FIGURES).get(slug,slug.replace('-',' ').replace('_',' ').capitalize()))
        if base!=slug:title+=' · Example '+slug.rsplit('-',1)[1]
        guide=DOCS+('tasks/'+base+'.html' if base in task_names else 'data/index.html')
        cards.append(f'<article class="gallery-card" data-family="{family}"><a href="assets/gallery/{slug}.png" data-figure data-guide="{guide}"><img src="assets/gallery/{slug}.png" alt="{escape(title)} — actual recorded results" loading="lazy"></a><div class="gallery-caption"><h3>{escape(title)}</h3><a href="{guide}">Inputs, outputs and source →</a><a class="download" href="assets/gallery/{slug}.svg">SVG ↗</a></div></article>')
    text=text.replace('__GALLERY__',''.join(cards)).replace('__FIGURE_COUNT__',str(len(cards)))
    if '__' in text:raise ValueError('Unfilled site template marker')
    (output/'index.html').write_text(text)
    (output/'.nojekyll').write_text('')
    (output/'README.md').write_text('# OpenMolSpec v1.0 project site\n\nhttps://jiaqingxie.github.io/openmolspec.github.io/\n\nStatic HTML/CSS/JS built from the versioned OpenMolSpec documentation evidence.\nSource generator: https://github.com/jiaqingxie/openmolspec-studio-frontend/tree/release/openmolspec-v1/website\n\nModel calls and training run through the Python package and documented author environments.\n')
    report={'completed':True,'active_tasks':len(tasks),'scientific_figures':len(cards),'executed_tutorials':proof['executed_notebooks'],
        'cleaned_nmr_molecular_identities':cleaned['molecular_identities'],'interactive_3d_examples':3,
        'manual_html_pages':manifest['html_pages'],'manual_languages':manifest['languages'],
        'external_runtime_dependencies':False,'target':'https://jiaqingxie.github.io/openmolspec.github.io/'}
    (output/'build-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
