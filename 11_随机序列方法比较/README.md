# 步骤 11：RandomSelection 方法比较

本步骤把论文表 II 的 RandomSelection 现场结果与论文参考值、以及本项目已有的 VCS 定向 Full 结果并列展示。它只比较可审计的公开指标，不把不同调度协议混写成同一个方法。

## 预注册比较口径

- RandomSelection：四条阶段 04/06 冻结核心序列，均匀有放回抽样；1000 submissions、10 workers、10×100 logical batches、seed 42、39 条初始语料、4507-bin 分母。
- Full 对照：`stage08_vcs_steered_full1000_v16_20261105`，是当前 VCS 定向 Jump/threshold steering 实验，1000/1000 成功，不能当作论文原始 Full 的严格同协议复现。
- 论文参考：RandomSelection 16.67% coverage、15355.71 s accumulated runtime、4450.20 s walltime；这些值只作参考，不覆盖现场测量。

## 结果

RandomSelection 的现场结果和脱敏证据保存在 `../09_对照与消融/evidence/stage09_random_selection_full1000_20261106/`。本地覆盖为 5.7466%，累计仿真 CPU runtime 为 65079.61 秒，walltime 为 8153.19 秒；论文参考分别为 16.67%、15355.71 秒和 4450.20 秒。`结果表.csv` 中将其标记为“本地四序列池复现”；Full 的 steering 也显式保留。

## 局限

论文没有公开 AON Timer 完整 sequence pool、逐次 seed 或 bin 身份清单。本步骤用于比较当前可审计的 VCS 现场结果，不能据此声称已经重现论文的隐藏输入或论文精确数值。
