# v22 两层 UCB：1000 次 Full

服务器真实 VCS 仿真已完成并通过独立事件/向量/奖励审计。预算 1000，接受 996 次，4 次失败、无重试；最终覆盖 **4105/4507（91.0805%）**，比 508-bin 初始并集新增 3597 bin。累计 simulator CPU 时间 169,428.39 秒，wall time 22,073.08 秒。

顶层序列用量为 stress-all 831、jump 129、smoke 22、prescaler 18；本轮不是全选 jump。31 个定向任务均确认参数已施加，并命中所选目标。4 次失败均为 stress-all 任务，VCS 退出码为 0，但 `aon_timer_scoreboard.sv:304` 检查 WKUP 期望中断为 1、实际引脚为 0，UVM_ERROR=1、UVM_FATAL=0。失败按预注册协议占用预算且不获覆盖奖励；未重试。

`audit.json` 确认 1000 个 seed、覆盖向量、奖励增量、补位事件和哈希链一致，996 次接受运行均通过 UVM 检查，990 次补位均发生在反馈后。当前使用的 4507-bin 初始矩阵、稳定 XML parser 与 VCS `simv` 的冻结哈希记录在 `protocol.json`。

本结果是 v22 处理组。配对的 v20 UCB 控制组 Full 为 1739/4507（38.5844%）；v22 多覆盖 2366 bins（52.4961 个百分点）。两组配对输入检查、事件/向量/奖励审计和原始 VDB URG bin 身份复核均通过。最终结果和单 seed 结论限制见[配对报告](../stage08_v20_v22_ucb_pair_full1000_20261110/README.md)。覆盖值是项目现场结果，不是论文指标。VDB、simv 和完整日志只在服务器。
