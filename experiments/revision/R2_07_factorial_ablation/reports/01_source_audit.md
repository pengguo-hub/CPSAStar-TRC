# 来源审计与原始行为恢复

审计顺序：先读取实际来源 ZIP，再比较现包，随后恢复基线，最后审计因素和统计。未更改任何来源 ZIP，也未操作 R2-04/05 项目。

权威源为 `experiment.zip/experiment/Lifelong/CPS_A_lifelong/`。实际比对七个算法文件以及六个输入/原实验运行文件共 13 个，旧包 `original/` 均逐字节匹配；这些快照在新包直接从权威 ZIP 复制。原始输入工具的孤立 `SRTP.experiment.map_config` 依赖在运行副本中改成包内相对导入，其函数体不变。

旧包实际运行副本存在以下与来源声明不一致之处：

| 文件 | 实际问题 | 处理 |
|---|---|---|
| Ticket_Manager.py | 新增 persistent hold 与 terminal-hold reservation | 恢复原文件，按字节一致 |
| Segment_Planner.py | 活动 holds 可达性预检查、5000 次扩展截断、terminal hold | 从原文件恢复，仅接回已定义 L 开关 |
| path_planner_lifelong.py | 初始/完成/pending 的持续占用行为及对应生命周期改动 | 从原文件恢复，只接回 S/L/P 和只读记录所需 hooks |
| run.py | 默认 1800 秒 subprocess timeout；smoke 还有 60 秒限制 | 删除参数和整个定时终止分支；所有 wait 均无 timeout |
| observations.py | 物理碰撞、反向边与非法位移诊断 | 删除，不作为因素或结果有效性门槛 |
| source_manifest.json | 以上三个源码文件的声明哈希已过期 | 依据真实交付文件重新生成，不沿用过期声明 |

旧包配置本来已经是 500 步，没有预热；新包保留此项而非声称修正了不存在的 600/100 协议。旧包的 S、L 和 P/R retry 队列分离基本合理，保留这几段逻辑，未重新设计 planner。

`audit/input_source_audit.json`、`audit/incoming_*.diff` 保存来包和原始源的实际差异。`source_diffs/` 是最终运行文件相对权威源的差异，二者不可混淆。

## 正式导入链

`run.py` → 独立 Python `worker.py` → `CPS_A_lifelong.path_planner_lifelong.LifelongPlanner` → 同包的 Segment_Planner / Ticket_Manager / Conflict_Field_Updater。

每个 worker 先执行源哈希检查并断言上述四个模块的 `__file__` 位于解压后项目根目录，再在结果中写入相对导入路径。输入使用本包 `reference_inputs.CustomBenchmarkLoader`，函数体与原版一致，只改变绝对导入为相对导入。

`original/` 不参与正式 planner 导入；它用于来源校验及 `verify_original.py` 直接加载原版的行为对照。没有 one-shot planner 或 `lifelong_engine.py`。

## 最小增量边界

运行副本中的改动仅为：相对导入；S/L/P 参数和原 R 参数的连接；规划耗时记录；assignment/phase/requeue/rollback/completion 的记录 hook；随请求保留 ID。ID 是 tuple 子类附带数据，两元素 pickup/dropoff 解包顺序不变。没有任务重新优化或新的分配策略。

来源文件的 `run_lifelong` 默认 horizon=10000 保留，正式 worker 显式传 500；这不会额外仿真。原始 class 的 R 默认 False 保留，而原始 benchmark runner 和正式基线显式使用 True。

静态验证检查可执行 AST，不把原注释、原实验其他算法的时间参数或惰性 MAX_EXPAND 常量误判为实际生效。有限场景逐 cycle 等价是经验验证，不是对所有输入的形式化等价证明。
