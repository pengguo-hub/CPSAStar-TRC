import heapq
import numpy as np


class SegmentPlanner:
    def __init__(self, grid, ticket_manager, conflict_updater):
        self.grid = grid
        self.ticket_manager = ticket_manager
        self.conflict_updater = conflict_updater
        self.enable_turn_penalty = True # 转弯惩罚
        self.MAX_WAIT = 2
        self.congestion_dict = {}
        self.conflict_regions = [] #(x_min,x_max,y_min,y_max)

    def plan_agv(self, agv_id, waypoints, priority,current_time,enable_turn_penalty = True):
        """为单个AGV执行分段规划"""
        self.enable_turn_penalty = enable_turn_penalty
        full_path = []
        full_times = []
        segment_start_time = current_time

        for i in range(len(waypoints) - 1):
            start, end = waypoints[i], waypoints[i + 1]

            # 分段A*规划
            segment, segment_times = self._plan_segment(
                agv_id, start, end, segment_start_time, priority
            )
            if not segment:  # 某段规划失败，释放该 AGV 所有票证
                self.ticket_manager.release_all(agv_id)
                return None,None
            if i == 0:
                full_path.extend(segment)
                full_times.extend(segment_times)
            else:
                full_path.extend(segment[1:])
                full_times.extend(segment_times[1:])

            segment_start_time = segment_times[-1]

        path = full_path if waypoints else []
        times = full_times if waypoints else []
        return path, times

    def _has_node_conflict(self, node, time, agv_id, priority):
        """优先级感知的冲突检测（增加空冲突场处理）"""
        # 点冲突
        if self.ticket_manager.is_node_conflict(node, time, agv_id, priority):
            return True # 有冲突
        return False

    def _has_edge_conflict(self,nx,ny,x,y,time,agv_id,priority):
        #检查是否存在反向行驶的AGV（边冲突）
        if self.ticket_manager.is_edge_conflict(nx,ny,x,y,time,agv_id,priority):
            return True
        return False

    def _plan_segment(self, agv_id, start, end, start_time, priority):
        """带时空约束的分段A*（正确版本）"""
        move_time = 1.0
        delta_t = self.conflict_updater.delta  # 时间槽粒度（如1秒）
        open_heap = []  # (f, h, g, time, pos)
        initial_h = self._heuristic(start, end, start_time, priority)
        initial_g = 0.0
        initial_f = initial_g + initial_h
        heapq.heappush(open_heap, (initial_f, initial_h, initial_g, start_time, start))
        g_score = {(start[0], start[1], start_time): initial_g}
        # 路径回溯：came_from[(x,y,t)] = (parent_x, parent_y, parent_t)
        came_from = {}

        while open_heap:
            #原来的
            # f_score, current, current_time = heapq.heappop(open_heap)
            # x, y = current
            f_score, current_h, current_g, current_time, current = heapq.heappop(open_heap)
            x, y = current
            # 检查是否达到目标
            if current == end:
                path, times = self._reconstruct_path_with_time(came_from, (x, y, current_time))
                if self._reserve_tickets(agv_id, path, times, priority):
                    return path, times
                return None, None
            # === 扩展邻居：移动 + 等待 ===
            neighbors = []
            # 1. 移动邻居（上下左右）
            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                nx, ny = x + dx, y + dy
                neighbor_pos = (nx, ny)
                arrival_time = round(current_time + move_time,1)
                if not self._is_valid_neighbor(neighbor_pos):
                    continue
                # 检查是否有点冲突（考虑优先级）
                if self._has_node_conflict(neighbor_pos, arrival_time, agv_id, priority):
                    continue  # 冲突跳过
                # 检查边冲突：是否有 AGV 正在 (nx,ny) → (x,y) 在 current_time
                if self._has_edge_conflict(nx,ny,x,y,current_time,agv_id,priority):
                    continue
                neighbors.append((neighbor_pos, arrival_time, False))  # False = 不是等待

            # 2. 等待动作：限制连续等待次数
            consecutive_waits = 0
            current_state = (x, y, current_time)

            # 获取当前状态的父状态，统计已连续等待次数
            if current_state in came_from:
                px, py, pt = came_from[current_state]
                if (px, py) == (x, y):  # 上一步也是在同一位置 → 是等待
                    # 向上追溯，统计连续等待了多少步
                    temp_state = (px, py, pt)
                    consecutive_waits = 1  # 已经有一次等待
                    while temp_state in came_from:
                        p = came_from[temp_state]
                        if p[0] != temp_state[0] or p[1] != temp_state[1]:
                            break
                        consecutive_waits += 1
                        temp_state = p
            # 如果还没达到最大等待次数，才允许再等一次
            if consecutive_waits < self.MAX_WAIT:
                wait_time = current_time + delta_t
                if not self._has_node_conflict(current, wait_time, agv_id, priority):
                    neighbors.append((current, wait_time, True))  # True = 等待

            # 处理所有邻居
            for neighbor_pos, arrival_time, is_wait in neighbors:
                nx, ny = neighbor_pos

                # 计算 tentative_g（实际代价）
                prev_g = g_score.get((x, y, current_time), float('inf'))
                turn_penalty = self._calculate_turn_penalty(
                    dir_at_node=current, new_pos=neighbor_pos,
                    prev_dir=self._get_direction(came_from, (x, y, current_time)),
                )
                move_cost = delta_t if is_wait else move_time
                # tentative_g = prev_g + move_cost + turn_penalty
                #新增
                slot = int(arrival_time//self.conflict_updater.delta)
                current_conflict = self.congestion_dict.get((nx, ny, slot), 0.0)
                conflict_cost_in_g = 5.0 * current_conflict
                tentative_g = prev_g + move_cost + turn_penalty + conflict_cost_in_g

                state = (nx, ny, arrival_time)

                # 使用 (x,y,time) 作为状态进行剪枝
                if state in g_score and tentative_g >= g_score[state]:
                    continue  # 已有更优路径到达此时空点

                g_score[state] = tentative_g
                came_from[state] = (x, y, current_time)

                h_val = self._heuristic(neighbor_pos, end, arrival_time, priority)
                f_val = tentative_g + h_val
                #原来的
                # heapq.heappush(open_heap, (f_val, neighbor_pos, arrival_time))
                heapq.heappush(
                    open_heap,
                    (f_val, h_val, tentative_g, arrival_time, neighbor_pos)
                )

        # 没找到路径
        self.ticket_manager.release_all(agv_id)
        return None, None

    def _reserve_tickets(self, agv_id, path, times, priority):
        reservations = []
        for i in range(len(path)):
            node = path[i]
            t = times[i]

            # ✅ 原有：预约节点
            reservations.append((node, t))

            # 🔺 新增：预约边（移动开始时间）
            if i < len(path) - 1:
                next_node = path[i + 1]
                if node != next_node:
                    # 预约从 node 到 next_node 的边，时间是移动开始时间 t
                    reservations.append(('edge', node[0], node[1], next_node[0], next_node[1], t))
        return self.ticket_manager.reserve(agv_id, reservations, priority)

    def _in_conflict_region(self, x, y):
        for (x_min, x_max, y_min, y_max) in self.conflict_regions:
            if x_min <= x <= x_max and y_min <= y <= y_max:
                return True
        return False

    def _heuristic(self, node, goal, arrival_time, priority):
        # dx, dy = goal[0] - node[0], goal[1] - node[1]
        # distance = abs(dx) + abs(dy)
        # # slot = int(arrival_time // self.conflict_updater.delta)
        # # conflict_cost = self.congestion_dict.get((node[0], node[1], slot), 0.0)
        # # penalty = 0*(1-np.exp(-conflict_cost))
        # return distance
        # """
        #         考虑距离衰减的启发式函数
        #         离当前点越近的区域，权重越大
        # """
        # 基础欧氏距离（保持 admissible）
        dx = goal[0] - node[0]
        dy = goal[1] - node[1]
        manhhatan_distance = abs(dx) + abs(dy)

        if manhhatan_distance == 0:
            return 0.0
        # if not self._in_conflict_region(node[0],node[1]):
        #     return euclidean_distance

        # === 关键参数（根据你的系统：1格=1时间单位，delta=1）===
        spatial_radius = 1  # 从当前点扩展到 3x3（radius=1）
        time_horizon = 2 * self.conflict_updater.delta  # 查看当前时间 t 到 t+2（共3个时间槽）
        current_slot = int(arrival_time // self.conflict_updater.delta)

        total_conflict = 0.0
        total_weight = 0.0

        # 遍历小空间邻域（以当前 node 为中心）
        for dx_local in range(-spatial_radius, spatial_radius + 1):
            for dy_local in range(-spatial_radius, spatial_radius + 1):
                x = node[0] + dx_local
                y = node[1] + dy_local

                # 跳过无效或越界点
                if not self._is_valid_neighbor((x, y)) and (x,y):
                    continue
                # 空间距离
                spatial_dist = abs(dx_local) + abs(dy_local)
                # 空间衰减：当前点惩罚以体现在g函数，邻居权重最高
                if spatial_dist == 0:
                    spatial_weight = 1
                else:
                    spatial_weight = np.exp(-spatial_dist / 2.0)
                # 时间维度：未来 1~2 步
                for dt in range(1,time_horizon + 1):  # dt = 1, 2
                    slot = current_slot + dt
                    conflict_val = self.congestion_dict.get((x, y, slot), 0.0)

                    # 时间衰减：越近越重要
                    time_weight = np.exp(-dt / 2)

                    weight = spatial_weight * time_weight
                    total_conflict += conflict_val * weight
                    total_weight += weight

        # 归一化平均冲突强度
        avg_conflict = total_conflict / total_weight if total_weight > 0 else 0.0
        penalty = 50 * avg_conflict
        return manhhatan_distance + penalty

    def _calculate_turn_penalty(self, dir_at_node, new_pos, prev_dir):
        if not self.enable_turn_penalty or prev_dir is None:
            return 0.0
        new_dir = (new_pos[0] - dir_at_node[0], new_pos[1] - dir_at_node[1])
        if new_dir != prev_dir:
            base_penalty = 0.5
            return base_penalty
        return 0.0

    def _get_direction(self, came_from, state):
        """从 came_from 获取到达 state 的方向"""
        if state not in came_from:
            return None
        prev_state = came_from[state]
        px, py, _ = prev_state
        cx, cy, _ = state
        return (cx - px, cy - py)

    def _is_valid_neighbor(self, pos):
        x, y = pos
        return (0 <= x < self.grid.width and
                0 <= y < self.grid.height and
                self.grid.grid[y][x] == 0)


    def _reconstruct_path_with_time(self, came_from, final_state):
        """从 (x,y,t) 状态重建路径和时间序列"""
        path = []
        times = []
        state = final_state  # (x, y, t)

        while True:
            x, y, t = state
            path.append((x, y))
            times.append(t)
            if state not in came_from:
                break
            state = came_from[state]

        return path[::-1], times[::-1]


    def replan_agv(self, agv_id, agv_info, start_position, goal_position, start_time, priority):
        speed = agv_info[agv_id]['speed']
        move_time = 1.0 / speed
        delta_t = self.conflict_updater.delta

        open_heap = []
        initial_f = self._heuristic(start_position, goal_position, start_time, priority)
        heapq.heappush(open_heap, (initial_f, start_position, start_time))

        g_score = {(start_position[0], start_position[1], start_time): 0}
        came_from = {}

        while open_heap:
            _, current, current_time = heapq.heappop(open_heap)
            if current == goal_position:
                path, times = self._reconstruct_path_with_time(came_from, (*current, current_time))
                if self._reserve_tickets(agv_id, path, times, priority):
                    return path
                return None

            # 扩展邻居（移动+等待）
            neighbors = []
            x, y = current

            # 移动
            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                nx, ny = x + dx, y + dy
                npos = (nx, ny)
                atime = current_time + move_time
                if (self._is_valid_position(npos) and
                        not self._has_node_conflict(npos, atime, agv_id, priority) and
                not self._has_edge_conflict(nx,ny,x,y,current_time,agv_id,priority)):
                    neighbors.append((npos, atime, False))

            # 等待
            wtime = current_time + delta_t
            if not self._has_node_conflict(current, wtime, agv_id, priority):
                neighbors.append((current, wtime, True))

            for npos, atime, is_wait in neighbors:
                nx, ny = npos
                state = (nx, ny, atime)
                cost = move_time if not is_wait else delta_t
                tentative_g = current_time + (move_time if not is_wait else delta_t)

                if state in g_score and tentative_g >= g_score[state]:
                    continue

                g_score[state] = tentative_g
                came_from[state] = (x, y, current_time)
                h = self._heuristic(npos, goal_position, atime, priority)
                f = tentative_g + h
                heapq.heappush(open_heap, (f, npos, atime))

        return None

    def _is_valid_position(self, pos):
        x, y = pos
        return 0 <= x < self.grid.width and 0 <= y < self.grid.height and self.grid.grid[y][x] == 0

