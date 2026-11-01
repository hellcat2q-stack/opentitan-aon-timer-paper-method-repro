# 阶段 08：两层 UCB 在线复现

**状态：待开始。** 本文件是新项目的执行边界，不代表该阶段已经运行。

## 目标

使用师兄的真实 continuous-refill runner 执行 Full 方法，不做 replay-only 代替真实仿真。

## 执行内容

- 使用 `generic_adaptive_runner_ucb_continuous_refill_norepeat_poolmi.py`。
- 先做 10-submit/10-worker smoke，再做论文协议 H=1000、logical batch=10、100 batches、P=10。
- 第一层选择 target cluster；第二层在 target-conditioned sequence domain 中选择 sequence。
- 每个 worker 完成后立即解析 coverage，按新 bin、target gain、opportunity gain 更新状态并补位。
- 记录 submitted/completed/failed、runtime、walltime、policy/event hash chain。

## 验收产物

Full 的真实事件日志、逐次向量、coverage-vs-runtime 曲线和预算审计；没有真实反馈的回放只能作为开发测试。

## 局限

如果工具、许可证、作者输入或 AON Timer sequence 不可用，必须记录为阻碍并停止推进，不用旧项目或 UART 结果填补。
