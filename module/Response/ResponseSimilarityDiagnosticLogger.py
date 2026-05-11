import os
import threading
from datetime import datetime
from typing import Any

from base.BasePath import BasePath
from model.Item import Item
from module.Utils.JSONTool import JSONTool


class ResponseSimilarityDiagnosticLogger:
    """把运行期相似度失败写入独立诊断文件，避免污染主日志。"""

    FILE_NAME: str = "similarity_diagnostics.log"
    MAX_TEXT_LENGTH: int = 800
    MAX_ITEM_CONTEXTS: int = 5
    LOCK: threading.Lock = threading.Lock()

    @classmethod
    def write(cls, payload: dict[str, Any]) -> None:
        """追加一条 JSONL 诊断记录；诊断失败不能影响翻译流程。"""
        try:
            log_dir = BasePath.get_log_dir()
            os.makedirs(log_dir, exist_ok=True)
            path = os.path.join(log_dir, cls.FILE_NAME)
            record = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                **payload,
            }
            line = JSONTool.dumps(record)
            with cls.LOCK:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception:
            # 诊断日志只是排障辅助，受限目录或磁盘错误不能导致任务失败。
            pass

    @classmethod
    def truncate_text(cls, text: str) -> str:
        """限制单条日志长度，避免失败原文过长时诊断文件膨胀。"""
        if len(text) <= cls.MAX_TEXT_LENGTH:
            return text
        return text[: cls.MAX_TEXT_LENGTH] + "...<truncated>"

    @classmethod
    def build_item_contexts(cls, items: list[Item]) -> list[dict[str, Any]]:
        """提取少量条目上下文，便于从诊断日志回到工程数据。"""
        contexts: list[dict[str, Any]] = []
        for item in items[: cls.MAX_ITEM_CONTEXTS]:
            contexts.append(
                {
                    "id": item.get_id(),
                    "file_path": item.get_file_path(),
                    "row": item.get_row(),
                    "tag": item.get_tag(),
                    "status": str(item.get_status()),
                    "retry_count": item.get_retry_count(),
                }
            )
        return contexts
