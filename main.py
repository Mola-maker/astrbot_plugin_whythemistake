import asyncio
import collections
import hashlib
import time

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.star.context import Context as _FullContext

_SELF_TAG = "[WhyTheMistake]"
_DEDUP_MAX = 200
_MIN_INTERVAL = 10.0   # 两次 LLM 调用最小间隔（秒）
_ERROR_TRUNCATE = 600  # 上报给 LLM 的报错最大字符数
_WATCH_LEVELS = frozenset({"WARNING", "ERROR", "CRITICAL"})


def _find_log_broker():
    """从框架 logger 的 handlers 中取出 LogBroker 实例（duck typing，无需 import logging）。"""
    for handler in logger.handlers:
        broker = getattr(handler, "log_broker", None)
        if broker is not None:
            return broker
    return None


@register("whythemistake", "Mola", "后台静默检测终端报错并用 LLM 分析原因", "1.0.0")
class WhyTheMistakePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 重声明为完整类型，消除 Pylance 对 _ContextLike 的限制
        self.context: _FullContext = context  # type: ignore[assignment]
        self._broker = None
        self._log_queue: asyncio.Queue | None = None
        self._monitor_task: asyncio.Task | None = None
        # FIFO 去重：set 负责 O(1) 查询，deque 负责按序淘汰
        self._seen_set: set[str] = set()
        self._seen_queue: collections.deque[str] = collections.deque()
        self._last_call_time: float = 0.0

    async def initialize(self):
        self._broker = _find_log_broker()
        if self._broker is None:
            logger.warning(f"{_SELF_TAG} 未找到 LogBroker，检测功能未启动")
            return
        self._log_queue = self._broker.register()
        self._monitor_task = asyncio.create_task(self._monitor_logs())
        logger.info(f"{_SELF_TAG} WARNING/ERROR/CRITICAL 检测已启动")

    def _track_hash(self, h: str) -> bool:
        """返回 True 表示首次出现；超出上限时 FIFO 淘汰最旧条目。"""
        if h in self._seen_set:
            return False
        if len(self._seen_set) >= _DEDUP_MAX:
            oldest = self._seen_queue.popleft()
            self._seen_set.discard(oldest)
        self._seen_set.add(h)
        self._seen_queue.append(h)
        return True

    async def _monitor_logs(self) -> None:
        while True:
            try:
                entry: dict = await self._log_queue.get()
            except asyncio.CancelledError:
                break

            if entry.get("level") not in _WATCH_LEVELS:
                continue

            data: str = entry.get("data", "")
            if _SELF_TAG in data:
                continue

            # 先限速，通过后再去重入库——防止冷却期内的新错误被永久吞噬
            now = time.monotonic()
            if now - self._last_call_time < _MIN_INTERVAL:
                continue

            h = hashlib.md5(data[:300].encode()).hexdigest()
            if not self._track_hash(h):
                continue

            self._last_call_time = now
            asyncio.create_task(self._analyze(data))

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
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        if self._broker is not None and self._log_queue is not None:
            self._broker.unregister(self._log_queue)
        logger.info(f"{_SELF_TAG} 错误检测已停止")
