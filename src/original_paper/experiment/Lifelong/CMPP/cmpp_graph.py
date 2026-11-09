"""
cmpp_graph.py
稀疏有向图（双向边），从网格中间隔采样顶点构建。

论文 Section VI.C 说明：
  "A sparse graph G=(V,E) is constructed from the original 4-connected grid G*=(V*,E*)
   by sampling vertices at fixed intervals. A surjective map f:V*→V assigns each grid
   cell to its nearest sparse vertex, while an injective map g:V→V* links each sparse
   vertex back to a representative grid cell."
"""


class CMPPGraph:
    """稀疏有向图（双向边）"""

    def __init__(self, vertices, edges, coords=None,
                 grid_to_vertex=None, vertex_to_grid=None):
        self.V = list(vertices)                   # 顶点列表 [(x,y),...]
        self.E = list(edges)                      # 有向边列表 [(u,v),...]（已去重）
        self.adj = {v: [] for v in self.V}
        for u, v in self.E:
            self.adj[u].append(v)

        # 坐标字典（用于启发式距离）
        self.coords = coords if coords else {v: (float(v[0]), float(v[1])) for v in self.V}

        # 论文中的两张映射
        # f : V* → V  每个原始格子 → 最近稀疏顶点
        self.grid_to_vertex = grid_to_vertex if grid_to_vertex else {}
        # g : V  → V* 每个稀疏顶点  → 代表性格子
        self.vertex_to_grid = vertex_to_grid if vertex_to_grid else {}

    # ------------------------------------------------------------------
    # 工厂方法：从网格构建稀疏图
    # ------------------------------------------------------------------
    @classmethod
    def from_grid(cls, width, height, obstacles, step=2):
        """
        从网格地图构建稀疏图。
        每隔 step 个格子采样一个顶点（仅当该格子不是障碍物）。
        对相邻（距离=step）的稀疏顶点添加双向有向边，
        并检查两点之间直线路径上所有格子均无障碍。

        Parameters
        ----------
        width, height : int   网格尺寸
        obstacles     : set   障碍物坐标集合 {(x,y),...}
        step          : int   采样步长（论文常用 2~4）
        """
        # ── 1. 采样稀疏顶点 ────────────────────────────────────────────
        vertices = []
        for x in range(0, width, step):
            for y in range(0, height, step):
                if (x, y) not in obstacles:
                    vertices.append((x, y))

        # 回退：步长过大导致无顶点
        if not vertices:
            step = 1
            for x in range(width):
                for y in range(height):
                    if (x, y) not in obstacles:
                        vertices.append((x, y))

        # ── 2. f : V* → V  （每个可通行格子 → 最近稀疏顶点，曼哈顿距离）──
        grid_to_vertex = {}
        for x in range(width):
            for y in range(height):
                if (x, y) in obstacles:
                    continue
                best, best_dist = None, float('inf')
                for vx, vy in vertices:
                    d = abs(x - vx) + abs(y - vy)
                    if d < best_dist:
                        best_dist = d
                        best = (vx, vy)
                grid_to_vertex[(x, y)] = best

        # ── 3. 构建稀疏图有向边（四连通，双向，去重）──────────────────
        vertex_set = set(vertices)
        edge_set = set()                         # 用 set 避免重复

        dirs = [(step, 0), (0, step)]            # 只扫描两个正方向，双向均加入
        for (vx, vy) in vertices:
            for dx, dy in dirs:
                nx, ny = vx + dx, vy + dy
                if (nx, ny) in vertex_set:
                    # 检查中间格子是否全部可通行（且在地图内）
                    if cls._is_clear_path(
                            (vx, vy), (nx, ny), obstacles, width, height):
                        edge_set.add(((vx, vy), (nx, ny)))
                        edge_set.add(((nx, ny), (vx, vy)))

        edges = list(edge_set)

        # ── 4. 坐标字典（启发式用）──────────────────────────────────────
        coords = {v: (float(v[0]), float(v[1])) for v in vertices}

        # ── 5. g : V → V*（稀疏顶点 → 代表性格子，即顶点本身）─────────
        vertex_to_grid = {v: v for v in vertices}

        return cls(vertices, edges, coords, grid_to_vertex, vertex_to_grid)

    # ------------------------------------------------------------------
    # 辅助：直线路径畅通检查
    # ------------------------------------------------------------------
    @staticmethod
    def _is_clear_path(v1, v2, obstacles, width, height):
        """检查 v1→v2 直线上的所有中间格子是否均无障碍（且在地图内）。"""
        x1, y1 = v1
        x2, y2 = v2
        dx = x2 - x1
        dy = y2 - y1
        steps = max(abs(dx), abs(dy))
        if steps == 0:
            return True
        for i in range(1, steps):
            ix = x1 + int(round(dx * i / steps))
            iy = y1 + int(round(dy * i / steps))
            if not (0 <= ix < width and 0 <= iy < height):
                return False
            if (ix, iy) in obstacles:
                return False
        return True

    # ------------------------------------------------------------------
    # 欧氏距离（低层规划启发式）
    # ------------------------------------------------------------------
    def distance(self, u, v):
        xu, yu = self.coords[u]
        xv, yv = self.coords[v]
        return ((xu - xv) ** 2 + (yu - yv) ** 2) ** 0.5
