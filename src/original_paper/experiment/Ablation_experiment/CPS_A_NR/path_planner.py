import numpy as np
from datetime import datetime
from .Conflict_Field_Updater import ConflictFieldUpdater
from .Segment_Planner import SegmentPlanner
from .Ticket_Manager import TicketManager


class GridMap:
    def __init__(self, width=100, height=100,cell_size=1):
        self.width = width
        self.height = height
        self.cell_size = cell_size
        self.grid = np.zeros((height, width), dtype=int) #0表示空地，1表示障碍物
        self.static_obstacles = set()  # 静态障碍物坐标集合
        self.dynamic_obstacles = set()  # 动态障碍物集合
        self.agv_positions = {}  # AGV当前位置字典，格式：{agv_id: (x,y)}

    def add_static_obstacle(self, x, y):
        """添加静态障碍物"""
        if 0 <= x < self.width and 0 <= y < self.height:
            self.grid[y][x] = 1
            self.static_obstacles.add((x, y))

    def remove_static_obstacle(self, x, y):
        """移除静态障碍物"""
        if (x, y) in self.static_obstacles:
            self.static_obstacles.remove((x, y))
            self.grid[y][x] = 0

    def add_dynamic_obstacle(self, x, y):
        """添加动态障碍物"""
        if 0 <= x < self.width and 0 <= y < self.height:
            self.dynamic_obstacles.add((x, y))

    def remove_dynamic_obstacle(self, x, y):
        """移除动态障碍物"""
        self.dynamic_obstacles.discard((x, y))

    def region_coordinate(self,x,y,value):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.grid[y][x] = value
            self.static_obstacles.add((x,y))

    def get_grid_matrix(self):
        """返回网格矩阵的深拷贝（NumPy数组）"""
        return self.grid.copy()  # 深拷贝NumPy数组

class IntegratedAGVPlanner:
    def __init__(self, grid):
        self.grid = grid
        # 状态记录
        self.agv_tasks = {}  # {agv_id: {path, tickets, ...}}
        self.conflict_field = None  # 动态冲突场
        # 核心组件
        self.ticket_manager = TicketManager()
        self.conflict_updater = ConflictFieldUpdater(self.grid,self.ticket_manager)
        self.segment_planner = SegmentPlanner(self.grid, self.ticket_manager,self.conflict_updater)


    def batch_plan(self,parsed_tasks):
        time_now = 0
        for agv_id, info in parsed_tasks.items():
            info["waypoints"] = [tuple(pt) for pt in info["waypoints"]]  # 把原来的list换成tuple[(x1,y1),...,(xn,yn)]

        # Step 2: 按优先级排序
        ## 初始化任务状态
        self.agv_tasks = {
            agv_id: {
                'start': info['waypoints'][0],
                'end': info['waypoints'][-1],
                'constraints': info['constraints'],
                'waypoints': [tuple(info['agv_position']), tuple(info['source']), tuple(info['destination'])],
                'path': [],
                'position': info['waypoints'][0]
            }
            for agv_id, info in parsed_tasks.items()
        }

        sorted_agvs = self._sort_agvs_by_priority_and_deadline()

        # >>>>>>>>>> 新增：注册所有 AGV 起点占用 <<<<<<<<<<
        for agv_id, info in self.agv_tasks.items():
            reservations = []
            start_pos = info['waypoints'][0]
            priority = sorted_agvs[agv_id]
            # 记录预占的时间点
            reserved_times = set()
            for i in range(self.segment_planner.MAX_WAIT + 1):
                t = round(time_now + i * self.conflict_updater.delta, 1)
                reservations.append((start_pos, t))
                reserved_times.add(t)
            success = self.ticket_manager.reserve(agv_id, reservations, priority)
            if success:
                self.agv_tasks[agv_id]['reserved_start_times'] = reserved_times
            # else:
            #     print(f" {agv_id} 在起点{start_pos}预约失败")

        # Step 3: 分段规划
        paths = {}
        planned_count = 0
        UPDATE_COUNT = 20
        for agv_id in sorted_agvs:
            weighted_priority = sorted_agvs[agv_id]

            path, times = self.segment_planner.plan_agv(
                agv_id=agv_id,
                waypoints=self.agv_tasks[agv_id]['waypoints'],
                priority=weighted_priority,
                enable_turn_penalty=True,
                current_time=round(time_now, 1)
            )

            if path:
                paths[agv_id] = path
                self.agv_tasks[agv_id]['path'] = path
                self.agv_tasks[agv_id]['times'] = times
                self.agv_tasks[agv_id]['status'] = 'planned'
                self._release_unused_start_reservations(agv_id)
                # 🔺 新增：累积路径到缓存
                self.conflict_updater.accumulate_path(path, times, agv_id)
                planned_count += 1

            if planned_count % UPDATE_COUNT == 0:
                # print(f"DEBUG 更新冲突场，上一轮smoothed_dict有{len(self.conflict_updater.smoothed_dict)}个")
                # 批量更新冲突场
                self.conflict_updater.batch_update_from_paths()
                # 保存baseline
                self.conflict_updater.finalize_batch_update()
                # 传递给规划器
                self.segment_planner.congestion_dict = self.conflict_updater.smoothed_dict

        # 🔺 最后的剩余AGV也要更新（不足UPDATE_COUNT个）
        if self.conflict_updater.pending_paths:
            self.conflict_updater.batch_update_from_paths()
            self.conflict_updater.finalize_batch_update()
            self.segment_planner.congestion_dict = self.conflict_updater.smoothed_dict

        return paths

    def _sort_agvs_by_priority_and_deadline(self):
        """
        同时考虑 priority（emergency>high>normal）与 time_limit（HH:MM 格式或 None）排序，
        返回排序后的 AGV ID 列表。
        """
        now = datetime.now()
        # 优先级映射
        priority_map = {'emergency': 3, 'high': 2, 'normal': 1}

        scores = {}
        # 先找出所有非 None 的剩余分钟，用于归一化
        all_time_left = []
        for agv_id, task in self.agv_tasks.items():
            time_limit = task['constraints'].get('time_limit')
            if time_limit:
                # 解析为 datetime（只取今日 HH:MM）
                deadline = datetime.strptime(time_limit, "%H:%M").replace(
                    year=now.year, month=now.month, day=now.day
                )
                time_left =  (deadline - now).total_seconds() / 60
            else:
                time_left = None
            task['priority_val'] = priority_map.get(task['constraints'].get('priority'), 1)
            task['timeleft_val'] = time_left
            if time_left is not None:
                all_time_left.append(time_left)

        max_time_left = max(all_time_left) if all_time_left else 1

        # 计算综合得分：优先级归一化 + （1 - 剩余时间归一化）
        for agv_id, task in self.agv_tasks.items():
            priority_norm = task['priority_val'] / 3.0
            time_left_raw = task['timeleft_val']
            if time_left_raw is None:
                time_norm = 0.0
            else:
                if time_left_raw < 0:
                    urgency_factor = 2
                    time_norm = 1 + (-time_left_raw)/max_time_left * urgency_factor
                else:
                    time_norm = 1 - (task['timeleft_val'] / max_time_left)
            # 权重各 0.5，可按需调整
            scores[agv_id] = 0.5 * priority_norm + 0.5 * time_norm

        # 按分数降序返回 AGV ID 列表
        return { agv_id: scores[agv_id] for agv_id in sorted(scores.keys(), key=lambda x: scores[x], reverse=True)}

    def _release_unused_start_reservations(self, agv_id):
        """基于实际路径时间，释放未使用的起点预约"""
        task = self.agv_tasks[agv_id]

        if 'reserved_start_times' not in task:
            # print(f"{agv_id} 无 reserved_start_times")
            return

        if 'times' not in task or 'path' not in task:
            print(f"{agv_id} 无 path 或 times，无法判断预约使用情况")
            return

        start_pos = tuple(task['waypoints'][0])
        reserved_times = set(round(t, 1) for t in task['reserved_start_times'])  # 统一精度

        # ✅ 从真实路径中提取在起点的时间点
        path = task['path']
        times = task['times']
        used_times_in_start = set()

        for pos, t in zip(path, times):
            pos = tuple(pos)
            rounded_t = round(t, 1)
            if pos == start_pos and rounded_t in reserved_times:
                used_times_in_start.add(rounded_t)

        times_to_release = reserved_times - used_times_in_start

        # 逐个释放
        for t in times_to_release:
            key = (start_pos, t)
            # 从 node_reservations 中安全移除该 AGV未使用的起点的预约
            if key in self.ticket_manager.node_reservations:
                self.ticket_manager.node_reservations[key].pop(agv_id, None)
                # 如果这个时空点没有 AGV 了，删除整个条目
                if not self.ticket_manager.node_reservations[key]:
                    del self.ticket_manager.node_reservations[key]

            # 2. 从反向索引中移除
            self.ticket_manager.agv_reservations[agv_id].discard((start_pos, t))

        # print(f"AGV {agv_id}: 释放了 {len(times_to_release)} 个未使用的起点预约")
