import numpy as np
from typing import Tuple

def euclidean_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    return np.hypot(p1[0] - p2[0], p1[1] - p2[1])

def manhattan_distance(p1: Tuple[int, int], p2: Tuple[int, int]) -> int:
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])

def gaussian_2d(x: float, y: float, mx: float, my: float, sigma: float) -> float:
    return np.exp(-((x - mx)**2 + (y - my)**2) / (2 * sigma**2))

def estimate_convection_diffusion(start: Tuple[int, int], goal: Tuple[int, int], T: float, max_speed: float = 1.0):
    dx = goal[0] - start[0]
    dy = goal[1] - start[1]
    if T == 0:
        return (0.0, 0.0), 0.01
    vx = dx / T
    vy = dy / T
    speed = np.hypot(vx, vy)
    if speed > max_speed:
        scale = max_speed / speed
        vx *= scale
        vy *= scale
    kappa = 0.005  # 论文E1配置
    return (vx, vy), kappa