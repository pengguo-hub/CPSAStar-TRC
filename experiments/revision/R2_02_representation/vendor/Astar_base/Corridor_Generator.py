class CorridorGenerator:
    def __init__(self, max_width=3, min_width=1):
        self.max_width = max_width
        self.min_width = min_width

    def create_between(self, start, end, width=None):
        """创建两点间的走廊"""
        width = self.max_width if width is None else width
        return {
            'start': start,
            'end': end,
            'width': width,
            'boundaries': self._calculate_boundaries(start, end, width)
        }

    def adjust_for_conflict(self, corridor):
        """因冲突缩小走廊"""
        corridor['width'] = max(self.min_width, corridor['width'] - 1)
        corridor['boundaries'] = self._calculate_boundaries(
            corridor['start'], corridor['end'], corridor['width'])
        return corridor

    def is_in_corridor(self, point, corridor):
        """判断点是否在走廊边界内"""
        x, y = point
        min_x, min_y, max_x, max_y = map(int,corridor['boundaries'])
        return (min_x <= x <= max_x) and (min_y <= y <= max_y)

    def _calculate_boundaries(self, start, end, width):
        """计算走廊边界"""
        x1, y1 = start
        x2, y2 = end
        min_x = min(x1, x2) - width
        max_x = max(x1, x2) + width
        min_y = min(y1, y2) - width
        max_y = max(y1, y2) + width
        return (min_x, min_y, max_x, max_y)