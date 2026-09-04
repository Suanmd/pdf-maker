# Changelog

本项目的重要变更记录。版本号遵循 [SemVer](https://semver.org/)。

---

## v2.3.0

由一部真实十章技术书的完整生产过程牵引的写作期体验升级。

- **Overfull 三层治理**：`check`/`lint` 写作期预警 `\texttt` 不可断行长串与 tabularx 单列挤压；规范化对长 `\texttt` 在分隔符后自动插入 `\allowbreak{}`（幂等，阈值可配、可关）；`overflow` 为每条阻断级 Overfull 附源文件行号定位，落入表格时列出候选单元格。
- **`verify` 验活豁免名单**：`PDFMAKER_VERIFY_ALLOW_HOSTS` / `verify_allow_hosts` 列出的内网、SSO 鉴权主机跳过联网探测，标记 EXEMPT 按已验证处理。
- **参考文献按需引用**：`MIN_REFS` 默认 0 不设下限，零引用章是合法形态；引用闭合与链接验活门禁不变。
- **字数门禁软化为告警**：默认 WARN 不阻断，`--strict` 恢复硬阻断，`--no-gate` 完全关闭。
- **骨架守卫**：未撰写的占位骨架在 `chapter` 中阻断、在 `build` 中告警，防止占位内容被编成 PDF 交付。
- **缺陷修复**：页眉长标题相撞（改为内核自绘 pagestyle，弃用 fancyhdr）、前置部分「空壳」检测、scaffold 生成骨架时剥离手写小节编号。
- **build 非阻断告警末尾汇总重列**：预检 WARN（空壳前置、占位骨架、补丁漂移等）散落在编译长输出之前，exit 0 时易被淹没；合并成功后统一重列，防静默出货。
- **文档修正**：明确 `pip install -e .` 为前置必做步骤——命令在书稿目录执行，未安装时 `python -m pdfmaker` 会报 `No module named pdfmaker`。

## v2.2.1

- **CWD 守卫**：`chapter` / `scaffold chapter` 拒绝在不像书稿项目根的目录创建章骨架（`--force-cwd` / `--force` 豁免），并附 cd 诊断线索。
- 占位骨架再生后早退并给出撰写指引；check 字数门禁文案给出缺口字数与计数口径出口。

## v2.2.0

- **新增 `compile` 子命令**：单章编译一体化（自动定位 xelatex → 编译两遍 → 日志体检），不再依赖手工 PATH。
- 占位骨架可由 `--material` 再生为素材驱动的富骨架；`track update --auto` 自动取数免手抄。
- 输出降噪：xelatex 默认静默编译、`reader ingest` 缓存短路等。

## v2.1.1

- 模板字号打磨：codeblock 小一档、表格统一 `\small`；preamble 漂移检测同步覆盖。

## v2.1.0

- 移植至 macOS / Claude Code；新增扁平布局（`--flat`）、素材位置约定与自动解析、扫描看门狗。
- 修复 `$...$` 掩码正则指数回溯挂死等严重缺陷；docstring / import / 注释风格统一。

## v2.0.0

首个对外开源版本。核心能力：

- **单章 ↔ 整书双模式**：单章独立编译（`fix` / `chapter`）与整书合并（`build` 一键完成 labels → xref → 规范化 → 编译 → 体检）。
- **关键节点质量关卡**：素材强制阅读、URL 联网验活、编译日志体检、跨章 `\label` 去重。
- **排版规范门禁**：三线表、表题在上 / 图题在下、伪代码强制 `codeblock` 环境，退化写法阻断。
- **工程化**：标准 Python 包、零第三方依赖、模板随包分发、单一规范化真源消除双源漂移。
