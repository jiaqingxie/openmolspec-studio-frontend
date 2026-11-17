"""Nonnegative regularized inversion of time-domain NMR measurements.

Theory and attribution: https://aris-mav.github.io/NMRInversions.jl/stable/theory/
This is a Python numerical implementation; the Julia package is cited separately.
"""
from dataclasses import dataclass


def kernel(samples, grid, *, experiment='T2'):
    """Construct T1/T2 kernels (same time unit) or diffusion kernel (b*D unitless)."""
    import numpy as np
    x=np.asarray(samples,dtype=float);tau=np.asarray(grid,dtype=float)
    if x.ndim!=1 or tau.ndim!=1 or len(x)<3 or len(tau)<3:
        raise ValueError('samples and grid must be vectors with at least three entries')
    if not np.isfinite(x).all() or not np.isfinite(tau).all() or (x<0).any() or (tau<=0).any():
        raise ValueError('Require finite, nonnegative sampling coordinates and positive grid values')
    if not np.all(np.diff(x)>0) or not np.all(np.diff(tau)>0):
        raise ValueError('Sampling coordinates and grid must be strictly increasing')
    if experiment=='diffusion':return np.exp(-np.outer(x,tau))
    decay=np.exp(-x[:,None]/tau[None,:])
    if experiment=='T2':return decay
    if experiment=='T1_saturation':return 1-decay
    if experiment=='T1_inversion':return 1-2*decay
    raise ValueError('experiment must be T2, T1_saturation, T1_inversion or diffusion')


@dataclass
class InversionResult:
    grid: object
    weights: object
    fitted_signal: object
    residuals: object
    alpha: float
    experiment: str
    diagnostics: dict


def invert(samples, signal, grid, *, experiment='T2', alpha=0.01,
           penalty='curvature', noise_std=None):
    """Minimize ||W(Kf-g)||² + alpha*||Lf||² subject to f>=0.

    ``weights`` are nonnegative discrete bin amplitudes, not a density per unit T.
    Curvature acts on an equally spaced log grid. Baseline and phase correction
    are the caller's responsibility. Alpha is supplied explicitly.
    """
    import numpy as np
    from scipy.optimize import lsq_linear
    from scipy import sparse
    k=kernel(samples,grid,experiment=experiment);y=np.asarray(signal,dtype=float)
    if y.ndim!=1 or len(y)!=len(k) or not np.isfinite(y).all():
        raise ValueError('Signal must have one finite value per sampling coordinate')
    if not np.isfinite(alpha) or alpha<0:raise ValueError('alpha must be finite and nonnegative')
    if penalty not in ('identity','curvature'):raise ValueError('penalty must be identity or curvature')
    tau=np.asarray(grid,dtype=float)
    if penalty=='curvature':
        step=np.diff(np.log(tau))
        if not np.allclose(step,step[0],rtol=1e-4):raise ValueError('Curvature regularization requires an equally spaced log grid')
        l=sparse.diags([np.ones(len(tau)-2),-2*np.ones(len(tau)-2),np.ones(len(tau)-2)],[0,1,2],shape=(len(tau)-2,len(tau))).toarray()
    else:l=np.eye(len(tau))
    if noise_std is None:scale=np.ones(len(y))
    else:
        scale=np.broadcast_to(np.asarray(noise_std,dtype=float),y.shape)
        if not np.isfinite(scale).all() or (scale<=0).any():raise ValueError('noise_std must be finite and positive')
    design=np.vstack([k/scale[:,None],np.sqrt(alpha)*l]);target=np.r_[y/scale,np.zeros(len(l))]
    solved=lsq_linear(design,target,bounds=(0,np.inf),method='bvls',tol=1e-10,max_iter=500)
    if not solved.success:raise RuntimeError('Nonnegative inversion did not converge: '+solved.message)
    fitted=k@solved.x;residuals=y-fitted
    return InversionResult(tau,solved.x,fitted,residuals,float(alpha),experiment,
        {'solver':'scipy.optimize.lsq_linear / BVLS','converged':bool(solved.success),'iterations':solved.nit,
         'samples':len(y),'bins':len(tau),'penalty':penalty,'residual_rmse':float(np.sqrt(np.mean(residuals**2))),
         'penalty_norm':float(np.linalg.norm(l@solved.x)),'weighted_residual_norm':float(np.linalg.norm(residuals/scale)),
         'kernel_condition_number':float(np.linalg.cond(k)),'weight_semantics':'discrete bin amplitudes',
         'alpha_selection':'explicit caller value; no automatic GCV claim'})
