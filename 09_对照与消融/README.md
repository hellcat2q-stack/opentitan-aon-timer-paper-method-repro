# 阶段 09：对照与消融

**最新状态（2026-11-11）：正在 V30 统一环境下重做六种方法的对照与消融。** 六种方法均完成 preflight，第一轮 Full 的 30 次 smoke 已启动；第九步尚未整体完成。旧 RandomSelection 的 1000 次原始结果保留为历史实验，使用旧解析器与旧 build，不能作为 V30 的同协议对照。见 [运行前协议与方法定义](V30统一环境对照与消融_20261111.md) 和 [冻结预注册](preregistration_v30_20261111.json)。

## 目标

在完全相同的初始语料、manifest、预算、worker 和 seed 下运行论文 AON Timer 的对照矩阵。

## 执行内容

- RandomSelection：使用 `algorithm_source/run_vcs_random_selection.py`，从阶段 04/06 冻结的四条 AON Timer 核心序列中均匀有放回随机选择；不启用 UCB、target steering 或 Bayesian training。
- NoIncrementalRefill：批次同步补位，其他组件不变。
- NoRuntimePenalty：去掉 runtime-aware penalty。
- SequenceUCBOnly：固定/取消 cluster-level UCB，只保留 sequence UCB。
- ClusterUCBOnly：固定/取消 sequence-level UCB，只保留 cluster UCB。
- 每个方法先 smoke，再完整 1000 submissions；失败和重试不改预算口径。

V30 新矩阵统一使用已验收的同一个 simv、39 条初始向量、508/4507 初始并集、751 个 cluster、四序列池、seed 42、10 workers 和每方法 1000 次预算。六种方法全部关闭额外参数定向 steering；因此重新运行一轮不定向 Full 作为共同对照，原 V30 的定向 Full 91.5687% 单独保留。每方法独立 30 次 smoke 后，经过事件/向量/目标与全局奖励、原始 UVM 日志及 URG 合并门禁，再从初始语料执行正式预算。

实施入口：`tools/run_stage09_matrix_v30.py`；逐方法执行器：`tools/run_stage09_v30.py`；消融实现：`tools/stage09_policy.py`。运行前 8 项行为测试与六方法 preflight 已通过，完整源码依赖与输入哈希已在服务器冻结。所有方法顺序执行，每轮最多 10 个 worker。最终结果必须等待六轮 Full 及独立合并审计完成后填写。

## 已完成结果

RandomSelection 的 VCS 1000-submit 结果保存在服务器结果目录 `runs/stage09_random_selection_full1000_20261106`，公开脱敏证据导出到本目录 `evidence/stage09_random_selection_full1000_20261106/`。它使用 39 条初始语料、4507 个冻结 bin、seed 42、10 workers、10×100 logical batches。论文未公开完整 AON Timer sequence pool，因此四条本地冻结序列是可复核的本地设定，不宣称等同作者隐藏 pool。coverage、runtime、walltime 和独立审计详见 `summary.json`、`audit.json` 与 `sequence_selection_audit.json`。

## 验收产物

六种方法的原始 manifest、逐次 coverage、runtime/walltime、最终表和曲线；不使用 Bayes 训练结果。

## 局限

如果工具、许可证、作者输入或 AON Timer sequence 不可用，必须记录为阻碍并停止推进，不用旧项目或 UART 结果填补。
