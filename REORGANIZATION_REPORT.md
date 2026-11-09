# CPS-A* 整理与核验报告

论文：**Spatiotemporal Potential Field-Based Proactive Coordination for Large-Scale Congested Multi-AGV Systems**；稿号：**TRC-26-01887**。基于此前23个来源的交付包，新增R2-02.zip、R2-03.zip并核验重传R2.07；未混入其他论文数据。

以下15项覆盖本次交付要求，未声称逐字转录旧提问。

1. **交付位置**：完整目录/ZIP为CPS-Astar-public-reproducibility；另有public-source-only源码版。完整包为作者审计归档，不能整包公开。
2. **原论文材料**：原experiment.zip字节完整保留；portable代码在src/original_paper/experiment。结果含42份one-shot JSON、1,310条算法×seed记录、179行lifelong汇总、384行ablation汇总及选取XLSX。
3. **R1对应**：R1.3 d_min90行；R1.5/1.6 Gaussian480行；R1.7/1.8 δ105行；R1.9 retry180行。各自代码、输入、结果和绘图分开。
4. **R2对应**：R2.2表征240行；R2.3原交互2,130行，新增omega390行；R2.4运营180行；R2.5最终替换版70行；R2.7全因子240行。R2.6是跨实验统计要求，不虚构独立实验包。
5. **Canonical选择**：R1独立结果ZIP；R2.04核心180行及配套jobs/workloads/snapshot；R2.05 FRANSEN200_replaced；R2.07五个seed CSV合并240行。
6. **重复与冲突**：d_min/retry内外ZIP字节相同；Gaussian成员相同；δ虽然一份合并、一份75+30拆分，排序105行数值完全相同，不重复计数。旧smoke/pilot只留归档。不同参数、R2.05替换版本、R2.07计划与实际seed差异均保留说明。
7. **可移植修改**：前版代码以显式包导入替换本地/父目录依赖；本次新增R2.02/03保留原始独立目录和compat命名空间，以隔离进程验证；worker以python -m启动；I/O改仓库相对路径；公开manifest记录新旧哈希。原绘图仅跳过没有数据的算法系列。变更清单和redacted diff可追溯。
8. **算法是否改变**：91个规划器文件的995个函数定义AST在排除导入后不变；21项baseline比对和28项R2.04执行快照比对均字节一致。这支持“本次未改规划器函数”，不是对算法正确性或全实验复现的证明。
9. **数据与输入保留**：返修共4,105条分析记录，另有R2.02的40,000条任务记录；统计独立单位仍为5个seed。现有原始结果、任务、jobs、workloads、configs、manifests和质量状态保留。RESULTS_MANIFEST逐文件列出SHA、粒度、行数和seed。
10. **大归档与损坏**：完整保留R2.04 attempts和R2.07 merged包。R2.04为180行结果、106个attempt目录、105个selected payload，105份的8项指标均匹配。R2.07有249损坏文件和1损坏目录头，3个run JSON不可读；237个可读JSON匹配CSV。240行CSV保留；源包损坏与新外层ZIP校验分开报告。
11. **图表复现**：Response图1–4、7、9–13的主要脚本通过；图5–6保留明确标注的SD重建版，并新增原CI流程的可运行输出；图8的omega数据和代码已补齐并重绘。原论文图6可重绘可用系列，图9仅6/8地图；图5、7、8及表7缺必要记录。原消融表4–6有汇总值，无逐seed记录和精确排版来源。详见逐图映射。
12. **统计一致性**：183个显示数值全部在报告精度内匹配。CI用真实5个seed；配对先在seed内做差；R2.04 pooled先对9个条件取seed内平均。R2.07表4用instrumented_pure_seconds，图13用planning_seconds。n=5精确双侧符号翻转最小p=0.0625，不能把t CI排零直接等同精确检验显著。新增Holm family明确是audit定义。
13. **验证程度**：当前环境版本有记录，不冒充历史环境。compile、20个隔离导入、3个源码verifier通过。正式runner命令与安全重分析命令分开。最终新ZIP需通过CRC、空目录解压、哈希/导入/编译检查，结果见交付验证记录。
14. **没有自动公开什么**：Reviewer PDFs、Response和原稿PDF均只在staging登记身份/哈希。原experiment.zip含硬编码凭据，私有精确保留；公开副本改环境变量，diff遮蔽原值。没有推送GitHub、选许可证或编造DOI。引用身份来自原稿，不用回复模板残留无关稿号。
15. **作者待办**：选许可证和发布范围、确认再分发条件、轮换凭据；R2.02/03源码、统计模块和omega数据已补齐；仍需核对R2.02历史代码摘要及正式参考模型、原稿缺失数据/算例/seed记录；提供完整R2.07归档和R2.04事件记录；确认历史环境与30-seed计划状态；统一SD/CI措辞及计时口径；选择大型归档发布位置。

必须披露：早期中断的一次验证曾对不解析参数的R1 Gaussian入口执行--help，误进入实验main。随后环境重置，无法确认完成状态或临时产出；交付未采用其产出。本次恢复的检查不调用runner main，所有数值均可追溯至此前来源和本次新增源码包附带的结果。

本包支持审查并继续完善公开仓库；已验证的部分与缺失、损坏、未验证部分明确区分，没有用猜测补齐。

本次补充详情见docs/UPDATE_20261102.md。R2.07新包与旧包哈希相同，因此保留实际读取限制；新增代码、结果和图表已纳入同一最终版，R2.04内容不变。
