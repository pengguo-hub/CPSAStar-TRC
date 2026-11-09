import numpy as np
from typing import Dict, Tuple

class DynamicCongestionFieldUpdater:
    def __init__(self, grid, predictor, blend_factor: float = 0.7):
        self.grid = grid
        self.predictor = predictor
        self.blend = blend_factor
        self.weights = {
            'robot_density': 0.5,
            'failure': 0.2,
            'human': 0.2,
            'obstacle': 0.1
        }

    def update(self, observed_data: Dict[str, np.ndarray], current_time: int) -> Dict[Tuple[int, int, int], float]:
        obs_field = np.zeros((self.grid.height, self.grid.width))
        for key, weight in self.weights.items():
            if key in observed_data:
                obs_field += weight * observed_data[key]

        pred_field = np.zeros((self.grid.height, self.grid.width))
        for x in range(self.grid.width):
            for y in range(self.grid.height):
                pred_field[y, x] = self.predictor.get_density_at(current_time, x, y)

        updated = self.blend * pred_field + (1 - self.blend) * obs_field

        field = {}
        for y in range(self.grid.height):
            for x in range(self.grid.width):
                field[(current_time, x, y)] = updated[y, x]
        return field