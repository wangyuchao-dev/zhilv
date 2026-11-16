"""日志配置。

之前全项目只有 print，线上出问题只能翻控制台、还没时间戳。
这里统一一下：所有模块用 logging.getLogger(__name__) 记录，
格式带时间、级别、模块名，一眼能看出是哪儿出的。

用法：
    在 main.py 启动时调一次 setup_logging()，
    其他地方直接 logger = logging.getLogger(__name__)。
"""
from __future__ import annotations

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)-28s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]

    # 这几个库默认话太多，压到 WARNING，不然控制台全是请求日志
    for noisy in ("httpx", "httpcore", "urllib3", "chromadb", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
