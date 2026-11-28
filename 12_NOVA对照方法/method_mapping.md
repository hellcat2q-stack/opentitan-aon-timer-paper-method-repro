# 论文到本地实现的对应关系

来源为用户提供 NOVA.pdf，共 8 页，arXiv:2512.00688v1，文件 SHA256 见 README。已核对第 3 页 Algorithm 1/2、第 4 页式 (1) 与求解器描述、第 5 页表 1 和实验设置。

| 来源 | 本地行为 | 属性 |
| --- | --- | --- |
| 第3页 Algorithm 1 line1 | 按官方 test ID 保存历史二值向量 H_c | 论文流程 |
| 第3页 Overview 与 line5 | 取剩余未覆盖 bin 数最多的簇；完全覆盖的簇不再选择 | 依据 overview 的 largest remaining uncovered space；不是 UCB |
| 第3页 Algorithm 2 | 对目标簇每个有历史命中的 bin 均匀抽相同数量历史，再取固定规模子集，重复组成 ensemble | 论文流程 |
| 第4页式 (1) | 对 H_c 每个向量，累加其到每个 ensemble subset 在目标簇上的最近邻距离 | 论文公式 |
| 第4页 top-R% | 按距离降序，取 ceil(R × 该类别历史数)，最少1条，求均值 | 论文给出比例含义；取整规则本地冻结 |
| Algorithm 1 line11–14 | 最高分类别执行，成功的真实 VCS feedback 更新该类别历史 | 论文流程；并发为本地适配 |
| 第4–5页 solver、SAASBO、SHAP | 本目录不执行 | 未移植；不将 VCS seed 或普通 SV steering 伪装为 solver 参数优化 |
| 第5页表1 | 作者 AON Timer 为12类别、2048 bins、Parameters“/” | 不推断该符号等于“确定没有优化” |
| 第5页 warm-up | 论文每类别10次；本地固定既有39条、来自4类 | 用户要求复用初始语料的明确偏差 |

## 未公开细节的固定选择

以下均为本地初始协议值，没有以旧 Full/Random 结果或在线反馈调参，不声称来自作者默认值：

- `Ensemble_Size=50`，`Samples_Per_Bin=1`，`Sample_Size=8`，`R=0.005` 即 top 0.5%。论文说 R 通常小于1%，没有公布具体数值。
- 距离取目标簇二值向量的 Euclidean distance，即 sqrt(Hamming count)。论文仅写 nearest-neighbor distance，未明确度量和归一化。
- 两阶段抽样均不放回；可选历史不足时取可用全体。集合以历史观察索引区分，同一观察重复抽中只计一次；相同向量的不同实际运行仍为不同观察。算法未明确这些实现细节。
- 目标簇剩余未覆盖 bin 数并列时，优先当前命中比例较低的簇，再用独立 selection RNG 并列抽样。最高类别分数并列时也用该 RNG 抽样。
- 目标簇所有 bin 均无历史命中时，Algorithm 2 无法形成非空 S。本地从全部成功历史均匀取子集，并在每个选择事件中记 `empty_ensemble_fallbacks`。绝不把未命中过的簇从目标池删除。
- 39条语料只给4个类别历史。余下13类先按在途数最少的空历史类别探索，避免10个worker在启动时重复同一个未知类别；成功回传后才进入其历史。所有这些尝试计入30或1000预算，失败不转成成功历史。
- 使用同一冻结751簇，未重做论文所述的结构加行为聚类或新增 warm-up reclustering。这是为了和现有六方法保持同一映射，结果名明确为选择器适配版。
- 论文为时间预算、伪代码顺序执行；本地沿用10 workers、连续补位、固定1000 submissions。选择只读到当时已经完成的反馈，未完成任务不作为覆盖观察。
- 失败停止后续提交并收尾在途任务，保留实际提交/完成/失败总数。没有隐藏重试。

## 验证层次

1. `tests/test_nova.py` 用可手算向量检查式 (1)、top-R、簇局部度量、稀有 bin 均衡采样、空历史与失败处理；另用临时目录测试调度和审计。所有夹具结果随临时目录消失，不导入运行数据。
2. server preflight 核对真实 V31 simv 与已冻结 canonical XML schema、39×4507 输入和官方 test catalog，不调用 VCS 或消耗正式预算。
3. 后续实际执行先跑独立30次 smoke，再逐次审计事件、UVM 日志、identity、raw counts，并执行39+30份VDB独立URG合并；通过才跑1000次。
4. 完成1000次后同样核对1000份日志与1039-VDB并集，才可纳入图表。代码准备、单元测试、preflight均不能当作NOVA仿真结果。
