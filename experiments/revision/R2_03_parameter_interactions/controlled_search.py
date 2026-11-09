"""Minimal parameterization of the original one-shot CPS-A SegmentPlanner.

Unchanged: state definition, neighbor order, reservation checks, wait rule,
tie-breaking, path reconstruction and ticket reservation.
Changed only where required for sensitivity: alpha/beta/gamma/omega and the
R1 map-specific heuristic switch. Base heuristic is Manhattan on all maps.
"""
import heapq
import numpy as np
from vendor.CPS_A.Segment_Planner import SegmentPlanner

class ControlledSegmentPlanner(SegmentPlanner):
    def __init__(self, grid, ticket_manager, updater, config, use_lookahead_congestion):
        super().__init__(grid, ticket_manager, updater)
        self.config = config
        self.use_lookahead_congestion = bool(use_lookahead_congestion)
        self.MAX_WAIT = config.max_wait
        self.expansions = 0
        self.lookahead_evaluations = 0

    def _calculate_turn_penalty(self, dir_at_node, new_pos, prev_dir):
        if not self.enable_turn_penalty or prev_dir is None:
            return 0.0
        new_dir = (new_pos[0] - dir_at_node[0], new_pos[1] - dir_at_node[1])
        return self.config.beta if new_dir != prev_dir else 0.0

    def _heuristic(self, node, goal, arrival_time, priority):
        manhattan = abs(goal[0] - node[0]) + abs(goal[1] - node[1])
        if manhattan == 0:
            return 0.0
        # R1 protocol: B/C stop here; their g still includes gamma*phi.
        if not self.use_lookahead_congestion or self.config.omega == 0:
            return float(manhattan)
        self.lookahead_evaluations += 1
        spatial_radius = 1
        time_horizon = 2 * self.conflict_updater.delta
        current_slot = int(arrival_time // self.conflict_updater.delta)
        total_conflict = 0.0
        total_weight = 0.0
        for dx_local in range(-spatial_radius, spatial_radius + 1):
            for dy_local in range(-spatial_radius, spatial_radius + 1):
                x, y = node[0] + dx_local, node[1] + dy_local
                if not self._is_valid_neighbor((x, y)):
                    continue
                spatial_dist = abs(dx_local) + abs(dy_local)
                spatial_weight = 1.0 if spatial_dist == 0 else float(np.exp(-spatial_dist / 2.0))
                for dt in range(1, time_horizon + 1):
                    slot = current_slot + dt
                    conflict_val = self.congestion_dict.get((x, y, slot), 0.0)
                    time_weight = float(np.exp(-dt / 2.0))
                    weight = spatial_weight * time_weight
                    total_conflict += conflict_val * weight
                    total_weight += weight
        avg_conflict = total_conflict / total_weight if total_weight > 0 else 0.0
        return float(manhattan + self.config.omega * avg_conflict)

    def _plan_segment(self, agv_id, agv_info, start, end, start_time, priority):
        speed = agv_info[agv_id]['speed']
        move_time = 1.0 / speed
        delta_t = self.conflict_updater.delta
        open_heap = []
        initial_h = self._heuristic(start, end, start_time, priority)
        heapq.heappush(open_heap, (initial_h, initial_h, 0.0, start_time, start))
        g_score = {(start[0], start[1], start_time): 0.0}
        came_from = {}
        while open_heap:
            self.expansions += 1
            _, _, _, current_time, current = heapq.heappop(open_heap)
            x, y = current
            if current == end:
                path, times = self._reconstruct_path_with_time(came_from, (x, y, current_time))
                if self._reserve_tickets(agv_id, path, times, priority):
                    return path, times
                return None, None
            neighbors = []
            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                nx, ny = x + dx, y + dy
                neighbor_pos = (nx, ny)
                arrival_time = round(current_time + move_time, 1)
                if not self._is_valid_neighbor(neighbor_pos):
                    continue
                if self._has_node_conflict(neighbor_pos, arrival_time, agv_id, priority):
                    continue
                if self._has_edge_conflict(nx, ny, x, y, current_time, agv_id, priority):
                    continue
                neighbors.append((neighbor_pos, arrival_time, False))
            consecutive_waits = 0
            current_state = (x, y, current_time)
            if current_state in came_from:
                px, py, pt = came_from[current_state]
                if (px, py) == (x, y):
                    temp_state = (px, py, pt)
                    consecutive_waits = 1
                    while temp_state in came_from:
                        p = came_from[temp_state]
                        if p[0] != temp_state[0] or p[1] != temp_state[1]:
                            break
                        consecutive_waits += 1
                        temp_state = p
            if consecutive_waits < self.MAX_WAIT:
                wait_time = current_time + delta_t
                if not self._has_node_conflict(current, wait_time, agv_id, priority):
                    neighbors.append((current, wait_time, True))
            for neighbor_pos, arrival_time, is_wait in neighbors:
                nx, ny = neighbor_pos
                prev_g = g_score.get((x, y, current_time), float('inf'))
                turn_penalty = self._calculate_turn_penalty(
                    current, neighbor_pos, self._get_direction(came_from, (x, y, current_time))
                )
                move_cost = delta_t if is_wait else move_time
                slot = int(arrival_time // self.conflict_updater.delta)
                current_conflict = self.congestion_dict.get((nx, ny, slot), 0.0)
                tentative_g = prev_g + self.config.alpha * move_cost + turn_penalty + self.config.gamma * current_conflict
                state = (nx, ny, arrival_time)
                if state in g_score and tentative_g >= g_score[state]:
                    continue
                g_score[state] = tentative_g
                came_from[state] = (x, y, current_time)
                h_val = self._heuristic(neighbor_pos, end, arrival_time, priority)
                heapq.heappush(open_heap, (tentative_g + h_val, h_val, tentative_g, arrival_time, neighbor_pos))
        self.ticket_manager.release_all(agv_id)
        return None, None
