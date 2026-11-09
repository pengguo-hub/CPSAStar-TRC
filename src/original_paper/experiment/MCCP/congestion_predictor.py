import numpy as np
from collections import defaultdict
from typing import Dict, List, Tuple
from src.original_paper.experiment.MCCP.utils import gaussian_2d, estimate_convection_diffusion

class MonteCarloCongestionPredictor:
    def __init__(self, grid, num_particles: int = 500, sigma_smooth: float = 0.8):
        self.grid = grid
        self.num_particles = num_particles
        self.sigma = sigma_smooth
        self.density_field = {}
        self.T = None
        self.dt = 1.0

    def predict(self, tasks: List[Dict], T: int, dt: float = 1.0) -> Dict[Tuple[int, int, int], float]:
        self.T = T
        self.dt = dt
        density = defaultdict(float)

        for task in tasks:
            start = task['start']
            goal = task['goal']
            (vx, vy), kappa = estimate_convection_diffusion(start, goal, T * dt)

            for _ in range(self.num_particles):
                x, y = start  # 初始位置（任务起点保证不在障碍物上）

                positions = [(x, y)]
                for t in range(1, T + 1):
                    # 生成候选位移
                    dx = vx * dt + np.random.normal(0, np.sqrt(2 * kappa * dt))
                    dy = vy * dt + np.random.normal(0, np.sqrt(2 * kappa * dt))
                    nx = x + dx
                    ny = y + dy
                    # 边界裁剪
                    nx = np.clip(nx, 0, self.grid.width - 1)
                    ny = np.clip(ny, 0, self.grid.height - 1)
                    # 障碍物检查
                    if (int(round(nx)), int(round(ny))) not in self.grid.static_obstacles:
                        x, y = nx, ny
                    # 如果新位置是障碍物，则保持原位置不变（粒子被阻挡）
                    positions.append((x, y))

                for t, (px, py) in enumerate(positions):
                    ix_min = max(0, int(px - 3*self.sigma))
                    ix_max = min(self.grid.width, int(px + 3*self.sigma) + 1)
                    iy_min = max(0, int(py - 3*self.sigma))
                    iy_max = min(self.grid.height, int(py + 3*self.sigma) + 1)
                    for ix in range(ix_min, ix_max):
                        for iy in range(iy_min, iy_max):
                            w = gaussian_2d(ix, iy, px, py, self.sigma)
                            density[(t, ix, iy)] += w / self.num_particles

        self.density_field = dict(density)
        return self.density_field

    def get_density_at(self, t: int, x: int, y: int) -> float:
        return self.density_field.get((t, x, y), 0.0)