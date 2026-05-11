from base.BaseLanguage import BaseLanguage


class PunctuationFixer:
    # 话语引用引号需要按原文保留；词内撇号另外判断，避免 It’s 被误当作闭合引号。
    QUOTE_MARKS: tuple[str, ...] = (
        "'",
        '"',
        "‘",
        "’",
        "“",
        "”",
        "「",
        "」",
        "『",
        "』",
    )
    WORD_APOSTROPHE_MARKS: tuple[str, ...] = ("'", "’")

    # 数量匹配规则
    RULE_SAME_COUNT_A: dict[str, tuple[str]] = {
        "　": (" ",),  # 全角空格和半角空格之间的转换
        "：": (":",),
        "・": ("·",),
        "？": ("?",),
        "！": ("!",),
        "\u2014": (
            "\u002d",
            "\u2015",
        ),  # 破折号之间的转换，\u002d = - ，\u2014 = ― ，\u2015 = —
        "\u2015": (
            "\u002d",
            "\u2014",
        ),  # 破折号之间的转换，\u002d = - ，\u2014 = ― ，\u2015 = —
        "<": ("＜", "《"),
        ">": ("＞", "》"),
        "＜": ("<", "《"),
        "＞": (">", "》"),
        "[": ("【",),
        "]": ("】",),
        "【": ("[",),
        "】": ("]",),
        "(": ("（",),
        ")": ("）",),
        "（": ("(",),
        "）": (")",),
        "「": ("‘", "“", "『"),
        "」": ("’", "”", "』"),
        "『": ("‘", "“", "「"),
        "』": ("’", "”", "」"),
        "‘": ("“", "「", "『"),
        "’": ("”", "」", "』"),
        "“": ("‘", "「", "『"),
        "”": ("’", "」", "』"),
    }

    # 数量匹配规则
    RULE_SAME_COUNT_B: dict[str, tuple[str]] = {
        " ": ("　",),  # 全角空格和半角空格之间的转换
        ":": ("：",),
        "·": ("・",),
        "?": ("？",),
        "!": ("！",),
        "\u002d": (
            "\u2014",
            "\u2015",
        ),  # 破折号之间的转换，\u002d = - ，\u2014 = ― ，\u2015 = —
    }

    # 强制替换规则
    # 译文语言为 CJK 语言时，执行此规则
    RULE_FORCE_CJK: dict[str, tuple[str]] = {
        "「": ("“"),
        "」": ("”"),
    }

    def __init__(self) -> None:
        super().__init__()

    # 检查并替换
    @classmethod
    def fix(
        cls,
        src: str,
        dst: str,
        source_language: BaseLanguage.Enum,
        target_language: BaseLanguage.Enum,
    ) -> str:
        # 首尾标点修正
        dst = cls.fix_start_end(src, dst, target_language)

        # CJK To CJK = A + B
        # CJK To 非CJK = A + B
        # 非CJK To CJK = A
        # 非CJK To 非CJK = A + B
        if BaseLanguage.is_cjk(source_language) and BaseLanguage.is_cjk(
            target_language
        ):
            dst = cls.apply_fix_rules(src, dst, cls.RULE_SAME_COUNT_A)
            dst = cls.apply_fix_rules(src, dst, cls.RULE_SAME_COUNT_B)
        elif BaseLanguage.is_cjk(source_language) and not BaseLanguage.is_cjk(
            target_language
        ):
            dst = cls.apply_fix_rules(src, dst, cls.RULE_SAME_COUNT_A)
            dst = cls.apply_fix_rules(src, dst, cls.RULE_SAME_COUNT_B)
        elif not BaseLanguage.is_cjk(source_language) and BaseLanguage.is_cjk(
            target_language
        ):
            dst = cls.apply_fix_rules(src, dst, cls.RULE_SAME_COUNT_A)
        else:
            dst = cls.apply_fix_rules(src, dst, cls.RULE_SAME_COUNT_A)
            dst = cls.apply_fix_rules(src, dst, cls.RULE_SAME_COUNT_B)

        # 译文语言为 CJK 语言时，执行强制规则
        if BaseLanguage.is_cjk(target_language):
            for key, value in cls.RULE_FORCE_CJK.items():
                dst = cls.apply_replace_rules(dst, key, value)

        # 最后按原文的引用引号序列兜底修正，避免中英文引号风格被强制规则改写。
        dst = cls.fix_quote_delimiters(src, dst)

        return dst

    @classmethod
    def is_word_apostrophe(cls, text: str, index: int) -> bool:
        """词内撇号表示缩写/所有格，不参与话语引用引号的数量和样式修正。"""
        mark = text[index]
        if mark not in cls.WORD_APOSTROPHE_MARKS:
            return False

        left = text[index - 1] if index > 0 else ""
        right = text[index + 1] if index + 1 < len(text) else ""
        return left.isalnum() and right.isalnum()

    @classmethod
    def count_mark(cls, text: str, mark: str) -> int:
        """统计引号规则字符时忽略词内撇号，避免英文缩写干扰闭合引号判断。"""
        if mark not in cls.WORD_APOSTROPHE_MARKS:
            return text.count(mark)

        count = 0
        for index, value in enumerate(text):
            if value == mark and not cls.is_word_apostrophe(text, index):
                count = count + 1

        return count

    @classmethod
    def collect_quote_delimiters(cls, text: str) -> tuple[tuple[int, str], ...]:
        """抽取真正作为话语边界的引号位置，后续按序对齐源文和译文。"""
        delimiters: list[tuple[int, str]] = []
        for index, value in enumerate(text):
            if value not in cls.QUOTE_MARKS:
                continue
            if cls.is_word_apostrophe(text, index):
                continue
            delimiters.append((index, value))

        return tuple(delimiters)

    @classmethod
    def can_align_quote_delimiters(cls, src: str, dst: str) -> bool:
        """只有引用引号数量一致时才允许自动修正；数量错乱必须触发重试。"""
        src_delimiters = cls.collect_quote_delimiters(src)
        dst_delimiters = cls.collect_quote_delimiters(dst)
        return len(src_delimiters) == len(dst_delimiters)

    @classmethod
    def fix_quote_delimiters(cls, src: str, dst: str) -> str:
        """把译文中的话语引用引号逐个替换为原文对应字符。"""
        src_delimiters = cls.collect_quote_delimiters(src)
        dst_delimiters = cls.collect_quote_delimiters(dst)
        if len(src_delimiters) == 0 or len(src_delimiters) != len(dst_delimiters):
            return dst

        chars = list(dst)
        for (_, src_mark), (dst_index, _) in zip(src_delimiters, dst_delimiters):
            chars[dst_index] = src_mark

        return "".join(chars)

    # 检查
    @classmethod
    def check(cls, src: str, dst: str, key: str, value: tuple[str, ...]) -> bool:
        num_s_x = cls.count_mark(src, key)
        num_s_y = sum(cls.count_mark(src, t) for t in value)
        num_t_x = cls.count_mark(dst, key)
        num_t_y = sum(cls.count_mark(dst, t) for t in value)

        # 首先，原文中的目标符号的数量应大于零，否则表示没有需要修复的标点
        # 然后，原文中目标符号和错误符号的数量不应相等，否则无法确定哪个符号是正确的
        # 然后，原文中的目标符号的数量应大于译文中的目标符号的数量，否则表示没有需要修复的标点
        # 最后，如果原文中目标符号的数量等于译文中目标符号与错误符号的数量之和，则判断为需要修复
        return (
            num_s_x > 0
            and num_s_x != num_s_y
            and num_s_x > num_t_x
            and num_s_x == num_t_x + num_t_y
        )

    # 应用修复规则
    @classmethod
    def apply_fix_rules(
        cls, src: str, dst: str, rules: dict[str, tuple[str, ...]]
    ) -> str:
        for key, value in rules.items():
            if cls.check(src, dst, key, value):
                dst = cls.apply_replace_rules(dst, key, value)

        return dst

    # 应用替换规则
    @classmethod
    def apply_replace_rules(cls, dst: str, key: str, value: tuple[str, ...]) -> str:
        for t in value:
            dst = dst.replace(t, key)

        return dst

    # 首尾标点修正
    @classmethod
    def fix_start_end(
        self, src: str, dst: str, target_language: BaseLanguage.Enum
    ) -> str:
        # 纠正首尾错误的引号
        if dst.startswith(("'", '"', "‘", "“", "「", "『")):
            if src.startswith(("「", "『")):
                dst = f"{src[0]}{dst[1:]}"
            elif BaseLanguage.is_cjk(target_language) and src.startswith(("‘", "“")):
                dst = f"{src[0]}{dst[1:]}"
        if dst.endswith(("'", '"', "’", "”", "」", "』")):
            if src.endswith(("」", "』")):
                dst = f"{dst[:-1]}{src[-1]}"
            elif BaseLanguage.is_cjk(target_language) and src.endswith(("’", "”")):
                dst = f"{dst[:-1]}{src[-1]}"

        # 移除首尾多余的引号
        # for v in ("‘", "“", "「", "『"):
        #     if dst.startswith(v) and not src.startswith(v) and dst.count(v) > src.count(v):
        #         dst = dst[1:]
        #         break
        # for v in ("’", "”", "」", "』"):
        #     if dst.endswith(v) and not src.endswith(v) and dst.count(v) > src.count(v):
        #         dst = dst[:-1]
        #         break

        return dst
