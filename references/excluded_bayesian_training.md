# 排除的贝叶斯训练内容

本项目按用户要求不纳入师兄 toolbox 的 Bayesian training 代码和生成物：

- `scripts/bayes_opt.py`
- `scripts/process_ckpt.py`
- `scripts/generate_bin_config.py`
- `scripts/generate_vars.py`
- `configs/config_bayes.yaml`
- `dummy_prob.bin`
- `scripts/cluster_with_entropy.py` 中服务于 Bayesian optimization 的训练说明/接口不作为本项目执行入口

保留的是论文 AON Timer 对照实验真正需要的覆盖提取、初始语料、组件聚类、两层 UCB 连续补位、随机 baseline、消融运行和结果绘图代码。任何来自 UART 示例配置的文件只作为原始输入模板，必须改写为 AON Timer 配置后才能运行，不得当作 AON Timer 结果。
