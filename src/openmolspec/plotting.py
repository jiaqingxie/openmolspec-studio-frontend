"""Shared Arial typography for scientific figures and molecular drawings."""
import os
from pathlib import Path


def arial_path():
    from matplotlib import font_manager
    candidates=[os.environ.get('OPENMOLSPEC_ARIAL_FONT',''),
                str(Path(__file__).resolve().parents[2]/'.runtime/fonts/Arial.TTF')]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            parent=Path(candidate).parent
            for path in parent.glob('*.TTF'):font_manager.fontManager.addfont(path)
            return str(Path(candidate).resolve())
    try:return font_manager.findfont('Arial',fallback_to_default=False)
    except ValueError as error:
        raise RuntimeError('Arial is required for these figures. Install a licensed Arial font or set OPENMOLSPEC_ARIAL_FONT to its TTF path.') from error


def figure_style():
    import matplotlib.pyplot as plt
    arial_path()
    plt.rcParams.update({'font.family':'Arial','font.sans-serif':['Arial'],'font.size':9,
        'axes.labelsize':9,'axes.titlesize':10,'xtick.labelsize':8,'ytick.labelsize':8,
        'legend.fontsize':8,'axes.spines.top':False,'axes.spines.right':False,
        'axes.linewidth':.6,'legend.frameon':False,'svg.fonttype':'none',
        'pdf.fonttype':42,'mathtext.fontset':'custom','mathtext.rm':'Arial',
        'mathtext.it':'Arial:italic','mathtext.bf':'Arial:bold',
        'mathtext.cal':'Arial','mathtext.sf':'Arial','font.cursive':['Arial']})
