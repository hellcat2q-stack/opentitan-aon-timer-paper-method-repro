# V31 17-test 修复回归与独立重跑

新轮次使用最终 reset-generation 修复版，旧结果完整保留。原 Full 的三条失败 seed 已在同一个 V31 simv 上重新通过：

| 原 run ID | seed | UVM_ERROR/FATAL | VCS/URG 返回码 | CPU 秒 | wall 秒 |
| --- | --- | --- | --- | ---: | ---: |
| 307 | 969559112 | 0 / 0 | 0 / 0 | 467.61 | 502.997 |
| 547 | 1885763299 | 0 / 0 | 0 / 0 | 650.36 | 700.295 |
| 918 | 589693528 | 0 / 0 | 0 / 0 | 73.11 | 82.743 |

每条回归都具有非零仿真时间、完整 UVM summary、TEST PASSED CHECKS 和有效 URG 覆盖。故障注入门禁通过：人为将 WKUP 输出卡低时，严格断言仍报出预期的一次错误，该故障测试不计入正式预算。具体检查结果和日志哈希见 `gates.json`。

新轮次的 policy、test-arm identity 和 17-test catalog 共 14 项检查已通过。全部 17 个官方 test 的实际探测已 17/17 通过、0 失败，wall 458.938 秒、CPU 580.92 秒；每项均通过严格日志检查和 4507-bin 解析。随后各方法 30 次 smoke、正式 1000 次和独立审计依次进行，当前进度以 `checkpoint.json` 与 `workflow_status.json` 的观测时间为准。三个 seed 回归通过不能代替正式轮次完成。

Full smoke 已完成 30/30、0 失败、0 重试，覆盖 909/4507（20.1686%），CPU 5212.59 秒、wall 971.152 秒。事件/向量/奖励、test 身份、原始 UVM 日志和输入对照审计通过；39 份初始 VDB 加 30 份 smoke VDB 的独立 URG 合并与 XML 身份核对均通过，合并覆盖同为 909/4507。完整脱敏 smoke 证据见相邻 `stage09_17test_v31_Full_smoke30_20261125/`。

服务器时间 2026-11-25 12:33:18，Full 正式 1000 次已启动。其余五种方法依次先 smoke 再执行正式预算。当前轮次仍在运行，尚未产生正式最终结果；不得将 smoke 的零失败作为正式 1000 次已零失败完成的结论。

六种方法共享同一个修复版 simv、39 条初始语料、4507-bin 分母、10 个 worker、seed 42 和 1000 次预算；关闭 steering，不自动重试。正式预算也必须零失败才能验收；出现失败反馈即保留现场并停止排查。

`source_patch_audit.json` 记录源码补丁逐文件校验和未改动的 RTL、scoreboard、复位后 CSR 检查哈希。`original_failures.json` 保存旧三次断言失败的脱敏摘要和日志哈希；`old_workflow_stop.json` 保存旧 Full 与未完成 NoIncrementalRefill 的停止快照。

服务器工作目录：`scratch/stage09_17test_v31_all_20261125/`。

正式结果目录：`runs/stage09_17test_v31_<方法>_full1000_20261125/`。

此目录仅保存脱敏元数据、哈希和记录。完整日志、simv、VDB 和 URG 报告留在学校服务器。
