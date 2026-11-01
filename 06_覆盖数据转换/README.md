# 阶段 06：覆盖数据转换

**状态：转换完成，已冻结 bin-by-run 输入（2026-11-01）。**

阶段 06 将阶段 05 的真实 VCS VDB 转为统一的 bin-by-run CSV。输入规则固定为：原始 40 次中满足 VCS=0、URG=0、UVM PASS 的 35 次，加上 timeout 参数修复重放中满足同样条件的 4 次，共 39 次；5 个原始 PH_TIMEOUT 和 1 个重放 UVM_ERROR 仅保留为排除证据。

转换器为 [run_stage06_conversion.py](tools/run_stage06_conversion.py)。它在服务器上对每个输入 VDB 重新运行 URG `-format both`，以 URG 详细 bin 表作为命中计数来源，并检查每个 VDB 都有对应的 VCS `testbench.cumulative.xml`。首个报告的 covergroup/item/行序被冻结为列布局，后续报告按相同布局映射。每个 run 单独生成报告，绝不合并 VDB。

## 冻结口径

- canonical bin 数：**4507**，每个接受 run 都得到 4507 列；
- dashboard 的 `4525` 是 URG group 汇总分母，详细 `groups.txt` 行合计是 4507，二者差异保留在 manifest 中；
- 覆盖值是整数 hit count，缺失 bin 补 0；`covered_bins` 是该 run 中 hit count 大于 0 的列数；
- `runtime_cpu_seconds` 取阶段 05 的 simulator CPU time，`wall_seconds` 单独保留；
- VCS cumulative XML 作为 VDB 完整性证据保留；最终列和 hit count 采用 URG 详细表，避免把 URG 压缩 cross 内部树误当成逐 bin 计数。

## 产物

服务器保留完整 URG 报告、VDB 和日志；仓库只提交脱敏的小型证据与转换器。公开产物包括：

- `coverage_bin_by_run.csv`：39 行、4507 个 coverage 列及运行元数据；
- `bin_manifest.json`：输入排除清单、bin 分母、dashboard/详细表差异和每份报告的计数；
- `urg_commands.json`：服务器路径已脱敏的 URG 命令；
- `conversion_sha256.txt`：上述文件 SHA-256 索引。

初始来源算法 [algorithm_source/process_csv.py](algorithm_source/process_csv.py) 仅作为师兄脚本的方法来源保留；由于它面向旧 Verisim/Vericov 格式，阶段 06 使用 VCS/URG 适配器完成实际转换。

## 验收与限制

已在服务器 `.venv` 中通过 `py_compile`，并对 39 个现有 VDB/XML 做了独立核验：每次 4507 列，CSV 的每行 hit count、covered-bin 数和总数均与对应 URG 详细表一致。阶段 06 的 CSV 是后续聚类和在线 runner 的唯一 coverage 输入，不代表论文表 II 的最终结果。
