from model.Item import Item
from base.Base import Base
from module.Fixer.PunctuationFixer import PunctuationFixer


class TranslationQuotePostProcessor:
    """翻译完成后按文本段落修正话语引用引号。"""

    JOIN_SEPARATOR: str = "\n"
    GROUP_EPUB: str = "EPUB"
    GROUP_ITEM: str = "ITEM"

    @classmethod
    def fix_items(cls, items: list[Item]) -> list[Item]:
        """就地修复已完成条目，并返回实际发生变化的条目列表。"""
        changed_items: list[Item] = []
        groups = cls.collect_groups(items)
        for group_items in groups.values():
            changed_items.extend(cls.fix_group_items(group_items))
        return changed_items

    @classmethod
    def collect_groups(cls, items: list[Item]) -> dict[tuple[str, ...], list[Item]]:
        """EPUB 使用块级路径做段落键；其他格式退回单 item，避免跨行误改。"""
        groups: dict[tuple[str, ...], list[Item]] = {}
        for index, item in enumerate(items):
            if not cls.is_processable_item(item):
                continue
            key = cls.get_group_key(item, index)
            groups.setdefault(key, []).append(item)
        return groups

    @classmethod
    def is_processable_item(cls, item: Item) -> bool:
        """只处理已成功翻译且有译文的条目，避免改写未完成或跳过状态。"""
        return (
            item.get_status() == Base.ProjectStatus.PROCESSED
            and item.get_src() != ""
            and item.get_dst() != ""
        )

    @classmethod
    def get_group_key(cls, item: Item, index: int) -> tuple[str, ...]:
        """返回稳定分组键，EPUB 优先使用 AST 中的块级路径。"""
        epub_key = cls.get_epub_group_key(item)
        if epub_key is not None:
            return epub_key
        return (
            cls.GROUP_ITEM,
            item.get_file_path(),
            str(item.get_row()),
            str(item.get_id() if item.get_id() is not None else index),
        )

    @classmethod
    def get_epub_group_key(cls, item: Item) -> tuple[str, ...] | None:
        """从 EPUB AST 元数据中取段落键，没有元数据时交给单 item 兜底。"""
        if item.get_file_type() != Item.FileType.EPUB:
            return None

        extra_field = item.get_extra_field()
        if not isinstance(extra_field, dict):
            return None

        epub = extra_field.get("epub")
        if not isinstance(epub, dict):
            return None

        doc_path = epub.get("doc_path")
        block_path = epub.get("block_path")
        if not isinstance(doc_path, str) or doc_path == "":
            doc_path = item.get_tag()
        if not isinstance(block_path, str) or block_path == "":
            return None

        return (
            cls.GROUP_EPUB,
            item.get_file_path(),
            doc_path,
            block_path,
        )

    @classmethod
    def fix_group_items(cls, items: list[Item]) -> list[Item]:
        """把同段落文本合并后修复，再按原长度切回各 item。"""
        src_parts = [item.get_src() for item in items]
        dst_parts = [item.get_dst() for item in items]
        src_joined = cls.JOIN_SEPARATOR.join(src_parts)
        dst_joined = cls.JOIN_SEPARATOR.join(dst_parts)
        fixed_joined = PunctuationFixer.fix_quote_delimiters(src_joined, dst_joined)

        if fixed_joined == dst_joined or len(fixed_joined) != len(dst_joined):
            return []

        fixed_parts = cls.split_fixed_text_by_lengths(fixed_joined, dst_parts)
        changed_items: list[Item] = []
        for item, old_dst, new_dst in zip(items, dst_parts, fixed_parts):
            if old_dst == new_dst:
                continue
            item.set_dst(new_dst)
            changed_items.append(item)
        return changed_items

    @classmethod
    def split_fixed_text_by_lengths(
        cls, fixed_text: str, original_parts: list[str]
    ) -> list[str]:
        """引号修复只替换等长字符，因此可按原片段长度安全切回。"""
        parts: list[str] = []
        offset = 0
        for index, original in enumerate(original_parts):
            length = len(original)
            parts.append(fixed_text[offset : offset + length])
            offset = offset + length
            if index < len(original_parts) - 1:
                offset = offset + len(cls.JOIN_SEPARATOR)
        return parts
