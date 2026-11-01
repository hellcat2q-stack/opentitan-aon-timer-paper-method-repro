# 阶段 07：聚类与信息评分

**状态：待开始。** 本文件是新项目的执行边界，不代表该阶段已经运行。

## 目标

用师兄的 component-aware/DBSCAN 聚类和信息评分构建调度器离线输入，不引入 Bayesian training。

## 执行内容

- 以 `dbscan_clustering.py` 及其 new/new2/new3 变体做可比性试验，选定一个并记录参数。
- 按 component、covergroup、coverpoint/cross 和语义 token 分区。
- 计算 rarity/self-information、entropy-shaped uncertainty、diversity、size、structure 和动态 residual prior。
- 冻结 cluster mapping、bin-to-cluster、初始命中和静态权重。

## 验收产物

clusters、scores、参数和独立校验；Bayesian optimization 文件不在执行链中。

## 局限

如果工具、许可证、作者输入或 AON Timer sequence 不可用，必须记录为阻碍并停止推进，不用旧项目或 UART 结果填补。
