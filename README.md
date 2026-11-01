# OpenTitan AON Timer 论文方法复现（重设计）

这是一个全新的复现项目，目标是最大限度复现论文 **Entropy-Aware and UCB-Driven Coverage Closure for Hardware Verification** 在 OpenTitan AON Timer 上的真实方法链和对照数据。它不沿用旧项目的阶段划分、旧调度器或旧结果。

## 论文中要复现的协议

论文 AON Timer 表 II 给出的比较方法为：Full、NoIncrementalRefill、NoRuntimePenalty、RandomSelection、SequenceUCBOnly、ClusterUCBOnly。统一实验设置是逻辑 batch size 10、100 个 logical batches、总计 1000 次提交、10 个并行 worker、相同初始覆盖语料和相同随机种子。论文报告值只作为待核对的公开参考，不预先写入现场结果：Full 75.33%，Random Selection 16.67%，其余方法见 `01_论文协议与来源/论文协议.md`。

论文没有公开完整 AON Timer 回归池、逐次 coverage CSV、作者脚本、随机种子和每次运行日志；因此本项目把“最大限度复现”定义为：锁定同一公开 DUT/revision，重建相同的 coverage 抽取和 bin 口径，直接纳入师兄提供的非 Bayes UCB/聚类/随机运行代码，按论文预算执行真实闭环，并对所有偏差做证据化记录。

## 十步流程

| 步骤 | 目标 | 关键真实产物 | 状态 |
| --- | --- | --- | --- |
| 01 | 锁定论文协议、表 II 目标、不可知参数和来源哈希 | protocol manifest、参考结果表 | 已完成（2026-11-01） |
| 02 | 验收学校服务器、Verisim/Vericov/VCS、许可证和 Python 依赖 | 环境与能力证据 | 已完成（2026-11-01） |
| 03 | 锁定 OpenTitan revision、AON Timer DV 配置并完成 coverage build smoke | 源码/构建哈希、smoke 报告 | 已完成（2026-11-01） |
| 04 | 建立 AON Timer 测试序列与命令配置，逐项验证 seed/coverage 参数传递 | AON Timer config、sequence inventory | 已完成（2026-11-01） |
| 05 | 4 条核心序列各运行 10 次，保存 seed、runtime、覆盖报告和失败 | initial corpus、run manifest | 已完成（40 次尝试；35 UVM PASS，5 PH_TIMEOUT 已记录） |
| 06 | 将真实 coverage 报告转换为 bin-by-run CSV，冻结分母和命中解析 | coverage CSV、bin manifest | 待开始 |
| 07 | 用师兄 DBSCAN/组件聚类和信息评分代码生成 cluster mapping 与静态优先级 | clusters、information scores | 待开始 |
| 08 | 用师兄两层 UCB continuous-refill runner 做真实在线实验：1000 submissions、10 workers、反馈后补位 | Full 在线事件、向量、覆盖曲线 | 待开始 |
| 09 | 在同一初始语料和预算下运行 Random、NoIncrementalRefill、NoRuntimePenalty、SequenceUCBOnly、ClusterUCBOnly | 对照/消融曲线和表格 | 待开始 |
| 10 | 独立复核哈希、覆盖分母、预算、runtime/walltime，生成与论文表 II 的差异报告 | final report、reproducibility index | 待开始 |

## 算法来源

师兄 toolbox 中的非 Bayes 文件按步骤复制到 `algorithm_source/`：

- 阶段 05：保留 `sequence_based_parallel_test.py` 作为来源参考；VCS 执行入口为 `05_初始语料/tools/run_aon_timer_initial_corpus.py`；
- 阶段 06：`process_csv.py`；
- 阶段 07：`dbscan_clustering*.py`；
- 阶段 08：`generic_adaptive_runner_ucb_continuous_refill_norepeat_poolmi.py`；
- 阶段 09：`generic_parallel_test.py` 和绘图脚本。

排除清单见 `references/excluded_bayesian_training.md`。仓库中的 AON Timer 配置使用无私有路径的脱敏模板；不得把师兄 UART 配置或其 Bayes 路径直接用于 AON Timer。

## 当前边界

阶段 01–05 的执行已完成。阶段 05 共运行 40 次，其中 35 次 UVM PASS、5 次 stress-all 触发 PH_TIMEOUT；失败记录保留且未重跑，失败的部分 coverage 不纳入成功语料。阶段 03–05 的 smoke/单序列/初始语料 coverage 都不是论文表 II 结果；阶段 06 将在通过的 run 上转换 coverage 并冻结正式 bin 分母。
