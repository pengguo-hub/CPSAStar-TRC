"""Predeclared Reviewer-2 Comment-2 controlled representation protocol.

The formal experiment has two orthogonal comparison families:
1) Information-source isolation, with the SAME Gaussian kernel:
   gaussian (exact committed reservations), historical_gaussian, learned_gaussian.
2) Kernel/decay isolation, with the SAME exact reservation source:
   raw, gaussian, exponential, linear, uniform.

Everything outside the soft congestion representation is common across methods.
"""
from dataclasses import dataclass, asdict
import math

KERNEL_FAMILY = ("raw", "gaussian", "exponential", "linear", "uniform")
SOURCE_FAMILY = ("gaussian", "historical_gaussian", "learned_gaussian")
PRIMARY_REPRESENTATIONS = ("no_field", "raw", "gaussian", "exponential", "linear", "uniform",
                           "historical_gaussian", "learned_gaussian")
REPRESENTATIONS = PRIMARY_REPRESENTATIONS + ("time_aggregated", "time_shifted")
MAPS = {
    "A": dict(key="STANDARD", width=16, height=11, loads=[50, 70]),
    "B": dict(key="FRANSEN", width=20, height=20, loads=[250, 280]),
    "C": dict(key="RING", width=20, height=20, loads=[150, 200]),
}

@dataclass(frozen=True)
class Config:
    alpha: float = 1.0
    gamma: float = 5.0
    omega: float = 50.0
    L: int = 1
    T: int = 1
    sigma_l: float = 2.0
    sigma_t: float = 2.0
    delta: int = 1
    speed: float = 1.0
    max_wait: int = 2
    lookahead_radius: int = 1
    lookahead_slots: int = 2
    update_interval: int = 20
    retry_limit: int = 5
    timeout: float = 60.0
    neutral_radius: int = 1
    neutral_time_radius: int = 1
    bootstrap_replicates: int = 10000
    statistics_seed: int = 20261017
    test_seed_start: int = 42
    time_shift_fraction: float = 0.5
    reference_horizon: int = 256
    source_profile: str = "direct_R1_aligned_controlled_representation_fixed_turn0.5"

    def validate(self):
        for name, value in self.to_dict().items():
            if isinstance(value, (int, float)) and (isinstance(value, bool) or not math.isfinite(value)):
                raise ValueError(f"Non-finite or boolean numeric parameter: {name}")
        for name in ["L","T","delta","max_wait","lookahead_radius","lookahead_slots","update_interval",
                     "retry_limit","neutral_radius","neutral_time_radius","bootstrap_replicates",
                     "statistics_seed","test_seed_start","reference_horizon"]:
            if type(getattr(self,name)) is not int:
                raise ValueError(f"Integer required: {name}")
        if self.alpha <= 0 or self.omega < 0:
            raise ValueError("alpha must be positive and omega nonnegative")
        if (self.delta, self.speed, self.lookahead_radius, self.lookahead_slots) != (1, 1.0, 1, 2):
            raise ValueError("This controlled source profile requires delta=1, speed=1, look-ahead=(1,2).")
        if self.L < 0 or self.T < 0 or self.sigma_l <= 0 or self.sigma_t <= 0:
            raise ValueError("Invalid kernel support/width")
        if min(self.alpha,self.gamma) < 0 or self.neutral_radius < 0 or self.neutral_time_radius < 0:
            raise ValueError("Weights and neutral metric radii must be nonnegative")
        if self.update_interval < 1 or self.retry_limit < 0 or self.max_wait < 0:
            raise ValueError("Invalid batch/retry/wait setting")
        if self.timeout <= 0:
            raise ValueError("Timeout must be positive")
        if self.bootstrap_replicates < 100:
            raise ValueError("At least 100 bootstrap replicates required")
        if self.reference_horizon < 8:
            raise ValueError("reference_horizon is too short for a meaningful spatiotemporal representation")
        if not 0 < self.time_shift_fraction < 1:
            raise ValueError("Time shift must be a nonzero fraction of the finite support")
        return self

    def to_dict(self):
        return asdict(self)
