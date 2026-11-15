# C02 · 精确修改并保持混合换行与非目标字节

## 第 1 轮

仅将 conf/service.conf 中完整行 mode = staging 改为 mode = production。其他全部字节必须原样，包括混合CRLF/LF、中文、注释及无末尾换行。不要改备份文件。交付 change.json，包含 replacements、bytes_before、bytes_after 三个整数；报告实际依据。
