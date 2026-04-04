class RequestCancelledError(Exception):
    """用户触发停止导致的主动取消（不应记为翻译错误）。"""


class RequestHardTimeoutError(Exception):
    """请求级硬超时（按可恢复失败处理，不等同于用户停止）。"""


class RequestConnectionError(Exception):
    """网络连接层异常，通常来自连接建立、连接池等待或读写阶段。"""


class RequestRateLimitError(Exception):
    """上游明确返回速率限制，需要降速或等待窗口重置。"""


class RequestHTTPStatusError(Exception):
    """HTTP 状态异常，保留原始状态码和请求标识用于诊断。"""


class StreamDegradationError(Exception):
    """流式输出检测到明显退化/重复，提前中断。"""
