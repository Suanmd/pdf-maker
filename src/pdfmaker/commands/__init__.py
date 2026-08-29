# -*- coding: utf-8 -*-
"""pdfmaker 命令实现。

每个模块暴露 ``main(argv=None) -> int`` 并自行完成 argparse 解析，
统一由 ``pdfmaker.cli`` 分发（``python -m pdfmaker <cmd>`` 或安装后的
``pdfmaker <cmd>`` 控制台脚本）。
"""
