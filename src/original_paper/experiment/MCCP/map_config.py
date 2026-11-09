# 50x50 四种仓库地图布局配置

# ========================
# Map A: Standard Grid Layout (50x50)
# ========================
SHELF_MAP_A = {}
# 每隔 8 行一组货架，共 6 组
for row_group in range(6):
    y_base = 2 + row_group * 8
    # 每组两排货架，上下分布
    shelf_name_h1 = f'货架区H_{row_group * 2 + 1}_排1'
    shelf_name_h2 = f'货架区H_{row_group * 2 + 1}_排2'
    SHELF_MAP_A[shelf_name_h1] = [(x, y_base) for x in range(2, 24)]
    SHELF_MAP_A[shelf_name_h2] = [(x, y_base + 2) for x in range(2, 24)]

    shelf_name_v1 = f'货架区V_{row_group * 2 + 2}_排1'
    shelf_name_v2 = f'货架区V_{row_group * 2 + 2}_排2'
    SHELF_MAP_A[shelf_name_v1] = [(x + 26, y_base) for x in range(2, 22)]
    SHELF_MAP_A[shelf_name_v2] = [(x + 26, y_base + 2) for x in range(2, 22)]

OUTBOUND_MAP_A = {
    '出库口': [(49, y) for y in range(10, 40)],  # 右侧中间长条出口
}

REGION_VALUES_A = {key: 2 for key in SHELF_MAP_A.keys()}
REGION_VALUES_A.update({'出库口': 7})


# ========================
# Map B: Central Corridor Layout (50x50)
# ========================
SHELF_MAP_B = {}
# 左右两侧密集货架，中间留出纵向主干道
for y_start in range(2, 48, 4):
    # 左侧区块
    for x in range(2, 20):
        SHELF_MAP_B.setdefault(f'左侧区块_{y_start // 4}', []).append((x, y_start))
    # 右侧区块
    for x in range(30, 48):
        SHELF_MAP_B.setdefault(f'右侧区块_{y_start // 4}', []).append((x, y_start))

OUTBOUND_MAP_B = {
    '出库口': [(49, y) for y in [5, 15, 25, 35, 45]],  # 分散出口点
}

REGION_VALUES_B = {key: 3 for key in SHELF_MAP_B.keys()}
REGION_VALUES_B.update({'出库口': 7})


# ========================
# Map C: Ring Road Layout (50x50)
# ========================
SHELF_MAP_C = {}
# 中心实心矩形货架区（只保留外框）
center_shelf = []
for x in range(15, 35):
    for y in range(15, 35):
        if (x == 15 or x == 34 or y == 15 or y == 34) and \
                not ((x == 15 and y in [20, 21]) or  # 左边的门
                     (x == 34 and y in [20, 21]) or  # 右边的门
                     (y == 15 and x in [20, 21]) or  # 上边的门
                     (y == 34 and x in [20, 21])):  # 下边的门
            center_shelf.append((x, y))
SHELF_MAP_C['中心环形货架'] = center_shelf

# 外围环形通道内散布小型存储点
small_stores = [
    (5, 10), (5, 40), (45, 10), (45, 40),
    (10, 5), (10, 45), (40, 5), (40, 45),
    (25, 2), (25, 48), (2, 25), (48, 25)
]
for i, pos in enumerate(small_stores):
    SHELF_MAP_C[f'外围存储点_{i}'] = [pos]

OUTBOUND_MAP_C = {
    '出库口': [(49, y) for y in [5, 15, 25, 35, 45]],
}

REGION_VALUES_C = {key: 4 for key in SHELF_MAP_C.keys()}
REGION_VALUES_C.update({'出库口': 7})


# ========================
# Map D: Sparse Random Layout (50x50)
# ========================
import random
random.seed(42)

SHELF_MAP_D = {}
shelf_blocks = []
for i in range(30):  # 30 个 2x2 货架块
    x = random.randint(5, 45)
    y = random.randint(5, 45)
    block_coords = [(x, y), (x+1, y), (x, y+1), (x+1, y+1)]
    # 检查是否重叠
    if not any(coord in [c for b in shelf_blocks for c in b] for coord in block_coords):
        shelf_blocks.append(block_coords)
        SHELF_MAP_D[f'随机货架_{i}'] = block_coords

OUTBOUND_MAP_D = {
    '出库口': [(49, y) for y in range(20, 30)],  # 中部出口
}

REGION_VALUES_D = {key: 5 for key in SHELF_MAP_D.keys()}
REGION_VALUES_D.update({'出库口': 7})

# ========================
# Map E: High-Density Grid Layout (80x80) - FOR TESTING IMPROVEMENTS
# ========================

SHELF_MAP_E = {}

# 扩大版本的 Map A：将每隔 8 行扩大到 12 行
for row_group in range(6):
    y_base = 3 + row_group * 12  # 从 8 改为 12

    # 每组两排货架，上下分布
    shelf_name_h1 = f'货架区H_{row_group * 2 + 1}_排1'
    shelf_name_h2 = f'货架区H_{row_group * 2 + 1}_排2'
    SHELF_MAP_E[shelf_name_h1] = [(x, y_base) for x in range(3, 35)]  # 范围扩大
    SHELF_MAP_E[shelf_name_h2] = [(x, y_base + 3) for x in range(3, 35)]

    shelf_name_v1 = f'货架区V_{row_group * 2 + 2}_排1'
    shelf_name_v2 = f'货架区V_{row_group * 2 + 2}_排2'
    SHELF_MAP_E[shelf_name_v1] = [(x + 38, y_base) for x in range(3, 32)]  # 范围扩大
    SHELF_MAP_E[shelf_name_v2] = [(x + 38, y_base + 3) for x in range(3, 32)]

OUTBOUND_MAP_E = {
    '出库口': [(79, y) for y in range(15, 65)],  # 右侧长条出口（扩大）
}

REGION_VALUES_E = {key: 2 for key in SHELF_MAP_E.keys()}
REGION_VALUES_E.update({'出库口': 7})


# ========================
# Map F: Central Corridor Layout (80x80)
# ========================
SHELF_MAP_F = {}
#扩大版B
# 每 6 行一组，共 13 组（6*13=78）
for y_start in range(2, 80, 6):
    group_id = y_start // 6
    # 左侧区块
    for x in range(2, 29):  # 宽度 27
        SHELF_MAP_F.setdefault(f'左侧区块_{group_id}', []).append((x, y_start))
    # 右侧区块
    for x in range(51, 79):  # 宽度 28
        SHELF_MAP_F.setdefault(f'右侧区块_{group_id}', []).append((x, y_start))

OUTBOUND_MAP_F = {
    '出库口': [(79, y) for y in range(10, 71, 10)],  # 多个出口点：10,20,...,70
}
REGION_VALUES_F = {key: 3 for key in SHELF_MAP_F.keys()}
REGION_VALUES_F.update({'出库口': 7})

# ========================
# Map G: Ring Road Layout (80x80)
# ========================
#放大C
SHELF_MAP_G = {}
center_shelf = []
# 环形区域：x,y ∈ [20, 60)
for x in range(20, 60):
    for y in range(20, 60):
        if (x == 20 or x == 59 or y == 20 or y == 59) and \
           not ((x == 20 and 35 <= y <= 44) or   # 左门宽 10
                (x == 59 and 35 <= y <= 44) or   # 右门
                (y == 20 and 35 <= x <= 44) or   # 上门
                (y == 59 and 35 <= x <= 44)):    # 下门
            center_shelf.append((x, y))
SHELF_MAP_G['中心环形货架'] = center_shelf

# 外围存储点：靠近四角和中点
small_stores = [
    (5, 15), (5, 65), (75, 15), (75, 65),
    (15, 5), (15, 75), (65, 5), (65, 75),
    (40, 2), (40, 78), (2, 40), (78, 40)
]
for i, pos in enumerate(small_stores):
    SHELF_MAP_G[f'外围存储点_{i}'] = [pos]

OUTBOUND_MAP_G = {
    '出库口': [(79, y) for y in range(20, 61, 8)],  # 多出口
}
REGION_VALUES_G = {key: 4 for key in SHELF_MAP_G.keys()}
REGION_VALUES_G.update({'出库口': 7})


# ========================
# Map H: Sparse Random Layout (80x80)
# ========================
random.seed(42)
SHELF_MAP_H = {}
shelf_blocks = []
# 增加到 50 个 2x2 块（原 30），分布更稀疏
for i in range(50):
    x = random.randint(5, 75)   # 原 5~45 → 现 5~75
    y = random.randint(5, 75)
    block_coords = [(x, y), (x+1, y), (x, y+1), (x+1, y+1)]
    # 检查重叠
    if not any(coord in [c for b in shelf_blocks for c in b] for coord in block_coords):
        shelf_blocks.append(block_coords)
        SHELF_MAP_H[f'随机货架_{i}'] = block_coords

OUTBOUND_MAP_H = {
    '出库口': [(79, y) for y in range(30, 50)],  # 中部出口
}
REGION_VALUES_H = {key: 5 for key in SHELF_MAP_H.keys()}
REGION_VALUES_H.update({'出库口': 7})

# ========================
# Map C Small: Ring Layout (15x15)
# ========================
SHELF_MAP_C_SMALL = {}

# 中心环形货架 - 在15x15地图中围成一圈
center_shelf = []
for x in range(3, 12):  # 3到11
    for y in range(3, 12):  # 3到11
        # 只保留外框，并在四个方向开口
        if (x == 3 or x == 11 or y == 3 or y == 11) and \
                not ((x == 3 and y in [6, 7, 8]) or  # 左边的门
                     (x == 11 and y in [6, 7, 8]) or  # 右边的门
                     (y == 3 and x in [6, 7, 8]) or  # 上边的门
                     (y == 11 and x in [6, 7, 8])):  # 下边的门
            center_shelf.append((x, y))
SHELF_MAP_C_SMALL['中心环形货架'] = center_shelf

# 外围存储点 - 在四个角落放置小型存储区
corner_stores = [
    (1, 1), (1, 2), (2, 1), (2, 2),  # 左上角
    (1, 12), (1, 13), (2, 12), (2, 13),  # 右上角
    (12, 1), (13, 1), (12, 2), (13, 2),  # 左下角
    (12, 12), (13, 12), (12, 13), (13, 13)  # 右下角
]
SHELF_MAP_C_SMALL['外围存储区'] = corner_stores

# 中间通道的独立存储点
middle_stores = [
    (7, 1), (7, 13),  # 上下中间
    (1, 7), (13, 7)   # 左右中间
]
SHELF_MAP_C_SMALL['通道存储点'] = middle_stores

OUTBOUND_MAP_C_SMALL = {
    '出库口': [(14, y) for y in range(6, 9)],  # 右侧中间出口
}

REGION_VALUES_C_SMALL = {
    '中心环形货架': 3,
    '外围存储区': 2,
    '通道存储点': 4,
    '出库口': 7
}


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



ALL_MAPS = {
    'A': (SHELF_MAP_A, OUTBOUND_MAP_A, REGION_VALUES_A),
    'B': (SHELF_MAP_B, OUTBOUND_MAP_B, REGION_VALUES_B),
    'C': (SHELF_MAP_C, OUTBOUND_MAP_C, REGION_VALUES_C),
    'D': (SHELF_MAP_D, OUTBOUND_MAP_D, REGION_VALUES_D),
    'E': (SHELF_MAP_E, OUTBOUND_MAP_E, REGION_VALUES_E),
    'F': (SHELF_MAP_F, OUTBOUND_MAP_F, REGION_VALUES_F),
    'G': (SHELF_MAP_G, OUTBOUND_MAP_G, REGION_VALUES_G),
    'H': (SHELF_MAP_H, OUTBOUND_MAP_H, REGION_VALUES_H),
    'C_SMALL':(SHELF_MAP_C_SMALL, OUTBOUND_MAP_C_SMALL, REGION_VALUES_C_SMALL),
    'STANDARD':(SHELF_MAP_STANDARD, OUTBOUND_MAP_STANDARD, REGION_VALUES_STANDARD),
    'FRANSEN': (SHELF_MAP_FRANSEN, OUTBOUND_MAP_FRANSEN, REGION_VALUES_FRANSEN)
}
