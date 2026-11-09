import numpy as np
from collections import defaultdict
from typing import Dict, List, Tuple, Set, Optional
from datetime import timedelta
# 规划的时候采用的是相对时间概念，需要换算后带入datetime

class DynamicObstacleHandler:
    def __init__(self, grid, ticket_manager, segment_planner,path,current_time, agv_info):
        """
        动态障碍物处理器（完整版）

        参数:
            grid_map: GridMap实例
            ticket_manager: 时空券管理器（需实现get_node_reservations和get_priority方法）
            segment_planner: 需实现replan_agv方法
        """
        self.grid = grid # GridMap实例
        self.ticket_manager = ticket_manager # Ticket_manager实例
        self.segment_planner = segment_planner # Segment_planner实例
        self.detected_obstacles = defaultdict(dict)  # {obstacle_id: {position, velocity, type, timestamp}}
        self.agv_paths = path  # {agv_id: [(x1,y1), (x2,y2), ...]}
        self.agv_positions = {}  # {agv_id: (current_x, current_y)}
        self.current_time = current_time # 当前时间
        self.agv_info = agv_info

    # ------------------- 核心方法 -------------------
    def update_sensor_data(self, sensor_data: List[Dict]) -> None:
        """
        更新传感器数据并记录AGV位置
        输入格式:
            [{
                'obstacle_id': str (格式为"类型_ID"，如"agv_1", "person_1"),
                'position': (x, y),
                'velocity': (vx, vy),
                'timestamp': datetime,
                'type': 'agv'/'person'/'cargo' (可选)
            }]
        """
        for data in sensor_data:
            obs_id = data['obstacle_id']
            pos = data['position']

            # 记录障碍物信息
            self.detected_obstacles[obs_id] = {
                'position': pos,
                'velocity': data.get('velocity', (0, 0)),
                'timestamp': data['timestamp'], # 发现障碍物的时间
                'type': data.get('type', obs_id.split('_')[0])
            }

            # 如果是AGV，更新其当前位置
            if obs_id.startswith('agv_'):
                agv_id = obs_id.split('_')[1]
                self.agv_positions[agv_id] = pos

            # 非AGV障碍物添加到网格
            if not obs_id.startswith('agv_'):
                self.grid.add_dynamic_obstacle(*pos)

        self._clean_expired_obstacles(self.current_time)

    def check_future_conflicts(self, lookahead_time: float, replan_window: float) -> Dict[str, List[Tuple]]:
        """
        检查未来冲突并触发重规划
        返回: {agv_id: [(冲突节点, 冲突时间), ...]}

        逻辑变更：
        1. 所有障碍物都会严格检查时空券占用
        2. 根据障碍物类型区分冲突检测策略
        """
        conflicts = defaultdict(list)

        for obs_id, obs_data in self.detected_obstacles.items():
            pos, vel = obs_data['position'], obs_data['velocity']
            obj_type = obs_data['type']  # 获取障碍物类型

            # 预测障碍物未来位置（每1秒一个检查点）
            for t in np.arange(0, lookahead_time, 1):
                future_t = self.current_time + timedelta(seconds=t)
                future_pos = (
                    round(pos[0] + vel[0] * t),
                    round(pos[1] + vel[1] * t)
                )

                # 严格位置检查（传入当前障碍物ID）
                if self._is_position_valid(
                        pos=future_pos,
                        time=future_t,
                        checking_obj_id=obs_id  # 格式应为"类型_ID"
                ):
                    continue  # 位置有效(无冲突)则跳过

                # 检测优先级冲突
                conflicting_agvs = self._check_priority_conflicts(future_pos, future_t, obs_id) # 找出比当前优先级低的AGV进行重规划
                for agv_id in conflicting_agvs:
                    conflicts[agv_id].append((future_pos, future_t))

        # 执行重规划
        self._replan_conflicting_agvs(self.agv_info, conflicts)
        return conflicts
    def _check_priority_conflicts(self, node: Tuple[int, int], time, obstacle_id: str) -> Set[str]:
        """优先级感知冲突检测"""
        reservations = self.ticket_manager.get_node_reservations(node, time)
        obstacle_priority = self._get_obstacle_priority(obstacle_id)
        low_priority_agvs = set()

        for agv_id, res_data in reservations.items():
            agv_priority = res_data.get('priority', self._get_agv_priority(agv_id))
            if agv_priority < obstacle_priority:
                low_priority_agvs.add(agv_id)

        return low_priority_agvs

    def _replan_conflicting_agvs(self,agv_info, conflicts: Dict[str, List[Tuple]]) -> None:
        """取消冲突AGV的所有未来预约并重规划"""

        for agv_id, conflict_list in conflicts.items():
            if not conflict_list or agv_id not in self.agv_paths:
                continue

            # 1. 取消该AGV当前时间后的所有预约
            self.ticket_manager.cancel_future_reservations(agv_id, self.current_time)

            # 2. 获取原路径和当前位置
            original_path = self.agv_paths[agv_id]
            current_pos,current_t = conflicts.get(agv_id, [])
            if not current_pos:
                continue

            # 3. 从当前位置开始重规划（不考虑原路径剩余部分）
            new_path = self.segment_planner.replan_agv(
                agv_id=agv_id,
                agv_info=agv_info,
                start_position=current_pos,
                goal_position=original_path[-1],  # 保持原目标点
                current_time=current_t,
                priority=self._get_agv_priority(agv_id)
            )

            if new_path:
                self.agv_paths[agv_id] = new_path
            else:
                print(f"AGV {agv_id} 重规划失败，进入等待状态")

    def _get_obstacle_priority(self, obstacle_id: str) -> int:
        """根据障碍物类型返回优先级"""
        if 'person' in obstacle_id or 'cargo' in obstacle_id:
            return 3 # 保证高于所有agv
        else:  # 普通AGV或其他
            return self._get_agv_priority(obstacle_id)

    def _get_agv_priority(self, agv_id: str) -> int:
        """安全获取AGV优先级（默认返回1）"""
        try:
            # 尝试从预约数据获取
            for reservations in self.ticket_manager.node_reservations.values():
                if agv_id in reservations:
                    priority = reservations[agv_id].get('priority', 1)
                    return priority
        except Exception as e:
            print(f"获取AGV {agv_id} 优先级失败: {str(e)}")
        return 1  # 默认普通优先级

    def _is_position_valid(self, pos: Tuple[int, int], time, checking_obj_id: str) -> bool:
        """
        严格位置有效性检查：
        1. 地图范围内
        2. 非静态障碍物
        3. 时空券冲突检查（精确到坐标和时间）：
           - 如果是AGV：检查是否被其他AGV预约
           - 如果是人/货物：检查是否被任何AGV预约

        参数:
            checking_obj_id: 必须为"类型_ID"格式（如"agv_1"）
        """
        x, y = pos

        # 1. 基础检查
        if not (0 <= x < self.grid.width and 0 <= y < self.grid.height):
            print("超出地图边界")
            return False
        if self.grid.grid[y][x] != 0:
            print("区域不可通行")
            return False

        # 2. 获取该位置该时间的所有预约
        reservations = self.ticket_manager.get_reservations_at(pos, time)
        if not reservations:  # 无预约则直接通过
            return True

        # 3. 解析检查对象类型
        try:
            obj_type, obj_id = checking_obj_id.split('_', 1)
        except ValueError:
            raise ValueError(f"Invalid object ID format: {checking_obj_id}")

        # 4. 精确冲突检测
        if obj_type == 'agv':
            # AGV：检查是否有其他AGV占用（允许自己占用）
            return not any(
                reserved_obj.startswith('agv_') and reserved_obj != checking_obj_id
                for reserved_obj in reservations.keys()
            )
        else:
            # 人/货物：检查是否有任何AGV占用
            return not any(
                reserved_obj.startswith('agv_')
                for reserved_obj in reservations.keys()
            )

    def _clean_expired_obstacles(self, current_time, expiry_seconds: float = 5.0) -> None:
        """清理过期障碍物"""
        to_remove = [
            obs_id for obs_id, obs_data in self.detected_obstacles.items()
            if (current_time - obs_data['timestamp']).total_seconds() > expiry_seconds
        ]
        for obs_id in to_remove:
            if not obs_id.startswith('agv_'):
                self.grid.remove_dynamic_obstacle(*self.detected_obstacles[obs_id]['position'])
            del self.detected_obstacles[obs_id]