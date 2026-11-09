"""
search_node.py
对应 C++ traffic_mapf/search_node.h + Memory.h

包含：
  SNode      : 搜索节点（对应 C++ struct s_node）
  MemoryPool : 基于标签的内存池，reset() 只需 O(1)

比较器（用于堆排序，内联在 heap.py 中实现）：
  cmp_less_of  : 先比 op_flow，再比 f，再比 -g（用于 OPEN 队列，无 FOCAL）
  cmp_less_jam : 先比 op_flow，再比 (vertex_flow+f)，再比 (vertex_flow+g)，再比 -g
                 （用于 FOCAL 队列）
  cmp_less_f   : 先比 f，再比 -g（用于 OPEN 队列，有 FOCAL）
  re_of        : 严格小于判断（op_flow 优先，然后 f），用于开/闭列表更新
  re_jam       : 严格小于判断（FOCAL 更新用）
  re_f         : 严格小于判断（f 优先），用于 OPEN 更新（FOCAL 模式）
"""

from __future__ import annotations
from typing import Optional, List


# ===========================================================================
# SNode（搜索节点）
# ===========================================================================

class SNode:
    """
    对应 C++ struct s_node
    用于 A* 搜索的单个节点，支持内存池复用。

    字段：
      label          : 所属内存池的当前批次标签（用于判断是否"已生成"）
      id             : 节点位置（map 中的 loc）；-1 表示未生成
      g              : 到此节点的代价（含顶点流惩罚）
      h              : 启发式值（到目标的估计距离）
      op_flow        : 对向流代价（contraflow cost）累积值
      all_vertex_flow: 顶点拥堵代价累积值（仅 FOCAL_SEARCH 模式使用）
      closed         : 是否已关闭
      depth          : 路径长度（步数）
      tie_breaker    : 随机打破平局（可选）
      parent         : 父节点指针
      priority       : 在堆中的位置索引（heap 内部使用）
    """
    __slots__ = (
        "label", "id", "g", "h", "op_flow", "all_vertex_flow",
        "closed", "depth", "tie_breaker", "parent", "priority"
    )

    def __init__(
        self,
        id: int = -1,
        g: int = 0,
        h: int = 0,
        op_flow: int = 0,
        depth: int = 0,
        all_vertex_flow: int = 0,
    ):
        self.label: int = 0
        self.id: int = id
        self.g: int = g
        self.h: int = h
        self.op_flow: int = op_flow
        self.all_vertex_flow: int = all_vertex_flow
        self.closed: bool = False
        self.depth: int = depth
        self.tie_breaker: float = 0.0
        self.parent: Optional["SNode"] = None
        self.priority: int = 0  # 在堆数组中的索引位置

    # 核心访问器
    def get_f(self) -> int:
        return self.g + self.h

    def is_closed(self) -> bool:
        return self.closed

    def close(self) -> None:
        self.closed = True

    def get_op_flow(self) -> int:
        return self.op_flow

    def get_all_vertex_flow(self) -> int:
        return self.all_vertex_flow

    def set_all_flow(self, op_flow: int, all_vertex_flow: int) -> None:
        self.op_flow = op_flow
        self.all_vertex_flow = all_vertex_flow

    def get_g(self) -> int:
        return self.g

    def get_h(self) -> int:
        return self.h

    def reset(self) -> None:
        """对应 C++ s_node::reset()"""
        self.label = 0
        self.id = -1
        self.g = 0
        self.h = 0
        self.op_flow = 0
        self.all_vertex_flow = 0
        self.closed = False
        self.depth = 0
        self.parent = None
        self.tie_breaker = 0.0

    def __repr__(self) -> str:
        return (f"SNode(id={self.id}, g={self.g}, h={self.h}, "
                f"f={self.get_f()}, op={self.op_flow}, closed={self.closed})")


# ===========================================================================
# 比较器函数（用于堆，对应 C++ 中的各 comparator struct）
# ===========================================================================

def cmp_less_of(a: SNode, b: SNode) -> bool:
    """
    对应 C++ struct cmp_less_of（OPEN 队列排序，无 FOCAL 模式）
    优先级（越小越先出队）：
      1. op_flow 小
      2. f 小
      3. g 大（-g 小）
    """
    if a.op_flow != b.op_flow:
        return a.op_flow < b.op_flow
    if a.get_f() != b.get_f():
        return a.get_f() < b.get_f()
    return a.g > b.g  # 同 f 时，g 大的优先（贪心）


def cmp_less_jam(a: SNode, b: SNode) -> bool:
    """
    对应 C++ struct cmp_less_jam（FOCAL 队列排序）
    优先级：
      1. op_flow 小
      2. all_vertex_flow + f 小
      3. all_vertex_flow + g 小
      4. g 大
    """
    if a.op_flow != b.op_flow:
        return a.op_flow < b.op_flow
    avf_a = a.all_vertex_flow + a.get_f()
    avf_b = b.all_vertex_flow + b.get_f()
    if avf_a != avf_b:
        return avf_a < avf_b
    avg_a = a.all_vertex_flow + a.g
    avg_b = b.all_vertex_flow + b.g
    if avg_a != avg_b:
        return avg_a < avg_b
    return a.g > b.g  # 同时，g 大的优先


def cmp_less_f(a: SNode, b: SNode) -> bool:
    """
    对应 C++ struct cmp_less_f（FOCAL 模式下 OPEN 队列排序）
    优先级：
      1. f 小
      2. g 大
    """
    if a.get_f() != b.get_f():
        return a.get_f() < b.get_f()
    return a.g > b.g


def re_of(a: SNode, b: SNode) -> bool:
    """
    对应 C++ struct re_of（严格小于，用于更新 OPEN 中已有节点）
    a 是否比 b 更优（无 FOCAL）：
      1. op_flow 更小，或
      2. op_flow 相等且 f 更小
    """
    if a.op_flow != b.op_flow:
        return a.op_flow < b.op_flow
    return a.get_f() < b.get_f()


def re_jam(a: SNode, b: SNode) -> bool:
    """
    对应 C++ struct re_jam（严格小于，用于 FOCAL 中更新节点）
    在 f 相同的前提下：
      1. op_flow 更小，或
      2. op_flow 相等且 (all_vertex_flow+f) 更小，或
      3. 以上相等且 g 更大
    注意：C++ 中先检查 f 不同则直接返回 false
    """
    if a.get_f() != b.get_f():
        return False
    if a.op_flow != b.op_flow:
        return a.op_flow < b.op_flow
    avf_a = a.all_vertex_flow + a.get_f()
    avf_b = b.all_vertex_flow + b.get_f()
    if avf_a != avf_b:
        return avf_a < avf_b
    return a.g > b.g


def re_f(a: SNode, b: SNode) -> bool:
    """
    对应 C++ struct re_f（严格小于，FOCAL 模式 OPEN 更新）
    a.f < b.f
    """
    return a.get_f() < b.get_f()


# ===========================================================================
# MemoryPool
# ===========================================================================

class MemoryPool:
    """
    对应 C++ class MemoryPool

    基于标签（label）的内存池：
      - nodes[id] 是 SNode 对象数组（按 id = location 索引）
      - reset() 只需将 label+1，O(1) 完成"清空"
      - has_node(id): nodes[id].label == label && nodes[id].id != -1
      - is_closed(id): 上述条件且 closed == True

    用法：
      pool = MemoryPool(map_size)
      node = pool.generate_node(id, g, h, op_flow, depth)
      pool.reset()   # 下次搜索前调用，所有旧节点自动"失效"
    """

    def __init__(self, size: int = 0):
        self._size: int = 0
        self._index: int = 0   # 已生成节点数（对应 C++ index）
        self._label: int = 0
        self._nodes: List[SNode] = []
        self._ready: bool = False

        if size > 0:
            self.init(size)

    def init(self, size: int) -> None:
        """对应 C++ MemoryPool::init()"""
        self._size = size
        self._index = 0
        self._label = 0
        self._nodes = [SNode() for _ in range(size)]
        self._ready = True

    def is_ready(self) -> bool:
        return self._ready

    def generated(self) -> int:
        """返回当前批次已生成的节点数"""
        return self._index

    def has_node(self, id: int) -> bool:
        """
        对应 C++ MemoryPool::has_node(int id)
        节点在当前批次中已生成（label 匹配且 id 有效）
        """
        n = self._nodes[id]
        return n.label == self._label and n.id == id

    def is_closed(self, id: int) -> bool:
        """对应 C++ MemoryPool::is_closed(int id)"""
        n = self._nodes[id]
        if n.label != self._label:
            return False
        return n.is_closed()

    def get_node(self, id: int) -> SNode:
        """
        对应 C++ MemoryPool::get_node(int id)
        返回已生成节点的引用（若未生成则报错）
        """
        n = self._nodes[id]
        assert n.label == self._label and n.id != -1, \
            f"MemoryPool.get_node: node {id} not generated yet"
        return n

    def generate_node(
        self,
        id: int,
        g: int,
        h: int,
        op_flow: int,
        depth: int,
        all_vertex_flow: int = 0,
    ) -> SNode:
        """
        对应 C++ MemoryPool::generate_node()
        在池中分配 id 对应的节点（同一 label 内不可重复生成）
        """
        n = self._nodes[id]
        assert not (n.label == self._label and n.id != -1), \
            f"MemoryPool.generate_node: node {id} already generated"
        n.reset()
        n.label = self._label
        n.id = id
        n.g = g
        n.h = h
        n.op_flow = op_flow
        n.depth = depth
        n.all_vertex_flow = all_vertex_flow
        self._index += 1
        return n

    def close_node(self, id: int) -> None:
        """对应 C++ MemoryPool::close_node()"""
        n = self._nodes[id]
        assert n.label == self._label and n.id != -1, \
            f"MemoryPool.close_node: node {id} not generated yet"
        n.close()

    def free_node(self, id: int) -> None:
        """对应 C++ MemoryPool::free_node()"""
        n = self._nodes[id]
        assert n.id != -1, "MemoryPool.free_node: node not generated"
        n.reset()
        self._index -= 1

    def reset(self) -> None:
        """
        对应 C++ MemoryPool::reset()
        O(1) 清空所有节点（只需递增 label）
        """
        self._index = 0
        self._label += 1
