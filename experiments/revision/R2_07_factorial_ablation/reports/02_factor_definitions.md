# 四因素定义、交互及可解释范围

本研究回答 Reviewer 2 第 7 条：在相同原始 lifelong 控制流程和外生请求下，四组明确的软件机制改变哪些输出。完整 2^4 设计保留全部 16 个组合，避免一次只关闭一个因素而无法识别交互。

## S：Gaussian smoothing

S1 沿用原 `ConflictFieldUpdater`：delta=3、空间和时间半径各 1、sigma_space=sigma_time=2；slot 中的 path visits 累计经原归一化 Gaussian 更新到 smoothed_dict。

S0 仅在 `_incremental_smooth_path` 入口直接复制 `path_conflict_dict` 为输出 field。路径累计、slot 索引、batch update、cleanup、约束预约和查询接口不变。未重标定权重，未二值化、未转为 exact-time occupancy。同一 AGV 在同一 slot 内三个时间点访问同一节点会累计 3，而不是二值 1。源算法保留 own contribution。

因此 S 效应包含原始平滑对 field 的空间/时间传播与数值幅值改变，不是“归一化后等幅信号的纯几何平滑效应”。S 会自然改变下游 waiting cost、L 查询和 P congestion score；这属于机制传递与交互，不是额外改动开关。不存在 Gaussian 必然更优的预设。

## L：新增 look-ahead 处理组

原 `_heuristic` 在 Manhattan distance 后有效 return，其后整段候选逻辑被注释，因此原始 L=0。L1 在该返回前加 `50 × weighted_mean_future_field`；目标距离为 0 时仍返回 0，其余启发式基底不变。

数值按源文件注释中的可执行表达式选择：3×3 有效邻域、空间 exp(-L1_distance/2)、时间 exp(-dt/2)、future slot offsets 1…2×delta、omega=50。delta=3 时是 6 个 slot 的前瞻；最后一个 slot 的起点相对 arrival_time 相差 16–18 时间单位（取决于 arrival_time 在当前 slot 内的位置），并不是“6 个仿真步”。

源注释文字中的“未来 1–2 步”和公式 `2*delta` 存在不一致。本实验明确采用后者的字面数值，并非证明作者原先意图如此。原被注释段的 Euclidean base 不恢复；有效 Manhattan base 保留。未修改权重或宣称 admissibility、最优性、完备性；L1 只支持对此新增候选处理的评价，不能反向归因原论文结果。

## P：动态评分与数值优先级调整

P1 保留 `1 + 0.1*(current_time-last_plan_time) + 0.5*local_congestion`，保留 `USE_CON` 原门控；这里的 age 采用真实源实现的 last_plan_time，不能重新解释成所有请求的完整已等待时长。R 启用时保留原数值 priority swap（±1e-4）。

P0 把该评分固定为 1，并关闭数值 swap。Python 原稳定排序和队列插入顺序保留。P 不修改任务候选匹配、request queue FIFO 回插或 pickup/dropoff 生命周期。

P 是两个相关子机制组成的开关，因此 P 主效应不能单独区分 age、local congestion 和数值 swap。拆分这些子项需要另一个设计，本次不越出既定四因素实验。

## R：原 bounded rollback

R1 使用原 `_handle_failure_with_replan`、`_find_blocker`、fallback blocker、原预约撤销、未提交路径回滚和最多 5 次 retry。P0/R1 仍把失败 AGV 插到 planning queue 头、blocker 追加到尾，从而能先重试失败任务；不能为了“无 priority”连这个 rollback 操作顺序也删掉。

R0 使用原 `_handle_failure_direct`，把相同 pickup/dropoff 任务放回原队列尾并释放原有限预约，后续仍由原 dispatcher 指派。不是丢弃任务或新建失败生命周期。

P1/R1 还会通过优先级阈值影响 blocker selection；P0/R1 使用相同选择代码但分值相等。R 的 retry 重排本身是一种顺序改变，因此 P0 不等于“所有形式的优先排序都消失”。P×R 是必须报告的条件性相互作用。

## 分析范围

原始基线 S1_L0_P1_R1 对其余 15 组逐一配对。4 主效应均按另外 3 因素的 8 个配对差异平均；6 个二阶交互按另外 2 因素的 4 个 difference-of-differences 平均。另报告 P 在 R0/R1、R 在 P0/P1、S 在 L0/L1、L 在 S0/S1 下的条件效应。

不假定三阶/四阶交互为零：主效应和二阶交互是设计内的边际平均，15 个原基线对比与全部 16 个 cell 的汇总保留具体组合差异。没有把边际平均推断成所有配置下同方向有效。按地图分别报告，尤其避免把某张瓶颈地图的 rollback 收益宣称为普适收益。
