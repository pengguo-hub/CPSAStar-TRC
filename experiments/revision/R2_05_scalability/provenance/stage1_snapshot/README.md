# R2-05：原始 Lifelong 源码审计与基线准备

日期：2026-10-26（北京时间）。本包对应本轮最后要求的“第一阶段源码审计和基线准备”，不是正式实验结果包。

**当前结论：原始来源与输入已核对，30 辆入口已准备；尚未执行 500 步基线，基线门槛未通过，正式矩阵未启动，新有效样本数 n=0。**

16×11 的新车队规模统一为 **10 / 30 / 50**。12 / 30 / 48 仅出现在旧结果的原始证据中，不属于新实验配置。

## 已完成的工作

- 从 `experiment.zip/experiment/Lifelong/CPS_A_lifelong/` 复制全部 7 个 Python 文件，并保存相关原始输入、入口和绘图源码，共 14 个原始文件；全部逐字节一致，包括换行符。
- 实际执行的搜索没有 MAX_EXPAND 判断。原文件中的 `MAX_EXPAND = 5000` 是未被读取的局部变量，原有被注释的判断完整保留。没有新增搜索上限、trial 墙钟超时、静态可达性预检查、持续占用修复或物理碰撞检查。
- 新入口直接调用原始 `LifelongPlanner.run_lifelong(max_time=500)`，没有另写仿真引擎、替换任务匹配、覆盖 planner 方法或插入运行回调。
- 检查了 10/30/50 辆 × 原入口 seeds 39–43 的 15 组输入；每组均为原始 100 个任务重复 30 次、共 3000 个队列条目。输入检查不等于 15 次仿真。
- 30 辆、seed=39 的 `--prepare-only` 子进程成功退出，保存地图数组、原始队列、初始位置及实际导入路径。
- 对旧结果 65 条 CSV 和对应 JSON 核对关键字段，未发现不一致；54 completed、10 timeout、1 aborted。aborted 的原始日志缺失，已如实记录。

## 首个基线命令

解压后进入本目录：

```bash
python -m pip install -r requirements.txt
python verify_preparation.py
python run_baseline.py --fleet 30 --seed 39 --output results/baseline_30_seed39
```

最后一条才真正运行 500 步；本次未执行。一次命令只运行一个条件、一个 seed，不自动接着运行其他条件。输出目录必须尚不存在，防止覆盖结果。

只准备输入、不运行仿真：

```bash
python run_baseline.py --fleet 30 --seed 39 --prepare-only --output results/prepare_30_seed39
```

30 辆结果与论文核验通过后，才分别运行：

```bash
python run_baseline.py --fleet 10 --seed 39 --output results/baseline_10_seed39
python run_baseline.py --fleet 50 --seed 39 --output results/baseline_50_seed39
```

原入口设置为 seeds 39–43；旧 R2-05 的正式方案为 seeds 1001–1005。两者的用途和结果应分开记录，不混成一个样本组。

## 关键报告

1. [源码与论文审计](reports/01_source_audit.md)：实际入口、地图、参数、源码差异与任务生命周期。
2. [指标口径](reports/02_metrics.md)：原论文、原始程序与旧版的分子、分母和时间边界。
3. [旧版异常诊断](reports/03_old_results_diagnosis.md)：仅分析旧数据，不把旧数值当作重建结果。
4. [基线与 Figure 9 对照准备](reports/04_baseline_gate.md)：图中约值、运行验收项及未完成状态。
5. [扩展接入边界](reports/05_extension_design.md)：地图、到达率与 OD 配对的下一阶段设计和阻碍。
6. [来源与运行说明](reports/06_provenance_and_execution.md)：哈希、导入兼容、运行状态与计时范围。

## 文件分工

- `vendor/`：原始文件副本；请勿修改。
- `original_runtime.py`：仅解决原始绝对导入路径。
- `run_baseline.py`：单次运行、日志和原公式输出；没有矩阵调度入口。
- `configs/baseline.json`：基线规格；入口的实际参数固定为相同值。它是可审查规格，不是可动态覆盖的配置文件。
- `configs/extensions_design_only.json`：明确不可执行的扩展设计草案，不是已验证正式配置。
- `validation/`：实际执行的源码及输入准备证据。
- `results/stage_status.json`：本轮状态；没有伪造的实验结果或均值。
- `provenance/diffs/`：原始文件 → 旧版 R2-05 的逐行差异。
- `provenance/old_results/`：旧结果审计证据，严格与新结果分开。

本轮未生成综合性能图或宣称完成的英文审稿回复。它们必须等真实基线与后续实验完成后再生成。本包也不声称验证了原始 pending 行为的物理正确性。
