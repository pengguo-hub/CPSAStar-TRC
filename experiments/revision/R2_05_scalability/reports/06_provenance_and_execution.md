# 来源、版本和证据目录

## 来源保持

experiment.zip未修改。vendor/SRTP/experiment内14个Python文件逐字节来自原ZIP，7个core均原始，逐成员路径/字节数/SHA-256见provenance/original_sources.json。五个输入文件SHA-256见input_archives.json。没有可证明的原Git commit，使用归档哈希说明版本。

original_runtime.py仅处理原绝对导入路径和SRTP命名空间。原native基线直接使用vendor主planner；扩展入口使用integration中最小改动副本，必要性和全部diff已记录。SegmentPlanner、TicketManager、ConflictFieldUpdater、原loader和task_generator仍来自vendor。没有旧lifelong_engine、持久占用逻辑或旧验证器。

本轮运行内容指纹覆盖runtime、protocol、recorder、worker、integration、traffic配置及全部vendor源码，见每trial的environment.json和manifest.spec.source_files。路径采用POSIX相对表示，支持移到其他目录及Windows；字节变化会使运行门槛拒绝。PACKAGE_MANIFEST.json另外覆盖整个交付项目（含runner、统计、绘图和文档），可区分后处理修订。

## 原生与接入版输出

| 范围 | 文件 | 证据 |
|---|---|---|
| 原生单trial | inputs.json、metadata.json、source_verification.json | 原数组、3000队列、初始位置、环境、导入路径与源哈希 |
| 原生单trial | native.log、native_result.json、result.json、final_native_state.json、status.json | 原公式结果、父/子墙钟、OD多重集与计数、完整末态、PID/退出状态 |
| 矩阵根 | manifest.json、workloads/*.json | 目的、配置、seed、源码hash、预生成全部输入、每条尝试和PID |
| 接入trial | native.log、environment.json、progress.json、result.json | 原日志和最终结果、环境、每10步进度、不同计时范围 |
| 接入trial | events.jsonl.gz、timeline.jsonl.gz、requests.json | 请求身份、释放/分配/回队/完成、全程位置、等待/运动/删失 |
| 接入trial | segment_calls.jsonl.gz、final_native_state.json | 单段调用时间和原状态，不改规划结果 |
| 交通trial | traffic_evidence.json | 实际移动到达与±2步其他车到达证据，非碰撞检查 |
| 统计 | analysis/*.csv、*.json、audit_report.md | 逐trial审计、逐条件n/均值/CI、配对统计、输入匹配 |

请求跟踪在原匹配结果确定后执行；每个正常完成trial都有完整末态，日志中RESULT与result.json由离线审计交叉核对。计时包括已记录的旁路开销，调整值与inclusive值分列，不声称零测量扰动。

## 保留历史及未运行项

provenance/old_results只用于旧异常诊断，保存CSV、65条核对摘要与64份日志；缺失的旧aborted日志明确标出。旧原始大JSON仍在用户原结果ZIP内，未覆盖。旧两次代码和新代码结果绝不合并。

provenance/stage1_snapshot保留先前仅准备阶段文档及状态；其“未运行/blocked”等语句是历史，不是本交付状态。当前文档以根README、reports与validation/smoke_final为准。validation/smoke_full500与integration_parity为此前验证修订，保留但不纳入当前汇总。

validation/formal_plan为70条正式输入dry-run，全部planned、attempts为空。results/formal_trial_plan.csv列出70条待执行状态；没有正式trial结果、正式均值或正式性能图。正式跑完后用postprocess.py生成，不能以0占位替代缺测。

## 验证范围

14原始文件与最小diff校验；原生10/30/50 seed39；三车队接入完整末态等价；最终14条件seed901、每条500步；原始事件/日志/输入重放审计；统计与边界测试；PDF渲染检查；迁移目录测试。详细结果见08报告。

测试环境Python3.12.14、NumPy2.3.5、SciPy1.17.0、Matplotlib3.10.8；完整版本在requirements-tested.txt。正式建议在同一环境、同一机器顺序执行，不混用并行资源争用造成的时间结果。运行无per-trial墙钟限制；没有保证任何未运行seed都必然结束。

该证据支持来源、被测输入上的行为一致和流程可运行，不证明未测试输入的全局等价、严格拥堵梯度或物理正确性，也不替代正式独立seed实验。
