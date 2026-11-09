"""Conditional learned occupancy predictor used only as a congestion representation.

This predictor is deliberately outside the planner.  It maps the CURRENT task-demand
pattern (start, pickup, destination maps + time) to a predicted RAW occupancy probability.
The predicted raw field is then smoothed with the exact same Gaussian kernel used by CPS-A.
Thus, in the source-family comparison, planner/search/kernel are fixed and only the source of
congestion information changes.

Training labels are raw spatiotemporal occupancies from disjoint calibration episodes.  The
calibration planner is collision-only (no soft congestion field), so the learned baseline is
not trained to imitate the proposed Gaussian CPS-A method.
"""
from __future__ import annotations
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


class FourierConvLayer(nn.Module):
    """Small FNO-style block, adapted from experiment.zip/MCCP/neural_predictor.py."""
    def __init__(self, channels: int, modes1: int, modes2: int):
        super().__init__()
        self.channels = channels
        self.modes1 = modes1
        self.modes2 = modes2
        scale = 1 / (channels * channels)
        self.weights = nn.Parameter(scale * torch.randn(channels, channels, modes1, modes2, dtype=torch.cfloat))
        self.conv = nn.Conv2d(channels, channels, kernel_size=3, padding=1)

    def forward(self, x):
        b, c, h, w = x.shape
        xf = torch.fft.rfft2(x)
        m1 = min(self.modes1, h)
        m2 = min(self.modes2, w // 2 + 1)
        out_f = torch.zeros(b, c, h, w // 2 + 1, dtype=torch.cfloat, device=x.device)
        out_f[:, :, :m1, :m2] = torch.einsum(
            "bikl,oikl->bokl", xf[:, :, :m1, :m2], self.weights[:, :, :m1, :m2]
        )
        fourier = torch.fft.irfft2(out_f, s=(h, w))
        return F.gelu(fourier + self.conv(x))


class LearnedOccupancyPredictor(nn.Module):
    """Predict P(cell occupied at t) from task-demand maps and normalized time."""
    def __init__(self, height: int, width: int, hidden: int = 24):
        super().__init__()
        self.height = int(height)
        self.width = int(width)
        self.hidden = int(hidden)
        self.lift = nn.Conv2d(7, hidden, kernel_size=1)
        modes1 = min(8, height)
        modes2 = min(8, width // 2 + 1)
        self.blocks = nn.ModuleList([FourierConvLayer(hidden, modes1, modes2) for _ in range(4)])
        self.proj1 = nn.Conv2d(hidden, hidden, 1)
        self.proj2 = nn.Conv2d(hidden, 1, 1)

    def forward(self, demand, t_norm, free_mask=None):
        """
        demand: (B,3,H,W): start, pickup, destination count maps.
        t_norm: (B,) in [0,1].
        free_mask: optional (1,1,H,W), 1 traversable, 0 obstacle.
        """
        b, _, h, w = demand.shape
        yy, xx = torch.meshgrid(
            torch.linspace(0, 1, h, device=demand.device),
            torch.linspace(0, 1, w, device=demand.device), indexing="ij"
        )
        xx = xx.expand(b, 1, h, w)
        yy = yy.expand(b, 1, h, w)
        tt = t_norm.view(b, 1, 1, 1).expand(b, 1, h, w)
        obstacle = torch.zeros_like(tt) if free_mask is None else (1.0 - free_mask).expand(b, -1, -1, -1)
        x = torch.cat([demand, xx, yy, tt, obstacle], dim=1)
        x = self.lift(x)
        for block in self.blocks:
            x = block(x)
        x = F.gelu(self.proj1(x))
        out = torch.sigmoid(self.proj2(x))
        if free_mask is not None:
            out = out * free_mask
        return out


def task_demand_array(tasks, height, width):
    out = np.zeros((3, height, width), dtype=np.float32)
    for task in tasks:
        for c, key in enumerate(("agv_position", "source", "destination")):
            x, y = task[key]
            if 0 <= x < width and 0 <= y < height:
                out[c, y, x] += 1.0
    return out


def predict_dense(model, tasks, free_mask_np, horizon, device="cpu", batch_size=64):
    model = model.to(device).eval()
    demand_np = task_demand_array(tasks, model.height, model.width)
    demand = torch.from_numpy(demand_np).unsqueeze(0).to(device)
    mask = torch.from_numpy(free_mask_np.astype(np.float32)).view(1,1,model.height,model.width).to(device)
    chunks = []
    with torch.no_grad():
        for start in range(0, horizon + 1, batch_size):
            ts = np.arange(start, min(horizon + 1, start + batch_size), dtype=np.float32)
            tn = torch.from_numpy(ts / max(1, horizon)).to(device)
            d = demand.expand(len(ts), -1, -1, -1)
            pred = model(d, tn, mask).squeeze(1).cpu().numpy().astype(np.float32)
            chunks.append(pred)
    return np.concatenate(chunks, axis=0)
