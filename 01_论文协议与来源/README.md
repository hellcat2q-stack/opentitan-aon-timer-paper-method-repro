# 阶段 01：论文协议与来源

**状态：待开始。** 本文件是新项目的执行边界，不代表该阶段已经运行。

## 目标

把论文表 II 的实验协议、方法定义、公开参考值和未知参数分离。确认本项目不把表 II 数字当成实测结果。

## 执行内容

- 读取 `references/IM-1175.pdf`，建立方法、预算、worker、指标和对照矩阵。
- 登记 AON Timer 表 II 的 Full、RandomSelection、NoIncrementalRefill、NoRuntimePenalty、SequenceUCBOnly、ClusterUCBOnly。
- 为未公开的 sequence pool、逐次 CSV、seed、cluster 数量建立 `TBD` 字段。
- 固定论文 PDF、抽取文本和来源 SHA-256。

## 验收产物

protocol_manifest.json、参考结果表和未知参数清单；通过“参考值不等于现场结果”检查。

## 局限

如果工具、许可证、作者输入或 AON Timer sequence 不可用，必须记录为阻碍并停止推进，不用旧项目或 UART 结果填补。
