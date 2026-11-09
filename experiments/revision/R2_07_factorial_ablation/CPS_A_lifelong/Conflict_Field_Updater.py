import numpy as np


class ConflictFieldUpdater:
    def __init__(self, grid, ticket_manager, delta=3, k_space=1, m_time=1, sigma_space=2.0, sigma_time=2.0, smoothing=True):
        self.smoothing = smoothing  # False is the raw SLOT-count ablation only.
        self.grid = grid
        self.ticket_manager = ticket_manager

        # delta: 时间槽大小（秒），用于将绝对时间戳 t_abs 离散到整数槽
        self.delta = delta
        # k_space: 空间平滑半径，局部高斯平滑时在 x, y 方向扩展的格点数
        self.k_space = k_space
        # m_time: 时间平滑半径，局部高斯平滑时在时间方向扩展的槽数
        self.m_time = m_time
        # sigma_space: 空间方向的高斯核标准差，用于计算空间维度的权重
        self.sigma_space = sigma_space
        # sigma_time: 时间方向的高斯核标准差，用于计算时间维度的权重
        self.sigma_time = sigma_time
        # 平滑后缓存：key=(x,y,slot), value=smoothed_cost
        self.smoothed_dict = {}

        # 🔺 新增：用于路径累积更新
        self.pending_paths = []  # [(path, times, agv_id), ...] 缓存待更新的路径
        self.path_conflict_dict = {}  # {(x,y,slot): agv_count} 路径对应的冲突
        self.last_path_conflict_dict = {}  # 上次批量更新的baseline
        self.path_updated_points = set()  # 本批路径冲突的变化点
        self._precompute_gaussian_kernel()


    def cleanup_expired_slots(self, current_time):
        current_slot = int(current_time // self.delta)
        # 只删严格小于 current_slot 的历史 slot
        expired_keys = [k for k in self.smoothed_dict if k[2] < current_slot]
        for k in expired_keys:
            del self.smoothed_dict[k]
        expired_keys2 = [k for k in self.path_conflict_dict if k[2] < current_slot]
        for k in expired_keys2:
            del self.path_conflict_dict[k]
            self.last_path_conflict_dict.pop(k, None)

    def _precompute_gaussian_kernel(self):
        """预计算所有相对位置的高斯权重"""
        self.gaussian_kernel = {}

        for dx in range(-self.k_space, self.k_space + 1):
            for dy in range(-self.k_space, self.k_space + 1):
                for ds in range(-self.m_time, self.m_time + 1):
                    weight = np.exp(
                        -(dx * dx) / (2 * self.sigma_space ** 2)
                        - (dy * dy) / (2 * self.sigma_space ** 2)
                        - (ds * ds) / (2 * self.sigma_time ** 2)
                    )
                    self.gaussian_kernel[(dx, dy, ds)] = weight

    def accumulate_path(self, path, times, agv_id):
        """
        将一条AGV路径加入待更新队列
        多个AGV规划后，统一调用 batch_update_from_paths()

        Args:
            path: 完整路径 [(x1,y1), (x2,y2), ...]
            times: 对应时间 [t1, t2, ...]
            agv_id: AGV标识符
        """
        self.pending_paths.append((path, times, agv_id))

    def batch_update_from_paths(self):
        self.path_updated_points.clear()

        for path, times, agv_id in self.pending_paths:
            for pos, t in zip(path, times):
                x, y = pos
                if not (0 <= x < self.grid.width and 0 <= y < self.grid.height):
                    continue

                slot = int(t // self.delta)
                key = (x, y, slot)

                # 关键改动：直接累加路径计数，不查 node_reservations
                old_count = self.last_path_conflict_dict.get(key, 0)
                self.path_conflict_dict[key] = self.path_conflict_dict.get(key, 0) + 1

                if self.path_conflict_dict[key] != old_count:
                    self.path_updated_points.add(key)

        if self.path_updated_points:
            self._incremental_smooth_path(self.path_updated_points)

        self.pending_paths.clear()
        return self.smoothed_dict

    def finalize_batch_update(self):
        """
        批量更新完成后调用，保存当前路径冲突为baseline供下一批对比使用
        """
        self.last_path_conflict_dict = self.path_conflict_dict.copy()

    def _incremental_smooth_path(self, updated_points):
        """
        对指定的更新点集合进行局部高斯平滑
        【关键】：只查询 path_conflict_dict，不查 conflict_dict

        Args:
            updated_points: 需要平滑的点集合 {(x,y,slot), ...}
        """
        if not self.smoothing:
            self.smoothed_dict = self.path_conflict_dict.copy()
            return
        points_to_smooth = set()

        # 扩展邻域（与原 _incremental_smooth() 逻辑相同）
        for (x, y, slot) in updated_points:
            for dx in range(-self.k_space, self.k_space + 1):
                for dy in range(-self.k_space, self.k_space + 1):
                    for ds in range(-self.m_time, self.m_time + 1):
                        points_to_smooth.add((x + dx, y + dy, slot + ds))

        # 对邻域点重新计算平滑值
        for (cx, cy, cslot) in points_to_smooth:
            if not (0 <= cx < self.grid.width and 0 <= cy < self.grid.height):
                continue
            if self.grid.grid[cy][cx] != 0:
                continue
                # 过滤过期slot
            if cslot < 0:
                continue
            total = 0.0
            wsum = 0.0

            for dx in range(-self.k_space, self.k_space + 1):
                for dy in range(-self.k_space, self.k_space + 1):
                    for ds in range(-self.m_time, self.m_time + 1):
                        key = (cx + dx, cy + dy, cslot + ds)
                        # 🔺 关键点：只从 path_conflict_dict 查询
                        count = self.path_conflict_dict.get(key, 0)

                        w=self.gaussian_kernel[(dx,dy,ds)]

                        total += count * w
                        wsum += w

            self.smoothed_dict[(cx, cy, cslot)] = total / wsum if wsum > 0 else 0.0
