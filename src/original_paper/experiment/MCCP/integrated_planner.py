from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from .utils import manhattan_distance
from .path_planner import CongestionAwareAStar

class IntegratedAGVPlanner:
    def __init__(self, grid, llm_deployer=None, api_deployer=None, agv_info=None, waypoint_generator=None,
                 predictor_type='neural', model_path=None):
        self.grid = grid
        self.agv_info = agv_info or {}
        self.predictor_type = predictor_type
        self.model_path = model_path
        self.predictor = None
        self.planner = None
        self.updater = None
        self.planned_count = 0
        self.UPDATE_INTERVAL = 5

    def _init_predictor(self):
        if self.predictor_type == 'monte_carlo':
            from .congestion_predictor import MonteCarloCongestionPredictor
            self.predictor = MonteCarloCongestionPredictor(self.grid, num_particles=500, sigma_smooth=0.8)
        else:  # neural
            from .neural_predictor import NeuralPredictorWrapper
            from .path_planner import CongestionFieldManager
            self.predictor = NeuralPredictorWrapper(self.grid, model_path=self.model_path)
            self.congestion_manager=CongestionFieldManager(predictor=self.predictor,grid_size=(self.grid.width, self.grid.height))


    def batch_plan(self, parsed_tasks: Dict, reset: bool = True) -> Dict[str, List]:
        if reset or self.predictor is None:
            self._init_predictor()
            self.planned_count = 0

        # 构建预测任务（只需要起点和终点）
        tasks_for_pred = []
        for agv_id,task in parsed_tasks.items():
            tasks_for_pred.append({
                'task_id': task['task_id'],
                'start': tuple(task['agv_position']),
                'goal': tuple(task['destination'])
            })


        # 估计总时间T
        max_dist = 0
        for agv_id,task in parsed_tasks.items():
            # print(agv_id)
            start = task['agv_position']
            source = task['source']
            dest = task['destination']
            dist = manhattan_distance(start, source) + manhattan_distance(source, dest)
            if dist > max_dist:
                max_dist = dist
        T = max_dist + 300

        # 生成密度场
        self.predictor.future_predict(tasks_for_pred, T)

        # 创建规划器

        self.planner = CongestionAwareAStar(self.grid, self.congestion_manager,
                                            move_cost=1.0,
                                            congestion_weight=5.0,
                                            prediction_window=1)

        def get_priority(task):
            constraints = task.get('constraints', {})
            priority_str = constraints.get('priority', 'normal')
            priority_map = {'emergency': 3.0, 'high': 2.0, 'normal': 1.0}
            return priority_map.get(priority_str, 1.0)

        sorted_agvs = sorted([(agv_id, task) for agv_id,task in parsed_tasks.items()],
                             key=lambda x: get_priority(x[1]), reverse=True)

        paths = {}
        occupied = {}

        for agv_id, task in sorted_agvs:
            start = tuple(task['agv_position'])
            source = tuple(task['source'])
            destination = tuple(task['destination'])

            path1 = self.planner.plan(agv_id,start, source, start_time=0, time_limit=T, occupied=occupied,robot_paths=paths)
            # print(path1)
            if not path1:
                # print(f"Warning: AGV {agv_id} 无法规划到 source，跳过")
                continue

            for t, pos in enumerate(path1):
                occupied[(t, pos[0], pos[1])] = agv_id

            t_start2 = len(path1) - 1
            path2 = self.planner.plan(agv_id,source, destination, start_time=t_start2, time_limit=T, occupied=occupied,robot_paths=paths)
            if not path2:
                # print(f"Warning: AGV {agv_id} 无法规划到 destination，回滚")
                for t, pos in enumerate(path1):
                    del occupied[(t, pos[0], pos[1])]
                continue

            for offset, pos in enumerate(path2[1:], start=1):
                t = t_start2 + offset
                occupied[(t, pos[0], pos[1])] = agv_id

            full_path = path1[:-1] + path2
            paths[agv_id] = full_path
            self.planned_count += 1

        #     if self.planned_count % self.UPDATE_INTERVAL == 0:
        #         self._update_congestion_field(parsed_tasks, paths, occupied)
        #
        # self._update_congestion_field(parsed_tasks, paths, occupied)
        # print(paths)
        return paths

    # def _update_congestion_field(self, parsed_tasks, paths, occupied):
    #     if not paths:
    #         return
    #     max_t = max(len(p) for p in paths.values())
    #     if max_t == 0:
    #         return
    #
    #     obs_fields = [np.zeros((self.grid.height, self.grid.width)) for _ in range(max_t)]
    #     for agv_id, path in paths.items():
    #         for t, (x, y) in enumerate(path):
    #             if t < max_t:
    #                 obs_fields[t][y, x] += 1
    #
    #     from .field_updater import DynamicCongestionFieldUpdater
    #     self.updater = DynamicCongestionFieldUpdater(self.grid, self.predictor, blend_factor=0.7)
    #     for t in range(max_t):
    #         observed = {'robot_density': obs_fields[t]}
    #         updated = self.updater.update(observed, t)
    #         for (tt, x, y), val in updated.items():
    #             if tt == t:
    #                 self.predictor.density_field[(t, x, y)] = val