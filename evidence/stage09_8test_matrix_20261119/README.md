# 第九步八测试池统一环境对照与消融：最终结果

2026-11-23 诊断更新：Full、NoIncrementalRefill、NoRuntimePenalty 存在新增 test ID 与执行 sequence 类名的反馈身份错位。下表保留现场覆盖和耗时，但受影响方法不能据此形成预期算法性能结论；此前审计未检查此身份一致性。详见 [身份记账缺陷诊断](../stage09_8test_identity_diagnosis_20261123/README.md)。

六种方法均完成 1000 次，全部通过事件/向量/奖励、原始 UVM 日志与独立 URG 合并审计。

| 方法 | 覆盖 bins/4507 | 覆盖率 | 失败 | CPU 秒 | Wall 秒 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full | 2979 | 66.0972% | 0 | 59442.40 | 8415.78 |
| NoIncrementalRefill | 2526 | 56.0462% | 0 | 43711.23 | 14091.24 |
| NoRuntimePenalty | 3512 | 77.9232% | 0 | 96965.38 | 12774.06 |
| RandomSelection | 2406 | 53.3836% | 0 | 36805.57 | 5483.08 |
| SequenceUCBOnly | 4010 | 88.9727% | 0 | 138934.34 | 18217.11 |
| ClusterUCBOnly | 3207 | 71.1560% | 0 | 69272.22 | 12777.98 |

统一初始 39 条语料、508/4507、V30 build、seed 42、10 workers、1000 次预算，全部关闭 steering。测试池由独立 catalog 冻结为 8 个官方 AON Timer test，common_vseq 的官方 plusarg 随 test 一起记录。逐方法的 30 次 smoke 为独立门禁，不拼入正式预算。

本表为单 seed 本地作者衍生实现；论文隐藏回归池、seed 和覆盖分母尚未完全对齐，不能声称逐数复现论文。原 V30 4127/4507 为开启额外 steering 的单独参考；旧随机基线使用旧解析器，也不作为本表对照。共享服务器负载会影响 CPU 与 walltime，单轮耗时差不能作为统计显著性结论。
