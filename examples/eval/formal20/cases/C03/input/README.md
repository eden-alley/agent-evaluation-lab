用 `python -B demo.py` 复现三个调用。该命令只展示结果。

通过 `python -B edit_source.py inspect PATH` 获得当前文件及 SHA256，将修改后的完整文件写到独立提案文件，再用 `python -B edit_source.py apply PATH SHA256 PROPOSAL` 提交业务源文件。遇到版本冲突时，inspect 新版本并保留同事的更新，再提交。
