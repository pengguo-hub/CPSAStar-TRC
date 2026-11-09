# ========================
#16×11
# ========================
SHELF_MAP_STANDARD = {
    '货架区1': [(1, y) for y in range(1, 5)],
    '货架区2': [(1, y) for y in range(6, 10)],
    '货架区3': [(3, y) for y in range(1, 5)],
    '货架区4': [(3, y) for y in range(6, 10)],
    '货架区5': [(5, y) for y in range(1, 5)],
    '货架区6': [(5, y) for y in range(6, 10)],
    '货架区7': [(7, y) for y in range(1, 5)],
    '货架区8': [(7, y) for y in range(6, 10)],
    '货架区9': [(9, y) for y in range(1, 5)],
    '货架区10': [(9, y) for y in range(6, 10)],
    '货架区11': [(11, y) for y in range(1, 5)],
    '货架区12': [(11, y) for y in range(6, 10)],
    '货架区13': [(13, y) for y in range(1, 5)],
    '货架区14': [(13, y) for y in range(6, 10)],
}

OUTBOUND_MAP_STANDARD = {
    # '包装台': [(0, y) for y in range(0, 3)],
    # '出库口': [(0, y) for y in range(4, 7)],
    # '入库口': [(0, y) for y in range(7, 10)],
    '工作站': [(15, y) for y in range(3, 8)],
}

REGION_VALUES_STANDARD = {
    '货架区1': 2,
    '货架区2': 2,
    '货架区3': 2,
    '货架区4': 2,
    '货架区5': 2,
    '货架区6': 2,
    '货架区7': 2,
    '货架区8': 2,
    '货架区9': 2,
    '货架区10': 2,
    '货架区11': 2,
    '货架区12': 2,
    '货架区13': 2,
    '货架区14': 2,
    '包装台': 3,
    '出库口': 4,
    '入库口': 5,
    '工作站': 6,
}

# ========================
#20×20
# ========================
SHELF_MAP_FRANSEN = {
    '货架行1': [(2, 2), (5, 2), (8, 2), (11, 2), (14, 2), (17, 2)],
    '货架行2': [(2, 5), (5, 5), (8, 5), (11, 5), (14, 5), (17, 5)],
    '货架行3': [(2, 8), (5, 8), (8, 8), (11, 8), (14, 8), (17, 8)],
    '货架行4': [(2, 11), (5, 11), (8, 11), (11, 11), (14, 11), (17, 11)],
    '货架行5': [(2, 14), (5, 14), (8, 14), (11, 14), (14, 14), (17, 14)],
    '货架行6': [(2, 17), (5, 17), (8, 17), (11, 17), (14, 17), (17, 17)],
}

OUTBOUND_MAP_FRANSEN = {
    '出库口': [(0, 5), (0, 14), (5, 0), (5, 19), (14, 0), (14, 19), (19, 5), (19, 14)],
}

REGION_VALUES_FRANSEN = {
    '货架行1': 2,
    '货架行2': 2,
    '货架行3': 2,
    '货架行4': 2,
    '货架行5': 2,
    '货架行6': 2,
    '出库口': 7,
}


# ========================
# Map RING: 3 环布局 (20x20)
# - 外圈 / 中圈：连续闭合一圈（货架，不可通行）
# - 内圈：整圈作为工作站区域（可通行终点）
# - 环间道路宽度 = 2
# - 每个环：上下左右各 2 格入口
# ========================

SHELF_MAP_RING = {}

# ------- 外圈：边界 [2,17] x [2,17] -------
outer_x0, outer_y0, outer_x1, outer_y1 = 2, 2, 17, 17
outer_mid_x = (outer_x0 + outer_x1) // 2  # = 9
outer_mid_y = (outer_y0 + outer_y1) // 2  # = 9

outer_top_entrance    = [outer_mid_x, outer_mid_x + 1]
outer_bottom_entrance = [outer_mid_x, outer_mid_x + 1]
outer_left_entrance   = [outer_mid_y, outer_mid_y + 1]
outer_right_entrance  = [outer_mid_y, outer_mid_y + 1]

SHELF_MAP_RING['外圈上'] = [
    (x, outer_y0) for x in range(outer_x0, outer_x1 + 1)
    if x not in outer_top_entrance
]
SHELF_MAP_RING['外圈下'] = [
    (x, outer_y1) for x in range(outer_x0, outer_x1 + 1)
    if x not in outer_bottom_entrance
]
SHELF_MAP_RING['外圈左'] = [
    (outer_x0, y) for y in range(outer_y0 + 1, outer_y1)
    if y not in outer_left_entrance
]
SHELF_MAP_RING['外圈右'] = [
    (outer_x1, y) for y in range(outer_y0 + 1, outer_y1)
    if y not in outer_right_entrance
]

# ------- 中圈：边界 [5,14] x [5,14] -------
mid_x0, mid_y0, mid_x1, mid_y1 = 5, 5, 14, 14
mid_mid_x = (mid_x0 + mid_x1) // 2  # = 9
mid_mid_y = (mid_y0 + mid_y1) // 2  # = 9

mid_top_entrance    = [mid_mid_x, mid_mid_x + 1]
mid_bottom_entrance = [mid_mid_x, mid_mid_x + 1]
mid_left_entrance   = [mid_mid_y, mid_mid_y + 1]
mid_right_entrance  = [mid_mid_y, mid_mid_y + 1]

SHELF_MAP_RING['中圈上'] = [
    (x, mid_y0) for x in range(mid_x0, mid_x1 + 1)
    if x not in mid_top_entrance
]
SHELF_MAP_RING['中圈下'] = [
    (x, mid_y1) for x in range(mid_x0, mid_x1 + 1)
    if x not in mid_bottom_entrance
]
SHELF_MAP_RING['中圈左'] = [
    (mid_x0, y) for y in range(mid_y0 + 1, mid_y1)
    if y not in mid_left_entrance
]
SHELF_MAP_RING['中圈右'] = [
    (mid_x1, y) for y in range(mid_y0 + 1, mid_y1)
    if y not in mid_right_entrance
]

# ------- 内圈：边界 [8,11] x [8,11]，整圈当工作站 -------
inner_x0, inner_y0, inner_x1, inner_y1 = 8, 8, 11, 11

# 内圈一整圈坐标（这里不用放到 SHELF_MAP_RING，而是放到 OUTBOUND_MAP_RING 里）
inner_ring_cells = []
# 上边
inner_ring_cells += [(x, inner_y0) for x in range(inner_x0, inner_x1 + 1)]
# 下边
inner_ring_cells += [(x, inner_y1) for x in range(inner_x0, inner_x1 + 1)]
# 左边（不含角）
inner_ring_cells += [(inner_x0, y) for y in range(inner_y0 + 1, inner_y1)]
# 右边（不含角）
inner_ring_cells += [(inner_x1, y) for y in range(inner_y0 + 1, inner_y1)]

# ------- 出库口 & 工作站 -------
# 这张图里：不再设置外圈工作站/出库口，只用内圈一整圈作为工作站区域

OUTBOUND_MAP_RING = {
    '工作站': inner_ring_cells,  # 终点只能从这些格子里选
}

# ------- 区域权重 -------
REGION_VALUES_RING = {
    '外圈上': 2, '外圈下': 2, '外圈左': 2, '外圈右': 2,
    '中圈上': 3, '中圈下': 3, '中圈左': 3, '中圈右': 3,
    # 内圈不再是货架，不在这里定义
    # '内圈上': 4, '内圈下': 4, '内圈左': 4, '内圈右': 4,
    '工作站': 6,
}



ALL_MAPS = {
    'STANDARD':(SHELF_MAP_STANDARD, OUTBOUND_MAP_STANDARD, REGION_VALUES_STANDARD),
    'FRANSEN': (SHELF_MAP_FRANSEN, OUTBOUND_MAP_FRANSEN, REGION_VALUES_FRANSEN),
    'RING': (SHELF_MAP_RING, OUTBOUND_MAP_RING, REGION_VALUES_RING),
}
