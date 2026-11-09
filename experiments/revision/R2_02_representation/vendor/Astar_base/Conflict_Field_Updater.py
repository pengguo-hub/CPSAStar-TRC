import numpy as np
from scipy.ndimage import gaussian_filter


class ConflictFieldUpdater:
    def __init__(self, grid, ticket_manager, delta=1, k_space=1, m_time=1, sigma_space=1.0, sigma_time=1.0):
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

        # 稀疏存储
        # key=(x,y,slot), value=conflict_count
        self.conflict_dict = {}
        # 平滑后缓存：同样 key, value=smoothed_cost
        self.smoothed_dict = {}

    def update_from_tickets(self, reservations=None):
        """根据传入的时空券预约信息更新冲突场"""
        # 如果未传入reservations，则使用ticket_manager的默认数据
        if reservations is None:
            reservations = self.ticket_manager.node_reservations

        if not reservations:
            print("警告：没有找到任何时空券预约")
            return {}

        self.conflict_dict.clear()
        self.smoothed_dict.clear()

        # 根据预约信息更新冲突场
        for (node, t), agv_dict in reservations.items():
            x, y = node
            if not (0 <= x < self.grid.width and 0 <= y < self.grid.height) :
                continue
            # 冲突值 = 该时空位置的AGV数量
            slot= int(t//self.delta)
            self.conflict_dict[(x,y,slot)] = len(agv_dict)
            # self.smoothed_dict = self.conflict_dict.copy()

        # 先收集所有要计算的中心点 keys_to_smooth
        keys_to_smooth = set()
        for (x, y, slot) in self.conflict_dict:
            for dx in range(-self.k_space, self.k_space + 1):
                for dy in range(-self.k_space, self.k_space + 1):
                    for ds in range(-self.m_time, self.m_time + 1):
                        keys_to_smooth.add((x + dx, y + dy, slot + ds))

        # 然后对这些中心点做局部高斯加权平均
        for (cx, cy, cslot) in keys_to_smooth:
            total = 0.0
            wsum = 0.0
            for dx in range(-self.k_space, self.k_space + 1):
                for dy in range(-self.k_space, self.k_space + 1):
                    for ds in range(-self.m_time, self.m_time + 1):
                        key = (cx + dx, cy + dy, cslot + ds)
                        count = self.conflict_dict.get(key, 0)
                        #局部高斯平滑
                        w = np.exp(
                            -(dx * dx) / (2 * self.sigma_space ** 2)
                            - (dy * dy) / (2 * self.sigma_space ** 2)
                            - (ds * ds) / (2 * self.sigma_time ** 2)
                        )
                        total += count * w
                        wsum += w
            self.smoothed_dict[(cx, cy, cslot)] = total / wsum if wsum>0 else 0.0

        return self.smoothed_dict


    def update_dynamic_conflicts(self, current_time, lookahead=50):
        """动态更新冲突场（只关注当前时间及未来一段时间）"""
        # 计算时间范围
        start_time = max(0, current_time - 5)  # 包含少量历史用于平滑
        end_time = current_time + lookahead

        time_range = end_time - start_time
        if time_range <= 0:
            return np.zeros((self.grid.width, self.grid.height, 10))

        # 重置冲突场
        self.max_time = time_range
        self.conflict_field = np.zeros((self.grid.width, self.grid.height, time_range))

        # 只处理相关时间段的预约
        reservations = self.ticket_manager.node_reservations
        for (node, t), agv_dict in reservations.items():
            if start_time <= t < end_time:
                x, y = node
                time_index = t - start_time
                if 0 <= x < self.grid.width and 0 <= y < self.grid.height and time_index < time_range:
                    self.conflict_field[x, y, time_index] += len(agv_dict)

        # 平滑处理
        self.conflict_field = self._smooth_field()
        return self.conflict_field

    def get_conflict_probability(self, x, y, t):
        """获取指定时空位置的冲突概率"""
        if self.conflict_field is None:
            return 0.0

        if t >= self.max_time:
            return 0.0

        if not (0 <= x < self.grid.width and 0 <= y < self.grid.height):
            return 0.0

        raw_value = self.conflict_field[x, y, t]
        # 归一化到概率值（0-1之间）
        return min(1.0, raw_value / 10.0)  # 假设最多10个AGV冲突

    def get_high_conflict_zones(self, threshold=0.3):
        """获取高冲突区域（冲突概率超过阈值）"""
        if self.conflict_field is None:
            return []

        conflicts = []
        for x in range(self.grid.width):
            for y in range(self.grid.height):
                for t in range(self.max_time):
                    prob = self.get_conflict_probability(x, y, t)
                    if prob > threshold:
                        conflicts.append({
                            'position': (x, y),
                            'time': t,
                            'probability': prob,
                            'raw_value': self.conflict_field[x, y, t]
                        })

        # 按冲突概率排序
        conflicts.sort(key=lambda x: x['probability'], reverse=True)
        return conflicts

    def _smooth_field(self, sigma=1):
        """高斯平滑处理"""
        if self.conflict_field is not None:
            return gaussian_filter(self.conflict_field, sigma=[sigma,sigma,0])
        return None


    def visualize_conflict_snapshot(self, time_slice):
        """可视化指定时间片的冲突场"""
        if self.conflict_field is None or time_slice >= self.max_time:
            print(f"无法可视化时间片 {time_slice}，冲突场未初始化或时间超出范围")
            return None

        snapshot = self.conflict_field[:, :, time_slice]
        return snapshot

    def get_temporal_conflict_summary(self):
        """获取时间维度的冲突摘要"""
        if self.conflict_field is None:
            return {}

        summary = {}
        for t in range(self.max_time):
            time_slice = self.conflict_field[:, :, t]
            total_conflict = np.sum(time_slice)
            max_conflict = np.max(time_slice) if time_slice.size > 0 else 0
            conflict_cells = np.sum(time_slice > 0)

            summary[t] = {
                'total_conflict': total_conflict,
                'max_conflict': max_conflict,
                'conflict_cells': conflict_cells
            }

        return summary