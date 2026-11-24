# 阶段 09：对照与消融

2026-11-24：用户取消剩余 6-test 仿真，改为全部 17 个官方 test 的六方法实验。新轮次使用独立 catalog 和输出；见 [十七测试池实验说明](17test实验说明_20261124.md)。保留所有旧结果，不改变预算或原算法。

2026-11-23 身份修复：八/六测试池的 Full、NoIncrementalRefill、NoRuntimePenalty 受 test ID/sequence 类名混用影响，正在按独立协议重跑；其余三种方法不重跑。详见 [修复与重跑说明](身份修复重跑说明_20261123.md)。旧轮次数据保留，不能据受影响结果推断预期算法性能。

本分支的六测试池实验见 [六测试池实验说明](6test实验说明_20261123.md)，使用独立 `aon_timer_6test_catalog.json` 与 `stage09_6test_*_20261123` 输出。它从原八测试池移除 mem_walk 和 tl_errors，保留四个 IP 专用 test、中断和 CSR 读写；六方法、初始语料、预算、种子、算法与原轮次一致。

本分支新增的八测试池实验见 [八测试池实验说明](8test实验说明_20261119.md)。它使用独立的 8-test catalog 和 `stage09_8test_*_20261119` 输出目录；下文已有六方法结果仍是原四序列池的 V30 结果，不与新实验混合。

八测试池六方法现已全部完成（2026-11-23 复核），每方法 1000/1000、0 失败、0 重试且审计通过；见 [八测试池最终矩阵](../evidence/stage09_8test_matrix_20261119/README.md)。

**最新状态（2026-11-14）：六方法矩阵全部完成并验收。** Full 4125/4507（91.5243%）、NoIncrementalRefill 4096/4507（90.8809%）、NoRuntimePenalty 4156/4507（92.2121%）、RandomSelection 3274/4507（72.6426%）、SequenceUCBOnly 4023/4507（89.2611%）、ClusterUCBOnly 3695/4507（81.9836%），均为 1000/1000 成功、0 失败、0 重试；事件/向量/奖励、原始 UVM 日志及各自 1039-VDB 独立合并审计通过。

六种方法的 smoke 与正式运行脱敏证据均已归档，最后三轮导出的 36 份文件和最终矩阵的 5 份文件哈希与服务器一致。[最终矩阵与比较图](evidence/stage09_v30_matrix_20261111/README.md) 已生成；[第十步六方法独立复核](../10_结果复核与论文对比/evidence/stage10_v30_final_20261114/README.md) 重新读取共 6000 份原始日志、执行记录和覆盖计数后通过。原始数据库、完整日志和 simv 只留服务器。旧随机结果和第八步定向 V30 单独保留。完整方法表、证据入口和分析见 [运行协议与进度](V30统一环境对照与消融_20261111.md)；[预注册](preregistration_v30_20261111.json) 与所有冻结算法保持原样。

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

实施入口：`tools/run_stage09_matrix_v30.py`；逐方法执行器：`tools/run_stage09_v30.py`；消融实现：`tools/stage09_policy.py`。运行前 8 项行为测试与六方法 preflight 已通过，完整源码依赖与输入哈希已在服务器冻结。所有方法顺序执行，每轮最多 10 个 worker。六轮正式预算与独立合并审计现均已完成。

## 历史结果（旧解析器与旧 build）

RandomSelection 的 VCS 1000-submit 结果保存在服务器结果目录 `runs/stage09_random_selection_full1000_20261106`，公开脱敏证据导出到本目录 `evidence/stage09_random_selection_full1000_20261106/`。它使用 39 条初始语料、4507 个冻结 bin、seed 42、10 workers、10×100 logical batches。论文未公开完整 AON Timer sequence pool，因此四条本地冻结序列是可复核的本地设定，不宣称等同作者隐藏 pool。coverage、runtime、walltime 和独立审计详见 `summary.json`、`audit.json` 与 `sequence_selection_audit.json`。

## 验收产物

六种方法的原始 manifest、逐次 coverage、runtime/walltime、最终表和曲线；不使用 Bayes 训练结果。

## 局限

如果工具、许可证、作者输入或 AON Timer sequence 不可用，必须记录为阻碍并停止推进，不用旧项目或 UART 结果填补。
