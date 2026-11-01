# 阶段 03：DUT 与源码锁定

**状态：待开始。** 本文件是新项目的执行边界，不代表该阶段已经运行。

## 目标

锁定论文对应的 OpenTitan revision、AON Timer DV 配置和 coverage build，避免 UART 模板或旧项目混入。

## 执行内容

- 固定 revision `9f20940d494a223cc950a5b98f748fb28109d458`，记录源码 tree/hash。
- 核对 AON Timer testbench、coverage source、build mode 和 coverage options。
- 生成可重复的 VCS/Verisim image。
- 完成单次 coverage smoke 和 URG/Vericov 报告。

## 验收产物

源码锁定清单、build command、smoke return code、报告摘要；不得把 smoke 覆盖率当论文结果。

## 局限

如果工具、许可证、作者输入或 AON Timer sequence 不可用，必须记录为阻碍并停止推进，不用旧项目或 UART 结果填补。
