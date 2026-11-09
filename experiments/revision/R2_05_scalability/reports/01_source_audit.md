# 原始源码与论文审计（重建版）

源码事实沿用第一阶段审计；本报告已更新执行状态。完整验证结果见 04_baseline_gate.md 与 08_validation_results.md，原报告快照保存在 provenance/stage1_snapshot。

## 1. 依据与证据强度

唯一算法来源为本次上传的 `experiment.zip`。正式审稿依据为 `TRC_Referee_Report_CPS_Astar.pdf`，已完整阅读其详细批评及总结条目；第 5 条要求系统改变 fleet size、map size、task arrival rate 和 congestion level。前文同时质疑“大规模实时性”，因此时间范围、未完成试验和输入因素能否真正操纵实际交通交互都必须可核查。没有使用 `R4_Response.pdf` 作为审稿依据。

已阅读论文 §4.4、Algorithm 2、§5.1、§5.3、Figure 4、Figure 9 及相关结论。Figure 4 位于 PDF 第 16 页（论文页码 14），Figure 9 位于 PDF 第 22 页（论文页码 20）。源码引用下文以原始 `experiment/Lifelong/` 为根，行号按未改动文件计算。

原始 ZIP 不包含 Figure 9 的结果 CSV、逐 seed 记录或提交版本。`plot_throughput_ourmaps.py:36` 引用 `lifelong_results/test_ourmaps_results_20260421_225013.csv`，但该文件不在上传的原始 ZIP 中。因此，下文可确认“与 Figure 9 自定义地图实验相对应的源码入口与设置”，不能反向证明图中每个点确由这份归档的相同字节版本生成。

## 2. 实际入口

对应 Map A 的入口是 `test_ourmap.py` 的 `build_inputs()` → `run_cpsa()` → `CustomBenchmarkLoader.load_all()` → 原始 `LifelongPlanner`。不能使用核心目录的 `test_lifelong.py` 替代：后者针对 `random-64-64-10`，NUM_AGVS=1000，而且输出 `len(total_assigned)` 会对整数调用 len，属于打印阶段错误。

| 项目 | 原入口实际设置 | 本轮基线 |
|---|---|---|
| 地图 | STANDARD，16×11 | 相同 |
| 原入口车队 | 10/30/50/70/90 | 按本轮要求先 30，再 10/50 |
| max_tasks / repeat | 100 / 30 | 相同 |
| 任务供给 | 开始时整个队列已有 3000 条 | 相同 |
| 仿真时域 | MAX_TIME=500 | 相同，无预热 |
| 随机种子 | SEED=39，N_RUNS=5，即 39–43 | 验证 seed=39 已运行；正式 seeds1001–1005 尚未执行 |
| speed | 1.0 | 相同；原 segment 实际 move_time 固定 1 |
| 初始位置禁用工作站 | False | 相同 |
| pickup_strategy / region | None / None | 相同 |
| priority replan | True | 相同 |

原文件注释提到“四种算法”，实际 ALGORITHMS 有五项；本轮只调用 CPS-A，不加载其他算法。新入口复用原构建函数所调用的原类和原参数，不运行多算法总入口。

## 3. 论文文字与源码的差异

| 论文描述或可能的理解 | 源码实际行为 | 本轮采用 |
|---|---|---|
| 请求连续到达 | 所有请求在 t=0 已进入 deque；无到达率、release_time 或随机到达过程 | 复现源码的预置积压任务供给；不称 Poisson 到达 |
| Algorithm 2 的循环示意 | 源码依次分配、批规划、推进、释放、清理；首轮从 t=0 开始 | 原函数原顺序 |
| 动态优先级中的 unfinished-task age | `current_time-last_plan_time`；取货阶段切换、部分失败会重设 last_plan_time | 原字段，不换成首次任务年龄 |
| priority 由任务属性决定 | 原生成器生成 priority，但 loader 只提取 OD；planner 基值固定 1 | 固定基值 1 |
| “total computation time” | Figure 9 坐标为 Pure Time；入口同时存 wall 与 wall-assignment | 分开报告，不能混用 |
| one-shot 参数表可直接套到 Lifelong | Lifelong 的等待拥堵系数=1，转弯惩罚=.5，启发式为 Manhattan；UPDATE_COUNT=40，delta=3 | 以 Lifelong 源码为准，不套用 one-shot 参数 |

这些是实现口径记录，不对原算法做修正。特别是 `Segment_Planner._heuristic()` 直接返回 Manhattan distance，后面 look-ahead 代码全部被注释；不能把归档的 Lifelong 描述成启用了该段 look-ahead。

## 4. 地图与数组审计

`custom_benchmark_loader.py:9–13` 明确 STANDARD=(16,11)。`map_config.py:4–26` 定义：

- 货架：x ∈ {1,3,5,7,9,11,13}，y ∈ {1,2,3,4,6,7,8,9}，共 56 格。
- 工作站：(15,3)、(15,4)、(15,5)、(15,6)、(15,7)，共 5 格，**可通行**。
- 总格数 176，自由格 120；y=0、5、10 是横向通道，x=0、2、4、6、8、10、12、14、15 是无货架列。
- `GridMap.grid` 形状是 (height,width)=(11,16)，索引 `grid[y][x]`；任务坐标为 (x,y)。静态规划图只有 0/1，区域配色值不是规划器的障碍编码。

实际数组检查确认：旧版 `grid_for('STANDARD',1)` 与原 loader 完全相等；旧版 `reference_inputs/map_config.py` 与原 Lifelong 的 map_config 文件哈希相同。因而不能把这次异常归因于 STANDARD 换成了另一张地图。

原 `experiment/path_simulation.py` 使用根目录 map_config、`imshow(origin='lower')` 和按 (x,y) 绘制格子；根目录与 Lifelong 的 **STANDARD 配置值相同**，尽管两个完整 map_config 文件哈希不同。论文 Figure 4 和 Figure 9 的 Map A 形状、尺寸、56 个货架格及右侧工作站与此对应。归档没有生成 Figure 9 全部布局的最终组图程序，因此不能进一步声称验证了其绘图全链路。

已在真实数组上检查原有平铺：

| tiles | 尺寸 | 数组 shape | 障碍格 | 自由格 | 工作站格 |
|---|---|---|---:|---:|---:|
| 1 | 16×11 | (11,16) | 56 | 120 | 5 |
| 2 | 32×22 | (22,32) | 224 | 480 | 20 |
| 3 | 48×33 | (33,48) | 504 | 1080 | 45 |

旧平铺数组均等于 `np.tile(original_grid,(tiles,tiles))`。货架和工作站坐标偏移分别为 x+16·tx、y+11·ty，工作站转换后仍在自由格。本轮扩展已通过最小输入接口接入原逻辑，实际500步smoke通过；没有增加可达性搜索。完整证据在 `validation/map_array_audit.json`。

## 5. 任务生成、匹配及生命周期

| 阶段 | 原实现的实际调用链与行为 | 旧 R2-05 的差异 |
|---|---|---|
| 任务生成 | `task_generator.generate_test_tasks()`：随机货架邻接取货点、随机工作站；还生成不参与实际初始位置的 agv_position、priority | 独立的 Poisson 流、匹配距离层、热点混合或 FRANSEN 配对，不是相同任务输入 |
| 队列创建 | `CustomBenchmarkLoader.load_task_queue():109–146`，提取 OD，截取 100 条再重复 30 次，全部在开始时可分配 | 初始空队列，按 release 逐轮加入带 rid 的 Request |
| 初始位置 | 单独用 `random.Random(seed).sample()` 从自由格采样，工作站可选 | seed+101 洗牌；交通组另排除端点邻域 |
| 取新任务 | `_assign_new_tasks():93–166`，仅无 agv_tasks 项的 AGV 是 idle；候选为队首 min(3×idle数,队列长度) 条 | 最近距离匹配主体仍沿用，但候选池因释放过程而变；不能说整个分配体系相同 |
| 匹配 | 每轮在所有剩余 AGV×候选任务中找最小 Manhattan 到取货点距离，依次剔除匹配项；并非严格 FIFO | 大体相同匹配循环，新增记录回调和占用处理 |
| 初始阶段 | 从当前点到 pickup；相邻重复 waypoint 去重；任务设为 pending，净 assigned 加 1；只预约当前时刻的点 | 持续 current hold，并加入请求 ID |
| 规划 | 按等待年龄和局部拥堵形成优先级；成功路径加入临时批次并累计场；每 40 次成功或批尾提交 | 新增 hold 约束、静态预检查、扩展上限、单节点路径处理 |
| 到达 pickup | `_clean_completed_tasks()` → `_assign_second_phase()`，改 phase 为 to_dropoff、pending，清空旧路径和该阶段重规划计数 | 额外释放/建立 persistent holds；记录 pickup 事件 |
| 到达 dropoff | completed_tasks append 一次、删除 agv_tasks 项、释放预约；下一个 while 迭代在同一 current_time 可取新任务 | 额外建立 current hold；记录 completion 事件 |
| 队列为空 | 无 idle 或无 queue 时分配函数直接返回；若既无 active 又无 queue，主循环直接 break | 观察器 has_future() 维持整个时域，即使暂时没有任务 |
| 规划失败 | 有限次数优先级交换/未提交 blocker 回滚；原 MAX_REPLAN_PER_AGV=5；超过后退队 | 上限 5 仍在，但额外的失败来源显著改变调用频率 |
| 退队 | `_handle_failure_direct():279–299`，完整 (pickup,dropoff) 放队尾，删除活动任务，净 assigned 减 1，AGV 变 idle | 保留 rid、建立当前持续占用；其他基本回队意图相同 |

失败发生在 delivery 阶段时，也会把完整取送任务退队。下一次分配重新从 pickup 开始，不是“已经取货后只重分配 delivery”。这属于原有生命周期，不能在本轮换掉。

## 6. 原始状态边界与潜在问题

1. **单节点 waypoint 的原始行为**：当前位置等于 pickup 时，去重后只有一个 waypoint；`plan_agv()` 的分段循环不执行，返回 `([],[])`。调用方把它当作失败，可能重试、回队；pickup=dropoff 的 delivery 阶段也存在相同问题。已用独立微检查确认该返回值，未修改。
2. `completed_tasks` 只在 dropoff 分支追加并删除活动项，源码没有把 pickup 当成完成任务。相同 OD 出现多次是预置重复工作负载，不应按 OD 去重。
3. 原实现没有稳定请求 ID、release/assignment/completion 时间戳；无法仅靠原记录证明每个重复 OD 的逐请求身份唯一。只能先核查计数和 OD 多重集守恒，不能据此宣称完全排除了所有任务身份问题。
4. 预期账本关系是 N0=C+A+Q，`total_assigned_tasks=C+A`。这里 A 为当前活动任务数，含 pending、planned、executing；Q 是未分配队列。第二个量是净分配计数，不是累计 assignment 次数，也不是 unique-ever-assigned。
5. 生成器为每个基础任务采样互异 agv_position，尽管 loader 最后丢弃这个字段。若基础任务数超过自由格，原 while 采样可能不能结束。基线显式 100≤120，避免触发该设置问题；没有加入新的运行时上限或改写采样。
6. 原代码 pending/idle 的持续预约不足按本轮要求保留；没有新增物理正确性检查。本报告只记录来源与实际行为，不证明其物理正确性。

## 7. 原始文件与旧版差异

| 核心文件 | 原始与旧版是否逐字节相同 | 主要变化 |
|---|---|---|
| path_planner_lifelong.py | 否 | 相对导入、experiment 回调、未来释放维持循环、持久占用、阶段与回队处的辅助逻辑 |
| Segment_Planner.py | 否 | 单节点路径修复、active-hold 静态 BFS 预检查、5000 扩展上限、终点持久占用预约、诊断计数 |
| Ticket_Manager.py | 否 | 无限期 current/terminal holds、额外反向边检查、终点未来预约检查、新 reserve 方法 |
| Conflict_Field_Updater.py | 是 | 保留原实现 |
| benchmark_loader.py | 是 | 该 core 内副本不作为自定义 Map A 的主要 loader |
| test_lifelong.py | 是 | MovingAI 独立测试入口，非 Map A 入口 |
| __init__.py | 是 | 空文件 |

三份非空 diff 和四份空 diff 均保存在 `provenance/diffs/`。恢复后 **7 个核心文件全部与原 ZIP 相同**；不是基于旧版逐项回退后声称等价。

## 8. 搜索上限完整调用链

实际链路为 `run_lifelong()` → `_plan_one_batch()` → `SegmentPlanner.plan_agv()` → `_plan_segment()`。原 `Segment_Planner.py:76–83` 保留局部常量和被注释的 expanded/if/return；AST 核查 MAX_EXPAND 和 expanded 均不存在 executable Load 读取。实际导入路径指向 vendor 中的原文件，不会读到旧 planner。

原有 MAX_WAIT=2 是连续等待动作规则，MAX_REPLAN_PER_AGV=5 是已有优先级修复规则，均保留。它们不是本轮添加的搜索扩展预算。500 是仿真时间终点，不是墙钟秒数，也不会终止正在执行的单次搜索。

## 9. 当前执行版的最小接口

原始14个vendor文件仍全部不变。正式扩展入口使用独立 integration/path_planner_lifelong.py，原主文件复制后只增加释放/等待和旁路记录接口，完整差异见 provenance/integration.diff，必要性见07报告。其实际搜索、预约、场更新类全部导入vendor原文件。10/30/50辆、seed39、500步的原生与接入版最终完整任务状态逐项相等；更细指标来自新增被动记录，不能冒充原论文已有记录。
