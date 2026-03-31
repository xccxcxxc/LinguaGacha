from __future__ import annotations

from typing import Any
from typing import cast

from PySide6.QtCore import QAbstractTableModel
from PySide6.QtCore import QModelIndex
from PySide6.QtCore import QObject
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from frontend.Proofreading.ProofreadingDomain import ProofreadingDomain
from model.Item import Item
from module.Localizer.Localizer import Localizer
from module.ResultChecker import WarningType


class ProofreadingTableModel(QAbstractTableModel):
    """校对页表格 Model。

    设计目标：
    - 不创建任何 per-row QWidget，避免快速翻页/滚动时的对象风暴。
    - 通过自定义 roles 为 Delegate 提供绘制所需数据（status/warnings）。
    - 不做分段加载：Qt 的 view 本身具备虚拟化能力，仅在可视区域请求 data()。
    """

    # ========== 列索引常量 ==========
    COL_SRC: int = 0
    COL_DST: int = 1
    COL_STATUS: int = 2
    COL_COUNT: int = 3

    # ========== 自定义 roles ==========
    # Qt.UserRole 常量在 stubs 中可能缺失，这里直接使用其数值以保证类型检查通过。
    USER_ROLE_BASE: int = 0x0100
    ITEM_ROLE: int = USER_ROLE_BASE + 1
    STATUS_ROLE: int = USER_ROLE_BASE + 2
    WARNINGS_ROLE: int = USER_ROLE_BASE + 3
    PLACEHOLDER_ROLE: int = USER_ROLE_BASE + 4

    # ========== 行与加载策略 ==========
    PLACEHOLDER_ROWS: int = 30

    def __init__(self, ui_font: QFont, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.ui_font = ui_font
        self.readonly: bool = False
        self.start_index: int = 0

        self.source_items: list[Item] = []
        self.warning_map: dict[int, list[WarningType]] = {}
        self.warning_tuples: dict[int, tuple[WarningType, ...]] = {}
        self.row_by_item_key: dict[int, int] = {}

        # 精译模式下每个精译 item 展开为两行：(item, is_ref_row)
        # is_ref_row=True → 参考行（显示原文 | 粗译）；False → 精译行（显示空 | 精译）
        self._display_rows: list[tuple[Item, bool]] = []

        # DisplayRole 热路径缓存：按需缓存 compact 结果，避免滚动重绘时重复计算/分配。
        self.display_src_cache: dict[int, str] = {}
        self.display_dst_cache: dict[int, str] = {}
        self.display_ref_dst_cache: dict[int, str] = {}

    # ========== 数据源与状态 ==========
    def set_data_source(
        self,
        items: list[Item],
        warning_map: dict[int, list[WarningType]],
        start_index: int = 0,
    ) -> None:
        self.beginResetModel()
        self.source_items = list(items)
        self.warning_map = dict(warning_map) if warning_map else {}
        self.warning_tuples = {
            k: tuple(v)
            for k, v in self.warning_map.items()
            if isinstance(v, list) and v
        }
        self.start_index = max(0, int(start_index))

        # 构建展示行列表：精译 item（有 ref_dst）展开为两行，普通 item 一行
        self._display_rows = []
        for item in self.source_items:
            if item.get_ref_dst() != "":
                self._display_rows.append((item, True))  # 参考行
                self._display_rows.append((item, False))  # 精译行
            else:
                self._display_rows.append((item, False))  # 普通行

        # 仅记录每个 item 对应的第一展示行（用于 find_row_by_item 跳转）
        self.row_by_item_key = {}
        for row, (item, _) in enumerate(self._display_rows):
            if id(item) not in self.row_by_item_key:
                self.row_by_item_key[id(item)] = row

        # 数据源切换意味着所有派生缓存均失效。
        self.display_src_cache.clear()
        self.display_dst_cache.clear()
        self.display_ref_dst_cache.clear()
        self.endResetModel()

    def set_item_warnings(self, item: Item, warnings: list[WarningType]) -> None:
        key = ProofreadingDomain.get_warning_key(item)
        if warnings:
            resolved = list(warnings)
            self.warning_map[key] = resolved
            self.warning_tuples[key] = tuple(resolved)
        else:
            self.warning_map.pop(key, None)
            self.warning_tuples.pop(key, None)

    def invalidate_display_cache_by_row(
        self, row: int, *, src: bool = False, dst: bool = False
    ) -> None:
        item = self.get_source_item(row)
        if item is None:
            return
        key = id(item)
        if src:
            self.display_src_cache.pop(key, None)
        if dst:
            self.display_dst_cache.pop(key, None)
            self.display_ref_dst_cache.pop(key, None)

    def set_readonly(self, readonly: bool) -> None:
        self.readonly = bool(readonly)

    def total_count(self) -> int:
        return len(self.source_items)

    def find_row_by_item(self, item: Item) -> int:
        return self.row_by_item_key.get(id(item), -1)

    def get_source_item(self, row: int) -> Item | None:
        if row < 0 or row >= len(self._display_rows):
            return None
        return self._display_rows[row][0]

    def is_placeholder_row(self, row: int) -> bool:
        return row < 0 or row >= len(self._display_rows)

    # ========== Qt Model 接口 ==========
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        del parent
        # 保持表格高度稳定：真实行数不足时补齐占位行。
        return max(len(self._display_rows), self.PLACEHOLDER_ROWS)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        del parent
        return self.COL_COUNT

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:  # noqa: ANN401
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if orientation == Qt.Orientation.Horizontal:
            headers = (
                Localizer.get().table_col_source,
                Localizer.get().table_col_translation,
                Localizer.get().proofreading_page_col_status,
            )
            if 0 <= section < len(headers):
                return headers[section]
            return None

        if self.is_placeholder_row(section):
            return ""
        _, is_ref_row = self._display_rows[section]
        # 精译参考行不显示序号，精译行和普通行显示 item 在 source_items 中的序号
        if is_ref_row:
            return ""
        item = self._display_rows[section][0]
        item_index = (
            self.source_items.index(item) if item in self.source_items else section
        )
        return str(self.start_index + item_index + 1)

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:  # noqa: N802
        if not index.isValid():
            return cast(Qt.ItemFlags, Qt.ItemFlag.NoItemFlags)

        if self.is_placeholder_row(index.row()):
            # 占位行：保持 enabled 以维持样式，但不允许选中/编辑。
            return cast(Qt.ItemFlags, Qt.ItemFlag.ItemIsEnabled)

        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        row = index.row()
        _, is_ref_row = (
            self._display_rows[row] if row < len(self._display_rows) else (None, False)
        )
        # 精译参考行只读；精译行和普通行按 readonly 开关决定
        if index.column() == self.COL_DST and not self.readonly and not is_ref_row:
            flags = flags | Qt.ItemFlag.ItemIsEditable
        return cast(Qt.ItemFlags, flags)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # noqa: ANN401, N802
        if not index.isValid():
            return None

        row = index.row()
        if self.is_placeholder_row(row):
            if role == self.PLACEHOLDER_ROLE:
                return True
            if role in (self.ITEM_ROLE, self.STATUS_ROLE):
                return None
            if role == self.WARNINGS_ROLE:
                return tuple()
            if role == Qt.ItemDataRole.DisplayRole:
                return ""
            if role == Qt.ItemDataRole.FontRole:
                return self.ui_font
            if role == Qt.ItemDataRole.TextAlignmentRole:
                if index.column() == self.COL_STATUS:
                    return Qt.AlignmentFlag.AlignCenter
                return Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            return None

        item, is_ref_row = self._display_rows[row]

        if role == self.ITEM_ROLE:
            return item
        if role == self.STATUS_ROLE:
            # 精译参考行不提供状态角色（委托不为其绘制状态图标）
            return None if is_ref_row else item.get_status()
        if role == self.WARNINGS_ROLE:
            if is_ref_row:
                return tuple()
            key = ProofreadingDomain.get_warning_key(item)
            return self.warning_tuples.get(key, tuple())
        if role == self.PLACEHOLDER_ROLE:
            return False
        if role == Qt.ItemDataRole.FontRole:
            return self.ui_font
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if index.column() == self.COL_STATUS:
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft

        if role != Qt.ItemDataRole.DisplayRole:
            return None

        cache_key = id(item)

        if is_ref_row:
            # 精译参考行：原文列显示原文，译文列显示粗译
            if index.column() == self.COL_SRC:
                cached = self.display_src_cache.get(cache_key)
                if cached is not None:
                    return cached
                text = self.compact_multiline_text(item.get_src())
                self.display_src_cache[cache_key] = text
                return text
            if index.column() == self.COL_DST:
                cached = self.display_ref_dst_cache.get(cache_key)
                if cached is not None:
                    return cached
                text = self.compact_multiline_text(item.get_ref_dst())
                self.display_ref_dst_cache[cache_key] = text
                return text
            return ""

        # 普通行或精译行
        if index.column() == self.COL_SRC:
            # 精译 item 的精译行原文列留空（原文已在参考行显示）
            if item.get_ref_dst() != "":
                return ""
            cached = self.display_src_cache.get(cache_key)
            if cached is not None:
                return cached
            text = self.compact_multiline_text(item.get_src())
            self.display_src_cache[cache_key] = text
            return text
        if index.column() == self.COL_DST:
            cached = self.display_dst_cache.get(cache_key)
            if cached is not None:
                return cached
            dst = item.get_dst()
            ref_dst = item.get_ref_dst()
            # 精译与粗译相同时显示"无变化"以节省阅读成本
            if ref_dst != "" and dst == ref_dst:
                text = Localizer.get().proofreading_page_no_change
            else:
                text = self.compact_multiline_text(dst)
            self.display_dst_cache[cache_key] = text
            return text
        return ""

    # ========== 文本展示工具 ==========
    @staticmethod
    def compact_multiline_text(text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        parts = [part.strip() for part in normalized.split("\n") if part.strip()]
        return " ↲ ".join(parts)
