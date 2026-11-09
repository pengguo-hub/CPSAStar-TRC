import numpy as np


class ConflictFieldUpdater:
    def __init__(self, grid, ticket_manager, delta=1):
        self.grid = grid
        self.ticket_manager = ticket_manager

        # delta: 时间槽大小（秒），用于将绝对时间戳 t_abs 离散到整数槽
        self.delta = delta

        #用于路径累积更新
        self.pending_paths = []  # [(path, times, agv_id), ...] 缓存待更新的路径
        self.path_conflict_dict = {}  # {(x,y,slot): agv_count} 路径对应的冲突
        self.last_path_conflict_dict = {}  # 上次批量更新的baseline
        self.path_updated_points = set()  # 本批路径冲突的变化点

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

                self.path_conflict_dict[key] = agv_count

        # 清空缓存，为下一批做准备
        self.pending_paths.clear()
        return self.path_conflict_dict

