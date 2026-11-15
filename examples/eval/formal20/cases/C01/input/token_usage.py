"""进程内的 token 统计；实例由 Agent 持有，/new 不重置。"""


class TokenUsage:
    def __init__(self):
        self.totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self.incomplete = False

    def record(self, usage, source):
        if usage is None:
            self.incomplete = True
            print(f"   [{source} tokens] 未返回 usage，本次未计入累计。")
            return

        counts = {}
        for name in self.totals:
            value = getattr(usage, name, None)
            counts[name] = value if type(value) is int and value >= 0 else None
        self.incomplete = self.incomplete or any(value is None for value in counts.values())
        for name, count in counts.items():
            if count is not None:
                self.totals[name] += count
        shown = {name: count if count is not None else '未知' for name, count in counts.items()}
        print(
            f"   [{source} tokens] 输入={shown['prompt_tokens']} "
            f"输出={shown['completion_tokens']} 合计={shown['total_tokens']} | "
            f"本次运行累计：输入={self.totals['prompt_tokens']} "
            f"输出={self.totals['completion_tokens']} 合计={self.totals['total_tokens']}"
            + ('（累计含缺失，仅统计已知值）' if self.incomplete else '')
        )
