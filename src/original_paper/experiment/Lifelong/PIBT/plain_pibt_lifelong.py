from __future__ import annotations

from typing import Deque, Dict, List, Tuple
import numpy as np
import time
from src.original_paper.experiment.Lifelong.PIBT.pypibt.dist_table import DistTable
from src.original_paper.experiment.Lifelong.PIBT.pypibt.pibt import PIBT
from collections import deque

CoordXY = Tuple[int, int]
CoordYX = Tuple[int, int]


class PIBTLifelongPlanner:
    def __init__(
        self,
        grid,
        agv_info: dict,
        initial_positions: dict,
        task_queue: Deque,
        seed: int = 42,
        max_steps: int = 500,
        print_every: int = 10,
    ) -> None:
        self.grid_obj = grid
        self.grid = self._convert_grid(grid)
        self.agv_info = agv_info
        self.current_time = 0
        self.max_steps = max_steps
        self.print_every = print_every
        self.seed = seed
        self.task_queue = deque(task_queue)
        self.total_assignment_time = 0.0

        self.agv_ids = sorted(list(agv_info.keys()), key=self._agv_sort_key)
        self.N = len(self.agv_ids)
        self.id2idx = {aid: i for i, aid in enumerate(self.agv_ids)}
        self.idx2id = {i: aid for aid, i in self.id2idx.items()}

        self.agv_positions: Dict[str, CoordXY] = {aid: tuple(initial_positions[aid]) for aid in self.agv_ids}
        self.agv_tasks: Dict[str, dict] = {}
        self.completed_tasks: List[Tuple[str, dict]] = []
        self.total_assigned_tasks = 0

        starts_yx = [self._xy_to_yx(self.agv_positions[aid]) for aid in self.agv_ids]
        stay_goals = list(starts_yx)
        self.pibt = PIBT(self.grid, starts_yx, stay_goals, seed=seed)
        self.priorities = [0.0 for _ in starts_yx]
        self.goal_cache: List[CoordYX] = list(stay_goals)
        self.dist_cache: Dict[CoordYX, DistTable] = {g: DistTable(self.grid, g) for g in stay_goals}
        self.pibt.dist_tables = [self.dist_cache[g] for g in stay_goals]

    @staticmethod
    def _agv_sort_key(agv_id: str):
        try:
            return int(str(agv_id).split("_")[-1])
        except Exception:
            return str(agv_id)

    @staticmethod
    def _convert_grid(grid_obj) -> np.ndarray:
        arr = np.asarray(grid_obj.grid)
        return arr != 1


    @staticmethod
    def _xy_to_yx(p: CoordXY) -> CoordYX:
        x, y = p
        return (y, x)

    @staticmethod
    def _yx_to_xy(p: CoordYX) -> CoordXY:
        y, x = p
        return (x, y)

    def _assign_new_tasks(self):
        busy_agvs = set(self.agv_tasks.keys())
        idle_agvs = [aid for aid in self.agv_ids if aid not in busy_agvs]
        if not idle_agvs or not self.task_queue:
            return

        look_ahead = min(len(idle_agvs) * 3, len(self.task_queue))
        candidates = []
        for i, task in enumerate(self.task_queue):
            if i >= look_ahead:
                break
            candidates.append((i, task))

        remaining_agvs = list(idle_agvs)
        remaining_indices = [i for i, _ in candidates]
        index_to_task = {i: t for i, t in candidates}
        matched = []

        while remaining_agvs and remaining_indices:
            best_agv, best_index, best_cost = None, None, float("inf")
            for agv_id in remaining_agvs:
                pos = self.agv_positions[agv_id]
                for idx in remaining_indices:
                    pickup, _ = index_to_task[idx]
                    c = abs(pos[0] - pickup[0]) + abs(pos[1] - pickup[1])
                    if c < best_cost:
                        best_cost, best_agv, best_index = c, agv_id, idx

            if best_agv is None:
                break

            matched.append((best_agv, best_index))
            remaining_agvs.remove(best_agv)
            remaining_indices.remove(best_index)

        matched_indices = set(idx for _, idx in matched)
        self.task_queue = deque(
            task for i, task in enumerate(self.task_queue) if i not in matched_indices
        )

        for agv_id, idx in matched:
            pickup, dropoff = index_to_task[idx]
            current_pos = self.agv_positions[agv_id]
            self.agv_tasks[agv_id] = {
                "start": current_pos,
                "pickup": tuple(pickup),
                "dropoff": tuple(dropoff),
                "phase": "to_pickup",
                "status": "assigned",
                "position": current_pos,
                "assigned_time": self.current_time,
                "pickup_time": None,
                "completed_time": None,
            }
            self.total_assigned_tasks += 1

    def _build_current_goals(self) -> List[CoordYX]:
        goals: List[CoordYX] = []
        for aid in self.agv_ids:
            if aid not in self.agv_tasks:
                goals.append(self._xy_to_yx(self.agv_positions[aid]))
                continue
            task = self.agv_tasks[aid]
            goals.append(self._xy_to_yx(task["pickup"] if task["phase"] == "to_pickup" else task["dropoff"]))
        return goals

    def _update_dist_tables_incremental(self, goals_yx: List[CoordYX]):
        self.pibt.goals = list(goals_yx)
        disttables = []
        for i, goal in enumerate(goals_yx):
            if goal not in self.dist_cache:
                self.dist_cache[goal] = DistTable(self.grid, goal)
            disttables.append(self.dist_cache[goal])
            self.goal_cache[i] = goal
        self.pibt.dist_tables = disttables

    def _update_priorities(self, next_config_yx: List[CoordYX], goals_yx: List[CoordYX]):
        for i, q in enumerate(next_config_yx):
            aid = self.idx2id[i]
            if q != goals_yx[i]:
                bonus = 1.5 if aid in self.agv_tasks else 1.0
                self.priorities[i] += bonus
            else:
                self.priorities[i] -= np.floor(self.priorities[i])

    def _advance_one_step(self):
        current_config_yx = [self._xy_to_yx(self.agv_positions[aid]) for aid in self.agv_ids]
        goals_yx = self._build_current_goals()
        self._update_dist_tables_incremental(goals_yx)
        next_config_yx = self.pibt.step(current_config_yx, self.priorities)

        for i, q in enumerate(next_config_yx):
            aid = self.idx2id[i]
            pos_xy = self._yx_to_xy(q)
            self.agv_positions[aid] = pos_xy
            if aid in self.agv_tasks:
                self.agv_tasks[aid]["position"] = pos_xy

        self._update_priorities(next_config_yx, goals_yx)
        self.current_time += 1

    def _clean_completed_tasks(self):
        arrived_pickup = []
        arrived_dropoff = []
        for agv_id, task in list(self.agv_tasks.items()):
            pos = task["position"]
            if task["phase"] == "to_pickup" and pos == task["pickup"]:
                arrived_pickup.append(agv_id)
            elif task["phase"] == "to_dropoff" and pos == task["dropoff"]:
                arrived_dropoff.append(agv_id)

        for agv_id in arrived_pickup:
            task = self.agv_tasks[agv_id]
            task["phase"] = "to_dropoff"
            task["status"] = "delivering"
            task["pickup_time"] = self.current_time
            task["start"] = task["position"]

        for agv_id in arrived_dropoff:
            task = self.agv_tasks[agv_id]
            task["status"] = "completed"
            task["completed_time"] = self.current_time
            self.completed_tasks.append((agv_id, dict(task)))
            del self.agv_tasks[agv_id]

    def run_lifelong(self, max_time: int = 500):
        step_limit = min(max_time, self.max_steps)
        total_assignment_time = 0.0

        for step in range(step_limit):
            if step % self.print_every == 0:
                print(
                    f"cycle={step:4d} time={self.current_time:4d} "
                    f"completed={len(self.completed_tasks)} executing={len(self.agv_tasks)} "
                    f"assigned={self.total_assigned_tasks} queue={len(self.task_queue)}",
                    flush=True,
                )
            # 任务分配计时
            t_start = time.perf_counter()
            self._assign_new_tasks()
            assignment_time = time.perf_counter() - t_start
            total_assignment_time += assignment_time

            if not self.agv_tasks and not self.task_queue:
                break
            self._advance_one_step()
            self._clean_completed_tasks()
        self.total_assignment_time = total_assignment_time
        return self.completed_tasks, self.total_assigned_tasks

    def runlifelong(self, max_time: int = 500):
        return self.run_lifelong(max_time=max_time)

    def get_throughput(self) -> float:
        if self.current_time <= 0:
            return 0.0
        return len(self.completed_tasks) / float(self.current_time)

    def getthroughput(self) -> float:
        return self.get_throughput()
