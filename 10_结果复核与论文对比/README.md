# 阶段 10：结果复核与论文对比

**状态（2026-11-14 17:45）：阶段 10 已完成。** 在服务器使用冻结复核程序复核六种正式方法，共重新读取 6000 份原始 UVM 日志、执行记录和覆盖计数；六种方法的事件、覆盖向量、奖励、CPU/wall 曲线、失败预算和已有独立 URG 身份审计均通过。每种方法 1000/1000 完成，0 失败、0 重试，共享同一初始语料、覆盖定义、seed 和 worker 配置。

最新 [六方法最终报告](evidence/stage10_v30_final_20261114/README.md)、[机器可读复核](evidence/stage10_v30_final_20261114/verification.json) 和 [论文参考比较表](evidence/stage10_v30_final_20261114/comparison.csv) 已生成。覆盖依次为 4125、4096、4156、3274、4023、3695/4507；各方法最后 100 次新增分别为 56、29、46、141、56、149 bins。8 项阶段 10 行为测试通过；最终报告文件哈希已复核。[11 月 12 日和 13 日的 partial 报告](evidence/stage10_v30_partial_20261113/README.md) 保留为历史快照。此处对比为第九步统一关闭参数定向的矩阵，第八步定向 V30 4127/4507 单独保留。

最终交付的[复现索引](evidence/stage10_v30_final_20261114/reproducibility_index.md)汇总六种方法的逐次证据、比较图、冻结输入及[六项来源哈希](evidence/stage10_v30_final_20261114/source_sha256.txt)，可从报告追溯到每项正式运行。

## 已实施的独立复核

- 冻结输入为当前真正使用的 39 条初始语料、4507 个 bin、508-bin 初始并集、751 个 cluster；[输入副本与哈希](inputs/v30_20261112/README.md) 保留原始字节，不沿用旧解析器的数据。
- [复核程序](tools/verify_stage10_v30.py) 只读已完成的第九步导出及服务器原始文件，独立核对 manifest、预注册 seed、事件链、预算、补位/批次屏障、向量、覆盖并集、目标与全局新增奖励、逐次 CPU/wall 曲线、失败预算和末段增益。
- 服务器模式通过 `--raw-runs-root` 重新读取每项原始 `execution.json`、UVM 日志和 `coverage_counts.json`，对比日志 CPU 时间、真实 PASS、非零仿真时间、ERROR/FATAL 数和逐 bin 向量；原始日志和数据库不导出。URG 合并结果与第九步已有独立身份审计核对，本次未重新启动 URG。
- 本地与服务器 8 项行为/错误拦截测试均通过，覆盖实际 Full 重算、缺失方法处理、改错奖励/CPU/向量/worker/URG 并集及导出文件变更。本轮测试和原始复核状态见[最终测试记录](evidence/stage10_v30_final_20261114/behavior_tests.txt)。
- 缺少正式方法或未执行原始文件复核时，输出明确为 `partial`、`complete=false`，默认退出码为 2。输入或证据矛盾时失败并退出 1；只有六方法完整、共享协议一致且原始文件复核通过才允许最终 `pass`。`--allow-incomplete` 仅允许准备流程接受部分报告，不会改变其完成状态。

复核程序拒绝覆盖已有输出目录，下一次运行需选择新的目录。原第九步算法、冻结文件、仿真进程和结果目录均保持原样。

## 运行方式

从仓库根目录执行本地导出复核（本地未提供原始日志目录，因此报告会明确保持部分复核状态）：

```text
python 10_结果复核与论文对比/tools/verify_stage10_v30.py --evidence-root 09_对照与消融/evidence --initial-csv 10_结果复核与论文对比/inputs/v30_20261112/coverage_bin_by_run.csv --mapping 10_结果复核与论文对比/inputs/v30_20261112/bin_to_cluster.csv --preregistration 10_结果复核与论文对比/inputs/v30_20261112/preregistration_v30_20261111.json --paper-reference 10_结果复核与论文对比/inputs/v30_20261112/reference_results.csv --output <新的输出目录>
```

在学校服务器运行时，使用服务器项目根目录的 `evidence`、真实初始 CSV 和 mapping，并加入 `--raw-runs-root <服务器项目根目录>/runs`。隔离工具和测试保存在服务器 `scratch/stage10_v30_review_20261112/`；历史 partial 输出为 `evidence/stage10_v30_partial_20261112/` 和 `evidence/stage10_v30_partial_20261113/`，本轮最终输出为 `evidence/stage10_v30_final_20261114/`。

Full 的 walltime 摘要为 30043.107 秒，最后一次覆盖反馈为 30036.399 秒，报告尾部开销约 6.708 秒。分别记录这三个量，避免把摘要收尾时间解释为纯仿真时间。论文覆盖分母、pool、seed 和 runtime 定义未完全对齐，报告只列描述性差值，不计算算法加速比。

## 目标

独立检查所有结果是否真的满足论文协议，并形成可审计差异报告。

## 执行内容

- 重新计算 bin 分母、最终覆盖、累计 runtime、walltime 和 late-stage 增益。
- 检查所有方法是否同一 initial corpus、H、P、logical batch、seed 和 failure policy。
- 对照论文表 II，报告绝对差异和可归因偏差；不强行解释或伪造缺失数据。
- 生成最终图、CSV、manifest、hash index 和复现实验说明。

## 验收产物

final verification、论文差异表、结果归档和 GitHub 交付；结论只基于本项目真实证据。

## 局限

如果工具、许可证、作者输入或 AON Timer sequence 不可用，必须记录为阻碍并停止推进，不用旧项目或 UART 结果填补。
