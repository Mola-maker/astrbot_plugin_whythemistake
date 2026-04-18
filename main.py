import asyncio
import hashlib  #哈希算法
import time
import traceback as tb_module

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.star.context import Context as _FullContext
try:
    from loguru import logger as loguru_logger

    _LOGURU_AVAILABLE = True
except ImportError:
    _LOGURU_AVAILABLE = False


_SELF_TAG = "[WhyTheMistake]"
_DEDUP_MAX = 200
_MIN_INTERVAL = 10.0  # 两次 LLM 调用最小间隔（秒）
_ERROR_TRUNCATE = 600  # 上报给 LLM 的报错最大字符数


@register("whythemistake", "Mola", "后台静默检测终端报错并用 LLM 分析原因", "1.0.0")

class WhyTheMistakePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.context: _FullContext = context  # type: ignore[assignment]
        self._sink_id: int | None = None
        self._seen_hashes: set[str] = set()
        self._last_call_time: float = 0.0
        self._loop: asyncio.AbstractEventLoop | None = None

    async def initialize(self):
        if not _LOGURU_AVAILABLE:
            logger.warning(f"{_SELF_TAG} loguru 不可用喵，请检查python环境和网络环境")
            return
        

        self._loop = asyncio.get_running_loop()
        #注册一个sink用来拦截错误日志
        # level 是最低阈值，设为 WARNING 即可同时捕获 WARNING/ERROR/CRITICAL
        self._sink_id = loguru_logger.add(self._sink, level="WARNING")
        logger.info(f"{_SELF_TAG} WARNING/ERROR/CRITICAL 检测已启动")

    # loguru 同步回调 —— 不可使用 await
    def _sink(self, message) -> None:
        record = message.record
        msg_text: str = record["message"]

        # 跳过自身日志，防止递归
        if _SELF_TAG in msg_text:
            return

        # 拼接 traceback（若有）
        parts = [msg_text]
        exc = record.get("exception")
        if exc and exc[0] is not None:
            parts.append("".join(tb_module.format_exception(*exc)))
        full_text = "\n".join(parts)

        # 去重：相同内容 hash 跳过
        h = hashlib.md5(full_text[:300].encode()).hexdigest()
        if h in self._seen_hashes:
            return
        self._seen_hashes.add(h)
        if len(self._seen_hashes) > _DEDUP_MAX:
            self._seen_hashes.clear()

        # 限速：避免短时间内大量 LLM 调用
        now = time.monotonic()
        if now - self._last_call_time < _MIN_INTERVAL:
            return
        self._last_call_time = now

        # 调度异步分析任务 当前线程有事件循环 ->返回对象，不然就返回runtime error
        '''
            try:
            # 先尝试情况 A
            loop = asyncio.get_running_loop()
            loop.create_task(...)
            except RuntimeError:
                # 情况 A 失败，走情况 B
                asyncio.run_coroutine_threadsafe(...)
            同步回调想调异步
            直接 await 行不通
            事件循环来帮忙
            两种方式记心中

            主线程里 create_task
            后台线程 thread_safe
            try 里先试第一种
            失败再走第二种

            两者自动做切换
            管它线程从哪来
            任务最终都执行
            异步分析跑起来
        '''
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._analyze(full_text)) #不阻碍当前代码
        except RuntimeError:
            # 从非事件循环线程触发，使用线程安全提交
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
        if self._sink_id is not None and _LOGURU_AVAILABLE:
            try:
                loguru_logger.remove(self._sink_id)
            except Exception:
                pass
        logger.info(f"{_SELF_TAG} 错误检测已停止")