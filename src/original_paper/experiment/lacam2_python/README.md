# LaCAM2 One-Shot MAPF — Python 实现

本项目是 [Guided-PIBT](https://github.com/nobodyczcz/Guided-PIBT) 中 `guided-lacam2`（one-shot 场景）的完整 Python 翻译版本。
**算法逻辑、公式、数据结构与原 C++ 完全一致，仅语言不同。**

## 项目结构

```
lacam2_python/
├── main.py                  # 命令行入口（对应 C++ main.cpp）
├── assets/                  # 示例地图和场景文件
└── lacam2/
    ├── __init__.py          # 包入口，导出所有公开接口
    ├── graph.py             # Vertex / Graph / Config（对应 graph.hpp/cpp）
    ├── instance.py          # Instance 加载（对应 instance.hpp/cpp）
    ├── dist_table.py        # 懒惰 BFS 距离表（对应 dist_table.hpp/cpp）
    ├── planner.py           # HNode/LNode/PIBT/LaCAM2 主循环（对应 planner.hpp/cpp + lacam2.hpp/cpp）
    └── post_processing.py   # 可行性检测 + 指标 + 日志（对应 post_processing.hpp/cpp）
```

## 依赖

- Python 3.8+
- 无第三方依赖（仅标准库）

## 运行

```bash
# 基础用法
python main.py -m assets/random-32-32-10.map \
               -i assets/random-32-32-10-random-1.scen \
               -N 10 -t 60 -v 2 -O 1

# 随机生成智能体（不提供 .scen）
python main.py -m assets/random-32-32-10.map -N 20 -t 60 -O 3
```

## 参数说明

| 参数 | 默认值 | 含义 |
|------|--------|------|
| `-m` / `--map` | 必填 | `.map` 地图文件 |
| `-i` / `--scen` | "" | `.scen` 场景文件（不填则随机生成） |
| `-N` / `--num` | 必填 | 智能体数量 |
| `-s` / `--seed` | 0 | 随机种子 |
| `-v` / `--verbose` | 0 | 日志级别 |
| `-t` / `--time_limit_sec` | 3 | 时间限制（秒） |
| `-o` / `--output` | result.txt | 输出日志文件 |
| `-l` / `--log_short` | False | 只写统计头，不写路径 |
| `-O` / `--objective` | 0 | 0=none, 1=makespan, 2=sum_of_loss, 3=sum_of_cost |
| `-r` / `--restart_rate` | 0.001 | 随机重启概率 |

## 作为库调用

```python
import random
from lacam2 import Instance, Objective, Deadline, solve
from lacam2 import is_feasible_solution, print_stats, make_log

rng = random.Random(42)
ins = Instance.from_scen("map.scen", "map.map", N=50, rng=rng)
# 或: ins = Instance.from_random("map.map", N=50, rng=rng)

deadline = Deadline(60_000)  # 60 秒
solution, info = solve(
    ins,
    verbose=1,
    deadline=deadline,
    rng=rng,
    objective=Objective.OBJ_MAKESPAN,
)

if is_feasible_solution(ins, solution, verbose=1):
    print_stats(1, ins, solution, deadline.elapsed_ms())
    make_log(ins, solution, "output.txt", deadline.elapsed_ms(), "map.map", 42, info)
```

## 算法对应关系

| Python 类/函数 | C++ 对应 | 说明 |
|---------------|----------|------|
| `Graph` | `Graph` | 地图加载与邻接表构建 |
| `Vertex` | `Vertex` | 顶点（id=密集编号, index=坐标编号） |
| `Instance` | `Instance` | 问题实例（地图+起终点） |
| `DistTable` | `DistTable` | 懒惰 BFS 反向距离表（Reverse Resumable BFS） |
| `HNode` | `HNode` | 高层配置节点（C-node），含动态优先级 |
| `LNode` | `LNode` | 低层约束节点，记录已确定位置的智能体 |
| `Planner.solve()` | `Planner::solve()` | LaCAM2 主循环：高层 DFS + 低层 PIBT |
| `Planner._funcPIBT()` | `Planner::funcPIBT()` | PIBT：优先级继承回退算法 |
| `Planner._rewrite()` | `Planner::rewrite()` | Dijkstra 风格代价回传 |

## 注意事项

- 本翻译实现**基础版本**（无 `GUIDANCE` / `FLOW_GUIDANCE` 编译选项），即不含 LNS 流量引导启发式。
  距离函数 `get_g` / `get_gd` 均退化为普通 BFS 距离，与原 C++ 中关闭所有编译选项时的行为完全一致。
- 若需扩展流量引导功能，可继承 `DistTable` 类覆盖 `get_g` / `get_gd` 方法。
