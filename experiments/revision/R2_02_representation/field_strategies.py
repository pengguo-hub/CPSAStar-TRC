"""Same path admission/update semantics; only occupancy -> soft field changes.

Gaussian delegates ALL numerical operations to the original updater.
Exponential: exp(-lambda_l*sqrt(dx^2+dy^2)-lambda_t*abs(ds))/Z.
Rates match discrete Gaussian E[r^2] and E[ds^2] on identical finite support.
"""
import math
from collections import defaultdict
import numpy as np
from vendor.CPS_A.Conflict_Field_Updater import ConflictFieldUpdater
from reference_fields import (DenseTimeLookup, gaussian_smooth_dense, require_historical, require_learned)

def _match_rate(distances, second_moments, target):
    d = np.asarray(distances, dtype=float)
    q = np.asarray(second_moments, dtype=float)
    if not np.any(q):
        return 0.0
    def moment(rate):
        w = np.exp(-rate * d)
        return float(w @ q / w.sum())
    if abs(target - moment(0.0)) < 1e-14:
        return 0.0
    lo, hi = 0.0, 1.0
    while moment(hi) > target:
        hi *= 2.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if moment(mid) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2

def matched_exponential(config):
    spatial = [(x, y) for x in range(-config.L, config.L + 1) for y in range(-config.L, config.L + 1)]
    r2 = np.array([x*x + y*y for x, y in spatial], float)
    gs = np.exp(-r2 / (2*config.sigma_l**2))
    ts = np.arange(-config.T, config.T + 1, dtype=float)
    gt = np.exp(-ts*ts / (2*config.sigma_t**2))
    target_l = float(gs @ r2 / gs.sum())
    target_t = float(gt @ (ts*ts) / gt.sum())
    rate_l = _match_rate(np.sqrt(r2), r2, target_l)
    rate_t = _match_rate(np.abs(ts), ts*ts, target_t)
    kernel = {(x, y, t): np.exp(-rate_l*math.hypot(x, y) - rate_t*abs(t))
              for x, y in spatial for t in range(-config.T, config.T + 1)}
    z = sum(kernel.values())
    actual_l = sum(w*(x*x+y*y) for (x,y,t),w in kernel.items())/z
    actual_t = sum(w*t*t for (x,y,t),w in kernel.items())/z
    return kernel, dict(lambda_l=rate_l, lambda_t=rate_t,
                        gaussian_spatial_second_moment=target_l,
                        exponential_spatial_second_moment=actual_l,
                        gaussian_temporal_second_moment=target_t,
                        exponential_temporal_second_moment=actual_t,
                        temporal_kernels_identical=config.T <= 1)

class GaussianField(ConflictFieldUpdater):
    """Exact upstream implementation: no numerical overrides."""
    pass

class RawField(ConflictFieldUpdater):
    def _incremental_smooth_path(self, updated_points):
        # Same raw snapshot as upstream NS; same publication points as Gaussian.
        self.smoothed_dict = self.path_conflict_dict.copy()

class NoField(RawField):
    def _incremental_smooth_path(self, updated_points):
        self.smoothed_dict = {}

class ExponentialField(ConflictFieldUpdater):
    def __init__(self, *args, config, **kwargs):
        super().__init__(*args, **kwargs)
        self.gaussian_kernel, self.calibration = matched_exponential(config)
        # Parent's historical attribute name is retained; its smoothing routine is unchanged.

class SpatialLookup:
    def __init__(self, spatial):
        self.spatial = spatial
    def get(self, key, default=0.0):
        return self.spatial.get(key[:2], default)

class ShiftedLookup:
    def __init__(self, field, low, high, offset):
        self.field, self.low, self.high, self.offset = field, low, high, offset
    def get(self, key, default=0.0):
        x, y, t = key
        if not self.low <= t <= self.high:
            return default
        source_t = self.low + ((t-self.low+self.offset) % (self.high-self.low+1))
        return self.field.get((x,y,source_t), default)

class TemporalAblationField(GaussianField):
    """Gaussian numerical state retained separately from its time-erased/reindexed view."""
    def __init__(self, *args, mode, shift_fraction=0.5, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode, self.shift_fraction = mode, shift_fraction
        self.view = SpatialLookup({})
        self.temporal_domain = None

    def batch_update_from_paths(self):
        result = super().batch_update_from_paths()
        keys = [k for k,v in self.path_conflict_dict.items() if v]
        if not keys:
            self.view = SpatialLookup({})
            return result
        # Complete time support including zero padding; exact for the current committed snapshot.
        low = min(k[2] for k in keys) - self.m_time
        high = max(k[2] for k in keys) + self.m_time
        H = high - low + 1
        self.temporal_domain = (low, high)
        if self.mode == "time_aggregated":
            spatial = defaultdict(float)
            for (x,y,t), value in sorted(self.smoothed_dict.items()):
                spatial[(x,y)] += value / H
            self.view = SpatialLookup(dict(spatial))
        else:
            offset = max(1, min(H-1, int(H*self.shift_fraction))) if H > 1 else 0
            self.view = ShiftedLookup(self.smoothed_dict, low, high, offset)
        return result

class TimeAggregatedField(TemporalAblationField):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, mode="time_aggregated", **kwargs)

class TimeShiftedField(TemporalAblationField):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, mode="time_shifted", **kwargs)


def matched_linear(config):
    """Separable compact linear decay; match each Gaussian discrete second moment."""
    spatial=[(x,y) for x in range(-config.L,config.L+1) for y in range(-config.L,config.L+1)]
    r2=np.array([x*x+y*y for x,y in spatial],float)
    ts=np.arange(-config.T,config.T+1,dtype=float)
    def slope(d,q,sigma):
        g=np.exp(-q/(2*sigma*sigma));target=float(g@q/g.sum())
        lo,hi=0.0,1.0
        for _ in range(100):
            mid=(lo+hi)/2;w=np.maximum(0,1-mid*d)
            if float(w@q/w.sum())>target:lo=mid
            else:hi=mid
        return (lo+hi)/2
    a=slope(np.sqrt(r2),r2,config.sigma_l);b=slope(np.abs(ts),ts*ts,config.sigma_t)
    kernel={(x,y,t):max(0,1-a*math.hypot(x,y))*max(0,1-b*abs(t)) for x,y in spatial for t in range(-config.T,config.T+1)}
    return kernel,dict(spatial_slope=a,temporal_slope=b)

class LinearField(ConflictFieldUpdater):
    def __init__(self,*args,config,**kwargs):
        super().__init__(*args,**kwargs)
        self.gaussian_kernel,self.calibration=matched_linear(config)

class UniformField(ConflictFieldUpdater):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.gaussian_kernel={k:1.0 for k in self.gaussian_kernel}

class ExternalGaussianField(ConflictFieldUpdater):
    """Static exogenous raw occupancy estimate followed by the SAME CPS-A Gaussian kernel.

    It intentionally does not consume current committed reservations into the soft field.  Hard
    collision reservations remain in the shared TicketManager and shared search code.
    """
    def __init__(self, *args, raw_dense, source_metadata=None, config=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.raw_external = np.asarray(raw_dense, dtype=np.float32)
        self.smoothed_external = gaussian_smooth_dense(self.raw_external, config)
        self.view = DenseTimeLookup(self.smoothed_external)
        self.source_metadata = dict(source_metadata or {})
        self.temporal_domain = (0, self.smoothed_external.shape[0]-1)

    def batch_update_from_paths(self):
        # Keep the planner's batch cadence identical but do not replace the exogenous representation
        # with current reservations. Pending paths are only a coordinator bookkeeping object here.
        self.pending_paths.clear()
        return self.view

    def finalize_batch_update(self):
        return None


def make_field(name, grid, tickets, config, context=None):
    kwargs = dict(delta=config.delta, k_space=config.L, m_time=config.T,
                  sigma_space=config.sigma_l, sigma_time=config.sigma_t)
    if name in ("historical_gaussian", "learned_gaussian"):
        if context is None or not context.get("reference_dir"):
            raise ValueError(f"{name} requires a reference_dir and trial context")
        if name == "historical_gaussian":
            raw, meta = require_historical(context["reference_dir"], context["map"], context["task_count"], config)
        else:
            raw, meta = require_learned(context["reference_dir"], context["map"], grid, context["tasks"], config)
        meta = dict(meta)
        meta.update(representation=name, soft_kernel="same_gaussian_as_exact_CPS_A")
        return ExternalGaussianField(grid, tickets, raw_dense=raw, source_metadata=meta, config=config, **kwargs)
    cls = {"gaussian": GaussianField, "raw": RawField, "no_field": NoField,
           "exponential": ExponentialField, "linear": LinearField, "uniform": UniformField,
           "time_aggregated": TimeAggregatedField, "time_shifted": TimeShiftedField}[name]
    if name in ("exponential", "linear"):
        kwargs["config"] = config
    if name == "time_shifted":
        kwargs["shift_fraction"] = config.time_shift_fraction
    return cls(grid, tickets, **kwargs)

def lookup(field):
    if isinstance(field, (TemporalAblationField, ExternalGaussianField)):
        return field.view
    return field.smoothed_dict

def kernel_diagnostics(config):
    ek, report = matched_exponential(config)
    gk = {(x,y,t): np.exp(-(x*x+y*y)/(2*config.sigma_l**2)-t*t/(2*config.sigma_t**2)) for x,y,t in ek}
    ez, gz = sum(ek.values()), sum(gk.values())
    report["max_normalized_kernel_difference"] = max(abs(ek[k]/ez-gk[k]/gz) for k in ek)
    report["kernel_l1_difference"] = sum(abs(ek[k]/ez-gk[k]/gz) for k in ek)
    report["matching"] = "same finite support, unit mass, discrete spatial and temporal second moments"
    report["normalization"] = "full rectangular support, including obstacles/out-of-map zero occupancy"
    lk,linear_report=matched_linear(config)
    kernels={"gaussian":gk,"exponential":ek,"linear":lk,"uniform":{k:1.0 for k in gk}}
    report["linear_calibration"]=linear_report
    report["kernels"]={}
    for name,kernel in kernels.items():
        z=sum(kernel.values());w={k:float(v/z) for k,v in kernel.items()}
        report["kernels"][name]=dict(spatial_second_moment=sum(v*(k[0]**2+k[1]**2) for k,v in w.items()),
            temporal_second_moment=sum(v*k[2]**2 for k,v in w.items()),l1_from_gaussian=sum(abs(w[k]-gk[k]/gz) for k in w),
            normalized_weights=[dict(dx=k[0],dy=k[1],dt=k[2],weight=v) for k,v in w.items()])
    report["uniform_caveat"]="same support and mass, NOT second-moment matched"
    return report
