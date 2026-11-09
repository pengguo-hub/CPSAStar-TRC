# 统计口径与时间边界

记 T 为实际仿真时间，C 为完整 pickup–dropoff 完成数，A 为仍有任务的 AGV 数，Q 为队列条数，N0 为初始 3000 条任务。时间步是离散仿真时间单位，perf_counter 的秒是执行机器上的墙钟秒，两者不可互换。

## 1. 原始基线

| 指标 | 分子、分母或计算式 | 窗口与单位 | 是否原生提供 |
|---|---|---|---|
| Throughput | `len(completed_tasks)/current_time` | 整个 [0,T]，任务/仿真时间单位；完整运行 T=500 | 是：path_planner_lifelong.py:493–496 |
| Success rate | `C/total_assigned_tasks*100`，正常账本下 assigned=C+A | 最终状态，百分比 | 是：test_ourmap.py:run_cpsa |
| 完成比例（全部供给） | C/N0 | 分母是 3000，非 C+A | 可由原始计数导出，但不能冒充论文 Success rate |
| 到达/生成数 | t=0 的队列条目 N0=3000；100 基础条目重复 30 次 | 无连续到达过程，无 λ | 入口可记录 |
| 未完成数 / backlog | N0−C=Q+A | 终点任务条数 | 可导出 |
| Queue length | Q，仅尚未分配；不含 pending/executing | 原日志每 10 cycles 的离散快照 | 原生没有逐步时间平均 |
| Waiting time | 若扩展：排队等待+接单后驻留时间，需逐任务和逐步观察 | 仿真时间单位 | 原生未记录，当前输出 null |
| Flow time | 若扩展：completion_time−release_time | 完成任务条件均值；未完任务需删失处理 | 原生未记录完成时间，当前输出 null |
| 单次 segment 规划耗时 | 每次 `_plan_segment` 的墙钟耗时 | 秒/调用 | 原生未测；不使用 native pure 冒充 |
| 累计批规划时间 | 各次 `_plan_one_batch` 墙钟耗时之和 | 秒，含批内搜索、预约、场更新等 | 原生未测，当前输出 null |
| 原 assignment time | 原 run_lifelong 内围绕 `_assign_new_tasks` 的 perf_counter 差值之和 | 整个运行的秒 | 原生 total_assignment_time |
| 原 loop wall | 进入 `run_lifelong` 前到返回后 | 秒；不含输入构建和 planner 构造，含原生打印 | 原入口 wall_elapsed |
| 原 Pure Time | loop wall−assignment time | 秒；仍含仿真推进、清理、预约释放和日志等 | 原入口 pure_planning_time |
| 子程序总墙钟时间 | 父进程启动子进程至结束的时差 | 秒；含启动、导入、输入、构造、仿真及子进程输出 | 新外围计时，单独命名 |

`Pure Time` 不是“仅 A* 搜索时间”，也不是严格的逐次规划耗时总和。即使变量名叫 pure_planning_time，也应以实际测量范围解释。父进程最终写 result.json 的少量开销不在 child_process_wall_seconds 内，范围已写入结果。

## 2. 500 步的精确定义

原循环从 `current_time=0` 开始，条件 `current_time<max_time`。以原 move_time=1 和整数起始时间运行时，推进后的状态覆盖 t=1,…,500。第一个区间 [0,1] 发生的任务处理计入全过程；在 t=500 完成的任务也经 `_clean_completed_tasks()` 计入后才退出。

没有丢弃最初 100 步、没有先跑预热、没有把总时域设成 600。原函数若任务完全耗尽会提前 break；新入口不会伪造补满时间，结束后仅标识 T 是否等于 500。若不到 500，不进入完整试验均值，但保留其原始计数与原公式结果。

## 3. 旧 R2-05 的口径

以下来自旧 `observations.py:130–178`，不导入新运行：

| 指标 | 旧版实际计算 | 与原基线的差异 |
|---|---|---|
| throughput | completion 在 (100,600] 的任务数 / 500 | 丢弃前 100 步完成数，系统已先运行 100 步 |
| throughput_full | 全部完成数 / 实际 observed_time | 完整试验分母 600；中断时只是部分时域数值 |
| completion_fraction | 全程 completed / arrived | 对所有实际释放请求，不是原 Success rate 的 assigned 分母 |
| waiting_time | (100,600] 内完成任务的累计 queue_wait+assigned_wait 均值 | 包含这些任务在预热期内的等待；不是所有到达任务平均 |
| flow_time | 同一完成任务集合的 completion−release 均值 | 完成条件均值；未完成任务未计入该均值 |
| restricted_flow_arrival_cohort | release∈[100,600) 的任务，用 min(completion,end)−release | 包含右删失；不可称所有任务真实完成时长 |
| queue_length | warmup 之后 trace 中 Q 以 duration 加权 | 原函数只稀疏打印 Q，不能直接当作相同统计 |
| final_backlog | final_queue+active | 含未分配和已分配未完成 |
| planning_seconds | 所有 `_plan_one_batch` 的累计时长 | 完整 600 步，含预热；与 native pure 不同 |
| planning_seconds_measurement | 测量窗内批规划累计 | 只取后 500 步 |
| planning_mean/p95 | 测量窗各 cycle 的批规划时长（含无事可做的批次）均值/95分位 | 不是单个请求、单个 AGV 或单段搜索的延迟 |
| wall_seconds | worker 范围内输入验证、运行、记录、部分后处理 | 比原 loop wall 包含更多工作 |
| trial_wall_seconds | runner 对 worker 整体测量 | 含进程启动/退出；有旧 1800 秒限制 |

低负荷 Poisson 流下，长期完成吞吐量受实际供给率约束；λ=.5 不可直接与始终有大量待选任务的原始饱和供给曲线比较。有限测量窗可能消化窗前积压，因此不能机械宣称每个 trial 的窗口 throughput 必须 ≤ 名义 λ。

## 4. 后续统计规则

只有完整到达 T=500 且原任务账本能核对的运行进入对应完整性能均值；失败、中断、未结束单列并保留。每个条件报告有效 n 和计划 n；不能把未运行视作 0，也不能把无耗时记录视作 0 秒。

先完成源基线，再设计需要的只读事件记录。首次基线保留原运行函数、不插入逐步统计回调，以免先用新观察机制取代原流程。更细的时间指标和等待/流程时间当前明确缺测，后续不能凭现有 completed_tasks 逆推出缺失时间戳。
