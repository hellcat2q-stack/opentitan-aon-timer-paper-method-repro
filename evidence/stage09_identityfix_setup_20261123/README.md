# 身份修复实验：预注册与启动检查

运行代码提交 `47c4a89021f4a5d2085035d91051406f6e40def8`，GitHub 分支 `codex/test-arm-identity-fix`。两个测试池的全部六方法共 12 次 preflight 通过；每次均确认 39 条初始向量、508/4507。服务器运行了原有 8 项策略行为测试和 3 项精确源码身份测试，两池各通过一次。本地另外通过 7 项 catalog 检查。

`preregistration.json` 冻结重跑范围及预算；`8test_preregistration.json`、`6test_preregistration.json` 为逐池记录，两个 `frozen_relative_sha256.txt` 将服务器原始绝对路径改为仓库相对路径，以保留脱敏后的文件身份与哈希。原始冻结清单的哈希保存在预注册中，完整清单留服务器。

Full、NoIncrementalRefill、NoRuntimePenalty 各重跑八/六测试池，顺序为 Full 8/6、NoIncrementalRefill 8/6、NoRuntimePenalty 8/6。每任务 30 次 smoke 后独立正式 1000 次，seed 42、batch 10、10 workers、全局任务并发 1、无 steering、无 retry。所有正式运行必须先通过各自 smoke 的完整审计。

`unaffected_methods_review.json` 对 RandomSelection、SequenceUCBOnly、ClusterUCBOnly 的原八测试池共 3000 次记录逐项连接并核对 test ID、执行 sequence、官方 test 和 options，未发现错位。这三种方法不重跑。六测试池尚无后三者正式结果，本次也不新增任务。

`launch_record.json`、`launch_snapshot.json` 只表示实际启动状态，不能视为正式实验完成。完整仿真日志和数据库仅留服务器；后续结果另按独立运行名导出。
