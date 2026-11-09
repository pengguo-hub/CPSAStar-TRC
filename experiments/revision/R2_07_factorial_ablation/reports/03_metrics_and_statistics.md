# 指标、统计单位与比较族

## 指标

每个正式 trial 从 t=0 直接运行至 t=500，无预热。backlog 为同一 seed 的 100 对原始 pickup/dropoff 重复 30 次，共 3000 个带不同 request ID 的请求。初始 AGV 位置按原 CustomBenchmarkLoader 独立生成，任务分配保持原 planner。重复任务不会被当作独立实验重复。

| 字段 | 定义与限制 |
|---|---|
| throughput | 原 get_throughput：完成任务 / 实际仿真时间。仅完整 500 步 trial 进入正式统计 |
| throughput_fixed_window | 完成任务 / 设定 horizon；提前结束记录虽保留此诊断值，仍不进入完整窗口分析 |
| waiting_time | 已完成请求的 queue_wait + assigned_wait 均值。queue_wait 含失败后回队列；assigned_wait 是已分配且当前 cycle 位置不变的时长 |
| flow_time | 已完成请求 completion − release，含排队及两阶段执行；release=0 |
| queue_length | 每次规划后、执行前的未分配队列长度按 cycle 时长平均 |
| waiting_all_arrived | 所有初始请求在其完成或观察末端之前累积的 queue_wait + assigned_wait 均值 |
| restricted_flow_all_arrived | 全部请求 min(completion,500) − release 的均值；未完成填 500 是预定义的受限观察时间，而非伪造完成时间 |
| completion_fraction / final_backlog | 完成数/3000；未完成包括队列中和已分配两类 |
| source_field_exposure | 每次规划后，所有 AGV 当前位置、当前 delta=3 slot 的输出 field，先跨车平均再按时间平均；含 own contribution |
| source_raw_slot_exposure | 同位置和时间查询原 path_conflict_dict 的 slot visit counts |
| planning_seconds / planning_p95 | 各 cycle 的原 `_plan_one_batch` 调用耗时总和 / 95% 分位；该函数内的事件 hook 也有开销 |
| assignment_seconds | 原 total_assignment_time；现在包含 assignment 记录 hook 的微小开销 |
| loop_wall_seconds | 仿真主循环墙钟耗时，包含输出和 checkpoint / 观察开销 |
| instrumented_pure_seconds | loop_wall_seconds − assignment_seconds；明确是带记录开销的计算量，不可冒充原论文机器上的 Pure Time |

waiting_time 和 flow_time 条件于“该组合完成了哪些请求”，受完成样本选择影响。主结果必须同时查看 completion_fraction、未完成数以及全到达队列的受限指标。此设计不通过选择任务子集来隐藏拥堵或失败。

S0 输出 raw counts，S1 输出平滑值：source_field_exposure 的数值尺度随 S 改变，所以跨 S 的 field 减少本身不能证明实际拥堵改善。raw_slot exposure 的测量接口一致，但其预约轨迹仍受规划决策影响。四个独立交通结果是判断组件收益的主要依据。未增加物理碰撞验证，不能由这些指标声称已验证物理安全。

## 配对与推断

每张地图分别分析，独立统计单位是 seed。每个对比先在 seed 内形成一个数值，然后才跨 30 个 seeds 估计均值、SD、95% Student t CI。另保存 10,000 次 percentile bootstrap CI 作为敏感性结果，bootstrap 对完整的 seed 差值重采样。

主效应：对某因素 on−off 在另外 3 因素的 8 个 matched pairs 上等权平均；该 seed 的 16 个必要 cell 必须完整。二阶交互：(11−10−01+00) 在其余因素的 4 个配置上平均；本包采用完整 difference-of-differences 尺度，不是回归模型 ±1 编码下缩小四倍的系数。条件主效应按另两个因素的 4 个配对平均，需要 8 个 cell。

双侧符号翻转检验作用于每个 seed 的对比均值。n≤16 时枚举，较大 n 使用确定随机流的 Monte Carlo（10,000 次，+1 校正）。需要对比差值在零假设下可符号交换/对称的假设；这是模拟 seed 推断，不是现实随机分配实验。Wilcoxon signed-rank 仅作为分布敏感性列，不以最小 p 值挑选结果。

n<2 时仍报告描述性均值和有效数，CI 与 p 留空。全部零差值的 p=1；不能把单个 smoke seed 的差值称为显著效果。

## 预定义多重比较族

主指标层为 throughput、waiting_time、flow_time、queue_length。其余 12 个指标为次要层。每种对比类型 × 指标层为一个族，跨全部 3 张地图一起 Holm 校正，不逐图挑选显著结果。

| 族类型 | 每图每指标对比数 | 正式主指标族大小 | 正式次要指标族大小 |
|---|---:|---:|---:|
| vs_original | 15 | 180 | 540 |
| main_effect | 4 | 48 | 144 |
| two_factor_interaction | 6 | 72 | 216 |
| conditional_effect | 8 | 96 | 288 |

无有效配对的对比保留在族总数内，不因缺失而缩小校正范围。族间没有声称一次性控制所有探索性分析的整体 FWER。未经 Holm 校正的 Wilcoxon 不用于主要显著性结论。

## 不完整数据

raw_results 始终包含计划中的每一行，包括未执行、运行错误、用户中断、提前结束和审计失败。完整窗口性能分析要求 status=completed、观察末端等于 horizon、逐 cycle 记录完整、身份与工作负载哈希匹配、任务账本守恒。未完成任务本身是正常交通结果；未完成 trial 则是另一个可靠性状态，不能混淆。

stdout 汇总行缺失单独记为 console warning，不把它伪造成完整日志，也不自动否定经结构化记录独立核对的完整任务结果。`seed_contrasts.csv` 对每个 seed/对比输出 eligibility 与 exclusion_reason。所有组件平均效应是完整配对条件下的估计，失败偏倚无法由丢弃失败数据消除，须同时报告完整率并限制结论。

`postprocess.py` 先从每个 job/result/workload 重新审计，再分析，不依赖旧 CSV。分析结果记录输入文件指纹和表格哈希，绘图检查表格未过期。
