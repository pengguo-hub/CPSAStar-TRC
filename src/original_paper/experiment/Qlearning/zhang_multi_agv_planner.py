from .zhang_q_learning_core import ZhangQCorePlanner

class ZhangMultiAGVPlanner:
    """
    基于Zhang等人论文的多AGV在线无冲突路径规划器。
    此类提供与您现有测试框架兼容的batch_plan接口。
    """

    def __init__(self, grid_map, **kwargs):
        """
        初始化多AGV规划器。

        Args:
            grid_map (np.ndarray): 二维网格地图。
            **kwargs: 传递给核心规划器的参数。
        """
        self.grid_map = grid_map
        self.core_planner = ZhangQCorePlanner(grid_map, **kwargs)
        self.agv_schedules = {}  # 存储每个AGV的时空计划: {agv_id: [(x, y, t), ...]}
        self.time_step = 1.0  # 每个时间步长对应的实际秒数 (假设每格1米)

    def _path_to_schedule(self, path, start_time=0):
        """
        将路径坐标列表转换为带时间戳的调度计划。
        """
        schedule = []
        current_time = start_time
        for coord in path:
            schedule.append((*coord, current_time))
            current_time += self.time_step
        return schedule

    def _build_time_index(self, schedules_dict):
        """
        从调度字典构建两个时间索引：
        - time_pos:   {t_int -> set of (x,y)}        用于点冲突检测
        - time_edges: {t_int -> set of ((x1,y1),(x2,y2))}  用于边冲突检测
        """
        time_pos = {}
        time_edges = {}
        for sched in schedules_dict.values():
            for i, (x, y, t) in enumerate(sched):
                t_int = round(t)
                time_pos.setdefault(t_int, set()).add((x, y))
                if i + 1 < len(sched):
                    x2, y2, t2 = sched[i + 1]
                    # 边：从(x,y)在t时刻出发走向(x2,y2)
                    time_edges.setdefault(t_int, set()).add(((x, y), (x2, y2)))
        return time_pos, time_edges

    def _has_conflict(self, schedule, time_pos, time_edges):
        """
        检测一条新 schedule 与已有时间索引之间是否存在：
        - 点冲突：同一时刻占据相同格
        - 边冲突：同一时刻两车互换位置（对向行驶）
        """
        for i, (x, y, t) in enumerate(schedule):
            t_int = round(t)
            # 点冲突
            if (x, y) in time_pos.get(t_int, set()):
                return True
            # 边冲突：若新车在 t->t+1 走 (x,y)->(x2,y2)，
            # 则已有车不能在同一 t 走 (x2,y2)->(x,y)
            if i + 1 < len(schedule):
                x2, y2, _ = schedule[i + 1]
                if ((x2, y2), (x, y)) in time_edges.get(t_int, set()):
                    return True
        return False

    def _schedule_to_spatial_path(self, schedule):
        """
        将带时间戳的调度 [(x,y,t),...] 展开为时空路径列表。
        所有AGV从 t=0 开始，等待或延迟通过重复该点来体现。
        输出: [(x0,y0), (x0,y0), ..., (x1,y1), ...]
        其中列表的索引就是时间步。
        """
        if not schedule:
            return []
        # 按时间戳排序
        sorted_sched = sorted(schedule, key=lambda p: round(p[2]))
        max_t = round(sorted_sched[-1][2])

        # 建立 t -> (x,y) 的映射（只记录该时刻到达的坐标）
        t_to_pos = {round(t): (x, y) for x, y, t in sorted_sched}

        path = []
        current_pos = (sorted_sched[0][0], sorted_sched[0][1])  # 起点
        for t in range(0, max_t + 1):
            if t in t_to_pos:
                current_pos = t_to_pos[t]
            path.append(current_pos)
        return path

    def batch_plan(self, parsed_tasks, reset=True):
        """
        主入口函数，与您的测试框架兼容。

        Args:
            parsed_tasks (dict): 格式如前所述。
            reset (bool): 是否重置内部状态。对于在线规划，通常为False。

        Returns:
            dict: 成功规划的路径字典 {agv_id: path}。
        """
        if reset:
            self.agv_schedules.clear()

        successful_paths = {}
        new_schedules = {}

        # 第一步：为所有新任务独立规划初始路径（起点 -> 取货点 -> 终点）
        for agv_id,task in parsed_tasks.items():
            start_pos = tuple(task["agv_position"])  # AGV当前物理位置
            pickup = tuple(task["source"])           # 取货点
            dropoff = tuple(task["destination"])     # 终点/卸货点
            # print(agv_id)
            # print(start_pos)
            # print(pickup)
            # print(dropoff)

            # 规划第一段路径：从当前位置到取货点
            path_to_pickup = self.core_planner.plan_path(start_pos, pickup)
            if path_to_pickup is None:
                # print(f"Warning: Failed to plan path to pickup for {agv_id}")
                continue

            # 规划第二段路径：从取货点到终点
            path_to_dropoff = self.core_planner.plan_path(pickup, dropoff)
            if path_to_dropoff is None:
                # print(f"Warning: Failed to plan path to dropoff for {agv_id}")
                continue

            # 拼接两段路径，注意避免在取货点重复
            # path_to_pickup 的最后一个点 == pickup
            # path_to_dropoff 的第一个点 == pickup
            # 所以拼接时去掉 path_to_dropoff 的第一个点
            full_path = path_to_pickup + path_to_dropoff[1:]

            # 转换为调度计划，起始时间为0
            schedule = self._path_to_schedule(full_path, start_time=0)
            new_schedules[agv_id] = schedule
            successful_paths[agv_id] = full_path

            # print(f"{agv_id} 单路径规划成功")

        # 第二步：检测并解决冲突
        all_schedules = {**self.agv_schedules, **new_schedules}
        wait_time = 5.0
        max_attempts = 20
        attempt = 0

        while attempt < max_attempts:
            # --- 第一阶段：检测所有冲突对 ---
            all_conflicts = []  # 存储所有冲突对 [(agv_a, agv_b), ...]

            # 检查每一对新AGV之间，以及新AGV与旧AGV之间的冲突
            new_agv_ids = list(new_schedules.keys())
            all_agv_ids = list(all_schedules.keys())

            # 检查新AGV vs 所有AGV (包括自己和其他新AGV)
            for i, agv_a in enumerate(new_agv_ids):
                for agv_b in all_agv_ids[i + 1:]:
                    if agv_a == agv_b:
                        continue
                    # 用新方法：以 agv_b 的 schedule 建时间索引，检测 agv_a 是否冲突
                    t_pos, t_edges = self._build_time_index({agv_b: all_schedules[agv_b]})
                    if self._has_conflict(all_schedules[agv_a], t_pos, t_edges):
                        all_conflicts.append((agv_a, agv_b))

            # 如果没有冲突，成功退出
            if not all_conflicts:
                break

            # --- 第二阶段：基于优先级统一决策谁等待 ---
            agvs_to_delay = set()
            for agv_a, agv_b in all_conflicts:
                sched_a = all_schedules[agv_a]
                sched_b = all_schedules[agv_b]

                # 计算曼哈顿距离
                dist_a = abs(sched_a[0][0] - sched_a[-1][0]) + abs(sched_a[0][1] - sched_a[-1][1])
                dist_b = abs(sched_b[0][0] - sched_b[-1][0]) + abs(sched_b[0][1] - sched_b[-1][1])

                # 决策逻辑
                if dist_a > dist_b:
                    # A路径更长，A等待
                    agvs_to_delay.add(agv_a)
                elif dist_b > dist_a:
                    # B路径更长，B等待
                    agvs_to_delay.add(agv_b)
                else:
                    # 路径长度相同，让新来的（或ID更大的）等待，保证确定性
                    # 注意：我们不能让已经存在的旧AGV (不在 new_schedules 中) 等待
                    if agv_a in new_schedules and agv_b not in new_schedules:
                        agvs_to_delay.add(agv_a)
                    elif agv_b in new_schedules and agv_a not in new_schedules:
                        agvs_to_delay.add(agv_b)
                    else:
                        # 两者都是新的，按ID决定
                        if agv_a > agv_b:
                            agvs_to_delay.add(agv_a)
                        else:
                            agvs_to_delay.add(agv_b)

            # --- 第三阶段：统一执行延迟 ---
            for agv_id in agvs_to_delay:
                delayed_schedule = [(x, y, t + wait_time) for (x, y, t) in all_schedules[agv_id]]
                new_schedules[agv_id] = delayed_schedule
                all_schedules[agv_id] = delayed_schedule
                # 同时更新successful_paths中的路径（路径点不变，只是时间变了）
                # 注意：我们的输出只需要路径点，所以这里可以不更新successful_paths
                # 但内部调度必须更新

            attempt += 1

        if attempt >= max_attempts:
            # 找出仍然存在冲突的新AGV，将其从本轮结果中移除
            # 逻辑：逐一检查每辆新AGV与其他所有车是否还有冲突
            failed_agvs = set()
            for agv_id in list(new_schedules.keys()):
                others = {k: v for k, v in all_schedules.items() if k != agv_id}
                t_pos, t_edges = self._build_time_index(others)
                if self._has_conflict(new_schedules[agv_id], t_pos, t_edges):
                    failed_agvs.add(agv_id)
            for agv_id in failed_agvs:
                del new_schedules[agv_id]
                # all_schedules 也要同步删除，防止影响后续 update
                if agv_id in all_schedules:
                    del all_schedules[agv_id]

        # 第三步：将最终的新计划合并到全局状态
        self.agv_schedules.update(new_schedules)

        # 第四步：将内部时间戳调度展开为含等待点的时空路径序列
        final_paths = {}
        for agv_id, sched in new_schedules.items():
            final_paths[agv_id] = self._schedule_to_spatial_path(sched)

        return final_paths