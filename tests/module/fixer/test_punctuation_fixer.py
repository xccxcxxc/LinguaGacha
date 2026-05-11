from base.BaseLanguage import BaseLanguage
from module.Fixer.PunctuationFixer import PunctuationFixer


class TestPunctuationFixer:
    def test_fix_start_end_align_with_source_quotes(self) -> None:
        src = "「你好」"
        dst = '"你好"'

        assert (
            PunctuationFixer.fix_start_end(src, dst, BaseLanguage.Enum.EN) == "「你好」"
        )

    def test_non_cjk_to_cjk_apply_rule_a_only(self) -> None:
        src = "A:B"
        dst = "A：B"

        assert (
            PunctuationFixer.fix(
                src,
                dst,
                BaseLanguage.Enum.EN,
                BaseLanguage.Enum.ZH,
            )
            == "A：B"
        )

    def test_non_cjk_to_non_cjk_apply_rule_b(self) -> None:
        src = "A:B"
        dst = "A：B"

        assert (
            PunctuationFixer.fix(
                src,
                dst,
                BaseLanguage.Enum.EN,
                BaseLanguage.Enum.EN,
            )
            == "A:B"
        )

    def test_cjk_to_non_cjk_apply_rule_a_and_b(self) -> None:
        src = "A：B"
        dst = "A:B"

        assert (
            PunctuationFixer.fix(
                src,
                dst,
                BaseLanguage.Enum.JA,
                BaseLanguage.Enum.EN,
            )
            == "A：B"
        )

    def test_fix_start_end_align_with_cjk_curly_quotes(self) -> None:
        src = "“你好”"
        dst = '"你好"'

        assert (
            PunctuationFixer.fix_start_end(src, dst, BaseLanguage.Enum.ZH) == "“你好”"
        )

    def test_fix_start_end_keep_quotes_when_source_has_no_quote(self) -> None:
        src = "你好"
        dst = '"你好"'

        assert (
            PunctuationFixer.fix_start_end(src, dst, BaseLanguage.Enum.ZH) == '"你好"'
        )

    def test_cjk_target_force_convert_corner_quotes(self) -> None:
        src = "\u300chello\u300d"
        dst = "\u201chello\u201d"

        assert (
            PunctuationFixer.fix(
                src,
                dst,
                BaseLanguage.Enum.JA,
                BaseLanguage.Enum.ZH,
            )
            == "\u300chello\u300d"
        )

    def test_non_cjk_to_cjk_preserves_source_speech_double_quotes(self) -> None:
        src = (
            "\u201cGods. It\u2019s a sob story after all.\u201d "
            "For an Eyeless Priest, the Thiefmaker\u2019s sternum held. "
            "\u201cFind some other lackwit.\u201d"
        )
        dst = (
            "\u300c诸神在上。原来还真是个苦情故事。\u300d"
            "作为无眼祭司，盗贼匠的胸骨挡住了。"
            "\u300c去找别的蠢货。\u300d"
        )

        assert (
            PunctuationFixer.fix(
                src,
                dst,
                BaseLanguage.Enum.EN,
                BaseLanguage.Enum.ZH,
            )
            == "\u201c诸神在上。原来还真是个苦情故事。\u201d"
            "作为无眼祭司，盗贼匠的胸骨挡住了。"
            "\u201c去找别的蠢货。\u201d"
        )

    def test_non_cjk_to_cjk_preserves_source_speech_single_quotes(self) -> None:
        src = "\u2018Don\u2019t,\u2019 Alice said."
        dst = "\u300c别这样，\u300d爱丽丝说。"

        assert (
            PunctuationFixer.fix(
                src,
                dst,
                BaseLanguage.Enum.EN,
                BaseLanguage.Enum.ZH,
            )
            == "\u2018别这样，\u2019爱丽丝说。"
        )

    def test_word_apostrophes_do_not_drive_quote_replacement(self) -> None:
        src = "It\u2019s the Thiefmaker\u2019s problem."
        dst = "\u300d这是盗贼匠的问题。"

        assert (
            PunctuationFixer.fix(
                src,
                dst,
                BaseLanguage.Enum.EN,
                BaseLanguage.Enum.ZH,
            )
            == "\u300d这是盗贼匠的问题。"
        )
