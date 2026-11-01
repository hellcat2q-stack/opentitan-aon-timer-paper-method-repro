# 阶段 03：DUT 与源码锁定

**状态：已完成（2026-11-01）。** 目标 revision、AON Timer 配置、VCS build、coverage smoke 和直接 URG 报告均已在学校服务器的新项目目录中验收。

## 目标

锁定论文对应的 OpenTitan revision、AON Timer DV 配置和 coverage build，避免 UART 模板或旧项目混入。

## 执行内容

- 固定 revision `9f20940d494a223cc950a5b98f748fb28109d458`，记录源码 tree/hash。
- 核对 AON Timer testbench、coverage source、build mode 和 coverage options。
- 生成可重复的 VCS image；商业 `simv` 只保留在服务器。
- 完成固定 seed 42 的单次 coverage smoke 和直接 URG 报告。

## 验收产物

源码锁定清单、build command、smoke return code、报告摘要见 `evidence/`；不得把 smoke 覆盖率当论文结果。

## 局限

目标 revision 自带的 Python 依赖要求旧版 FuseSoC/Edalize，而阶段 02 的环境较新；本阶段在 `runtime/stage03_compat/` 建立隔离兼容层，未修改原始源码或阶段 02 环境。四个 `dv/cov/*.el` 文件不是目标 commit 的 tracked 内容，未用于最终 URG 报告；它们只作为服务器上的辅助配置保留。

## 结果摘要

- OpenTitan revision：`9f20940d494a223cc950a5b98f748fb28109d458`。
- VCS build：`aon_timer_smoke` 目标，固定 seed 42，返回码 0，生成 `simv`。
- Coverage smoke：返回码 0，UVM `aon_timer_smoke` 为 1/1（100%）。DVSIM coverage dashboard 的 smoke 摘要为 functional 0.99%、total 55.31%；这些数字只用于环境验收。
- 直接 URG（单 VDB、无外部 exclusion 文件）：返回码 0，45/4525 functional group bins，score 0.99%。该报告不是论文正式 coverage 分母。
- 原始 VDB、simv、完整日志和许可证信息仍只保留在服务器；公开哈希和脱敏命令见 `evidence/stage03_*`。
