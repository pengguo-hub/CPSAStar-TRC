"""R2-03: one-shot CPS-A Gaussian spatiotemporal parameter sensitivity.

Protocol alignment:
- Same two task loads per map as the completed Reviewer-1 Gaussian sensitivity.
- Same Gaussian baseline L=T=1, sigma_l=sigma_t=2.
- Map A heuristic: Manhattan + omega * look-ahead congestion.
- Maps B/C heuristic: Manhattan only (g still contains gamma * current congestion).
- Each map/load/seed task list is generated once and reused across every parameter cell.
- No Astar_base background and no frozen-background insertion protocol.
"""
from dataclasses import dataclass, asdict
import math

MAPS = {
    "A": dict(key="STANDARD", width=16, height=11),
    "B": dict(key="FRANSEN", width=20, height=20),
    "C": dict(key="RING", width=20, height=20),
}

# Exact task loads recorded in result_R1_gaussian_sensitivity/config.json.
TASK_COUNTS = {
    "A": (50, 70),
    "B": (250, 280),
    "C": (150, 200),
}
LOOKAHEAD_BY_MAP = {"A": True, "B": False, "C": False}

R1_GAUSSIAN_BASELINE = dict(L=1, T=1, sigma_l=2.0, sigma_t=2.0)
R1_GAUSSIAN_SWEEPS = {
    "L": (0, 1, 2, 3),
    "T": (0, 1, 2, 3),
    "sigma_l": (0.5, 1.0, 2.0, 4.0),
    "sigma_t": (0.5, 1.0, 2.0, 4.0),
}

# gamma values are all from the manuscript's declared 0..10 (step 0.5) range.
GAMMA_INTERACTION_VALUES = (2.5, 5.0, 7.5)
SIGMA_INTERACTION_VALUES = R1_GAUSSIAN_SWEEPS["sigma_l"]
# K values already appear in the manuscript's NU-K ablation.
UPDATE_INTERVAL_INTERACTION_VALUES = (1, 10, 20, 30, 40)

MANUSCRIPT_TABLE3_DEFAULTS = dict(alpha=1.0, beta=0.5, gamma=2.0, omega=50.0)
MANUSCRIPT_SELECTED_ONE_SHOT_TEXT = dict(
    alpha=1.0, beta=1.0, gamma=5.0, omega=50.0,
    L=1, T=1, sigma_l=2.0, sigma_t=2.0, update_interval=20,
)
EXECUTABLE_SOURCE_BASELINE = dict(
    alpha=1.0, beta=0.5, gamma=5.0, omega=50.0,
    L=1, T=1, sigma_l=2.0, sigma_t=2.0, update_interval=20,
)

@dataclass(frozen=True)
class Config:
    alpha: float = 1.0
    beta: float = 0.5
    gamma: float = 5.0
    omega: float = 50.0
    L: int = 1
    T: int = 1
    sigma_l: float = 2.0
    sigma_t: float = 2.0
    delta: int = 1
    speed: float = 1.0
    max_wait: int = 2
    update_interval: int = 20
    retry_limit: int = 5
    bootstrap_replicates: int = 10000
    statistics_seed: int = 20261017
    seed_start: int = 10000
    source_profile: str = "R1-aligned one-shot CPS-A; full batch; no background"

    def validate(self):
        for name, value in self.to_dict().items():
            if isinstance(value, (int, float)) and (isinstance(value, bool) or not math.isfinite(value)):
                raise ValueError(f"Non-finite/bool numeric parameter: {name}")
        for name in ["L","T","delta","max_wait","update_interval","retry_limit","bootstrap_replicates","statistics_seed","seed_start"]:
            if type(getattr(self, name)) is not int:
                raise ValueError(f"Integer required: {name}")
        if self.alpha <= 0 or min(self.beta,self.gamma,self.omega) < 0:
            raise ValueError("Invalid weights")
        if (self.delta, self.speed) != (1, 1.0):
            raise ValueError("Protocol is locked to delta=1 and speed=1")
        if self.L < 0 or self.T < 0 or self.sigma_l <= 0 or self.sigma_t <= 0:
            raise ValueError("Invalid Gaussian support/width")
        if self.update_interval < 1 or self.retry_limit < 0 or self.max_wait < 0:
            raise ValueError("Invalid update/retry/wait setting")
        if self.bootstrap_replicates < 100:
            raise ValueError("At least 100 bootstrap replicates required")
        return self

    def to_dict(self):
        return asdict(self)
