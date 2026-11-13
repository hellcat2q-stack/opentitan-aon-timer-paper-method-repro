# OpenTitan AON Timer 论文方法复现（重设计）

这是一个全新的复现项目，目标是最大限度复现论文 **Entropy-Aware and UCB-Driven Coverage Closure for Hardware Verification** 在 OpenTitan AON Timer 上的真实方法链和对照数据。它不沿用旧项目的阶段划分、旧调度器或旧结果。

最新实测（2026-11-11）：阶段 08 的 V30 失败修复 Full 已完成，1000/1000 成功、0 失败、0 重试，覆盖 4127/4507（91.5687%），全量原始 UVM 日志及 1039-VDB 独立 URG 合并审计通过。原 V22 保留为 4105/4507、4 次失败；本轮保留其 UCB 算法及冻结输入，修复测试平台与执行流程。详细分析见 [V30 修复与最终报告](08_两层UCB在线复现/v30_WKUP复位与CDC写入修复_20261111.md)，实测证据见 [Full 结果](08_两层UCB在线复现/evidence/stage08_v30_full1000_20261111/README.md)。本项目详细功能 bin 指标尚未与论文分母完全对齐，下文历史结果按各版本保留。

阶段 09 最新进度（2026-11-13 09:16）：统一 V30 build 与输入、六方法全部关闭额外参数定向，已验收 4/6。Full 4125/4507（91.5243%）、NoIncrementalRefill 4096/4507（90.8809%）、NoRuntimePenalty 4156/4507（92.2121%）、RandomSelection 3274/4507（72.6426%），均为 1000/1000 成功、0 失败、0 重试且全量审计通过。第五种 SequenceUCBOnly 完成 262/1000、0 失败，2228/4507；ClusterUCBOnly 等待顺序执行。[第十步四方法部分复核](10_结果复核与论文对比/evidence/stage10_v30_partial_20261113/README.md) 重读 4000 份原始日志/覆盖计数并独立重算通过，最终比较仍需等待余下两方法。方法定义、证据入口与描述性比较见 [第九步协议与进度](09_对照与消融/V30统一环境对照与消融_20261111.md)。

## 论文中要复现的协议

论文 AON Timer 表 II 给出的比较方法为：Full、NoIncrementalRefill、NoRuntimePenalty、RandomSelection、SequenceUCBOnly、ClusterUCBOnly。统一实验设置是逻辑 batch size 10、100 个 logical batches、总计 1000 次提交、10 个并行 worker、相同初始覆盖语料和相同随机种子。论文报告值只作为待核对的公开参考，不预先写入现场结果：Full 75.33%，Random Selection 16.67%，其余方法见 `01_论文协议与来源/论文协议.md`。

论文没有公开完整 AON Timer 回归池、逐次 coverage CSV、作者脚本、随机种子和每次运行日志；因此本项目把“最大限度复现”定义为：锁定同一公开 DUT/revision，重建相同的 coverage 抽取和 bin 口径，直接纳入师兄提供的非 Bayes UCB/聚类/随机运行代码，按论文预算执行真实闭环，并对所有偏差做证据化记录。

## 复现流程

| 步骤 | 目标 | 关键真实产物 | 状态 |
| --- | --- | --- | --- |
| 01 | 锁定论文协议、表 II 目标、不可知参数和来源哈希 | protocol manifest、参考结果表 | 已完成（2026-11-01） |
| 02 | 验收学校服务器、Verisim/Vericov/VCS、许可证和 Python 依赖 | 环境与能力证据 | 已完成（2026-11-01） |
| 03 | 锁定 OpenTitan revision、AON Timer DV 配置并完成 coverage build smoke | 源码/构建哈希、smoke 报告 | 已完成（2026-11-01） |
| 04 | 建立 AON Timer 测试序列与命令配置，逐项验证 seed/coverage 参数传递 | AON Timer config、sequence inventory | 已完成（2026-11-01） |
| 05 | 4 条核心序列各运行 10 次，保存 seed、runtime、覆盖报告和失败 | initial corpus、run manifest | 已完成（40 次原始尝试；修复 timeout 参数后重放 5 个失败 seed，4 PASS、1 UVM_ERROR） |
| 06 | 将真实 coverage 报告转换为 bin-by-run CSV，冻结分母和命中解析 | coverage CSV、bin manifest | 已完成（39 个接受 run、4507 个 bin；2026-11-01） |
| 07 | 用师兄 DBSCAN/组件聚类和信息评分代码生成 cluster mapping 与静态优先级 | clusters、information scores | 已完成（2026-11-02） |
| 08 | 用师兄两层 UCB continuous-refill runner 做真实在线实验：1000 submissions、10 workers、反馈后补位 | Full 在线事件、向量、覆盖曲线 | 已完成（2026-11-02；1000/1000 提交，独立审计通过） |
| 09 | 在同一初始语料和预算下运行 Random、NoIncrementalRefill、NoRuntimePenalty、SequenceUCBOnly、ClusterUCBOnly | 对照/消融曲线和表格 | V30 六方法矩阵验收 4/6，均零失败；SequenceUCBOnly 262/1000、0 失败，ClusterUCBOnly 未启动 |
| 10 | 独立复核哈希、覆盖分母、预算、runtime/walltime，生成与论文表 II 的差异报告 | final report、reproducibility index | 四方法原始文件独立复核通过；最终结论等待步骤 09 六方法齐全，尚未验收 |
| 11 | 独立记录随机序列基线及其与论文随机结果、本地 Full 的比较 | 比较表、曲线和脱敏证据 | RandomSelection 1000 次已完成，Full 对照受定向约束 |

## 算法来源

师兄 toolbox 中的非 Bayes 文件按步骤复制到 `algorithm_source/`：

- 阶段 05：保留 `sequence_based_parallel_test.py` 作为来源参考；VCS 执行入口为 `05_初始语料/tools/run_aon_timer_initial_corpus.py`；
- 阶段 06：`process_csv.py`；
- 阶段 07：`dbscan_clustering*.py`；
- 阶段 08：`generic_adaptive_runner_ucb_continuous_refill_norepeat_poolmi.py`；
- 阶段 09：保留 `generic_parallel_test.py` 作为 Verisim 源码参考；VCS RandomSelection 入口为 `09_对照与消融/algorithm_source/run_vcs_random_selection.py`。

排除清单见 `references/excluded_bayesian_training.md`。仓库中的 AON Timer 配置使用无私有路径的脱敏模板；不得把师兄 UART 配置或其 Bayes 路径直接用于 AON Timer。

## 早期实验记录与当前边界

以下段落保留早期解析器、build 和聚类下的结果；当前验收以文首 V30 结果及第九步进度为准。早期百分比不与新矩阵直接比较。

阶段 01–07 的执行已完成。阶段 05 原始 40 次结果保持不变；查明 stress-all runner 漏传官方仿真 timeout 参数后，独立重放原 5 个失败 seed，4 次通过、1 次出现单独记录的 UVM_ERROR。阶段 06 输入为原始 35 个 PASS 加重放 4 个 PASS，排除 6 个失败尝试，冻结 4507 个 bin 并生成 39 行 CSV。阶段 07 在同一输入上比较四个聚类变体，选定 `dbscan_clustering_new2`，生成 78 个 cluster、bin 映射和自信息/静态权重。阶段 08 已完成真实 smoke 和 1000 次 Full 在线实验：Full 1000 次提交、22 次 UVM_ERROR、最终覆盖 296/4507（6.5676%），独立审计通过。该现场结果不是论文表 II 结果。阶段 09 的 RandomSelection VCS 1000 次已独立审计通过，覆盖 259/4507（5.7466%）；其余四个消融仍未运行。独立步骤 11 已记录随机基线与论文参考及定向 V16 Full 的可比性边界。
