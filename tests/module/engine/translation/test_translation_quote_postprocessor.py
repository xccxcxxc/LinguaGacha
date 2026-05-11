from base.Base import Base
from model.Item import Item
from module.Engine.Translation.TranslationQuotePostProcessor import (
    TranslationQuotePostProcessor,
)


def create_epub_item(
    src: str,
    dst: str,
    *,
    block_path: str = "/html/body/p[1]",
) -> Item:
    return Item(
        src=src,
        dst=dst,
        status=Base.ProjectStatus.PROCESSED,
        file_type=Item.FileType.EPUB,
        file_path="book.epub",
        extra_field={
            "epub": {
                "doc_path": "chapter.xhtml",
                "block_path": block_path,
            }
        },
    )


def test_fix_items_aligns_epub_quote_delimiters_across_item_lines() -> None:
    item = create_epub_item(
        src="\u201cHello\nworld.\u201d",
        dst="\u300c你好\n世界。\u300d",
    )

    changed_items = TranslationQuotePostProcessor.fix_items([item])

    assert changed_items == [item]
    assert item.get_dst() == "\u201c你好\n世界。\u201d"


def test_fix_items_groups_epub_items_by_block_path_not_translation_chunk() -> None:
    first = create_epub_item(src="\u201cHello", dst="\u300c你好")
    second = create_epub_item(src="world.\u201d", dst="世界。\u300d")

    changed_items = TranslationQuotePostProcessor.fix_items([first, second])

    assert changed_items == [first, second]
    assert first.get_dst() == "\u201c你好"
    assert second.get_dst() == "世界。\u201d"


def test_fix_items_keeps_mismatched_quote_counts_unchanged() -> None:
    item = create_epub_item(
        src="\u201cHello.\u201d",
        dst="\u300c你好\u300d\u300c多余\u300d",
    )

    changed_items = TranslationQuotePostProcessor.fix_items([item])

    assert changed_items == []
    assert item.get_dst() == "\u300c你好\u300d\u300c多余\u300d"


def test_fix_items_ignores_unfinished_items() -> None:
    item = create_epub_item(
        src="\u201cHello.\u201d",
        dst="\u300c你好。\u300d",
    )
    item.set_status(Base.ProjectStatus.NONE)

    changed_items = TranslationQuotePostProcessor.fix_items([item])

    assert changed_items == []
    assert item.get_dst() == "\u300c你好。\u300d"


def test_fix_items_uses_single_item_fallback_without_epub_metadata() -> None:
    item = Item(
        src="\u201cHello.\u201d",
        dst="\u300c你好。\u300d",
        status=Base.ProjectStatus.PROCESSED,
        file_type=Item.FileType.EPUB,
        file_path="legacy.epub",
    )

    changed_items = TranslationQuotePostProcessor.fix_items([item])

    assert changed_items == [item]
    assert item.get_dst() == "\u201c你好。\u201d"


def test_fix_items_uses_item_fallback_when_epub_block_path_missing() -> None:
    first = create_epub_item(
        src="\u201cHello",
        dst="\u300c你好",
        block_path="",
    )
    second = create_epub_item(
        src="world.\u201d",
        dst="世界。\u300d",
        block_path="",
    )

    changed_items = TranslationQuotePostProcessor.fix_items([first, second])

    assert changed_items == [first, second]
    assert first.get_dst() == "\u201c你好"
    assert second.get_dst() == "世界。\u201d"
