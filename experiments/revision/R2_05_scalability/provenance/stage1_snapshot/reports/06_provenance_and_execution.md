# 来源、文件保持与运行可核查性

## 1. 原始文件保持不变

源压缩包未写入或覆盖。`vendor/SRTP/experiment/` 的14个文件全部直接取自 ZIP bytes。7 个核心文件均为 `experiment/Lifelong/CPS_A_lifelong/` 中的原始文件，而不是旧版还原的近似副本。

逐文件 ZIP 成员路径、保存路径、byte 数及 SHA-256 见 `provenance/original_sources.json`；五个任务输入文件的完整 SHA-256 见 `provenance/input_archives.json`。旧版 manifest 和原始→旧版 diff 均独立保存。新工程没有 Git 上游版本可引用，内容哈希是本轮归档版本标识。

## 2. 仅在外围处理的兼容性

原 planner 使用 `from Segment_Planner import ...` 等绝对同级导入，而任务生成器保留 `from SRTP.experiment.map_config import ALL_MAPS`。新 `original_runtime.py` 把冻结 Lifelong 目录、核心目录和 vendor 根依次放入 sys.path，保留原 SRTP 命名空间目录结构。

原自定义 loader 从 Lifelong 根的 benchmark_loader 取 GridMap；不误导入核心目录中的 MovingAI-only 测试 loader。不需要更改原导入行，也不复制新的匹配或搜索函数。实际 module.__file__ 路径写入每次输入/结果记录。

未导入旧 worker、observations、validity、TicketManager 或 SegmentPlanner。未使用 subclass、monkey-patching、逐步回调、profiling hook 或新的 lifelong_engine。外围的来源检查和运行结束后的账本核对不会参与路径选择、重试或任务分配。

## 3. 运行输出

每条命令创建一个新目录，若目录已存在则拒绝覆盖。

| 文件 | 内容 |
|---|---|
| status.json | 父/子PID、开始结束UTC、状态、退出码、总耗时，无timeout |
| source_verification.json | 原始文件 SHA-256 是否一致 |
| metadata.json | 配置、平台、库版本、导入路径、任务数与输入哈希 |
| inputs.json | 真实二维数组、AGV info、初始位置和3000条原始队列 |
| native.log | 原程序输出及异常栈；每10cycles的原生打印保留 |
| final_native_state.json | 真实运行后的 completed_tasks、agv_tasks、queue、位置和计数；prepare-only不生成 |
| native_result.json | 原公式结果、独立计时与事后账本核对；prepare-only不填性能值 |
| result.json | 子进程结果与父进程整体墙钟范围 |

无正式运行时不产生吞吐量0或时间0占位。真正运行异常会写 error 或 interrupted 并保留能读取的原状态，不自动重试。硬杀进程或宿主崩溃可能来不及写最终文件，已有 status/log/inputs 必须保留并按未完成处理。

原日志每10cycles一次，无法代替每步轨迹，更不能独立证明全部请求的逐ID生命周期。完整状态保存提供计数和OD多重集核对，相关局限在指标报告中明确。

## 4. 本轮实际验证清单

1. `python verify_preparation.py`：退出0。14源文件、无生效扩展上限、15组原始输入、图数组/车队/队列关系、原单节点返回行为通过；执行完整仿真数为0。
2. `python run_baseline.py --fleet 30 --seed 39 --prepare-only --output validation/prepared_30_seed39`：子进程退出0，prepared_only。
3. 原/旧 STANDARD 数组、旧2×2及3×3平铺和工作站偏移通过；不包含可达性预检查或任何仿真。
4. 旧65条 CSV/JSON关键字段核对通过；原始日志64份，缺失1份已披露。
5. 独立解压到另一目录后执行30辆 prepare-only：退出0，全部实际导入路径指向解压目录，input_hash 与原准备结果相同。另将14个源文件再次直接与原 ZIP 成员 bytes 比较，全部相同。没有执行真实 trial。

准备环境为 Python 3.12.14、NumPy2.3.5。`requirements-tested.txt` 记录本次版本，`requirements.txt` 只列 NumPy；原生运行不需要 SciPy、pandas、绘图或完整多算法依赖。

所有本轮生成的校验证据均在 validation 中。正式算法性能、整段500步终止性、拥堵梯度和物理正确性均不在“准备验证通过”的含义内。
