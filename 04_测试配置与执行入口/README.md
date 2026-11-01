# 阶段 04：测试配置与执行入口

**状态：待开始。** 本文件是新项目的执行边界，不代表该阶段已经运行。

## 目标

把师兄 toolbox 的 UART YAML 改造成 AON Timer 可执行配置，并验证序列、参数、seed、runtime 和覆盖输出的传递。

## 执行内容

- 从官方 AON Timer DV 盘点所有可运行 sequence/variant。
- 每个 sequence+additional_params 作为独立 selectable test。
- 写 AON Timer YAML：base command、test name、sequence、coverage DB、runtime 和 seed 占位符。
- 逐项做 command echo/单次执行校验，确认 seed 不是只写在元数据里。

## 验收产物

AON Timer config、sequence inventory、命令传递证据；当前仓库只保存 `configs/aon_timer_config.template.yaml` 占位模板；师兄 UART YAML 和 Bayes 路径不复制入新项目。

## 局限

如果工具、许可证、作者输入或 AON Timer sequence 不可用，必须记录为阻碍并停止推进，不用旧项目或 UART 结果填补。
