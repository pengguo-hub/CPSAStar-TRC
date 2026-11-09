# 正式实验操作说明

## 安装与环境

在解压后的工程根目录运行，推荐 Python 3.12 的独立环境。`requirements-tested.txt` 是本次测试版本；`requirements.txt` 是兼容范围。只需要 NumPy、SciPy、Matplotlib，不依赖旧 R2-05 工程或外部 SRTP 安装。

```bash
python -m pip install -r requirements-tested.txt
python verify_sources.py
```

本包未执行正式 seeds1001–1005。不要把 validation 中的数值或 PNG/PDF 当作正式结果。路径中已有的绝对位置是验证时的环境记录，正常 runner 会按当前解压位置生成新的 job；不要直接执行旧验证 job.json。

## 先确认本机原生基线

```bash
python run_baseline.py --fleet 30 --seed 39 --output local_validation/native30
```

这是独立原始入口的一个诊断 trial：3000 条初始请求、30辆、500步、无预热。对照本包 seed39 的463完成、29活动、2508排队、吞吐量.926、原Success 94.1057%；它们不是强行写入的预期输出。不同机器的墙钟秒数不保证相等。若任务计数明显不一致，先保留日志并检查环境、输入和源码，不启动完整正式矩阵。

## 正式矩阵的分阶段执行

推荐先运行下面第一条。它创建完整70条计划，但只完成第一个30辆 trial 后暂停；暂停发生在完整 trial 之间，绝不截断单个 trial。

```bash
python run.py --formal --output results_formal --stop-after 1
```

第一个结果为 `results_formal/trials/A_fleet30__seed1001/attempt_01/result.json`。核查 `eligible=true`、observed_time=500、3000实际任务、账本守恒、原吞吐量公式以及 native.log。seed1001 不要求与seed39的463完成精确相等。若明显异常，停止在此排查。

确认30辆没有明显基线偏差后，再完成其余14个车队 trial；保留相同输出目录和默认完整配置。

```bash
python run.py --formal --output results_formal --resume --stop-after 14
```

这时30/10/50各有5个正式seed。查看车队结果和状态后，再执行剩余55个扩展 trial：

```bash
python run.py --formal --output results_formal --resume
```

已有本机基线及车队核验时，也可用 `python run.py --formal --output results_formal` 从新目录顺序运行全部70条，顺序仍先30、10、50，再扩展。不要并行启动相同输出目录，不要边运行边改配置或代码。若自己修改参数，应作为不同协议与新目录，不能混合成本文冻结矩阵。

`--cases` 和 `--seeds` 只允许已冻结条件/seed的子集；子集创建的manifest不能直接用全矩阵命令续接。正常正式实验推荐上面的完整计划+trial间暂停方式。`--dry-run` 只创建输入与计划，不运行任何仿真。

## 长时间运行、中断与续跑

无 timeout 参数、无自动 kill、无自动重试。`manifest.json` 保存当前PID、目录、状态；`native.log` 是原输出，`progress.json` 每10步写入当前仿真时刻、完成/排队数和经过秒数。单次搜索未返回时这些文件可能暂时不更新，不能把它当成功或失败。

进程长时间未完成，应保留PID、日志、输入、当前运行时间并由操作者决定是否继续。Ctrl+C或宿主中断保留现有目录；父进程不主动杀掉子进程，终端系统可能向同一进程组发信号。重跑前先确认旧进程已经结束，避免重复占用与重复结果。

```bash
python run.py --formal --output results_formal --resume
```

该命令跳过已有合格完成项，遇到未完成旧尝试会停下来。确实决定重试时：

```bash
python run.py --formal --output results_formal --resume --retry-incomplete
```

新尝试写 attempt_02 等新目录；旧失败/中断日志仍保留。统计每个条件/seed只取第一个合格完整尝试，不把重复尝试当独立样本。运行中使用强制结束可能没有最终JSON，此时审计仍以未完成记录保留。

## 运行后生成论文数据与图

```bash
python postprocess.py --input results_formal
```

该命令依次执行原始记录审计、按seed统计、PNG/PDF绘图和英文数值回复草稿。若有未完成/无效trial或只是子集，会停止完整交付流程，不伪造完整均值。

需要查看部分数据时可单独使用：

```bash
python analyze.py --input results_formal
python plot_results.py --analysis results_formal/analysis
python make_response.py --analysis results_formal/analysis
```

部分数据审计返回2是未完成提示，不代表已保存结果消失；图中缺测保留为空，回复标注未完成。不要把部分输出提交为完成矩阵。审稿回复的图表编号、正文行号和科学结论仍由作者最后核对。

主要输出：`analysis/trial_results.csv`、`trial_audit.csv`、`summary_results.csv`、`summary_long.csv`、`paired_contrasts.csv`、`raw_audit.json`、`traffic_matching.json`，以及 `figures/Figure_R2_05_scalability.png/pdf`、`Figure_R2_05_traffic_validation.png/pdf`、地图图与图注、`analysis/Reviewer_2_5_response_draft.md`。

## 另行运行 smoke

```bash
python run.py --smoke --output my_smoke
python analyze.py --input my_smoke
python plot_results.py --analysis my_smoke/analysis --validation-preview
```

smoke仅seed901；每条仍500步且无预热/timeout。它验证完整流程，不能进入正式论文统计。不要改purpose标签把smoke转换为正式数据。
