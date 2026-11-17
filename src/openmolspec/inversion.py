"""Nonnegative regularized inversion of time-domain NMR measurements.

Theory and attribution: https://aris-mav.github.io/NMRInversions.jl/stable/theory/
This is a Python numerical implementation; the Julia package is cited separately.
"""
from dataclasses import dataclass


def kernel(samples, grid, *, experiment='T2'):
    """Construct a relaxation or diffusion inversion matrix.

    Parameters
    ----------
    samples : array-like of shape (n_samples,)
        Strictly increasing, finite, nonnegative acquisition coordinates.
        Relaxation experiments use time; diffusion experiments use b-values.
    grid : array-like of shape (n_bins,)
        Strictly increasing positive relaxation times or diffusion constants.
        Relaxation times use the same unit as ``samples``; diffusion units
        are chosen so that ``samples * grid`` is dimensionless.
    experiment : {'T2', 'T1_saturation', 'T1_inversion', 'diffusion'}
        Select exponential decay, saturation recovery, inversion recovery,
        or diffusion attenuation. Defaults to ``'T2'``.

    Returns
    -------
    numpy.ndarray of shape (n_samples, n_bins)
        Matrix mapping discrete component amplitudes to the measured signal.

    Raises
    ------
    ValueError
        If coordinates are invalid, either vector has fewer than three values,
        or the experiment name is unsupported.
    """
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
    """Recovered nonnegative distribution and its fitted signal.

    Parameters
    ----------
    grid : numpy.ndarray
        Relaxation-time or diffusion-constant bins supplied to :func:`invert`.
    weights : numpy.ndarray
        Nonnegative discrete amplitudes, one per grid bin.
    fitted_signal : numpy.ndarray
        Signal reconstructed by multiplying the kernel by ``weights``.
    residuals : numpy.ndarray
        Observed signal minus the reconstructed signal.
    alpha : float
        Regularization strength used by the solver.
    experiment : str
        Kernel selected for the inversion.
    diagnostics : dict
        Solver convergence, iteration count, residual error, penalty norm,
        matrix condition number and coordinate counts.
    """
    grid: object
    weights: object
    fitted_signal: object
    residuals: object
    alpha: float
    experiment: str
    diagnostics: dict


def invert(samples, signal, grid, *, experiment='T2', alpha=0.01,
           penalty='curvature', noise_std=None):
    """Recover nonnegative amplitudes with Tikhonov regularization.

    Parameters
    ----------
    samples : array-like of shape (n_samples,)
        Acquisition coordinates accepted by :func:`kernel`.
    signal : array-like of shape (n_samples,)
        Finite observed signal, with baseline and phase corrections applied.
    grid : array-like of shape (n_bins,)
        Positive component coordinates. Curvature regularization requires an
        equally spaced logarithmic grid.
    experiment : str, default 'T2'
        Relaxation or diffusion kernel; see :func:`kernel`.
    alpha : float, default 0.01
        Nonnegative regularization strength.
    penalty : {'curvature', 'identity'}, default 'curvature'
        Second-difference smoothing on the log grid or amplitude regularization.
    noise_std : float or array-like, optional
        Positive standard deviation used to weight each residual. A scalar
        applies the same weight to all measurements.

    Returns
    -------
    InversionResult
        Discrete bin amplitudes, fitted signal, residuals and solver diagnostics.
        The objective is ``||W(Kf - signal)||² + alpha * ||Lf||²`` with ``f >= 0``.

    Raises
    ------
    ValueError
        If inputs, noise weights or regularization settings are invalid.
    RuntimeError
        If the bounded least-squares solver does not converge.

    Examples
    --------
    >>> import numpy as np
    >>> times = np.linspace(0, 1, 40)
    >>> bins = np.geomspace(0.01, 2, 80)
    >>> recovered = invert(times, np.exp(-times / 0.2), bins, alpha=0.01)
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
