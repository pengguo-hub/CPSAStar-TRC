def coord_to_node_id(coord, grid_width):
    """
    将二维坐标 (x, y) 转换为一维节点ID。

    Args:
        coord (tuple): (x, y) 坐标。
        grid_width (int): 网格地图的宽度（列数）。

    Returns:
        int: 对应的节点ID。
    """
    x, y = coord
    return y * grid_width + x


def node_id_to_coord(node_id, grid_width):
    """
    将一维节点ID转换为二维坐标 (x, y)。

    Args:
        node_id (int): 节点ID。
        grid_width (int): 网格地图的宽度（列数）。

    Returns:
        tuple: (x, y) 坐标。
    """
    y = node_id // grid_width
    x = node_id % grid_width
    return (x, y)


def manhattan_distance(node_a, node_b, grid_width):
    """
    计算两个节点之间的曼哈顿距离。

    Args:
        node_a (int): 起始节点ID。
        node_b (int): 目标节点ID。
        grid_width (int): 网格地图的宽度。

    Returns:
        int: 曼哈顿距离。
    """
    x1, y1 = node_id_to_coord(node_a, grid_width)
    x2, y2 = node_id_to_coord(node_b, grid_width)
    return abs(x1 - x2) + abs(y1 - y2)