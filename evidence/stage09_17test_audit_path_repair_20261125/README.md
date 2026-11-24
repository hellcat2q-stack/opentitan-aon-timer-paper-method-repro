# 十七测试池审计路径修复与恢复

2026 年 11 月 24 日 15 时 47 分，Full smoke30 完成 30/30，全部成功、0 失败、0 重试，覆盖 958/4507（21.2558%）。事件、身份、原始 UVM 日志、输入对照审计均通过，但独立 URG 合并审计发现新 checkout 缺少两处初始 VDB 目录，工作流按门禁停止，未启动正式预算。

原因是部署独立目录时遗漏 `runs/stage05_initial_corpus_20261101T` 与 `runs/stage05_timeout_fix_20261101T` 两个原始数据路径。2026 年 11 月 25 日补齐软链接前，已逐一核对原始 39 份 cumulative XML 的 SHA256，与冻结 manifest 全部一致；补齐后再次通过检查。

没有修改旧数据库、初始矩阵、冻结运行脚本、算法、预算、worker 或 seed；没有重跑 smoke。修复前后 smoke 协议、结果、事件与覆盖向量的哈希保持一致；87 份冻结依赖重新核对通过。原故障状态保存在 `workflow_before.json`，路径检查和恢复操作分别在 `initial_vdb_link_audit.json`、`repair_record.json` 和 `resume_launch.json`。

独立合并 39 份初始 VDB 和 30 份 smoke VDB 后，URG 得到 958/4507，与逐次向量并集及 XML 身份完全一致，合并审计通过。所有 smoke 门禁通过后，原冻结工作流使用 `--resume` 于 11 月 25 日 00 时 21 分启动 Full 正式 1000 次。

00 时 22 分 31 秒的快照显示 Full 正式提交 13 次、完成反馈 3 次、0 失败，当前覆盖 621/4507（13.7786%）。此为早期进度，不能据此判断最终性能；smoke 覆盖不计入正式结果。其余五方法依原预注册顺序等待执行。

为避免后续部署再次遗漏，新增 `ensure_stage09_initial_vdb_links.py`，并使未来的 17-test prepare 在冻结实验前检查全部初始 VDB。正在运行的工作流仍使用原冻结版本，未改动其源码或依赖。
