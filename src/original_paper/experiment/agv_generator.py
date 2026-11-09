import json
import random

# 原始 AGV 数据（你提供的前200个）
original_agvs = {
    "AGV-001": {"type": "防爆型", "position": [3, 3], "status": "idle", "speed": 1, "task_start": None, "task_duration": None, "priority": 1},
    # ... （此处省略，实际使用时请保留你提供的完整200项）
    "AGV-200": {"type": "防震型", "position": [2, 12], "status": "idle", "speed": 1, "task_start": None, "task_duration": None, "priority": 1}
}

# 如果你有原始数据文件，也可以用 json.load() 读入
# 但这里我们假设 original_agvs 已包含前200个

# 定义类型循环
types = ["防爆型", "冷链型", "标准型", "防震型"]

# 构建完整 agv_dict
agv_dict = {}

# 先加入原始的200个（确保格式一致）
# for agv_id, info in original_agvs.items():
#     agv_dict[agv_id] = info

# 生成 AGV-201 到 AGV-1000
for i in range(1, 1001):
    agv_id = f"AGV-{i:03d}"  # 格式化为 AGV-201, ..., AGV-1000
    agv_type = types[(i - 1) % 4]  # 循环分配类型（注意：AGV-001 是 index 0 → 防爆型）
    position = [random.randint(0, 49), random.randint(0, 49)]
    agv_dict[agv_id] = {
        "type": agv_type,
        "position": position,
        "status": "idle",
        "speed": 1,
        "task_start": None,
        "task_duration": None,
        "priority": 1
    }

# 可选：按 AGV 编号排序（美观）
sorted_agv_dict = dict(sorted(agv_dict.items(), key=lambda x: int(x[0].split('-')[1])))

# 输出为 JSON 字符串（可写入文件）
json_str = json.dumps(sorted_agv_dict, ensure_ascii=False, separators=(', ', ': '))
formatted_json = json_str.replace('}, "', '},\n"')
final_json = "{\n" + formatted_json[1:-1] + "\n}"
# 保存到文件
with open("agvs_1000.json", "w", encoding="utf-8") as f:
    # 注意：separators=(', ', ': ') 保留逗号后和冒号后的空格
    f.write(final_json)



print("✅ 已生成 AGV-001 到 AGV-1000，共 1000 个 AGV，保存为 agvs_1000.json")