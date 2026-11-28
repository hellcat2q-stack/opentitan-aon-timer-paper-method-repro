# NOVA 的 AON Timer 17test 对照适配

本目录用于新增 NOVA 参考方法，不改动已有六种方法。当前实现名称为 **NOVASelectionVCS**：按 NOVA 第 4 节的覆盖感知选择算法执行真实 VCS/URG 闭环，统一采用既有 17test catalog、39 条初始语料、751 簇和 V31 修复版 simv。代码已实现选择、执行、失败保留、独立审计和 smoke/full 门禁；当前完成情况见 `evidence/validation_20261128.json`，预检查不代表已运行仿真。

NOVA 包含“测试选择”和“求解器参数的贝叶斯优化”两部分。本目录实现的是前者。论文表 1 的 AON Timer 为 12 个测试类别、2048 bins，Parameters 为“/”；论文没有解释该符号是否表示完全未使用求解器优化。本地 VCS 尚无论文式逐分支概率控制接口，因此不声称已移植 SAASBO、SHAP 或完整参数化 SMT solver。后续图表请使用 **NOVASelectionVCS** 或“NOVA 测试选择适配版”这一名称。

## 代码与输入

| 文件或目录 | 用途 |
| --- | --- |
| `tools/nova_policy.py` | 论文 Algorithm 1/2：选目标簇、bin 均衡采样、ensemble 最近邻距离、top-R 均值评分 |
| `tools/run_nova_vcs.py` | 新的独立调度器；保留官方 test ID、plusarg、seed；VCS 执行和覆盖解析复用已验证接口 |
| `tools/audit_nova.py` | 重放每个选择决策，核对事件链、向量、身份、原始 UVM 日志、覆盖并集和计时 |
| `tools/run_nova_workflow.py` | 先 preflight，显式执行时依次 smoke30、审计/URG 合并、formal1000、审计/URG 合并 |
| `configs/nova_17test.json` | 参数、固定协议和与现有实验一致的输入/构建 SHA256 |
| `inputs/coverage_bin_by_run_39.csv` | 原始 39-run coverage CSV 的逐字节副本；508/4507 初始并集 |
| `inputs/bin_to_cluster.csv` | 与现有方法相同的 4507-bin / 751-cluster 映射 |
| `inputs/aon_timer_17test_catalog.json` | 服务器冻结 catalog 的逐字节副本，另核对与仓库公共 catalog 的 JSON 内容一致 |
| `vendor/run_stage06_conversion_stable.py` | 已验证 converter 的未改动快照，见 `vendor/README.md` |
| `tests/test_nova.py` | 数值例子、边界条件、身份、预算、失败停止和审计防篡改检查 |
| `method_mapping.md` | 论文对应关系、未公开参数及本地适配规则 |

## 与现有 17test 方法一致的协议

固定 OpenTitan revision `9f20940d494a223cc950a5b98f748fb28109d458`；17 个独立官方 test entry（共享 SV 类的入口也分别记账）；39 条成功历史向量；4507 个功能 bin；初始 508 bins；751 个冻结簇；seed 42；10 workers；正式预算 1000 次提交；smoke 独立 30 次；steering 关闭；不 retry、不替换失败 seed。

V31 simv SHA256 为 `8b0fd96293a6f85dc1fd3984edf1cdd68f16e6482802c85d784b3722cb0b2760`。CSV、catalog、映射和 parser 的 SHA256 都必须匹配，构建或分母不符时直接拒绝运行。13 个没有初始历史的 test 的首次探索计入正式预算，不扩大或重新生成初始语料。历史初始语料实际由四个核心 sequence 产生，并非每个官方 test 都有 10 条样本。

新增 test 选择器使用当前覆盖并集选择剩余未覆盖 bin 数最多的簇；每次反馈后更新历史和并集并补位。不同方法的时间比较需同时报告累计 simulator CPU、选择器计算时间和墙钟时间。线程完成顺序影响在线决策，因此保存完整事件链供重放，不能承诺相同 seed 在不同服务器负载下产生完全相同调度。

## 后续运行入口

在学校服务器的同一个 17test checkout 中，使用其 Python 3.11 `.venv`。以下路径相对仓库根目录，输出目录必须全新；命令只是说明入口，本次准备不会触发它们。

```bash
.venv/bin/python '12_NOVA对照方法/tests/test_nova.py' -v

# 只读校验真实 V31 构建、CSV 和解析器；不运行 VCS。
.venv/bin/python '12_NOVA对照方法/tools/run_nova_workflow.py' \
  --work-dir scratch/nova_17test_preflight_NEW

# 正式执行时才加 --execute：smoke 和 URG 合并全部通过后再启动1000次。
.venv/bin/python -u '12_NOVA对照方法/tools/run_nova_workflow.py' \
  --work-dir runs/nova_17test_NEW --execute
```

执行过程中发生 UVM/VCS/URG/解析失败，停止后续提交，已经提交的任务收尾；保留原始失败、日志、VDB 和部分反馈。结果不会被验收为 1000/1000 零失败，formal 也不会在 smoke 失败后启动。若覆盖提前闭合，停止新提交并记录提前结束，不伪造剩余预算。

`evidence/smoke`、`evidence/formal` 由运行入口在输出目录内生成脱敏 CSV、JSON 和哈希。真实 VDB、simv、完整日志保留服务器。不要把测试夹具的向量或 preflight 的结果当作真实仿真覆盖率。

## 依赖与范围

选择器只依赖 NumPy；执行层需要现有 VCS、URG、BeautifulSoup、V31 build、DV Tcl、canonical URG report 和原始初始 VDB。新代码不导入旧 UCB selector，不安装或调用 LLM agent。NOVA 论文与本地 DUT/test pool、warm-up、cluster、分母和预算不同，本实验是统一本地条件下的适配对照，不能直接验证论文的 98.3% 或 2.03 倍速度提升。

论文来源：[NOVA arXiv 2512.00688v1](https://arxiv.org/abs/2512.00688v1)，用户提供 PDF 的 SHA256 为 `8262e68452a7cfeb5891aae5aed7bb56b86e8eb538765f90a970370a4db5735e`。PDF 正文没有提供算法实现的开源仓库链接；此目录是根据公开伪代码独立编写的实现，不冒称作者原代码。论文 PDF 不提交到仓库。
