# 复用的覆盖转换器

`run_stage06_conversion_stable.py` 是本项目已有 V20/V31 仿真实际使用的 converter，取自服务器冻结文件，逐字节不改动。SHA256：`2f750cf5c4a7dbb78953dad9a2605753dbe5ca6ed4ab807e938efa39ba99db15`。

该副本只承担真实 URG 报告转换和 bin identity 解析，不能视为 NOVA 作者源码。这里固定副本是为了让 NOVA runner 可从 Git checkout 运行，不依赖未跟踪 scratch Python 文件。共享 VCS worker、strict UVM checker 和 stable schema 仍引用原阶段文件并校验 hash，不复制仿真器二进制或原始数据库。
