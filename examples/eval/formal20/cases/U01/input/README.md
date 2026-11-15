本地 Click 8.1.7 的 app.py 使用 default_map 指定 long=True。实际执行输出 long，但 --help 显示 short。修复本地 click 包，使有正反选项的布尔 flag 帮助显示最终生效默认值；不要改应用配置来掩盖问题。保留显式命令行覆盖、默认 False、没有 default_map 及其他选项帮助行为。
