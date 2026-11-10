# v20 覆盖解析、初始数据与 scoreboard 修复

## 本次修复

v19 的 URG HTML 解析会因覆盖行和压缩未覆盖区间的排序变化，把命中计数写入错误的 bin 列。v20 改为从 VCS `testbench.cumulative.xml` 读取 coverpoint/bin 序号和 cross 成员 tuple，URG 只提供自动 bin 数值回退及独立命中总数校验。遇到 cross 时，解析器先排除 XML 声明的 illegal/ignore 组合，再按 covergroup 的 cross bin 上限建立稳定 tuple 列表；否则直接截断笛卡尔积会漏掉后面的合法覆盖 tuple。

重建 39 条冻结初始语料后，每条都有 4507 个稳定特征，XML 命中数与同一 VDB 的 URG `groups.txt` 详细总数一致。重建矩阵并集为 **508/4507（11.2714%）**，输入 SHA-256 为 `a73d5cd6bd413d63894a8798ca3f6c20e31d1ebc4e3ddc3459d8b88696536f7d`。Stage 07 按原脚本和固定 `PYTHONHASHSEED=0` 重跑，完整映射 4507 个 bin，选择 `dbscan_clustering_new2`，得到 751 个 cluster、无 singleton；旧 78 个 cluster 是依据错误身份/命中矩阵生成，v20 不复用它。

服务器实际使用的 v12 build scoreboard 曾把 `ral.wkup_count_lo` 再读一次并赋给 `rtl_count[63:32]`。v20 在新的 `scratch/stage08_v20_20261110/source/opentitan` 副本中将其修成 `ral.wkup_count_hi`，并从该副本重新编译 VCS `simv`。原始 `src/opentitan`、旧 build 和既有运行目录未修改。构建副本 scoreboard SHA-256 为 `94d26e1e802334b4c3e80890cba03313f8304a8290fb222f5d230510dfdfa289`，v20 `simv` SHA-256 为 `1fc8644a2b40ef63d49f8e6f68ec75e60d4f4546193a79bb89f67912952f3cac`。

v20 steering 增加对稳定 `name:auto[index]` 标签的识别，保留 policy 选出的 sequence，并只在 jump/prescaler sequence 兼容时施加约束。3 项 steering 定向断言通过；cross illegal tuple 单元用例通过。Preflight 验证 39 条历史向量、4507 列和 508 个初始命中，并成功加载 751 个 cluster。

## 30 次 smoke

VCS/URG 真实仿真已完成 **30/30，0 失败**，10 workers，seed 42，连续补位 20 次，hash 链和覆盖反馈独立审计通过。最终并集 **561/4507（12.4473%）**，较修正后的初始矩阵增加 **53 bins**。序列使用量为 stress-all 10、jump 11、smoke 5、prescaler 4，并非全选 jump。11 次可定向任务均在日志确认约束生效，11 次均命中所选目标 bin。累计 simulator CPU 时间 2802.08 秒，wall time 2400.89 秒。

这次 30 次结果是 parser/scoreboard 修复后的 smoke，不是 1000 次 Full，也不能与 v19 旧 coverage 百分比直接比较；分母保持 4507，但 bin 身份定义已从 URG 行标签切换到 VCS XML ordinal/tuple。服务器 30 次 smoke 中有 10 次选择 stress-all，导致实际运行约 40 分钟；实验期间服务器 load average 达到 250–400。基于这个共享服务器负载，本轮没有启动 1000 次 Full。后续 Full 需要在资源允许时用同一 v20 初始矩阵、映射和新 scoreboard build 单独启动。

## 证据

- 服务器结果：`runs/stage08_vcs_paper_ucb_smoke30_20261110_v20/`；完整 VDB、simv 和日志仅保留在学校服务器。
- 本地脱敏摘要：`evidence/stage08_v20_smoke30_20261110/`，包含 run summary、审计、输入清单、Stage 07 验证、protocol 和源码/build 哈希。
- v20 工具：`tools/stage08_stable_coverage_v20.py`、`tools/rebuild_stage08_inputs_v20.py`、`tools/aon_timer_coverage_steering_v20.py`、`tools/run_vcs_ucb_paper_ucb_v20.py`，以及独立构建/启动脚本和 scoreboard patch。
