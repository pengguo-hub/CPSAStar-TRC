# 必要接入改动：在实现前冻结的边界

原文件保留在 vendor 内。原循环缺少 release 接口且空队列会立即 break，外围输入对象本身无法令未来任务按时到达；每步重入原 run_lifelong 会重置 cycle 和清理节奏。因此单独的 integration/path_planner_lifelong.py 从原文件复制，仅新增 optional experiment 参数、释放/继续等待接口、被动事件/计时回调。原 SegmentPlanner、TicketManager、ConflictFieldUpdater 和 loader 源码不改。

事件回调需要在原匹配确定后记录请求 ID，在原 failure 回队后保留相同 ID，在原阶段/完成时刻记录时间；它们不选任务、不改任务坐标、不改 phase/status、不引入重试。Request 是长度为2的 tuple 子类，只附加旁路 rid 元数据。原零距离失败行为保留。

唯一主动调度变化是开放输入模式下：暂时没有已释放任务时，不提前结束，调用原空批处理及原时间推进继续等待下一释放时刻，最晚至500。原生积压供给模式不使用这项延长行为。所有模式无预热、无trial墙钟超时、无搜索扩展上限、无静态可达性预检查或物理碰撞检查。

验证要求：相同3000条OD、原初始位置、seed和500步，原生/接入版的completed_tasks、agv_tasks、剩余队列、位置、仿真时间和净assigned必须一致。只有计时和额外记录允许不同。单段函数可由外围透明计时包装器调用原函数，返回值原样返回；所有计时开销分列，禁止将观察耗时作为纯规划耗时。
