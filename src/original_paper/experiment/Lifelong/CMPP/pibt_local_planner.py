"""
pibt_local_planner.py
PIBT（Priority Inheritance with Backtracking）局部规划器实现。

参考文献：
  Okumura et al., "Priority Inheritance with Backtracking for Iterative
  Multi-Agent Path Finding", Artificial Intelligence, vol.310, 2022.

论文 Section VI.C 说明：
  "Local collision avoidance is handled online with PIBT."
  每步为所有活跃 AGV 计算一步无冲突的网格移动。

算法核心（单步）：
  按优先级从高到低依次为每个 agent 选择下一步移动：
    1. 枚举候选动作（4邻域+等待），优先选择使曼哈顿距离减小的方向。
    2. 若目标格子已被更高优先级 agent 占用，尝试其他候选。
    3. 若所有候选都冲突，执行 backtracking（优先级继承）：
       让占用者为当前 agent 让路，重规划占用者。
    4. 若仍无法移动，原地等待。
"""

from collections import defaultdict


class PIBTLocalPlanner:
    """
    PIBT 单步规划器。

    Parameters
    ----------
    width, height : int    网格尺寸
    obstacles     : set    静态障碍物 {(x,y),...}
    """

    DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1)]

    def __init__(self, width, height, obstacles):
        self.width = width
        self.height = height
        self.obstacles = set(obstacles)

    def step(self, positions, goals):
        """
        为所有 agent 计算一步无冲突移动（PIBT）。

        Parameters
        ----------
        positions : dict {agv_id: (x, y)}
        goals     : dict {agv_id: (x, y)}

        Returns
        -------
        next_positions : dict {agv_id: (x, y)}
        """
        if not positions:
            return {}

        # ── 优先级：到目标距离越近优先级越高（同距离按 id 字典序）──────
        sorted_ids = sorted(
            positions.keys(),
            key=lambda a: (
                abs(positions[a][0] - goals[a][0]) +
                abs(positions[a][1] - goals[a][1]),
                a
            )
        )

        next_pos = {}          # {agv_id: (x,y)}  已确定的下一步位置
        reserved = {}          # {(x,y): agv_id}  已被预定的格子

        def _candidates(agv_id):
            """返回该 agent 所有合法候选格子（按与目标距离排序，等待排最后）。"""
            cur = positions[agv_id]
            goal = goals[agv_id]
            cx, cy = cur
            gx, gy = goal
            moves = []
            for dx, dy in self.DIRS:
                nx, ny = cx + dx, cy + dy
                if (0 <= nx < self.width and 0 <= ny < self.height
                        and (nx, ny) not in self.obstacles):
                    d = abs(nx - gx) + abs(ny - gy)
                    moves.append((d, (nx, ny)))
            moves.sort(key=lambda x: x[0])
            candidates = [m for _, m in moves]
            candidates.append(cur)   # 等待（排最后）
            return candidates

        def _pibt_assign(agv_id, depth=0):
            """
            递归 PIBT：为 agv_id 尝试分配下一步位置。
            返回 True 表示成功，False 表示失败（原地等待）。
            防止无限递归：depth > len(positions) 时返回 False。
            """
            if depth > len(positions):
                return False
            if agv_id in next_pos:
                return True

            for cand in _candidates(agv_id):
                # 检查是否被更高优先级 agent 预定
                if cand in reserved:
                    occupant = reserved[cand]
                    if occupant == agv_id:
                        # 自己预定的（等待格子重叠情况）
                        next_pos[agv_id] = cand
                        return True
                    # 尝试让 occupant 让路（优先级继承）
                    # 仅当 occupant 还未确定下一步时
                    if occupant not in next_pos:
                        # 暂时预定这个格子
                        old_reserved = reserved.get(cand)
                        reserved[cand] = agv_id
                        if _pibt_assign(occupant, depth + 1):
                            # occupant 已让路，自己占用
                            next_pos[agv_id] = cand
                            reserved[cand] = agv_id
                            return True
                        else:
                            # occupant 无法让路，恢复
                            if old_reserved is not None:
                                reserved[cand] = old_reserved
                            else:
                                reserved.pop(cand, None)
                    # occupant 已固定，不能让路，尝试下一个候选
                else:
                    # 格子空闲
                    reserved[cand] = agv_id
                    next_pos[agv_id] = cand
                    return True

            # 所有候选都失败，原地等待
            cur = positions[agv_id]
            # 若当前格也被占（罕见情况），放弃并返回
            if cur not in reserved:
                reserved[cur] = agv_id
            next_pos[agv_id] = cur
            return False

        # ── 按优先级依次分配 ───────────────────────────────────────────
        for agv_id in sorted_ids:
            if agv_id not in next_pos:
                _pibt_assign(agv_id)

        # ── 对未分配到的 agent（防御性处理）────────────────────────────
        for agv_id in positions:
            if agv_id not in next_pos:
                next_pos[agv_id] = positions[agv_id]

        return next_pos
