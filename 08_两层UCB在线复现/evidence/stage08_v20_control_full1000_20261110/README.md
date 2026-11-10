# v20 两层 UCB 控制组：1000 次 Full

真实 VCS 仿真完成 1000/1000，1000 次接受、0 失败、0 重试。最终覆盖 **1739/4507（38.5844%）**，从 508-bin 初始并集新增 1231 bins。序列使用量为 stress-all 64、jump 738、smoke 100、prescaler 98。累计 simulator CPU 时间为 18,385.44 秒，wall time 为 5,363.04 秒。

独立 `audit.json` 确认 seed、逐次覆盖向量、奖励增量、反馈后补位和事件哈希链均通过。原始 VDB URG 合并得到 1039 个 test 和 1739/4507；4507 个 bin 定义与命中身份均和逐次向量并集完全一致。合并摘要见[配对证据目录](../stage08_v20_v22_ucb_pair_full1000_20261110/v20_union_audit.json)。v20/v22 配对结论见同目录的 [最终报告](../stage08_v20_v22_ucb_pair_full1000_20261110/README.md)。

覆盖值是本地项目结果，不是论文原始指标。原始 VDB、simv 和完整仿真日志仅保留在学校服务器。服务器导出的原始文件 SHA-256 清单是 `sha256.txt`；本地补充说明由 `evidence_sha256.txt` 覆盖。
