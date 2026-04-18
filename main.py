import asyncio
import collections
import hashlib
import logging
import time
import traceback as tb_module

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.star.context import Context as _FullContext

_SELF_TAG = "[WhyTheMistake]"
_DEDUP_MAX = 200
_MIN_INTERVAL = 10.0   # 两次 LLM 调用最小间隔（秒）
_ERROR_TRUNCATE = 600  # 上报给 LLM 的报错最大字符数


class _ErrorSinkHandler(logging.Handler):
    """将 WARNING 及以上的标准 logging 记录转发给插件做 LLM 分析。"""

    def __init__(self, plugin: "WhyTheMistakePlugin") -> None:
        super().__init__(level=logging.WARNING)
        self._plugin = plugin

    def emit(self, record: logging.LogRecord) -> None:
        self._plugin._handle_record(record)


@register("whythemistake", "Mola", "后台静默检测终端报错并用 LLM 分析原因", "1.0.0")
class WhyTheMistakePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 重声明为完整类型，消除 Pylance 对 _ContextLike 的限制
        self.context: _FullContext = context  # type: ignore[assignment]
        self._handler: _ErrorSinkHandler | None = None
        # FIFO 去重：set 负责 O(1) 查询，deque 负责按序淘汰
        self._seen_set: set[str] = set()
        self._seen_queue: collections.deque[str] = collections.deque()
        self._last_call_time: float = 0.0
        self._loop: asyncio.AbstractEventLoop | None = None

    async def initialize(self):
        self._loop = asyncio.get_running_loop()
        self._handler = _ErrorSinkHandler(self)
        logging.getLogger("astrbot").addHandler(self._handler)
        logger.info(f"{_SELF_TAG} WARNING/ERROR/CRITICAL 检测已启动")

    def _track_hash(self, h: str) -> bool:
        """记录 hash；若已存在返回 False，否则入队并返回 True。超出上限时淘汰最旧条目。"""
        if h in self._seen_set:
            return False
        if len(self._seen_set) >= _DEDUP_MAX:
            oldest = self._seen_queue.popleft()
            self._seen_set.discard(oldest)
        self._seen_set.add(h)
        self._seen_queue.append(h)
        return True

    def _handle_record(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if _SELF_TAG in msg:
            return

        parts = [msg]
        if record.exc_info and record.exc_info[0] is not None:
            parts.append("".join(tb_module.format_exception(*record.exc_info)))
        full_text = "\n".join(parts)

        h = hashlib.md5(full_text[:300].encode()).hexdigest()
        if not self._track_hash(h):
            return

        now = time.monotonic()
        if now - self._last_call_time < _MIN_INTERVAL:
            return
        self._last_call_time = now

        # run_coroutine_threadsafe 对任意线程（含主线程）均安全
        if self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(self._analyze(full_text), self._loop)

    async def _analyze(self, error_text: str) -> None:
        try:
            providers = self.context.get_all_providers()
            if not providers:
                return

            provider_id = providers[0].meta().id
            prompt = (
                "以下是 AstrBot 运行时的报错信息。"
                "请用中文说明【问题原因】和【解决方案】，合计不超过 50 个字：\n\n"
                + error_text[:_ERROR_TRUNCATE]
            )
            response = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
            )
            result = (response.completion_text or "").strip()
            if result:
                logger.info(f"{_SELF_TAG} 错误分析: {result}")
        except Exception as e:
            logger.debug(f"{_SELF_TAG} LLM 分析失败: {e}")

    async def terminate(self):
        if self._handler is not None:
            logging.getLogger("astrbot").removeHandler(self._handler)
            self._handler = None
        logger.info(f"{_SELF_TAG} 错误检测已停止")
