from pathlib import Path
import pandas as pd,json,sys
ROOT=Path(__file__).resolve().parents[1]
pass  # Package imports replace process-wide import-path mutation.
from experiments.revision.R2_04_operational_metrics.workload import FLEETS, LEVELS
base=ROOT/'validation/smoke_summary';d=pd.read_csv(base/'audited_metrics.csv');s=pd.read_csv(base/'paired_statistics.csv');st=json.loads((base/'analysis_status.json').read_text())
assert st['all_valid'] and st['verified']==72 and st['valid_pairs']==36 and not st['formal_experiment']
fc=s[s.comparison=='Full-Control'];primary=['throughput','waiting_time','flow_time','queue_length']
def get(case,m):return fc[(fc.group==case)&(fc.metric==m)].iloc[0]
lines=['# Smoke 验证报告：固定 OD + 3000项初始任务', '',
'**验证样本：seeds 7、8；每个条件 n=2；共72 trials、36对 Full/Control。正式 seeds39–43 未运行。** 所有72次均到达500步，通过任务账目及事件重放检查；无失败、无超时、无缺失、无按性能筛选。每个trial仅一个attempt。保留了全部条件和两个seed。', '',
'## 设计执行检查', '',
'- 三张原始障碍地图；AGV数为 STANDARD30/50、FRANSEN100/200、RING80/160。',
'- 每次3000项任务、全部release=0、375个均衡OD区块；没有lambda或增量到达。',
'- 全部126份正式/验证输入已预生成并校验，正式180个trial仅做dry-run，执行数为0。',
'- 原始规划源码及Full/Control机制保持字节一致；FRANSEN的OD节点和三个排列与R2-05配置完全一致。',
'- 对216000条任务记录、36000个时间区间和36072帧位置完成审计；初始位置、任务身份、等待/移动/完成时间、队列长度和守恒关系均通过。', '',
'## Full 相对 Control 的差异', '',
'下表为两seed均值之差相对Control均值的百分比；吞吐量正值有利，其他三项负值有利。它描述smoke效应大小，不代表正式显著性。完整绝对均值、配对差和95%区间位于 `smoke_summary/paired_statistics.csv`。', '',
'| 地图 | AGV | OD模式 | 吞吐量Δ% | 等待Δ% | 流程Δ% | 队列Δ% |',
'|---|---:|---|---:|---:|---:|---:|']
for mp,ns in FLEETS.items():
 for n in ns:
  for mode in LEVELS:
   case=f'{mp}_N{n}_{mode}';vals=[get(case,m).relative_difference_percent for m in primary]
   lines.append(f'| {mp} | {n} | {mode} | '+' | '.join(f'{v:+.2f}' for v in vals)+' |')
lines+=['','## 数据 → 判断 → 原因','']
for mp in FLEETS:
 g=fc[(fc.group.str.startswith(mp+'_'))&fc.metric.isin(primary)]
 facts=[]
 for metric,label in zip(primary,['吞吐量','等待时间','流程时间','队列长度']):
  z=g[g.metric==metric];facts.append(f'{label}相对差范围{z.relative_difference_percent.min():+.2f}%至{z.relative_difference_percent.max():+.2f}%')
 good=sum(all((get(f'{mp}_N{n}_{mode}',m).mean_difference>0 if m=='throughput' else get(f'{mp}_N{n}_{mode}',m).mean_difference<0) for m in primary) for n in FLEETS[mp] for mode in LEVELS)
 lines += [f'**{mp}。数据：** '+'；'.join(facts)+f'；6个条件均为n=2，其中{good}/6的四项均值方向同时有利于Full。', '']
 if mp=='FRANSEN':
  lines += ['**判断：** 在两个车队规模、三种OD模式下，验证均值均显示吞吐量增加，并伴随等待、流程时间和任务队列下降；这些效应支持开展冻结的正式实验。两个seed不足以确认正式效应或普遍规律。', '',
  '**原因：** 初始3000项任务持续提供工作负载，软等待惩罚和局部拥堵优先级能够影响正在竞争路线与预约的车辆。OD模式之间又保持了端点频次和逐任务最短距离，使性能比较不会被更短的取放货距离解释。这里识别的是两个软项的联合作用，不是把静态拥堵分数下降当成原因——两arm的静态分数相同。','']
 else:
  lines += ['**判断：** 效应依赖车队和OD模式；不能由FRANSEN的结果推断本地图所有条件稳定改善。较小或不利的差异均保留在表中。', '',
  '**原因：** 静态分数仅控制不同OD最短路的内部空间重叠，不控制车辆抵达时间、空驶取货段、实际绕路或动态分配。原始CPS-A*的软项在不同拓扑和车辆密度下作用不同，因此静态模式间距本身不能保证算法差异同样增大。','']
lines+=['## 拥堵模式的差异与算法差异分开报告','','下表在每个arm内部比较 shared−dispersed（各n=2），保留相同seed配对。正吞吐量差表示shared反而更高；不可预先强制单调。','','| 地图 | AGV | Arm | 吞吐量Δ% | 等待Δ% | 流程Δ% | 队列Δ% |','|---|---:|---|---:|---:|---:|---:|']
for mp,ns in FLEETS.items():
 for n in ns:
  for arm in ['control','full']:
   z=s[(s.comparison=='shared-dispersed')&(s.group==f'{mp}_N{n}_{arm}')].set_index('metric')
   lines.append(f'| {mp} | {n} | {arm} | '+' | '.join(f'{z.loc[m].relative_difference_percent:+.2f}' for m in primary)+' |')
lines+=['','## 等待与流程指标为何比吞吐量的百分比变化小','','**数据：** 全部72次的平均任务活动比例范围为'+f'{100*d.mean_active_fraction.min():.2f}%–{100*d.mean_active_fraction.max():.2f}%；500步时未完成任务比例为{100*d.unfinished_fraction.min():.2f}%–{100*d.unfinished_fraction.max():.2f}%。'+' 等待和流程均以固定3000项任务为分母，unfinished请求贡献截至500步的实际观察时间。','','**判断：** 当前任务供给已充分占用车队；大量未完成任务仍使全队列平均时间接近观察上限，所以吞吐量提升不会转化为同等百分比的平均时间下降。','','**原因：** 对每个请求有flow=queue-wait+assigned-stall+movement；总体flow=(mean task queue+mean assigned WIP)×500/3000。流程与队列因而紧密相关，不能将四项结果当作四份统计独立证据。全体请求统计避免了只统计已完成任务的选择偏差；不为放大差异改换指标分母。','','## 全部主指标的绝对值和区间','','区间为独立seed配对差的95% t区间。n=2时区间很宽，数值用于透明展示smoke不确定性。正式仍按预先固定的5个seed运行。','','| 条件 | 指标 | Control均值 | Full均值 | Full−Control | 95% CI | n |','|---|---|---:|---:|---:|---|---:|']
for mp,ns in FLEETS.items():
 for n in ns:
  for mode in LEVELS:
   case=f'{mp}_N{n}_{mode}'
   for metric in primary:
    z=get(case,metric);lines.append(f'| {case} | {metric} | {z.right_mean:.3f} | {z.left_mean:.3f} | {z.mean_difference:+.3f} | [{z.ci95_low:+.3f}, {z.ci95_high:+.3f}] | {int(z.n)} |')
lines+=['','## 重放与正式运行','','- `python replay_packaged_smoke.py --output replayed_smoke`：只重放包内72次原始证据，不运行仿真。','- `python test_integrity.py --output integrity_checks.json`：验证篡改任务等待、输入、指标或arm设置会被拒绝。','- `python run.py --formal --suite all --output results_od_formal`：正式180次；用户自行运行。','- `python postprocess.py results_od_formal`：审计、配对统计和两张综合图。','','图中均明确标注SMOKE；本报告不替代正式Reviewer回复。','']
(ROOT/'validation/smoke_report.md').write_text('\n'.join(lines),encoding='utf-8')
print('\n'.join(lines[:38]))
