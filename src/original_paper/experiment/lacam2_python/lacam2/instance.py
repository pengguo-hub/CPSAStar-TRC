"""
instance.py
对应 C++ 的 instance.hpp / instance.cpp

Instance : 保存地图、智能体数量、起点列表、终点列表
Solution : List[Config]，即每个时间步所有智能体的位置序列

支持三种构建方式：
  1. from_indexes(map_file, starts_idx, goals_idx)  — 直接给顶点下标
  2. from_scen(scen_file, map_file, N, rng)          — 从 .scen 基准文件加载
  3. from_random(map_file, N, rng)                   — 随机生成
"""

from __future__ import annotations
import re
import random
from typing import List, Optional, Tuple
from .graph import Graph, Config, Vertex

# Solution = 时间步序列，每步是一个 Config（长度 N 的顶点列表）
Solution = List[Config]

# .scen 行格式：bucket  mapfile  w  h  x_s  y_s  x_g  y_g  optimal_cost
_R_INSTANCE = re.compile(
    r"\d+\t.+\.map\t\d+\t\d+\t(\d+)\t(\d+)\t(\d+)\t(\d+)\t.+"
)


class Instance:
    """对应 C++ struct Instance"""

    def __init__(self, G: Graph, starts: Config, goals: Config, N: int):
        self.G = G
        self.starts: Config = starts
        self.goals: Config = goals
        self.N: int = N

    # ------------------------------------------------------------------
    # 工厂方法 1：直接给顶点下标（对应 C++ 测试用构造函数）
    # ------------------------------------------------------------------
    @classmethod
    def from_indexes(
        cls,
        map_filename: str,
        start_indexes: List[int],
        goal_indexes: List[int],
    ) -> "Instance":
        G = Graph(map_filename)
        N = len(start_indexes)
        starts = [G.U[k] for k in start_indexes]
        goals  = [G.U[k] for k in goal_indexes]
        return cls(G, starts, goals, N)

    # ------------------------------------------------------------------
    # 工厂方法 2：从 .scen 文件加载（对应 C++ MAPF benchmark 构造函数）
    # ------------------------------------------------------------------
    @classmethod
    def from_scen(
        cls,
        scen_filename: str,
        map_filename: str,
        N: int,
        rng: Optional[random.Random] = None,
    ) -> "Instance":
        G = Graph(map_filename)
        starts: Config = []
        goals: Config  = []

        try:
            with open(scen_filename, "r") as f:
                lines = f.read().splitlines()
        except FileNotFoundError:
            # 找不到场景文件时随机生成，并写回文件（与 C++ 行为一致）
            print(f"{scen_filename} is not found, generate instance")
            ins = cls._random_agents(G, N, rng)
            cls._save_scen(ins, scen_filename, map_filename)
            return ins

        for line in lines:
            line = line.rstrip("\r")
            m = _R_INSTANCE.match(line)
            if not m:
                continue
            x_s, y_s, x_g, y_g = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            if not (0 <= x_s < G.width and 0 <= x_g < G.width):
                continue
            if not (0 <= y_s < G.height and 0 <= y_g < G.height):
                continue
            s = G.U[G.width * y_s + x_s]
            g = G.U[G.width * y_g + x_g]
            if s is None or g is None:
                continue
            starts.append(s)
            goals.append(g)
            if len(starts) == N:
                break

        return cls(G, starts, goals, N)

    # ------------------------------------------------------------------
    # 工厂方法 3：随机生成（对应 C++ random 构造函数）
    # ------------------------------------------------------------------
    @classmethod
    def from_random(
        cls,
        map_filename: str,
        N: int,
        rng: Optional[random.Random] = None,
    ) -> "Instance":
        G = Graph(map_filename)
        return cls._random_agents(G, N, rng)

    # ------------------------------------------------------------------
    # 内部：随机分配起点/终点
    # ------------------------------------------------------------------
    @classmethod
    def _random_agents(
        cls, G: Graph, N: int, rng: Optional[random.Random]
    ) -> "Instance":
        if rng is None:
            rng = random.Random(0)
        V_size = G.size()
        s_indexes = list(range(V_size))
        rng.shuffle(s_indexes)
        starts = [G.V[s_indexes[i]] for i in range(N)]

        g_indexes = list(range(V_size))
        rng.shuffle(g_indexes)
        goals = [G.V[g_indexes[j]] for j in range(N)]

        return cls(G, starts, goals, N)

    # ------------------------------------------------------------------
    # 内部：写回 .scen 文件（与 C++ 行为一致）
    # ------------------------------------------------------------------
    @staticmethod
    def _save_scen(ins: "Instance", scen_filename: str, map_filename: str) -> None:
        G = ins.G
        with open(scen_filename, "w") as f:
            f.write("version 1\n")
            for i in range(ins.N):
                sx = ins.starts[i].index % G.width
                sy = ins.starts[i].index // G.width
                gx = ins.goals[i].index % G.width
                gy = ins.goals[i].index // G.width
                f.write(
                    f"{i}\t{map_filename}\t{G.width}\t{G.height}"
                    f"\t{sx}\t{sy}\t{gx}\t{gy}\t0\n"
                )

    # ------------------------------------------------------------------
    # 合法性检查
    # ------------------------------------------------------------------
    def is_valid(self, verbose: int = 0) -> bool:
        if self.N != len(self.starts) or self.N != len(self.goals):
            if verbose >= 1:
                print("invalid N, check instance")
            return False
        return True
