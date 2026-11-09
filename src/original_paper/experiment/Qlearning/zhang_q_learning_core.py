import numpy as np
from .grid_map_utils import coord_to_node_id, node_id_to_coord
import math


class ZhangQCorePlanner:
    """
    复现论文中基于最短时间Q学习算法的核心路径规划器。
    此类负责为单个AGV在给定静态障碍物地图上规划从起点到终点的最优路径。
    """

    def __init__(self, grid_map, agv_speed=1, gamma=0.8, alpha=0.1, obstacle_reward=-10, goal_reward=100,epsilon=0.1):
        """
        初始化核心规划器。

        Args:
            grid_map (np.ndarray): 二维网格地图，0表示自由空间，1表示障碍物。
            agv_speed (float): AGV的移动速度 (m/s)。
            gamma (float): Q-Learning的折扣因子。
            alpha (float): Q-Learning的学习率。
            obstacle_reward (int): 进入障碍物格子的惩罚。
            goal_reward (int): 到达目标点的奖励。
        """
        self.grid_map = grid_map
        self.grid_height, self.grid_width = grid_map.shape
        self.total_nodes = self.grid_height * self.grid_width
        self.agv_speed = agv_speed
        self.gamma = gamma
        self.alpha = alpha
        self.obstacle_reward = obstacle_reward
        self.goal_reward = goal_reward
        self.epsilon = epsilon

        # 预计算完整的A-R矩阵（仅一次）
        self.full_ar_matrix = self._build_full_ar_matrix()

        self.DIRECTIONS = {
        'NORTH': 0,
        'EAST': 1,
        'SOUTH': 2,
        'WEST': 3
    }

    def _is_valid_coord(self, coord):
        """检查坐标是否在地图范围内且不是障碍物。"""
        x, y = coord
        if 0 <= x < self.grid_width and 0 <= y < self.grid_height:
            return self.grid_map[y, x] == 0
        return False

    def _get_neighbors(self, node_id):
        """获取一个节点的所有有效邻居节点（上、下、左、右）。"""
        x, y = node_id_to_coord(node_id, self.grid_width)
        neighbors = []
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = x + dx, y + dy
            if self._is_valid_coord((nx, ny)):
                neighbors.append(coord_to_node_id((nx, ny), self.grid_width))
        return neighbors

    def _build_full_ar_matrix(self):
        """
        构建完整的邻接-奖励 (A-R) 矩阵。
        矩阵大小为 [total_nodes, total_nodes]。
        - 如果i和j相邻，则 A-R[i, j] = 0 (自由移动的奖励)
        - 如果j是障碍物或越界，则 A-R[i, j] = obstacle_reward
        - 对角线元素 A-R[i, i] = obstacle_reward (不能停留)
        """
        # print("构建完整的邻接-奖励 (A-R) 矩阵")
        ar_matrix = np.full((self.total_nodes, self.total_nodes), self.obstacle_reward, dtype=np.float32)

        for i in range(self.total_nodes):
            if not self._is_valid_coord(node_id_to_coord(i, self.grid_width)):
                continue  # 起始点是障碍物，整行保持为obstacle_reward
            neighbors = self._get_neighbors(i)
            for j in neighbors:
                ar_matrix[i, j] = 0.0

        return ar_matrix

    def _build_ld_ar_matrix(self, start_node, goal_node):
        """
        根据起点和终点构建低维邻接-奖励 (LD-A-R) 矩阵。
        论文中的k是曼哈顿距离+1，但为了确保包含所有可能路径，我们使用一个包围盒。
        """
        # print("根据起点和终点构建低维邻接-奖励 (LD-A-R) 矩阵")
        start_x, start_y = node_id_to_coord(start_node, self.grid_width)
        goal_x, goal_y = node_id_to_coord(goal_node, self.grid_width)

        # 定义包围盒
        margin = max(self.grid_height, self.grid_width) // 4  # 或者直接写 margin = 5
        min_x = max(0, min(start_x, goal_x) - margin)
        max_x = min(self.grid_width - 1, max(start_x, goal_x) + margin)
        min_y = max(0, min(start_y, goal_y) - margin)
        max_y = min(self.grid_height - 1, max(start_y, goal_y) + margin)

        # min_x = 0
        # max_x = self.grid_width - 1
        # min_y = 0
        # max_y = self.grid_height - 1

        # 提取子矩阵
        sub_nodes = []
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                if self.grid_map[y, x] == 0:  # 只包含自由空间
                    sub_nodes.append(coord_to_node_id((x, y), self.grid_width))

        if start_node not in sub_nodes or goal_node not in sub_nodes:
            # 如果起点或终点不在子图中（理论上不应该发生），回退到完整矩阵
            return self.full_ar_matrix, list(range(self.total_nodes))

        sub_size = len(sub_nodes)
        ld_ar_matrix = np.full((sub_size, sub_size), self.obstacle_reward, dtype=np.float32)
        node_to_index = {node: idx for idx, node in enumerate(sub_nodes)}

        for i, node_i in enumerate(sub_nodes):
            for j, node_j in enumerate(sub_nodes):
                if i == j:
                    continue
                # 检查在原始A-R矩阵中是否相连
                if self.full_ar_matrix[node_i, node_j] == 0:
                    ld_ar_matrix[i, j] = 0.0

        # 设置目标点奖励
        goal_idx = node_to_index[goal_node]
        ld_ar_matrix[goal_idx, goal_idx] = self.goal_reward
        # --- 仅对终点的邻居设置高奖励 ---
        # 首先，找出在完整图中，所有与终点相邻的节点
        goal_neighbors = set(self._get_neighbors(goal_node))

        # 然后，在低维矩阵中，只为这些邻居（如果它们也在子图中）设置高奖励
        for i, node_i in enumerate(sub_nodes):
            if node_i in goal_neighbors:
                # node_i 是 goal 的邻居，设置从 node_i 到 goal 的奖励
                ld_ar_matrix[i, goal_idx] = self.goal_reward

        return ld_ar_matrix, sub_nodes

    def _get_direction_from_move(self, from_node, to_node):
        """根据两个相邻节点，返回移动方向 (0,1,2,3)"""
        from_x, from_y = node_id_to_coord(from_node, self.grid_width)
        to_x, to_y = node_id_to_coord(to_node, self.grid_width)
        if to_y == from_y + 1:
            return self.DIRECTIONS['NORTH']
        elif to_x == from_x + 1:
            return self.DIRECTIONS['EAST']
        elif to_y == from_y - 1:
            return self.DIRECTIONS['SOUTH']
        elif to_x == from_x - 1:
            return self.DIRECTIONS['WEST']
        else:
            raise ValueError("Invalid move between non-adjacent nodes")

    # 在 zhang_q_learning_core.py 中

    def _q_learning_train(self, ld_ar_matrix, sub_nodes, start_node, goal_node):
        """
        改进的Q-learning训练函数。
        - 使用ld_ar_matrix仅作为邻接关系（合法性）的判断依据。
        - 奖励机制采用标准路径规划设置：到达目标+100，每步-1。
        - 采用在线更新，在线学习。
        """
        n = len(sub_nodes)
        node_to_index = {node: idx for idx, node in enumerate(sub_nodes)}

        if start_node not in node_to_index or goal_node not in node_to_index:
            return np.zeros((n, n)), node_to_index

        start_idx = node_to_index[start_node]
        goal_idx = node_to_index[goal_node]

        # 初始化Q表
        Q_table = np.zeros((n, n))
        MAX_STEPS_PER_EPISODE = n * 2 # 每轮最多走多少步
        num_episodes = 3000  # 增加训练轮次以确保收敛

        for episode in range(num_episodes):
            current_idx = start_idx
            steps = 0

            while current_idx != goal_idx and steps < MAX_STEPS_PER_EPISODE:
                # === 关键修正1: 使用ld_ar_matrix判断动作合法性 ===
                # 找出所有非障碍物（即合法）的下一个节点索引
                valid_next_idxs = np.where(ld_ar_matrix[current_idx] != self.obstacle_reward)[0]
                if len(valid_next_idxs) == 0:
                    break  # 无路可走，结束本回合

                # ε-greedy 选择动作
                if np.random.rand() < self.epsilon:
                    next_idx = np.random.choice(valid_next_idxs)
                else:
                    q_values = Q_table[current_idx, valid_next_idxs]
                    max_q = np.max(q_values)
                    best_actions = valid_next_idxs[q_values == max_q]
                    next_idx = np.random.choice(best_actions)

                # === 关键修正2: 定义清晰、有效的奖励 ===
                # reward = ld_ar_matrix[current_idx, next_idx]
                if next_idx == goal_idx:
                    reward = 100  # 到达目标的巨大奖励
                else:
                    reward = -1  # 每走一步的小惩罚，鼓励最短路径
                # ===========================================

                # Q-learning 标准更新
                max_future_q = np.max(Q_table[next_idx, :])
                current_q = Q_table[current_idx, next_idx]
                new_q = current_q + self.alpha * (reward + self.gamma * max_future_q - current_q)
                Q_table[current_idx, next_idx] = new_q

                current_idx = next_idx
                steps += 1

        return Q_table, node_to_index

    # ---------------------------------------------------------

    # 修改 plan_path 函数中的回溯部分
    def plan_path(self, start_coord, goal_coord):
        start_node = coord_to_node_id(start_coord, self.grid_width)
        goal_node = coord_to_node_id(goal_coord, self.grid_width)
        if not self._is_valid_coord(start_coord) or not self._is_valid_coord(goal_coord):
            return None

        # 构建LD-A-R矩阵
        ld_ar_matrix, sub_nodes = self._build_ld_ar_matrix(start_node, goal_node)
        # print(ld_ar_matrix)
        if len(sub_nodes) == 0:
            return None

        # 训练Q表
        Q_table, node_to_index = self._q_learning_train(ld_ar_matrix, sub_nodes, start_node, goal_node)
        # print(Q_table)

        # --- 路径回溯 ---
        path_nodes = []
        current_node = start_node
        visited = set()  # 防止循环
        max_steps = len(sub_nodes) * 4  # 或者更大，视地图复杂度而定

        if start_node == goal_node:
            return [start_coord]

        for step in range(max_steps):
            path_nodes.append(current_node)
            visited.add(current_node)

            if current_node == goal_node:
                break

            if current_node not in node_to_index:
                return None
            current_idx = node_to_index[current_node]

            # 获取合法的下一个动作
            valid_next_idxs = np.where(ld_ar_matrix[current_idx] != self.obstacle_reward)[0]
            if len(valid_next_idxs) == 0:
                return None

            # === 关键修正: 贪婪选择 + 防回头 ===
            best_next_idx = None
            best_q_value = -np.inf

            for next_idx in valid_next_idxs:
                next_node = sub_nodes[next_idx]
                # 跳过已访问的节点，防止原地打转
                if next_node in visited:
                    continue
                # 选择Q值最高的未访问节点
                if Q_table[current_idx, next_idx] > best_q_value:
                    best_q_value = Q_table[current_idx, next_idx]
                    best_next_idx = next_idx

            # 如果找不到未访问的合法节点，则失败
            if best_next_idx is None:
                return None

            next_node = sub_nodes[best_next_idx]
            current_node = next_node
        else:
            # 超过最大步数仍未到达终点
            return None

        path_coords = [node_id_to_coord(node, self.grid_width) for node in path_nodes]
        return path_coords