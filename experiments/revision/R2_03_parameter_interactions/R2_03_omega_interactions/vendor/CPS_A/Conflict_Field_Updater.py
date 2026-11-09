import numpy as np


class ConflictFieldUpdater:
    def __init__(self, grid, ticket_manager, delta=1, k_space=1, m_time=1, sigma_space=2.0, sigma_time=2.0):
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
        """
        对 pending_paths 中所有缓存的路径进行批量更新
        每批更新后才重新计算平滑场

        Returns:
            smoothed_dict: 更新后的平滑冲突字典
        """
        # print(f"DEBUG ticket_manager的长度{len(self.ticket_manager.node_reservations)}")
        count=0
        self.path_updated_points.clear()
        for path, times, agv_id in self.pending_paths:
           count += len(path)
        # print(f"DEBUG 新增路径一共有{count}个点")
        # print(f"DEBUG last_path_conflict_dict 长度为{len(self.last_path_conflict_dict)}")
        # 遍历所有待更新的路径，提取冲突点
        for path, times, agv_id in self.pending_paths:
            for pos, t in zip(path, times):
                x, y = pos
                if not (0 <= x < self.grid.width and 0 <= y < self.grid.height):
                    continue

                slot = int(t // self.delta)
                key = (x, y, slot)

                # 从ticket_manager查询该时空点的AGV数量
                node_key = ((x, y), t)
                agv_count = len(self.ticket_manager.node_reservations.get(node_key, {}))

                old_count = self.last_path_conflict_dict.get(key, 0)
                self.path_conflict_dict[key] = agv_count

                # 标记有变化的点
                if agv_count != old_count:
                    self.path_updated_points.add(key)

        # # 检测已释放的点（在last中有，current中没有）
        # for old_key in self.last_path_conflict_dict:
        #     if old_key not in self.path_conflict_dict:
        #         self.path_updated_points.add(old_key)

        # 执行批量平滑
        if self.path_updated_points:
            self._incremental_smooth_path(self.path_updated_points)

        # 清空缓存，为下一批做准备
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
        points_to_smooth = set()

        # 扩展邻域（与原 _incremental_smooth() 逻辑相同）
        for (x, y, slot) in updated_points:
            for dx in range(-self.k_space, self.k_space + 1):
                for dy in range(-self.k_space, self.k_space + 1):
                    for ds in range(-self.m_time, self.m_time + 1):
                        points_to_smooth.add((x + dx, y + dy, slot + ds))

        # 对邻域点重新计算平滑值
        for (cx, cy, cslot) in points_to_smooth:
            total = 0.0
            wsum = 0.0

            for dx in range(-self.k_space, self.k_space + 1):
                for dy in range(-self.k_space, self.k_space + 1):
                    for ds in range(-self.m_time, self.m_time + 1):
                        key = (cx + dx, cy + dy, cslot + ds)
                        # 🔺 关键点：只从 path_conflict_dict 查询
                        count = self.path_conflict_dict.get(key, 0)

                        # w = np.exp(
                        #     -(dx * dx) / (2 * self.sigma_space ** 2)
                        #     - (dy * dy) / (2 * self.sigma_space ** 2)
                        #     - (ds * ds) / (2 * self.sigma_time ** 2)
                        # )
                        w=self.gaussian_kernel[(dx,dy,ds)]

                        total += count * w
                        wsum += w

            self.smoothed_dict[(cx, cy, cslot)] = total / wsum if wsum > 0 else 0.0
