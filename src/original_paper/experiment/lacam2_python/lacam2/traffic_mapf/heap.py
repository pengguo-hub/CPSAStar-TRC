"""
heap.py
对应 C++ traffic_mapf/heap.h

实现支持 decrease_key 的最小堆（pqueue）。

C++ 中有三种实例化：
  pqueue_min_of  = pqueue<s_node, cmp_less_of,  min_q>
  pqueue_min_jam = pqueue<s_node, cmp_less_jam, min_q>
  pqueue_min_f   = pqueue<s_node, cmp_less_f,   min_q>

Python 实现：
  - 使用数组（list）模拟堆
  - 每个 SNode 维护 .priority 字段记录自身在堆数组中的索引
  - decrease_key / increase_key 通过 heapify_up / heapify_down 实现
  - contains(node) 通过 priority < size 且 elts[priority] is node 判断
"""

from __future__ import annotations
from typing import List, Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .search_node import SNode

# 比较器类型：cmp(a, b) -> True 表示 a 应排在 b 前面（a 更优先）
CmpFunc = Callable[["SNode", "SNode"], bool]


class PQueue:
    """
    对应 C++ template class pqueue<s_node, Comparator, min_q>
    支持 push / pop / top / decrease_key / increase_key / contains / clear

    is_min = True  → 最小堆（min-heap）：堆顶是比较器认为"最优"的节点
    """

    def __init__(self, cmp: CmpFunc, is_min: bool = True):
        self._cmp: CmpFunc = cmp
        self._is_min: bool = is_min
        self._elts: List[Optional["SNode"]] = []
        self._size: int = 0

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def size(self) -> int:
        return self._size

    def empty(self) -> bool:
        return self._size == 0

    def clear(self) -> None:
        """对应 C++ pqueue::clear()"""
        self._size = 0
        self._elts.clear()

    def push(self, val: "SNode") -> None:
        """
        对应 C++ pqueue::push()
        如果节点已在堆中（contains 返回 True）则跳过
        """
        if self.contains(val):
            return
        priority = self._size
        if priority >= len(self._elts):
            self._elts.append(val)
        else:
            self._elts[priority] = val
        val.priority = priority
        self._size += 1
        self._heapify_up(priority)

    def pop(self) -> Optional["SNode"]:
        """
        对应 C++ pqueue::pop()
        移除并返回堆顶元素
        """
        if self._size == 0:
            return None
        ans = self._elts[0]
        self._size -= 1
        if self._size > 0:
            self._elts[0] = self._elts[self._size]
            self._elts[0].priority = 0
            self._heapify_down(0)
        return ans

    def top(self) -> Optional["SNode"]:
        """对应 C++ pqueue::top() / peek()"""
        if self._size == 0:
            return None
        return self._elts[0]

    def peek(self) -> Optional["SNode"]:
        return self.top()

    def contains(self, n: "SNode") -> bool:
        """
        对应 C++ pqueue::contains()
        通过节点自身的 priority 字段检查是否在堆中
        """
        idx = n.priority
        if idx < self._size and self._elts[idx] is n:
            return True
        return False

    def decrease_key(self, val: "SNode") -> None:
        """
        对应 C++ pqueue::decrease_key()
        节点的优先级变高（值变小），需要向上调整
        min_q → heapify_up; max_q → heapify_down
        """
        assert val.priority < self._size, \
            f"decrease_key: priority {val.priority} out of range {self._size}"
        if self._is_min:
            self._heapify_up(val.priority)
        else:
            self._heapify_down(val.priority)

    def increase_key(self, val: "SNode") -> None:
        """对应 C++ pqueue::increase_key()"""
        assert val.priority < self._size
        if self._is_min:
            self._heapify_down(val.priority)
        else:
            self._heapify_up(val.priority)

    # ------------------------------------------------------------------
    # 内部堆操作
    # ------------------------------------------------------------------

    def _heapify_up(self, index: int) -> None:
        """
        对应 C++ pqueue::heapify_up()
        将 index 位置的节点向上调整（满足堆性质）
        """
        while index > 0:
            parent = (index - 1) >> 1
            # 若 index 比 parent 更优先，交换
            if self._cmp(self._elts[index], self._elts[parent]):
                self._swap(parent, index)
                index = parent
            else:
                break

    def _heapify_down(self, index: int) -> None:
        """
        对应 C++ pqueue::heapify_down()
        将 index 位置的节点向下调整
        """
        first_leaf = self._size >> 1
        while index < first_leaf:
            child1 = (index << 1) + 1
            child2 = (index << 1) + 2
            which = child1
            if child2 < self._size and self._cmp(self._elts[child2], self._elts[child1]):
                which = child2
            if self._cmp(self._elts[which], self._elts[index]):
                self._swap(index, which)
                index = which
            else:
                break

    def _swap(self, i1: int, i2: int) -> None:
        """对应 C++ pqueue::swap()"""
        self._elts[i1], self._elts[i2] = self._elts[i2], self._elts[i1]
        self._elts[i1].priority = i1
        self._elts[i2].priority = i2


# ===========================================================================
# 三种具体堆的工厂函数
# ===========================================================================

def PQueueMinOF() -> PQueue:
    """
    对应 C++ typedef pqueue<s_node, cmp_less_of, min_q> pqueue_min_of
    用于无 FOCAL 模式下的 OPEN 队列
    """
    from .search_node import cmp_less_of
    return PQueue(cmp_less_of, is_min=True)


def PQueueMinJam() -> PQueue:
    """
    对应 C++ typedef pqueue<s_node, cmp_less_jam, min_q> pqueue_min_jam
    用于 FOCAL 队列
    """
    from .search_node import cmp_less_jam
    return PQueue(cmp_less_jam, is_min=True)


def PQueueMinF() -> PQueue:
    """
    对应 C++ typedef pqueue<s_node, cmp_less_f, min_q> pqueue_min_f
    用于 FOCAL 模式下的 OPEN 队列（按 f 值排序）
    """
    from .search_node import cmp_less_f
    return PQueue(cmp_less_f, is_min=True)
