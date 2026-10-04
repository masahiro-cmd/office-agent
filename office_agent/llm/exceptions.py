"""Custom exception types for LLM backends."""

from __future__ import annotations


class LLMError(RuntimeError):
    """LLM 関連エラーの基底クラス（RuntimeError のサブクラスで後方互換）。"""


class LLMConnectionError(LLMError):
    """LLM サーバーへの接続失敗（接続拒否・DNS 等）。"""


class LLMTimeoutError(LLMError):
    """LLM サーバーがタイムアウト時間内に応答しなかった。"""


class LLMBadResponseError(LLMError):
    """LLM サーバーが非 2xx または空レスポンスを返した。"""


class LLMJSONDecodeError(LLMError):
    """全リトライを使い切っても JSON パースに失敗した。"""

    def __init__(self, message: str, last_raw: str = "", cause: Exception | None = None) -> None:
        super().__init__(message)
        self.last_raw = last_raw
        self.__cause__ = cause
