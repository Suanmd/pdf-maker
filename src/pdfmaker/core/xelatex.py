# -*- coding: utf-8 -*-
"""core.xelatex —— 超时保护的 xelatex 调用封装。

直接 ``subprocess.run([xelatex, ...])`` 不带 timeout 的隐患：一旦 xelatex 因字体
缺失 / 宏包冲突 / 死循环宏陷入挂起，单章 ``chapter`` 编排与整书 ``build`` 合并都会
无限卡住，既不报错也不退出，作者只能手动 kill。本封装把超时逻辑收口到一处：

- 超时时长取自 ``cfg.XELATEX_TIMEOUT``（默认 300s，可被 .pdfmaker.toml 的
  ``xelatex_timeout`` 或环境变量 ``PDFMAKER_XELATEX_TIMEOUT`` 覆盖，运行时经
  ``cfg.X`` 动态读取，保证覆盖生效）；
- 超时不抛 ``TimeoutExpired`` 向上冒泡（避免吓人的栈回溯），而是杀掉进程并以约定的
  ``TIMEOUT_RC``（124，POSIX 惯例的 timeout 退出码）返回，与 ``subprocess`` 约定兼容，
  便于上层统一判断「编译失败 → 中止」。
"""

import sys
from subprocess import TimeoutExpired, run

import pdfmaker.core.config as cfg

# POSIX 惯例：命令被 timeout 杀掉时的退出码，与 subprocess 约定统一
TIMEOUT_RC = 124


def compile(xelatex: str, *tex_args: str, cwd: str, timeout: float | None = None,
            quiet: bool = False) -> int:
    """运行一次 xelatex（如 ``-halt-on-error -interaction=nonstopmode _tmp.tex``）。

    参数
    ----
    xelatex : 可执行文件路径（来自 --xelatex / .toml / 运行时探测）。
    tex_args : 传给 xelatex 的其余参数（如源 .tex 名）。
    cwd : 编译工作目录（章节目录或 _build）。
    timeout : 单次超时秒；默认取 cfg.XELATEX_TIMEOUT（可被环境变量 / toml 覆盖）。
    quiet : True 时捕获全部输出不回显（xelatex 两遍全量输出常达数万字节，
        会淹没编排器的步骤摘要）；仅在失败时回显末尾 40 行便于定位。
        False 保持旧行为（输出直接透传到终端）。

    返回
    ----
    进程的 returncode；若超过 timeout 秒仍未结束，终止进程并以 TIMEOUT_RC 返回。
    """
    if timeout is None:
        timeout = cfg.XELATEX_TIMEOUT
    try:
        if quiet:
            r = run([xelatex, *tex_args], cwd=str(cwd), timeout=timeout,
                    capture_output=True)
            if r.returncode != 0:
                tail = (r.stdout or b"").decode("utf-8", errors="replace").splitlines()
                print(f"[xelatex] 失败（rc={r.returncode}），输出末尾 40 行：",
                      file=sys.stderr)
                for line in tail[-40:]:
                    print(f"  {line}", file=sys.stderr)
            return r.returncode
        r = run([xelatex, *tex_args], cwd=str(cwd), timeout=timeout)
        return r.returncode
    except TimeoutExpired:
        print(
            f"[xelatex] 编译超过 {timeout}s 仍未结束，已终止（疑似挂起）。\n"
            f"          如需放宽，请在 .pdfmaker.toml 设 xelatex_timeout = <秒> "
            f"或导出环境变量 PDFMAKER_XELATEX_TIMEOUT。",
            file=sys.stderr,
        )
        return TIMEOUT_RC
