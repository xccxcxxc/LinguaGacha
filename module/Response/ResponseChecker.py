import re
from enum import StrEnum

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from model.Item import Item
from module.Config import Config
from module.QualityRule.QualityRuleSnapshot import QualityRuleSnapshot
from module.Filter.LanguageFilter import LanguageFilter
from module.Filter.RuleFilter import RuleFilter
from module.Text.TextHelper import TextHelper
from module.TextProcessor import TextProcessor


class ResponseChecker(Base):
    class Error(StrEnum):
        NONE = "NONE"
        UNKNOWN = "UNKNOWN"
        FAIL_DATA = "FAIL_DATA"
        FAIL_TIMEOUT = "FAIL_TIMEOUT"
        FAIL_LINE_COUNT = "FAIL_LINE_COUNT"
        FAIL_DEGRADATION = "FAIL_DEGRADATION"
        LINE_ERROR_KANA = "LINE_ERROR_KANA"
        LINE_ERROR_HANGEUL = "LINE_ERROR_HANGEUL"
        LINE_ERROR_EMPTY_LINE = "LINE_ERROR_EMPTY_LINE"
        LINE_ERROR_SIMILARITY = "LINE_ERROR_SIMILARITY"

    LINE_ERROR: tuple[Error, ...] = (
        Error.LINE_ERROR_KANA,
        Error.LINE_ERROR_HANGEUL,
        Error.LINE_ERROR_EMPTY_LINE,
        Error.LINE_ERROR_SIMILARITY,
    )

    # 重试次数阈值
    RETRY_COUNT_THRESHOLD: int = 2
    # 字符集合相似度只作为粗筛；跨语种翻译还要看目标语字符证据，避免专名/标题误触发重试。
    SIMILARITY_THRESHOLD: float = 0.80
    CROSS_SCRIPT_MIN_SOURCE_CHARS: int = 8
    CROSS_SCRIPT_MIN_SOURCE_WORDS: int = 2
    PRESERVED_SOURCE_TITLE_MAX_WORDS: int = 4
    RE_SOURCE_WORD: re.Pattern[str] = re.compile(r"[A-Za-zÀ-ɏ]+")

    def __init__(
        self,
        config: Config,
        items: list[Item],
        quality_snapshot: QualityRuleSnapshot | None = None,
    ) -> None:
        super().__init__()

        # 初始化
        self.items = items
        self.config = config
        self.quality_snapshot: QualityRuleSnapshot | None = quality_snapshot

    # 检查
    def check(
        self,
        srcs: list[str],
        dsts: list[str],
        text_type: Item.TextType,
        *,
        stream_degraded: bool = False,
    ) -> list[Error]:
        if stream_degraded:
            # 退化检测来自流式输出整体行为，不对应具体某一行的质量问题。
            return [__class__.Error.FAIL_DEGRADATION] * len(srcs)

        # 数据解析失败
        if len(dsts) == 0 or all(v == "" or v is None for v in dsts):
            return [__class__.Error.FAIL_DATA] * len(srcs)

        # 当翻译任务为单条目任务，且此条目已经是第二次单独重试时，直接返回，不进行后续判断
        if (
            len(self.items) == 1
            and self.items[0].get_retry_count() >= __class__.RETRY_COUNT_THRESHOLD
        ):
            return [__class__.Error.NONE] * len(srcs)

        # 行数检查
        if len(srcs) != len(dsts):
            return [__class__.Error.FAIL_LINE_COUNT] * len(srcs)

        # 逐行检查
        checks = self.check_lines(srcs, dsts, text_type)
        if any(v != __class__.Error.NONE for v in checks):
            return checks

        # 默认无错误
        return [__class__.Error.NONE] * len(srcs)

    # 逐行检查错误
    def check_lines(
        self, srcs: list[str], dsts: list[str], text_type: Item.TextType
    ) -> list[Error]:
        checks: list[__class__.Error] = []
        for src, dst in zip(srcs, dsts):
            src = src.strip()
            dst = dst.strip()

            # 原文不为空而译文为空时，判断为错误翻译
            if src != "" and dst == "":
                checks.append(__class__.Error.LINE_ERROR_EMPTY_LINE)
                continue

            # 原文内容符合规则过滤条件时，判断为正确翻译
            if RuleFilter.filter(src):
                checks.append(__class__.Error.NONE)
                continue

            # 原文内容符合语言过滤条件时，判断为正确翻译
            if LanguageFilter.filter(src, self.config.source_language):
                checks.append(__class__.Error.NONE)
                continue

            # 排除代码保护规则覆盖的文本以后再继续进行检查
            processor = TextProcessor(
                self.config,
                None,
                quality_snapshot=self.quality_snapshot,
            )
            rule: re.Pattern | None = processor.get_re_sample(
                custom=False,
                text_type=text_type,
            )

            if rule is not None:
                src = rule.sub("", src)
                dst = rule.sub("", dst)

            # 当原文语言为日语，且译文中包含平假名或片假名字符时，判断为 假名残留
            if (
                self.config.check_kana_residue
                and self.config.source_language == BaseLanguage.Enum.JA
                and (TextHelper.JA.any_hiragana(dst) or TextHelper.JA.any_katakana(dst))
            ):
                checks.append(__class__.Error.LINE_ERROR_KANA)
                continue

            # 当原文语言为韩语，且译文中包含谚文字符时，判断为 谚文残留
            if (
                self.config.check_hangeul_residue
                and self.config.source_language == BaseLanguage.Enum.KO
                and TextHelper.KO.any_hangeul(dst)
            ):
                checks.append(__class__.Error.LINE_ERROR_HANGEUL)
                continue

            # 判断是否包含或相似；跨脚本翻译不能只看字符集合，否则专名/标题保留会误触发切分重试。
            if self.has_similarity_error(src, dst):
                checks.append(__class__.Error.LINE_ERROR_SIMILARITY)
                continue

            # 默认为无错误
            checks.append(__class__.Error.NONE)

        # 返回结果
        return checks

    def has_similarity_error(self, src: str, dst: str) -> bool:
        """判断是否需要把相似文本视为运行期失败。"""
        if not self.config.check_similarity:
            return False

        # 文本保护规则可能把原文或译文剥离为空；空串包含关系不能作为失败依据。
        if src == "" or dst == "":
            return False

        if not self.has_basic_similarity(src, dst):
            return False

        if (
            self.config.source_language == BaseLanguage.Enum.JA
            and self.config.target_language == BaseLanguage.Enum.ZH
        ):
            # 日翻中只把残留假名视为运行期失败，中文译文中的汉字重叠不应触发重试。
            return TextHelper.JA.any_hiragana(dst) or TextHelper.JA.any_katakana(dst)
        elif (
            self.config.source_language == BaseLanguage.Enum.KO
            and self.config.target_language == BaseLanguage.Enum.ZH
        ):
            # 韩翻中同理，只把残留谚文视为运行期失败。
            return TextHelper.KO.any_hangeul(dst)
        elif self.is_cross_script_to_cjk():
            return self.has_cross_script_source_residue(dst)
        else:
            return True

    @classmethod
    def has_basic_similarity(cls, src: str, dst: str) -> bool:
        """先做便宜的包含/Jaccard 粗筛，避免每行都跑更复杂的分支。"""
        return (
            src in dst
            or dst in src
            or TextHelper.check_similarity_by_jaccard(src, dst)
            > cls.SIMILARITY_THRESHOLD
        )

    def is_cross_script_to_cjk(self) -> bool:
        """非 CJK 到 CJK 的翻译要按源文残留判断，而不是按普通相似度判断。"""
        if self.config.source_language == BaseLanguage.ALL:
            return False
        return not BaseLanguage.is_cjk(
            self.config.source_language
        ) and BaseLanguage.is_cjk(self.config.target_language)

    def has_cross_script_source_residue(self, dst: str) -> bool:
        """跨脚本翻译只有在缺少目标语证据且源语残留足够明显时才失败。"""
        if self.contains_language_text(dst, self.config.target_language):
            return False

        if self.looks_like_preserved_source_title(dst):
            return False

        source_char_count = self.count_language_chars(dst, self.config.source_language)
        source_word_count = len(self.RE_SOURCE_WORD.findall(dst))
        return (
            source_char_count >= self.CROSS_SCRIPT_MIN_SOURCE_CHARS
            or source_word_count >= self.CROSS_SCRIPT_MIN_SOURCE_WORDS
        )

    @classmethod
    def looks_like_preserved_source_title(cls, text: str) -> bool:
        """短标题或专名常常合法保留原文，运行期不应因此切分重试。"""
        words = cls.RE_SOURCE_WORD.findall(text)
        if len(words) == 0 or len(words) > cls.PRESERVED_SOURCE_TITLE_MAX_WORDS:
            return False
        return all(word.isupper() or word[0].isupper() for word in words)

    @classmethod
    def contains_language_text(
        cls, text: str, language: BaseLanguage.Enum | str
    ) -> bool:
        """按语言枚举检查文本中是否存在目标语字符。"""
        return cls.count_language_chars(text, language) > 0

    @classmethod
    def count_language_chars(cls, text: str, language: BaseLanguage.Enum | str) -> int:
        """集中处理语言到字符检测器的映射，避免相似度逻辑散落动态 getattr。"""
        if language == BaseLanguage.Enum.ZH:
            return sum(1 for char in text if TextHelper.CJK.char(char))
        elif language == BaseLanguage.Enum.EN:
            return sum(1 for char in text if TextHelper.Latin.char(char))
        elif language == BaseLanguage.ALL:
            return 0
        else:
            helper = getattr(TextHelper, str(language), None)
            char_checker = getattr(helper, "char", None)
            if not callable(char_checker):
                return 0
            return sum(1 for char in text if char_checker(char))
