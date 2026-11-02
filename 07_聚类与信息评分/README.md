# 阶段 07：聚类与信息评分

**状态：已完成（2026-11-02）。** 聚类和静态信息评分已在 SMW5 的项目专用 Python 3.11.7 环境中执行，并冻结到 `evidence/stage07_clustering_20261102/`。

## 目标

用师兄的 component-aware/DBSCAN 聚类和信息评分构建调度器离线输入，不引入 Bayesian training。

## 实际执行

- 输入是阶段 06 冻结的 39 行、4507 列 `coverage_bin_by_run.csv`，输入 SHA-256 为 `71c02be6b80cb63973eeb96b26340f7e1d1ae2246674d148774c39c616ff1e94`。
- 比较 `dbscan_clustering.py`、`dbscan_clustering_new.py`、`dbscan_clustering_new2.py` 和 `dbscan_clustering_new3.py`；固定 `PYTHONHASHSEED=0`，最大 cluster 大小参数为 256。
- 按 component、covergroup、variable/cross、coverpoint 和语义 token 记录分区统计；覆盖定义为 hit count > 0。
- 每个 bin 的 self-information 为 `-log(covered_run_frequency)`；cluster 静态权重为 cluster 内平均自信息除以正 cluster 分数均值，并截断到 `[0.25, 4.0]`。

## 结果

`dbscan_clustering_new2.py` 按公开选择规则被选中：78 个 cluster，大小范围 2–218，没有超过 256 的 cluster，也没有 singleton。初始 39 次语料的并集击中 233/4507 个 bin（5.1697%）。所有 4507 个自信息分数有限，4507 个 bin 均有且只有一个 cluster 映射。

选择规则依次最小化超出最大 cluster 大小的数量、singleton 数量、cluster 总数，最后按变体名排序；不使用论文结果或旧项目结果挑选变体。

## 产物和验收

- `clusters.json`、`bin_to_cluster.csv`：冻结的 cluster 成员和 Stage 08 映射；
- `cluster_initial_states.csv/json`、`bin_information_scores.csv`：初始命中、自信息和静态权重；
- `partition_summary.json`：component/covergroup/结构/coverpoint/token 统计；
- `variant_summary.json`、`parameters.json`、`validation.json`、`sha256.txt`：变体比较、参数、独立校验和哈希。

服务器端第二次检查确认矩阵形状为 39×4507、映射完整且无重复、所有分数有限，并返回 `STAGE07_INDEPENDENT_CHECK_OK`。完整仿真数据库仍只保留在学校服务器；本阶段产物只是调度器离线输入，不代表论文表 II 结果。下一步是阶段 08 的真实连续补位仿真。

## 局限

如果后续工具、许可证或作者输入不可用，必须记录为阻碍并停止推进，不用旧项目或 UART 结果填补。
