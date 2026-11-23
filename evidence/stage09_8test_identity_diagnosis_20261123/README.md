# 八测试池 Full 低覆盖的身份记账缺陷诊断

2026-11-23 只读排查确认：新增官方 test 的 ID 与 sequence 类名不同，而继承的 Full 选择器仍用 sequence 类名作为提交及反馈身份。旧四测试池的二者一致，因此该缺陷在扩展池中暴露。

以中断测试为例：catalog/候选评分使用 `aon_timer_intr_test`，解析后的执行类为 `aon_timer_common_vseq`。Full 返回后者，adapter 原样放入提交 context；成功次数、覆盖收益、历史向量和 CPU 耗时均更新到后者。再次给 `intr_test` 评分时，它仍没有成功观察或耗时记录，持续获得未探索加分。四个新增 test 共用同一类；评分并列时排在前面的中断 test 反复获选。

| 方法 | 最终覆盖 bins/4507 | 中断 test 运行次数 | 中断 test 新增 bins 合计 | 提交身份与真实 test ID 不符次数 |
| --- | ---: | ---: | ---: | ---: |
| Full | 2979 | 695 | 0 | 695 |
| SequenceUCBOnly | 4010 | 10 | 0 | 0 |
| ClusterUCBOnly | 3207 | 110 | 0 | 0 |

Full 的 CSR RW、mem walk、TL errors 均未获选。NoIncrementalRefill、NoRuntimePenalty 同样继承错误身份返回，分别出现 790、559 次错位。两个 UCBOnly 的专用分支返回真实 arm ID，因此没有该错位。RandomSelection 的 adapter 也返回真实 test ID。

核查方法：将每次运行的 `run_results.json.test_id` 与相同 run_id 的 `events.jsonl` submit.sequence 逐项连接；源码 SHA256 与各方法 protocol 一致。再从冻结源码 AST 提取并直接执行 `get_test_identifier`、`record_successful_ucb_feedback`、`compute_category_gain`、`compute_sequence_ucb_score` 四个方法，695 次成功零收益反馈后，common 类的计数为 695，而中断 arm 仍为 0。没有启动仿真。逐方法计数、源证据哈希及演示结果见 [diagnosis.json](diagnosis.json)。

源码链：`08_两层UCB在线复现/algorithm_source/generic_adaptive_runner_ucb_continuous_refill_paper_ucb_v17.py` 的候选 ID 列表、select_next_sequence 返回、submit_next_test context、process_completed_run 和 record_successful_ucb_feedback；扩展配置来自 `09_对照与消融/tools/run_stage09_v30.py`，两个 UCBOnly 的 ID 返回来自 `stage09_policy.py`。

这轮数据中的仿真成功、实际覆盖并集和耗时仍是现场记录，但受影响的方法不能作为预期 Full 算法与消融的有效性能结论。之前的事件/向量/奖励、UVM 和 URG 审计没有验证候选 arm 与反馈身份一致，审计 pass 不排除此缺陷。

同 CPU 截面也不能单独解释为两个 UCBOnly 花费更多 CPU：在累计 CPU 不超过 Full 最终 59442.40 秒的已观察曲线前缀，SequenceUCBOnly 为 3322 bins，ClusterUCBOnly 为 3053 bins，均高于 Full 的 2979。这只是曲线观察，并非新增的等 CPU 预算受控实验。

服务器 6-test 于 2026-11-23 11:56:01+08 的只读快照：提交 152、完成且接受 143；其中 115 次提交以 common 类为身份，日志反复选取中断 arm。当前 6-test 沿用同一源代码，也受此问题影响。此次排查没有更改正在运行的进程、参数、算法或已有结果。

修正应统一选择、提交、成功次数、收益、候选历史和耗时的 test ID，执行类及官方 plusarg 仍由 catalog 提供；加入所有方法与共享类 test 的身份回归检查，再以新预注册和独立目录完成 smoke 与正式对照。修正后的 Full 是否胜过 UCBOnly，必须由新实验确定。
