# v22：30 次 smoke 验证证据

真实 VCS 仿真 30/30 成功、0 失败，最终 916/4507（20.3239%），相对初始 508 个 bin 新增 408 个。四种顶层序列均被 UCB 选中；stress-all 23、jump 3、smoke 3、prescaler 1。按反馈顺序归属的新增 bin 为 stress-all 396、jump 12，另外两种为 0；stress-all 会创建随机 jump 子序列。这些是短预算诊断数据，不是 Full 的最终结果。

`audit.json` 是独立的事件、seed、向量、奖励和成功状态审计，结果为 pass。`union_audit.json` 是另外执行的原始数据库合并检查：39 个初始 VDB + 30 个在线 VDB，由 URG 独立合并，69 个 test，详细覆盖总数 **916/4507**，与向量并集一致。

合并 XML 的逐 bin 身份检查状态为 **partial**：冻结解析器在合并后的框架 `cip_base_pkg::intr_test_cg` cross 中得到 915 个命中，存在 2 个定义标签差异，其中 1 个涉及命中。未发现其他已覆盖 bin 的集合差异；这不等于已经证明全部物理 bin 身份正确。合并报告的 `Group :` 标题兼容仅在独立检查进程中处理，正在运行的 Full 源码和解析器未改动。问题及限制原样记录，不把 partial 改写为 pass。

`protocol.json`/`summary.json` 的 `method: Full` 是历史 runner 对算法配置的命名；实际预算以 `budget: 30` 和提交数为准。导出曲线沿用同一工具的通用 Full 标题，也只含这 30 次的测量数据。`audit.json` 的 URG 行序 limitation 为旧模板文字；本轮实际解析身份定义见 protocol 的 `bin_identity`。

`sha256.txt` 保留服务器原始导出的 8 项文件哈希；`evidence_sha256.txt` 覆盖本目录除其自身之外的全部文件，包含额外的映射验证、参数探针、源码哈希和合并检查摘要。真实 VDB、simv、合并数据库和完整日志只保留在服务器。
