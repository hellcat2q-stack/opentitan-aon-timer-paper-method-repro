# v22：30 次 smoke 验证证据

真实 VCS 仿真 30/30 成功、0 失败，最终 916/4507（20.3239%），相对初始 508 个 bin 新增 408 个。四种顶层序列均被 UCB 选中；stress-all 23、jump 3、smoke 3、prescaler 1。按反馈顺序归属的新增 bin 为 stress-all 396、jump 12，另外两种为 0；stress-all 会创建随机 jump 子序列。这些是短预算诊断数据，不是 Full 的最终结果。

`audit.json` 是独立的事件、seed、向量、奖励和成功状态审计，结果为 pass。原始 `union_audit.json` 是第一次合并检查，保留其 `partial` 结果作为诊断记录；根因是 URG 合并 XML 使用 `n_cn_d` 标签，并省略 singleton range 的 `high` 属性，旧诊断误读了 illegal cross 约束。

修复后的 `union_audit_rechecked.json` 重新读取同一批原始 VDB（39 个初始 + 30 个在线），由 URG 合并得到 69 个 test、**916/4507**。规范化仅作用于新解析的 XML 副本，不更改 VDB、仿真结果或正在运行的 Full。合并 XML 的 4507 个 bin 定义与逐次向量并集逐一一致；缺失/额外定义及命中均为 0，状态为 **pass**。合并报告 `Group :` 标题兼容也仅在独立检查进程处理，运行中的 Full 源码和冻结解析器未改动。

`protocol.json`/`summary.json` 的 `method: Full` 是历史 runner 对算法配置的命名；实际预算以 `budget: 30` 和提交数为准。导出曲线沿用同一工具的通用 Full 标题，也只含这 30 次的测量数据。`audit.json` 的 URG 行序 limitation 为旧模板文字；本轮实际解析身份定义见 protocol 的 `bin_identity`。

`sha256.txt` 保留服务器原始导出的 8 项文件哈希；`evidence_sha256.txt` 覆盖本目录除其自身之外的全部文件，包含映射验证、参数探针、源码哈希和两次合并检查摘要。真实 VDB、simv、合并数据库和完整日志只保留在服务器。
