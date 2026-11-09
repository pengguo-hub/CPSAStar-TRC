# R2-05：只重跑 FRANSEN，200 AGV / 3000 初始任务 / 500 步

## 适用版本与安装

依据是你实际运行的 `R2_5_results_formal.zip/results_formal/manifest.json`。该结果包记录的全部 21 个运行源码哈希，已与 `R2-05_Lifelong_verified_repacked.zip` 逐项核对一致。结果包本身是结果和输入，不包含 Python 项目源码。

将本补丁 ZIP 的内容**直接解压到你之前启动实验的工程根目录**，即有 `run.py`、`worker.py`、`protocol.py`、`vendor/` 的目录；不要解压到 `results_formal/` 内。

这是新增入口，不替换任何原文件。原 planner、worker、记录器、配置、原 baseline gate 和 PACKAGE_MANIFEST 均不改。补丁用独立清单校验新增文件，并记录输入生成器的哈希；原运行源码哈希继续保持。不要手动更新或伪造 baseline gate。版本不符时新入口会明确报出不同的文件并停止。

新增的运行必需文件只有：

- `run_fransen_backlog.py`：独立输入生成和单条/FRANSEN 子集运行入口。
- `fransen_backlog_config.json`：本次固定的 200/3000/500 参数。
- `fransen_backlog_reference.json`：实际结果包对应的源码哈希及原 FRANSEN 设置。
- `FRANSEN_BACKLOG_PATCH_MANIFEST.json`：上述新增文件及说明的完整性校验。

`fransen_backlog_validation/` 是本次输入测试与小型接口验证记录，可留作核查。

## 只跑一条 trial

一条 trial = 一种 OD 配对 × 一个 seed。例：只跑 shared、seed1001：

```bash
python run_fransen_backlog.py --level shared --seed 1001 --output results_fransen200_shared_s1001
```

`--level` 可用 `dispersed`、`intermediate`、`shared`；`--seed` 可用 1001–1005。这个命令只运行 1 条，绝不运行其他 69 条或其他两种 OD 配对。它仍是正式的 200 辆、3000 个任务、500 步；不是缩短步数的 smoke。

想先只生成输入、检查设置：

```bash
python run_fransen_backlog.py --level shared --seed 1001 --dry-run --output plan_fransen200_shared_s1001
```

从这份 dry-run 计划启动同一条：

```bash
python run_fransen_backlog.py --level shared --seed 1001 --resume --output plan_fransen200_shared_s1001
```

## 只重跑 FRANSEN 拥堵子实验

若要比较三种配对、保持原先每组五个 seeds，需要 **3×5=15 条**，不是 1 条。其余 STANDARD 的 55 条不必重跑：

```bash
python run_fransen_backlog.py --all --output results_fransen200
```

如想先跑第 1 条，确认后接着跑余下 14 条：

```bash
python run_fransen_backlog.py --all --output results_fransen200 --stop-after 1
python run_fransen_backlog.py --all --output results_fransen200 --resume
```

`--stop-after` 只在完整 trial 结束之后暂停，不截断搜索，也不设置墙钟超时。

完成后可用原审计/统计脚本读取这个独立目录：

```bash
python analyze.py --input results_fransen200
```

此目录只有 FRANSEN 子实验，不应运行要求原 70 条全部齐全的 `postprocess.py` 来伪装完整旧矩阵；旧图中关于 8 辆、λ=0.5 的标注也需据新设置更新。先保留其他 55 条旧结果与新的 15 条结果分开，后续绘图时明确按条件替换 FRANSEN 组，不把旧 8 辆与新 200 辆样本合并求均值。单条运行没有跨 seed 置信区间，也不能建立三组差异。

## 任务如何生成：保留原 OD 配对

沿用结果版本的 `configs/traffic_couplings.json`，不改地图、8 个 origin、8 个 destination、三种 permutation 和距离标签。

**3000 = 375 × 8**。每个完整 8 任务小组中：

1. 各 origin 出现一次；用原 `Random(seed+701)` 打乱组内起点顺序。
2. 用所选 level 的原 permutation，将每个 origin 配到对应 destination。
3. 每个 destination 也恰好出现一次；全部任务 release=0。

因此每组一共 3000 个独立 request ID，每个 origin 与每个 destination 各出现 375 次。三种配对之间保持相同的任务数量、释放时刻、起点顺序、距离标签序列、终点边际次数和 200 辆初始位置，只改变原设计的 OD 配对。

初始位置仍用原 FRANSEN 规则：排除共同取送点及其半径 1 邻域后，按 `Random(seed+101)` 打乱自由格并取前 200 个。实际可用 300 个初始化格点，足够容纳 200 辆且不重叠；前 8 辆的初始位置与旧同 seed 输入相同。这是初始输入规则，不是新增 planner 静态可达性或物理碰撞检查。

不能只把旧 `mode` 改成 `backlogged`：旧 `build_workload` 会优先进入原始随机任务队列分支，从而绕过这套 OD 配对。本入口明确为 backlog 构造原配对任务，再交给原 worker / recorder / Lifelong planner，避免这个问题。

不把 3000 理解为“重新随机生成 3000 对原始 OD”，也不调用原生成器一次生成 3000 个互异 dummy AGV 起点。保留原配对含义并在 375 个完整小组内重复；没有尾部不满 8 个任务的共同配对回退。

## λ、拥堵和结果解释

旧三组都用 λ=0.5，且同 seed 的释放序列匹配，因此 λ 本身不是组间变化的混杂因素。但它限制任务供给，测到的是该开放到达负载下的表现。

新设置不需要 λ：`arrival_rate=null`、`mode=backlogged`、3000 个 release=0；不是把 λ 设置成 0 或一个巨大值。测到的是固定初始积压、200 辆、有限 500 步下的任务处理能力。更符合本轮“充分供给下比较 OD 配对”的目标，但不是证明原来开放供给设计没有意义。

200 辆提高了密度，却不能自动证明三种配对对应严格低/中/高拥堵。继续报告原有 `traffic_encounter_rate`、其分母 `traffic_eligible_moves`、完成数、吞吐量和时间等指标。新旧实验同时改变 N 和任务供给方式，不能将它们的性能差异全归因于单一拥堵变化。

指标仍用原记录器，包括 throughput=completed/500；`source_success_percent`=completed/(completed+active)×100；`completion_fraction`=completed/3000；等待、流程时间、队列和运行时间。后两种完成比例分母不同，不能混用。因所有任务 t=0 到达，等待和流程时间解释也应按初始积压供给描述。

## 恢复、失败与校验范围

新输出目录必须与旧 `results_formal` 分开；相同输出目录恢复时，level/seed 或 --all 的选择、运行源码和输入生成器哈希必须一致。相同条件名仅为兼容旧分析，manifest 的 experiment_id、车队、mode、workload_hash 明确区分新协议。

中断/失败的旧尝试不会删除或自动重跑。确认旧 worker 已退出，检查日志/PID 后，确需重试时可在原命令加 `--resume --retry-incomplete`。未完成 trial 不当作完整 500 步结果。

本交付不运行任何 200 辆正式 trial。验证内容是：实际结果包的源码版本匹配；全部 15 份新输入及跨配对一致性；单条与全部 15 条 dry-run；新增入口与原 worker 的小型接口验证。200 辆正式运行的速度、是否顺利结束和拥堵梯度，须由你正式运行确认。本入口无 MAX_EXPAND、无新增 planner 检查、无 trial timeout，也不改变原 pending 行为。
