# -*- coding: utf-8 -*-
"""core.watchdog —— 扫描步骤的墙钟看门狗（SIGALRM，Unix）。

背景：check / balance / xref / fix 等步骤对章节源文件做大量正则扫描。一旦某条
正则存在歧义分支（量词分组内多分支在同一位置均可匹配），在「未闭合定界符 +
密集反斜杠」类对抗输入上会产生 2^N 指数回溯——进程 99% CPU 永久空转，且与
「步骤有点慢」无法区分（早期 _INLINE_MATH_RE 的真实事故，见 CHANGELOG）。

本模块给纯 Python 扫描步骤补上与 xelatex 超时（core/xelatex.py）同级的保护：
超时即抛 ``ScanTimeoutError``，由命令层收敛为「清晰错误信息 + exit 1（阻断）」。

平台说明：SIGALRM 仅 Unix 可用；非 Unix 平台（Windows）或不在主线程中调用时
退化为 no-op（静默放行，不影响功能）。本工具面向 macOS，主路径均有保护。
"""

import signal
from contextlib import contextmanager


class ScanTimeoutError(Exception):
    """扫描步骤超过看门狗时限（疑似正则回溯或病态输入）。

    消息为触发时限的步骤标签（如 "check"），供命令层打印精准错误。
    """


@contextmanager
def scan_watchdog(seconds: float, label: str):
    """给代码块加墙钟时限；超时抛 ``ScanTimeoutError(label)``。

    参数
    ----
    seconds : 墙钟时限（秒，支持浮点；用 setitimer 而非 alarm 以获得亚秒精度）。
    label : 步骤标签，超时异常携带，用于错误信息定位是哪一步挂死。

    说明
    ----
    - 仅在 Unix 主线程生效；非 Unix（无 SIGALRM）或非主线程（signal 只能在主线程
      设置）退化为 no-op，不影响功能。
    - 不支持嵌套：内层会覆盖外层的定时器。本工具的命令层只在每个命令 main()
      的最外层使用一次，不存在嵌套场景。
    """
    if not hasattr(signal, "SIGALRM"):
        yield  # 非 Unix 平台：无 SIGALRM，退化为 no-op
        return

    def _handler(signum, frame):
        raise ScanTimeoutError(label)

    try:
        old_handler = signal.signal(signal.SIGALRM, _handler)
    except ValueError:
        yield  # 非主线程（signal 只能在主线程设置）：退化为 no-op
        return
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
