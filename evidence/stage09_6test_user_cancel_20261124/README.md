# 六测试池按用户要求取消

2026 年 11 月 24 日 15 时 14 分 55 秒，停止原修复调度器及其当前六测试池进程。停止时任务为 NoIncrementalRefill smoke30，未开始该方法 full1000。

已完成的 6-test Full 及其他旧轮次完整保留，被停止的 smoke 目录也保留；取消剩余 6-test NoIncrementalRefill、NoRuntimePenalty，不再重启。保留原来待执行的 8-test NoRuntimePenalty，安排在新的十七测试池工作流之后独立执行。

`workflow_before.json` 为取消前快照，`cancellation.json` 记录取消范围及未删除旧数据。该停止不是仿真失败，不计入新十七测试池预算。
