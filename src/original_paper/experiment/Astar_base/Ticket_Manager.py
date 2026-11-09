from collections import defaultdict,OrderedDict
from typing import Dict, List, Tuple, Set
import json

class TicketManager:
    def __init__(self):
        self.node_reservations = defaultdict(dict)  # {((x,y),t): {agv_id: priority}}
        self.edge_reservations = defaultdict(dict)  # 🔺边预约 {((x1,y1),(x2,y2), t): {agv_id: priority}}
        self.agv_reservations = defaultdict(set)  # ✨ 新增反向索引 {agv_id: set( (node, t) 或 ('edge', ...) )}

    def save_current_reservations_by_agv(self, filename='final_reservations_by_agv.json'):
        """
        所有AGV规划完成后调用
        将当前所有预约按 AGV ID 分组，输出到JSON
        """
        # 使用 OrderedDict 确保 AGV ID 有序
        agv_reservations = OrderedDict()

        # 1. 收集 node_reservations
        for (x, y), t in self.node_reservations.keys():
            agv_dict = self.node_reservations[(x, y), t]
            for agv_id, priority in agv_dict.items():
                if agv_id not in agv_reservations:
                    agv_reservations[agv_id] = []

                agv_reservations[agv_id].append({
                    "type": "node",
                    "position": [float(x), float(y)],
                    "time": float(t),
                    "priority": priority
                })

        # 2. 收集 edge_reservations
        for (x1, y1), (x2, y2), t in self.edge_reservations.keys():
            agv_dict = self.edge_reservations[((x1, y1), (x2, y2), t)]
            for agv_id, priority in agv_dict.items():
                if agv_id not in agv_reservations:
                    agv_reservations[agv_id] = []

                agv_reservations[agv_id].append({
                    "type": "edge",
                    "from": [float(x1), float(y1)],
                    "to": [float(x2), float(y2)],
                    "time": float(t),
                    "priority": priority
                })

        # 3. 按 AGV ID 排序，并为每个 AGV 的预约按时间排序
        result = []
        for agv_id in sorted(agv_reservations.keys()):
            reservations = agv_reservations[agv_id]
            # 按时间排序，便于观察
            reservations.sort(key=lambda x: x["time"])
            result.append({
                "agv_id": agv_id,
                "reservations": reservations
            })

        # 4. 保存到文件
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"✅ 按 AGV 分组的预约已保存到: {filename}")
        for item in result:
            print(f"   AGV{item['agv_id']}: {len(item['reservations'])} 个预约")

    def reserve(self, agv_id, reservations, priority):
        """
        reservations: list of items, each is either:
        - (node, t) -> 节点预约
        - ('edge', x1, y1, x2, y2, t)  -> 边预约
        """
        # 🔺 第一阶段：检查所有预约是否冲突
        for item in reservations:
            if len(item) == 2:  # 节点预约: (node, t)
                node, t = item
                key = (node, t)
                existing = self.node_reservations[key]
                for other_id, other_priority in existing.items():
                    if other_priority >= priority and other_id != agv_id:
                        return False  # 冲突，直接失败

            elif item[0] == 'edge':  # 边预约: ('edge', x1,y1,x2,y2,t)
                _, x1, y1, x2, y2, t = item
                edge_key = ((x1, y1), (x2, y2), t)
                existing = self.edge_reservations[edge_key]
                for other_id, other_priority in existing.items():
                    if other_priority >= priority and other_id != agv_id:
                        return False
        # 注册券
        for item in reservations:
            if len(item)==2:
                node,t=item
                self.node_reservations[(node,t)][agv_id] = priority
                self.agv_reservations[agv_id].add((node,t))

            elif item[0]=='edge':
                _,x1,y1,x2,y2,t = item
                edge_key = ((x1,y1),(x2,y2),t)
                self.edge_reservations[edge_key][agv_id] = priority
                self.agv_reservations[agv_id].add(('edge',x1,y1,x2,y2,t))

        return True



    def is_node_conflict(self, node, t, agv_id, priority):
        """检查节点冲突"""
        existing = self.node_reservations.get((node, t), {})
        return any(p >= priority for aid, p in existing.items() if aid != agv_id)
        # existing.items()：遍历(agv_id, priority)键值对
        # if aid != agv_id：排除当前 AGV 自身的占用记录（允许同一 AGV 重复占用）
        # p >= priority：检查其他AGV的优先级是否 ≥ 当前AGV的优先级
        # any(...)：如果存在任意一个满足条件的占用，返回True（冲突存在）

    def is_edge_conflict(self,x1,y1,x2,y2,t,agv_id,priority):
        """
        是否有其他AGV沿(x1,y1)->(x2,y2)行驶
        """
        edge_key = ((x1,y1),(x2,y2),t)
        existing = self.edge_reservations.get(edge_key,{})
        return any(p >= priority for aid, p in existing.items() if aid != agv_id)

    def release_all(self, agv_id: str) -> None:
        """释放 AGV 所有预约（节点 + 边）"""
        if agv_id not in self.agv_reservations:
            return

        for key in list(self.agv_reservations[agv_id]):
            if isinstance(key, tuple) and len(key) == 2:  # (node, t)
                node, t = key
                if (node, t) in self.node_reservations:
                    self.node_reservations[(node, t)].pop(agv_id, None)
                    if not self.node_reservations[(node, t)]:
                        del self.node_reservations[(node, t)]
            elif isinstance(key, tuple) and key[0] == 'edge':  # ('edge', ...)
                _, x1, y1, x2, y2, t = key
                edge_key = ((x1, y1), (x2, y2), t)
                if edge_key in self.edge_reservations:
                    self.edge_reservations[edge_key].pop(agv_id, None)
                    if not self.edge_reservations[edge_key]:
                        del self.edge_reservations[edge_key]

        # 清理反向索引
        if agv_id in self.agv_reservations:
            del self.agv_reservations[agv_id]

    def release(self, current_time: float):
        """释放所有时间早于 current_time 的节点和边预约"""
        released_count = 0

        # 释放节点预约
        expired_node_keys = [key for key in self.node_reservations.keys() if key[1] < current_time]
        for (node, t) in expired_node_keys:
            for agv_id in self.node_reservations[(node, t)]:
                self.agv_reservations[agv_id].discard((node, t))
                if agv_id in self.agv_reservations and not self.agv_reservations[agv_id]:
                    del self.agv_reservations[agv_id]
            del self.node_reservations[(node, t)]
            released_count += 1

        # 释放边预约
        expired_edge_keys = [key for key in self.edge_reservations.keys() if key[2] < current_time]
        for ((x1,y1), (x2,y2), t) in expired_edge_keys:
            for agv_id in self.edge_reservations[((x1,y1), (x2,y2), t)]:
                self.agv_reservations[agv_id].discard(('edge', x1, y1, x2, y2, t))
                if agv_id in self.agv_reservations and not self.agv_reservations[agv_id]:
                    del self.agv_reservations[agv_id]
            del self.edge_reservations[((x1,y1), (x2,y2), t)]
            released_count += 1

        return released_count

    def get_node_reservations(self, node: Tuple[int, int], t: int) -> Dict[str, float]:
        """
        获取指定节点和时间的所有预定信息
        返回: {agv_id: priority} 字典
        """
        return self.node_reservations.get((node, t), {}).copy()  # 返回副本避免外部修改

    def get_all_reservations(self) -> Dict:
        """
            获取当前所有被预约的时空券（节点 + 边）

            返回: 字典，包含两类预约
                - 'node_reservations': { (node, t): {agv_id: priority} }
                - 'edge_reservations': { ((x1,y1),(x2,y2), t): {agv_id: priority} }
            示例:
                {
                    'node_reservations': {((5, 10), 15): {'agv1': 1.0, 'agv2': 0.5}},
                    'edge_reservations': {((5,10), (6,10), 15): {'agv3': 0.8}}
                }
            """

        return {
            'node_reservations': {k: v.copy() for k, v in self.node_reservations.items()},
            'edge_reservations': {k: v.copy() for k, v in self.edge_reservations.items()}
        }

    def cancel_future_reservations(self, agv_id: str, cancel_time):
        """取消 agv_id 在 cancel_time 及之后的所有预约"""
        to_remove = []
        for key in list(self.agv_reservations[agv_id]):
            if isinstance(key, tuple) and len(key) == 2:
                node, t = key
                if t >= cancel_time:
                    to_remove.append(key)
            elif isinstance(key, tuple) and key[0] == 'edge':
                _, x1, y1, x2, y2, t = key
                if t >= cancel_time:
                    to_remove.append(key)

        for key in to_remove:
            if isinstance(key, tuple) and len(key) == 2:
                node, t = key
                if (node, t) in self.node_reservations:
                    self.node_reservations[(node, t)].pop(agv_id, None)
                    if not self.node_reservations[(node, t)]:
                        del self.node_reservations[(node, t)]
            elif key[0] == 'edge':
                _, x1, y1, x2, y2, t = key
                edge_key = ((x1, y1), (x2, y2), t)
                if edge_key in self.edge_reservations:
                    self.edge_reservations[edge_key].pop(agv_id, None)
                    if not self.edge_reservations[edge_key]:
                        del self.edge_reservations[edge_key]
            self.agv_reservations[agv_id].discard(key)
        if agv_id in self.agv_reservations and not self.agv_reservations[agv_id]:
            del self.agv_reservations[agv_id]
