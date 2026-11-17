"""Build the GitHub Pages project portal from real documentation evidence.

No server or frontend build dependency is required. Relative asset paths support
the requested /openmolspec.github.io/ project URL and local preview prefixes.
"""
import argparse
from html import escape
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from openmolspec_bench.catalog import TASKS
from documentation_content import group
from build_bilingual_docs import profile

DOCS='https://openmolspec-10.readthedocs.io/en/latest/'


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
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    assets=ROOT/'documentation/assets';gallery=assets/'gallery'
    shutil.copytree(assets/'brand',output/'assets/brand',dirs_exist_ok=True)
    (output/'assets/gallery').mkdir(parents=True,exist_ok=True)
    for path in gallery.iterdir():
        if path.suffix in ['.png','.svg','.pdf']:shutil.copyfile(path,output/'assets/gallery'/path.name)
    for name in ['site.css','site.js']:shutil.copyfile(ROOT/'website'/name,output/name)
    text=(ROOT/'website/index.html').read_text()
    tasks=[task for task in TASKS if task.enabled]
    proof=json.loads((ROOT/'results/doc_notebook_execution.json').read_text())
    text=text.replace('__STATS__',''.join(f'<div class="stat"><strong>{value}</strong><span>{label}</span></div>' for value,label in [('2.68M','curated experimental H/C molecular identities'),(str(len(tasks)),'active task definitions'),(str(proof['executed_notebooks']),'executed bilingual tutorials')]))
    external=json.loads((ROOT/'results/external_data_census_20261117.json').read_text())['datasets']
    qme=json.loads((ROOT/'results/qme14s_alignment_20261117.json').read_text())
    massbank=json.loads((ROOT/'results/massbank_spectrum_qualification_20261117.json').read_text())
    rows=[('OpenDataLab · curated H/C view','Experimental','2,680,271 standard molecular identities',DOCS+'data/nmr.html'),
          ('NMRexp v2 · external reference','Experimental NMR','3,372,987 spectra / 1,499,173 standard molecular identities','https://zenodo.org/records/17296666'),
          ('OpenMolSpec · computed test view','Computed','20,390 records / 16,728 molecular structures',DOCS+'datasets.html'),
          ('MassSpecGym v1.5','Experimental MS/MS',f'{external["massspecgym_1_5"]["counts"]["spectra"]:,} spectra','https://huggingface.co/datasets/roman-bushuiev/MassSpecGym'),
          ('MassBank · local snapshot','Experimental MS',f'{massbank["counts"]["valid_numeric_ms2_with_valid_structure"]:,} MS2 spectra with valid structures','https://github.com/MassBank/MassBank-data'),
          ('QM9S · local view','Computed',f'{external["qm9s"]["mapping_ids"]:,} mapped molecular records','https://www.nature.com/articles/s43588-023-00550-y'),
          ('QMe14S · local view','Computed',f'{qme["counts"]["unique_standard_inchikeys"]:,} molecular identities / {qme["paired_array_quality"]["both_finite_nonconstant_rows"]:,} nonconstant IR–Raman pairs','https://arxiv.org/abs/2501.18876')]
    qualification=ROOT/'results/opendatalab_structure_qualification_20261117.json'
    if qualification.exists():
        qualified=json.loads(qualification.read_text())
        rows.insert(1,('OpenDataLab · qualified collection','Experimental NMR / MS / IR / Raman',f'{qualified["unique_valid_identities"]:,} identities / {qualified["benchmark_identities"]:,} in the fixed benchmark',DOCS+'data/splits.html'))
    text=text.replace('__DATA_ROWS__',''.join(f'<tr><td>{escape(name)}</td><td>{escape(domain)}</td><td>{escape(count)}</td><td><a href="{url}">Source / guide ↗</a></td></tr>' for name,domain,count,url in rows))
    figures=[]
    for slug,label in [('data-nmr-nuclei','NMR nucleus distributions'),('data-ms-distributions','MS molecular size and acquisition conditions'),('data-vibrational-distributions','Computed molecular and element coverage'),('data-multimodal-availability','Experimental modality co-occurrence'),('data-opendatalab-chemistry','OpenDataLab molecular size and mass'),('data-opendatalab-splits','Fixed benchmark and molecular coverage')]:
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
        slug=path.stem;family=task_families.get(slug,'nmr' if slug=='filtered-retrieval' else 'data')
        title=task_names.get(slug,slug.replace('-',' ').replace('_',' ').capitalize())
        guide=DOCS+('tasks/'+slug+'.html' if slug in task_names else 'benchmarks.html' if slug=='filtered-retrieval' else 'data/index.html')
        cards.append(f'<article class="gallery-card" data-family="{family}"><a href="assets/gallery/{slug}.png" data-figure data-guide="{guide}"><img src="assets/gallery/{slug}.png" alt="{escape(title)} — actual recorded results" loading="lazy"></a><div class="gallery-caption"><h3>{escape(title)}</h3><a href="{guide}">Inputs, outputs and source →</a><a class="download" href="assets/gallery/{slug}.svg">SVG ↗</a></div></article>')
    text=text.replace('__GALLERY__',''.join(cards)).replace('__FIGURE_COUNT__',str(len(cards)))
    if '__' in text:raise ValueError('Unfilled site template marker')
    (output/'index.html').write_text(text)
    (output/'.nojekyll').write_text('')
    (output/'README.md').write_text('# OpenMolSpec v1.0 project site\n\nhttps://jiaqingxie.github.io/openmolspec.github.io/\n\nStatic HTML/CSS/JS built from the versioned OpenMolSpec documentation evidence.\nSource generator: https://github.com/jiaqingxie/openmolspec-studio-frontend/tree/release/openmolspec-v1/website\n\nModel calls and training run through the Python package and documented author environments.\n')
    report={'completed':True,'active_tasks':len(tasks),'scientific_figures':len(cards),'executed_tutorials':proof['executed_notebooks'],'external_runtime_dependencies':False,'target':'https://jiaqingxie.github.io/openmolspec.github.io/'}
    (output/'build-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
