# 阶段 01：论文协议与来源

**状态：已完成（2026-11-01）。** 本阶段已完成协议登记、参考结果分离、未知参数清单和来源哈希固定；不代表任何现场仿真已经完成。

## 目标

把论文表 II 的实验协议、方法定义、公开参考值和未知参数分离。确认本项目不把表 II 数字当成实测结果。

## 执行内容

- 读取 `references/IM-1175.pdf`，建立方法、预算、worker、指标和对照矩阵。
- 登记 AON Timer 表 II 的 Full、RandomSelection、NoIncrementalRefill、NoRuntimePenalty、SequenceUCBOnly、ClusterUCBOnly。
- 为未公开的 sequence pool、逐次 CSV、seed、cluster 数量建立 `TBD` 字段。
- 固定论文 PDF、抽取文本和来源 SHA-256。

## 验收产物

- `protocol_manifest.json`：协议、方法定义、来源文件和哈希。
- `reference_results.csv`：论文表 II 的公开参考值，明确标为 `paper_reference_only`。
- `unknown_parameters.json`：尚待阶段 03–06 现场测量的参数。

已通过“参考值不等于现场结果”检查；仓库没有把论文数值写入现场结果。

## 局限

如果工具、许可证、作者输入或 AON Timer sequence 不可用，必须记录为阻碍并停止推进，不用旧项目或 UART 结果填补。
