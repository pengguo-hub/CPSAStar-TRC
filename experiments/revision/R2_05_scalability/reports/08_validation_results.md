# 最终版本验证结果（非正式实验）

运行代码指纹：`89396635d4c5f9d363d898eee42b9cd6c5b4bf4a2a49d861b099b127b1f6384e`。

**正式seeds1001–1005未运行；70条仅完成dry-run输入生成。以下仅是seed901的全时域smoke，各条件n=1，不计算置信区间，不用于论文数值结论。**

| 条件 | 生成/实际释放 | 完成 | 未完成 | 终点队列 | 吞吐量 | 规划秒 | 状态 |
|---|---:|---:|---:|---:|---:|---:|---|
| A_fleet30 | 3000/3000 | 458 | 2542 | 2513 | 0.916 | 1.9357 | completed, audited |
| A_fleet10 | 3000/3000 | 182 | 2818 | 2808 | 0.364 | 0.6295 | completed, audited |
| A_fleet50 | 3000/3000 | 548 | 2452 | 2403 | 1.096 | 5.3405 | completed, audited |
| A_open_base | 274/274 | 249 | 25 | 1 | 0.498 | 1.2287 | completed, audited |
| A_map2_fixed | 274/274 | 251 | 23 | 1 | 0.502 | 1.1372 | completed, audited |
| A_map3_fixed | 274/274 | 255 | 19 | 0 | 0.510 | 1.0492 | completed, audited |
| A_map2_density | 1036/1036 | 948 | 88 | 5 | 1.896 | 6.6861 | completed, audited |
| A_map3_density | 2279/2279 | 2093 | 186 | 11 | 4.186 | 14.6653 | completed, audited |
| A_rate0.25 | 139/139 | 117 | 22 | 0 | 0.234 | 0.5374 | completed, audited |
| A_rate1.0 | 524/524 | 414 | 110 | 80 | 0.828 | 2.1044 | completed, audited |
| A_rate2.0 | 1036/1036 | 443 | 593 | 564 | 0.886 | 1.8072 | completed, audited |
| B_traffic_dispersed | 274/274 | 135 | 139 | 131 | 0.270 | 0.5368 | completed, audited |
| B_traffic_intermediate | 274/274 | 132 | 142 | 134 | 0.264 | 0.6208 | completed, audited |
| B_traffic_shared | 274/274 | 136 | 138 | 131 | 0.272 | 0.5150 | completed, audited |

14/14完成500步，原始请求账本、全程逐步事件重放、完成/活动/排队分区、等待+运动=生存时间、计时求和、输入与代码哈希均通过。无timeout、无失败/中断trial。正式输入计划70条全部state=planned，attempts为空。

## 交通操纵的实际检验

| 配对 | 静态参考重叠 | 实际短时交互暴露比例 | 有效移动到达数 |
|---|---:|---:|---:|
| B_traffic_dispersed | 0.72594 | 0.17456 | 2618 |
| B_traffic_intermediate | 1.15316 | 0.10563 | 2594 |
| B_traffic_shared | 1.65970 | 0.06507 | 2551 |

三组完整释放流、起点序列、初始位置、终点边际计数和配置中的逐起点距离标签匹配。原始轨迹独立离线重算实际交互暴露与记录一致。参考重叠增加，但这一个seed的实际暴露下降；不支持按名称宣称低/中/高实际拥堵，不修改输入或挑选seed制造递增结果。正式结果应再次报告实际暴露、等待/队列和配对差值。

## 验证版本与记录保留

validation/smoke_full500是上一验证修订的14条seed901；validation/smoke_final是当前冻结版本的14条seed901。重复验证是因为源码指纹的相对路径序列化改为POSIX格式以支持Windows迁移；它没有改变规划算法，但需要重新绑定当前代码证据。两个目录独立保留，仅smoke_final进入本报告；不能把同seed重复执行当作n=2。integration_parity是旧修订证据，integration_parity_final是当前版本。

validation/native_baseline为原生10/30/50单seed；native_timing_repeat和native_timing_final为同一30辆任务的计时诊断，不是额外独立样本。9项单元/集成验证通过（含空输入保持500、晚到达、原零距离失败保留、地图数组、交通匹配、统计缺测与CI、离线暴露边界、未完成排除）；原生/接入版三车队末态等价另有证据。

PNG/PDF预览在validation/smoke_final/figures，醒目标注VALIDATION ONLY。正式图会由用户正式结果重新生成，不会混入上述smoke。

## 交付流程附加检查

两条件staged_runner_smoke验证新增的trial间暂停与续跑：第一条完整500步后第二条仍planned，再resume只执行第二条，两条均审计通过。它们仍是seed901的重复流程验证，不加入最终14条件均值。pipeline_checks.json确认smoke回复/无水印绘图/正式后处理入口均拒绝混用、缺测为blank、n=1无CI；最终迁移检查确认新目录原始输入与运行指纹相同且正式dry-run零模拟。三份最终PDF经渲染检查，无裁切和标签重叠。
