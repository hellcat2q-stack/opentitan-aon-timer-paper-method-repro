# 阶段 06：覆盖数据转换

**状态：待开始。** 本文件是新项目的执行边界，不代表该阶段已经运行。

## 目标

用师兄 `process_csv.py` 将真实报告转换为 bin-by-run 数据，并冻结唯一分母、命中解析和 runtime 字段。

## 执行内容

- 对每个初始 run 生成 HTML/coverage database 派生数据。
- 执行 `algorithm_source/process_csv.py`，保留命令、版本和输入哈希。
- 生成 canonical CSV：run、sequence、seed、runtime、bin columns。
- 核对 type/instance/summary 行，防止重复计数。

## 验收产物

coverage CSV、manifest、bin count/eligible rule、解析校验和；所有方法必须使用同一 manifest。

## 局限

如果工具、许可证、作者输入或 AON Timer sequence 不可用，必须记录为阻碍并停止推进，不用旧项目或 UART 结果填补。
