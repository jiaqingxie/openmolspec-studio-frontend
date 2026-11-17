"""Generate runnable, explicitly simulated spectroscopy teaching notebooks."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


EXPERIMENTS={
 'nmr-fourier':('NMR: from a free induction decay to a spectrum','NMR：从自由感应衰减到频谱',
'''import numpy as np
time = np.arange(4096) / 4096
frequencies = np.array([80., 145., 210.])
amplitudes = np.array([1., .65, .4])
signal = sum(a*np.exp(-time/.12)*np.exp(2j*np.pi*f*time) for a,f in zip(amplitudes,frequencies))
axis = np.fft.fftfreq(len(time), time[1]-time[0])
spectrum = np.fft.fft(signal).real
assert abs(axis[np.argmax(spectrum)] - 80) < 1.1
fig, axes = plt.subplots(1, 2, figsize=(7.1, 3.1))
axes[0].plot(time, signal.real, color=blue, lw=.7)
axes[0].set(xlabel='Time (s)', ylabel='Signal (a.u.)', xlim=(0, .5), title='Simulated free induction decay')
axes[1].plot(axis, spectrum, color=teal, lw=.9)
axes[1].set(xlabel='Frequency offset (Hz)', ylabel='Absorption (a.u.)', xlim=(40,250), title='Fourier spectrum')
print('Input frequencies (Hz):', frequencies.tolist())'''),
 'nmr-inversion':('NMR inversion: recovering a relaxation distribution','NMR 反演：恢复弛豫时间分布',
'''import numpy as np
from openmolspec.inversion import kernel, invert
rng = np.random.default_rng(2026)
time = np.linspace(0, 1.5, 100)
grid = np.geomspace(.005, 2, 100)
truth = np.zeros(100)
locations = [np.argmin(abs(grid-.05)), np.argmin(abs(grid-.35))]
truth[locations] = [.35, .65]
ideal = kernel(time, grid) @ truth
observed = ideal + rng.normal(0,.002,len(time))
result = invert(time, observed, grid, alpha=.01, penalty='curvature')
assert result.diagnostics['converged'] and (result.weights >= 0).all()
assert result.diagnostics['residual_rmse'] < .01
fig, axes = plt.subplots(1, 2, figsize=(7.1, 3.1))
axes[0].scatter(time, observed, color=grey, s=7, label='Simulated observations')
axes[0].plot(time, result.fitted_signal, color=blue, lw=1.1, label='Reconstruction')
axes[0].set(xlabel='Time (s)', ylabel='Normalized signal', title='Data and forward reconstruction')
axes[0].legend(fontsize=7)
axes[1].plot(grid, result.weights, color=teal, lw=1.2, label='Recovered bin amplitude')
axes[1].vlines(grid[locations], 0, truth[locations], color=grey, lw=1, label='Simulated components')
axes[1].set(xscale='log', xlabel='T₂ (s)', ylabel='Discrete bin amplitude', title='Nonnegative regularized inversion')
axes[1].legend(fontsize=7)
print(json.dumps(result.diagnostics, indent=2))'''),
 'vibrational-broadening':('IR and Raman: normal modes and spectral broadening','IR 与 Raman：简正模式和谱线展宽',
'''import numpy as np
axis = np.linspace(400, 4000, 3601)
frequencies = np.array([720., 1050., 1650., 2950., 3100.])
ir_activity = np.array([.2,.7,1.,.3,.5])
raman_activity = np.array([.5,.2,.1,1.,.6])
sigma = 12.
gaussians = np.exp(-.5*((axis[:,None]-frequencies[None,:])/sigma)**2)/(sigma*np.sqrt(2*np.pi))
ir = gaussians@ir_activity
raman = gaussians@raman_activity
assert np.isclose(np.trapezoid(ir, axis), ir_activity.sum(), rtol=.002)
fig, axes = plt.subplots(1, 2, figsize=(7.1, 3.1))
for ax, values, strengths, title, color in zip(axes,[ir,raman],[ir_activity,raman_activity],['Infrared','Raman'],[blue,teal]):
    ax.plot(axis, values, color=color, lw=1.1)
    ax.set(xlabel='Wavenumber (cm⁻¹)', ylabel='Activity density (a.u.)', title=title, xlim=(400,4000))
print('Simulated mode frequencies (cm^-1):', frequencies.tolist())
print('Gaussian sigma (cm^-1):', sigma)'''),
 'ms-isotopes':('Mass spectrometry: isotope envelopes and resolving power','质谱：同位素包络与分辨率',
'''import numpy as np
from math import comb
carbons = 10
abundance_13c = .0107
counts = np.arange(carbons+1)
probability = np.array([comb(carbons,int(k))*abundance_13c**k*(1-abundance_13c)**(carbons-k) for k in counts])
assert np.isclose(probability.sum(),1)
base_mz = 150.
isotope_mz = base_mz + counts*1.003354835
axis = np.linspace(149.5,154,4000)
fig, axes = plt.subplots(1, 2, figsize=(7.1, 3.1))
axes[0].vlines(isotope_mz, 0, probability, color=blue, lw=1.5)
axes[0].set(xlabel='m/z', ylabel='Probability', xlim=(149.5,154), title='Carbon-only isotope model · C₁₀')
for resolution,color in [(300,grey),(3000,teal)]:
    width=base_mz/resolution/2.35482
    spectrum=(np.exp(-.5*((axis[:,None]-isotope_mz)/width)**2)*probability).sum(axis=1)
    axes[1].plot(axis,spectrum,color=color,lw=1,label=f'R = {resolution}')
axes[1].set(xlabel='m/z',ylabel='Relative signal',xlim=(149.5,154),title='Illustrative resolving power')
axes[1].legend(fontsize=7)
print('M+1 / M ratio:', float(probability[1]/probability[0]))
print('Scope: carbon isotope contribution only; not an experimental MS/MS spectrum.')''')}


def build(name,en):
    a,z,experiment=EXPERIMENTS[name];cells=[]
    def md(text):cells.append({'cell_type':'markdown','metadata':{},'source':[text]})
    def code(text):cells.append({'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':[text]})
    md('# '+(a if en else z)+'\n\n'+('This is a physics teaching simulation with declared inputs. It does not use experimental measurements or claim a model benchmark. Change the parameters and rerun to inspect their effects.' if en else '这是明确给出参数的物理教学模拟，没有使用实验测量，也不作为模型基准。可修改参数并重新执行，观察结果变化。'))
    code('''import io, json, sys
from pathlib import Path
from IPython.display import display, SVG
root = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p/'openmolspec_bench').is_dir())
sys.path.insert(0, str(root/'src'))
import matplotlib.pyplot as plt
from openmolspec.plotting import figure_style
figure_style()
blue, teal, grey = '#397BA6', '#178F88', '#A8B3BF'
''')
    code(experiment)
    code('''for index, ax in enumerate(axes):
    ax.text(-.12,1.08,chr(97+index),transform=ax.transAxes,fontsize=9,weight='bold')
fig.tight_layout(w_pad=2)
image=io.StringIO()
fig.savefig(image,format='svg',metadata={'Date':None})
display(SVG(image.getvalue()))
plt.close(fig)''')
    md('[Theory](../theory/index.md) · [Inversion](../inversion/index.md) · [Tutorials](index.md)')
    for i,cell in enumerate(cells):cell['id']=hashlib.sha256(f'{name}:{en}:{i}'.encode()).hexdigest()[:12]
    return {'cells':cells,'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'},'language_info':{'name':'python'},
        'openmolspec_evidence_files':['scripts/build_theory_tutorials.py','src/openmolspec/plotting.py','src/openmolspec/inversion.py'],'openmolspec_simulation':True}}


if __name__=='__main__':
    for name in EXPERIMENTS:
        for en in (True,False):
            path=ROOT/'documentation/notebooks'/f'theory-{name}{"" if en else ".zh"}.ipynb'
            path.write_text(json.dumps(build(name,en),ensure_ascii=False,indent=2)+'\n')
    print('Eight bilingual simulation tutorial sources generated')
