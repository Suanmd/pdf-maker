# -*- coding: utf-8 -*-
"""core.chapters —— 章节枚举与排序（整书合并 / 全量验活共用）。"""

import glob
import re
from pathlib import Path


def chapter_sort_key(p: Path | str) -> tuple:
    """给章节路径一个「按章号数值排序」的键。

    排序分组（前导元组项保证优先级）：
    - 数字章 ``第N章`` → (0, N)   按章号数值升序；
    - 附录 ``附录X`` → (1, "X") 放数字章之后，按标识字符串升序；
    - 其它（不应出现） → (2, 路径)  兜底放最后。
    """
    s = str(p)
    m = re.search(r"第(\d+)章", s)
    if m:
        return (0, int(m.group(1)))
    m = re.search(r"附录([^/\\]+?)\.tex", s)
    if m:
        return (1, m.group(1))
    return (2, s)


def collect_chapters(root: Path) -> list[Path]:
    """列出书稿目录下全部章节源文件，按章号数值排序。

    匹配两种布局：标准布局（第N章/第N章.tex、附录X/附录X.tex）与旧扁平布局
    （第N章.tex、附录X.tex 直接在项目根）。
    """
    pats = [
        str(root / "第*章" / "第*章.tex"),
        str(root / "第*章.tex"),
        str(root / "附录*" / "附录*.tex"),
        str(root / "附录*.tex"),
    ]
    files = sorted({f for p in pats for f in glob.glob(p)}, key=chapter_sort_key)
    return [Path(f) for f in files]


def chapter_range(root: Path) -> tuple[int, int]:
    """从目录推导章节号范围 (min, max)，仅看数字章（忽略附录）。无数字章返回 (0, 0)。"""
    nums = []
    for f in collect_chapters(root):
        m = re.search(r"第(\d+)章", str(f))
        if m:
            nums.append(int(m.group(1)))
    if not nums:
        return (0, 0)
    return (min(nums), max(nums))
