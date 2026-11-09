# 本轮实际验证与限制

## 已完成

- 权威 ZIP 的 13 个算法/输入文件逐字节核对，实际导入路径检查。
- 原 Segment_Planner 七个搜索/预约方法及六个原生命周期方法 AST 一致；Ticket_Manager 字节一致。
- 静态检查：MAX_EXPAND 未读取执行；无 trial timeout 调用、预热、持续预约、静态可达性或物理碰撞检查。
- 11 项单元测试：S 原始计数/高斯、L 字面数值与 Manhattan 基底、P 评分/数值交换、R 失败分支、P0/R1 retry/blocker 保留、初始队列、两阶段、回队列 ID、种子推断与缺失配对、正式回复 guard。
- 原始对照：STANDARD/FRANSEN/RING，6 辆、30 步、20 个任务；另 STANDARD 30 辆、40 步、80 个任务。原生与接入版每周期完整内部状态一致。后者发生 24 次 rollback。
- 最新 smoke：STANDARD 10 辆，40 个初始任务，24 步，seed 39，全部 16 组合结构化审计通过。
- 正式 dry-run：三张原图/原车队、30 个 seeds、16 组合，1440 行计划、90 份输入；同 case/seed 的 16 个 workload_hash 一致。没有启动正式 worker。
- smoke 后处理、统计输出和五组 PDF/PNG 图实际执行；图上保留验证水印，不生成正式数值回复。

## 日志审计

首次 16 组合 smoke 中 1 份 stdout 为空。运行器随后加强逐行接收、flush、fsync 和捕获内容回读验证。修改后重新执行 16 组合，小场景结果相同，但最终查验仍发现 3 份 stdout 缺少末尾汇总：

- A_backlog_39_S0_L0_P1_R0（空日志）
- A_backlog_39_S0_L1_P1_R0（部分日志）
- A_backlog_39_S1_L1_P0_R0（末尾汇总缺失）

对应结构化文件完整。三条同输入单独复跑均返回 0，stdout 汇总存在，且 requests/events/executed_frames/queue 与 field trace 完全一致。原始日志未覆盖，单独证据保存在 `verification/console_replays/comparison.json`。重复运行不增加 n，也不从多次运行挑选更有利的交通结果。 stdout 缺口根因未确认，不承诺已经根治。

## 边界

小场景测试不能保证 1440 个正式 trial 都结束，尤其恢复原无搜索截断后，极端组合可能长时间停在一次规划中。没有为 smoke 或正式运行加入自动墙钟截断。

本包没有运行原正式车队的整套 500 步因子矩阵，不声称本轮已经复现论文均值或建立四因素效果。没有新增物理碰撞检查、物理有效性门槛或 pending 行为修复。所有来源与原行为的边界应如实写入论文。

压缩包的最终 `unzip -t` 与全新空目录验证另有实际记录。验证只读取解压文件和标准 Python/已安装第三方库；外部工程路径访问会被测试用 audit hook 拒绝。该 hook 是验证夹具，不是正式 planner 检查，不随运行生效。
