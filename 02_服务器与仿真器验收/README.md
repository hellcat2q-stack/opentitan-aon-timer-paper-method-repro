# 阶段 02：服务器与仿真器验收

**状态：已完成（2026-11-01）。** VCS/URG、覆盖报告和项目 Python 依赖均已通过阶段验收；本阶段没有运行 AON Timer 正式实验。

## 目标

确认学校服务器上有可用的 Verisim/Vericov 或 VCS/URG、许可证和 Python 依赖；验证最小仿真与覆盖报告闭环。

## 执行内容

- 记录主机、账户、工具版本、许可证状态、Python/依赖版本。
- 用 `algorithm_source/verisim`、`algorithm_source/vericov` 只作为入口参考，不提交商业环境。
- 运行一个最小 UVM/coverage 正例和一个失败/无覆盖对照。
- 验收报告生成、退出码和日志可解析。

## 验收产物

- `evidence/stage02_summary.json`：服务器、工具、覆盖能力和 Python 依赖的脱敏摘要。
- `evidence/coverage_return_codes.txt`：正例/负例覆盖探针返回码。
- 服务器隔离目录中的原始 VCS/VDB/URG 日志和哈希索引：`/SM03/home/bs2022/bs202264680312/opentitan_aon_timer_paper_method_repro/evidence/02_env/`。

VCS 最小编译/运行、覆盖正例/负例、URG 报告生成和项目 Python 模块导入均通过；算法源码尚未同步，`compileall` 留待后续仓库同步。项目专用 Python 3.11.7 环境的 `pip check` 输出 `No broken requirements found.`。

## 局限

如果工具、许可证、作者输入或 AON Timer sequence 不可用，必须记录为阻碍并停止推进，不用旧项目或 UART 结果填补。
