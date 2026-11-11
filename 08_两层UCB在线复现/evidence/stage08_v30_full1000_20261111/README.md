# V30 Full 实测结果

本文件在预算完成、事件/向量/奖励审计、原始 UVM 日志与独立 URG 合并核对后生成。

- 提交/完成：1000/1000；接受 1000；失败 0；重试 0。
- 覆盖：4127/4507（91.5687%）；初始 508 bins；新增 3619 bins。
- wall time：19175.48 秒；累计 simulator CPU：179038.03 秒。
- 原 V22：4105/4507，失败 4；源代码/build 的原始哈希清单核对通过。
- 原始日志复核 1000 次；已知失败 seed 真实回归 5/5。

| 顶层序列 | 提交数 |
| --- | ---: |
| aon_timer_stress_all_vseq | 844 |
| aon_timer_smoke_vseq | 24 |
| aon_timer_jump_vseq | 111 |
| aon_timer_prescaler_vseq | 21 |

保留 V22 的 UCB adapter/policy、初始向量、cluster map、seed 列表、worker 数和预算；本轮改变 testbench 的配置同步、复位进程作用域与合法分频首周期等待。这不是 UCB 对随机选择的优越性实验，也不是论文原始结果。scoreboard 的时序检查使用 12 位相位的有限上界，不声称是完整逐周期黄金模型。

原始 VDB、simv、完整日志保留服务器；本目录只包含脱敏证据、哈希及实测曲线。
