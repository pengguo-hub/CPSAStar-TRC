# R2-04：预置 OD 拥堵模式 × 原始 Lifelong CPS-A*

本包使用 `R2-04_ready_to_run.zip` 的原始 Lifelong 规划器及 Full/Control 干预，重新定义任务输入为 **3000 项任务在 t=0 全部进入任务队列，运行到 t=500**。没有 Poisson 到达过程，没有 lambda，不强制实际行驶最短路径，不修改 CPS-A* 的搜索、冲突检查、预约、回滚或等待上限。

已完成的验证和全部条件的结果见 [validation/smoke_report.md](validation/smoke_report.md)。这些是 seed 7、8 的 smoke，不是正式实验。正式实验的 seed 39–43 留给用户运行。包内不存在正式性能结果。

## 1. 实验矩阵

| 地图 | AGV 数量 | 静态 OD 模式 | 每个 trial | 正式 seed |
|---|---|---|---|---|
| STANDARD | 30、50 | dispersed / intermediate / shared | 3000项；500步 | 39–43 |
| FRANSEN | 100、200 | 同上 | 同上 | 同上 |
| RING | 80、160 | 同上 | 同上 | 同上 |

正式运行共 18 个条件 × 5 seeds × 2 arms = **180 trials，90 对 Full/Control**。不混用旧结果。每个地图/模式/seed 的任务序列在两档车队间相同；Full/Control 的任务、顺序、初始车辆位置和统计窗口完全相同。较小车队的初始位置是较大车队初始位置的前缀。

全部126份完整输入（90份正式、36份smoke，每份3000项任务）已预生成在 `prepared_inputs/`，以 `.json.gz` 保存。`verify_inputs.py` 检查它们与运行器确定性生成的输入逐项一致。运行器在启动任何trial前将对应明文输入写入输出目录；不在仿真过程中随机生成任务。`prepare_inputs.py` 可以复现这些输入，执行0次仿真。

## 2. 一次性运行正式实验

建议使用 Python 3.11 或 3.12；本包实测 Python 3.12。解压后在本目录执行：

```bash
python -m pip install -r requirements-tested.txt
python verify_package.py
python verify_inputs.py
python run.py --formal --suite all --dry-run --output results_od_formal
python run.py --formal --suite all --resume --output results_od_formal
python postprocess.py results_od_formal
```

`--dry-run` 生成并核验完整输入和运行计划，执行 **0 次仿真**。下一条 `--resume` 才开始仿真。也可以省略 dry-run，直接运行 `python run.py --formal --suite all --output results_od_formal`。

单进程按条件执行，Full/Control 的运行次序由 seed 确定；不限制每个 trial 的墙钟时间。每20秒打印心跳，日志和 progress.json 会显示实际仿真步数。单个 trial 到500步后结束，即使还有大量未完成任务；这是固定观察窗口，不是超时失败。

不要把现有旧版 R2-04 的输出目录传给本程序；输入与代码哈希不同会被拒绝。不要在运行中编辑脚本或配置。

## 3. 暂停、续跑及失败记录

```bash
python run.py --formal --suite all --resume --stop-after 10 --output results_od_formal
python run.py --formal --suite all --resume --output results_od_formal
```

`--stop-after` 在指定数量的新增完整 trial 之间暂停，不截断 trial。续跑校验现有结果、输入、代码和 attempt 记录后复用完整结果。

异常或中断的 attempt 原样保留，不填零，不静默删除，不自动重跑。先检查该 trial 的日志及进程状态；确认旧进程结束并排除技术故障后，可以显式重试：

```bash
python run.py --formal --suite all --resume --retry-trial FRANSEN_N200_shared_39_full --output results_od_formal
```

以上 trial 名仅为命令示例。重试会创建新的 attempt，保留旧 attempt；不得按性能好坏选择重试或删除完成结果。恢复时必须保持 `--suite`、`--seeds`、`--seed-start`、`--cases` 与原计划一致。

## 4. 输出与分析

`postprocess.py` 仅分析现有结果，不启动仿真。主要输出：

- `trial_audit.csv`：每个 trial 的数据状态、失败原因和配对有效性。
- `audited_metrics.csv`：独立事件重放核验通过的完整运行指标。
- `paired_seed_differences.csv`：逐 seed 的 Full−Control，以及各 arm 内 intermediate−dispersed、shared−dispersed。
- `paired_statistics.csv`：均值、配对差、95% t 区间、有效 n、精确符号翻转检验及四项主指标的 Holm 校正。
- `summary_results.csv`：仅使用有效 Full/Control 配对的各 arm 均值与区间。
- `figures/R2_04_OD_results.png`、`.pdf`：四项性能指标 × 三张地图；每张地图包含两档车队和三个 OD 模式。
- `figures/R2_04_OD_paired_effects.png`、`.pdf`：对应的 Full−Control 配对差及95%区间，便于辨认全尺度均值图中的小效应。
- `runs/`、`receipts/`、`workloads/`、`attempts/`、`source_snapshot/`：原始结果、输入、哈希、过程记录和执行源码。

本机smoke每个seed的36次完整结果约占2.7–2.9 GiB；正式五个seed建议预留至少20 GiB输出空间。运行包压缩了验证证据，正式运行仍保留原始日志与各attempt。

每个 trial 保存完整任务账本、事件、500个时间区间和501帧车辆位置。分析器从事件和位置重算任务等待、移动、完成及队列长度，并检查任务守恒和时间守恒。**正常完成但表现较差的结果同样纳入。**

包内的 `validation/smoke_evidence/` 保存全部72次smoke的压缩原始结果及attempt/receipt身份；`validation/smoke_summary/` 保存合并统计。可以只重放审计、不运行任何实验：

```bash
python replay_packaged_smoke.py --output replayed_smoke
python test_integrity.py --output integrity_checks.json
python plot_results.py replayed_smoke
```

## 5. 设计和指标的准确含义

- 详细设计、预先固定的 OD 坐标及静态分数见 [DESIGN.md](DESIGN.md) 和 [validation/input_checks/OD_PAIRINGS.csv](validation/input_checks/OD_PAIRINGS.csv)。
- 指标分母、未完成任务处理和代数关系见 [METRICS.md](METRICS.md)。
- 源码来源及相对旧包的修改范围见 [CHANGES.md](CHANGES.md)。

本实验的拥堵变量名称为 **static OD congestion potential**（静态 OD 拥堵潜势）。它来自与 CPS-A* 独立的地图最短路重叠计算，规划之前已冻结。同一条件下 Full 和 Control 的这个值相同。实际路径由原始 CPS-A* 生成，不受参考最短路约束。

本设计能检验“预置拥堵潜势变化时，Full/Control 的运行性能及其差异如何变化”。它不能单凭静态分数证明“Full 降低了实际拥堵暴露并因此提高性能”。正式回复应据实际五个 seed 的全部条件报告效应及不确定性；smoke 中未占优或差异小的条件也完整保留。

## 6. 可选：在本机重跑 smoke

```bash
python run.py --smoke --suite all --seeds 2 --output local_smoke
python postprocess.py local_smoke
```

将运行 seeds 7、8，共72 trials；输入和500步协议与正式相同，seed 与正式样本分离。默认不传 `--seeds 2` 时只跑seed 7。`run_baseline.py` 是旧包原有的单次原始基线入口，不是新实验矩阵；本任务无需运行它。
