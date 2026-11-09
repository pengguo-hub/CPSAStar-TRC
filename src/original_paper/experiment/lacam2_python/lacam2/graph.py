"""
graph.py
对应 C++ 的 graph.hpp / graph.cpp

Vertex   : 地图中的一个可通行格子
Graph    : 整张地图，包含顶点列表、邻接关系
Config   : 所有智能体当前所处位置的列表（长度 = N）

设计要点（与 C++ 保持一致）：
  - V  : 仅含可通行顶点（无 None），按创建顺序编号，id = index in V
  - U  : 长度 = width * height 的列表，障碍格为 None，可通行格存 Vertex 对象
  - index : width * y + x，与地图坐标一一对应
  - neighbor : 上下左右四连通的可通行邻居
"""

from __future__ import annotations
import re
from typing import List, Optional


class Vertex:
    """对应 C++ struct Vertex"""
    __slots__ = ("id", "index", "neighbor")

    def __init__(self, vid: int, index: int):
        self.id: int = vid          # V 数组中的下标（密集编号）
        self.index: int = index     # U 数组中的下标 = width * y + x
        self.neighbor: List["Vertex"] = []

    def __repr__(self) -> str:
        return f"V(id={self.id},idx={self.index})"


# C++ 中 Config = std::vector<Vertex*>；Python 直接用 list[Vertex]
Config = List[Optional[Vertex]]


class Graph:
    """对应 C++ struct Graph"""

    def __init__(self, filename: Optional[str] = None):
        self.V: List[Vertex] = []          # 无 None，密集顶点列表
        self.U: List[Optional[Vertex]] = []  # 含 None，按坐标索引
        self.width: int = 0
        self.height: int = 0
        self.filename: str = filename or ""

        if filename:
            self._load(filename)

    # ------------------------------------------------------------------
    # 加载 .map 文件（MovingAI 格式）
    # ------------------------------------------------------------------
    def _load(self, filename: str) -> None:
        r_height = re.compile(r"height\s(\d+)")
        r_width  = re.compile(r"width\s(\d+)")

        with open(filename, "r") as f:
            lines = f.read().splitlines()

        # 1. 读取 height / width，找到 "map" 行
        map_start = 0
        for idx, line in enumerate(lines):
            # 兼容 CRLF
            line = line.rstrip("\r")
            m = r_height.match(line)
            if m:
                self.height = int(m.group(1))
            m = r_width.match(line)
            if m:
                self.width = int(m.group(1))
            if line.strip() == "map":
                map_start = idx + 1
                break

        # 2. 初始化 U（全部 None）
        self.U = [None] * (self.width * self.height)

        # 3. 创建顶点
        y = 0
        for line in lines[map_start:]:
            line = line.rstrip("\r")
            for x, ch in enumerate(line):
                if ch in ("T", "@"):
                    pass  # 障碍
                else:
                    index = self.width * y + x
                    v = Vertex(len(self.V), index)
                    self.V.append(v)
                    self.U[index] = v
            y += 1

        # 4. 建立邻接关系（4 连通）
        for row in range(self.height):
            for col in range(self.width):
                v = self.U[self.width * row + col]
                if v is None:
                    continue
                # 左
                if col > 0:
                    u = self.U[self.width * row + (col - 1)]
                    if u is not None:
                        v.neighbor.append(u)
                # 右
                if col < self.width - 1:
                    u = self.U[self.width * row + (col + 1)]
                    if u is not None:
                        v.neighbor.append(u)
                # 下（y+1，与 C++ 的 "up" 对应，C++ 坐标系 y 向下增大）
                if row < self.height - 1:
                    u = self.U[self.width * (row + 1) + col]
                    if u is not None:
                        v.neighbor.append(u)
                # 上（y-1）
                if row > 0:
                    u = self.U[self.width * (row - 1) + col]
                    if u is not None:
                        v.neighbor.append(u)

    def size(self) -> int:
        """返回可通行顶点数量"""
        return len(self.V)


# ------------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------------

def is_same_config(c1: Config, c2: Config) -> bool:
    """检查两个配置是否相同（对应 C++ is_same_config）"""
    for v1, v2 in zip(c1, c2):
        if v1.id != v2.id:
            return False
    return True


def config_hash(config: Config) -> int:
    """
    配置的哈希值（对应 C++ ConfigHasher::operator()）
    使用与 C++ 相同的 Boost hash_combine 风格公式：
      hash ^= v.id + 0x9e3779b9 + (hash << 6) + (hash >> 2)
    Python int 无溢出，用掩码模拟 32 位行为。
    """
    MASK = 0xFFFFFFFF
    h = len(config) & MASK
    for v in config:
        h = (h ^ (v.id + 0x9E3779B9 + ((h << 6) & MASK) + (h >> 2))) & MASK
    return h
