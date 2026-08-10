# Changelog

本 skill 的所有重要变更记录。版本号遵循 [SemVer](https://semver.org/)。

---

## V2.0.0
> 重构：抽出共享模块、统一 CLI、清除历史补丁漂移，并以标准开源 skill 结构重新组织。

### 结构
- 新增 `references/SOP.md`：把 `SKILL.md` 的详细流程、命令参考、模板说明、URL 写法、踩坑速查下沉，遵循 skill 的「渐进式披露」原则（`SKILL.md` 精简为触发 + 红线 + 索引，细节按需加载）。
- `SKILL.md` 加标准 YAML frontmatter（`name` / `description` / `agent_created: true`），重写正文为祈使句式、精简到 < 5k 词。
- `README.md` 改为 GitHub 开源风格（特性 / 环境 / 安装 / 快速开始 / 结构树 / 命令表 / FAQ），修正 Python 版本为 **3.10+**，明确**零第三方依赖**。
- `CONTRIBUTING.md` 与新的代码结构对齐（共享模块 `common.py`、argparse CLI、`references/` 目录、五段式 docstring + 类型标注）。

### 脚本重构（消除补丁漂移）
- 新增 `scripts/common.py`：集中「源文件定位 / UTF-8 输出 / 中文字数统计」纯函数，成为**唯一真源**。
- 删除历史遗留的**四份重复**源定位逻辑：`fix.py` / `check.py` / `check_balance.py` 各一份 `resolve_source`（签名还不同），`verify_urls.py` 一份行为不一致的 `locate_source`；统一改为 import `common.resolve_source`。
- `cleanup.py` 独立的 `find_workdir` + `int(sys.argv[1])` 改为复用 `common.workdir_for` / `mid_name_for`，并支持**附录**。
- 全部 9 个 CLI 脚本统一为 argparse 子命令 / 位置参数，均支持 `-h`（含本项目示例 epilog）；`fix.py` 在 `scripts/` 目录误跑时主动给出指引。
- `verify_urls.py` 行为不变（LIVE / ARCHIVE / DEAD 三态，exit 0/1/2），**不做自动替换**（尊重作者人工选源）。
- `fix_labels.py` 补上**附录支持**（glob 原只匹配 `第*章`）。

### 清理过时文件
- 删除冗余的 `assets/templates/url-href.tex`：其知识（中文 URL 写法）已并入 `references/SOP.md §5`，且 `_tmp.tex` 已预置等价 hyperref 设置，该独立文件无人引用。

---

## V1.2.0
> 彻底重构：统一文档与模板、消除所有陈旧交叉引用；URL 联网验活恢复为强制 SOP 关卡。

### 重构
- `SKILL.md` 全量重写：去除所有带日期的战报式叙述，压缩为纯规则规范。
- `README.md` / `CONTRIBUTING.md` 的全部章节锚点对齐新 `SKILL.md` 编号（原失效的 §16/§17 等已修正）。
- `main.tex` 与 `_tmp.tex` 的 `breakatwhitespace` 统一为 `false`；`_tmp.tex` 陈旧引用 §3 → 对应章节。
- `check.py` / `check_balance.py` / `cleanup.py` 清理对旧编号/已删脚本的引用。
- 修正单章 SOP 步骤编号：移除 `3.5` 式补丁编号，`verify_urls` 归为步骤 4，后续步骤顺延。
- 移除 `track_materials.py` 未使用的 `detect_project_dir()`（死代码）。
- 环境项修正：明确脚本不依赖 pypdf / pymupdf（纯 stdlib）。

### URL 联网验活——恢复为强制 SOP（重要更正）
- **恢复 `scripts/verify_urls.py` 并列为强制关卡**。初版 v1.2.0 误将其与 `find_urls.py` 一并删除，对发布级 PDF 是错误决定：成书出现死链/假链即摧毁可信度，必须有联网验活兜底。
- 行为：抽取章节全部 `\url{}` / `\href{}` URL → 本地格式校验（ASCII / 无空格 / 合法 scheme）→ 联网逐 URL 检测；直连 2xx/3xx 记 LIVE，直连失败再查 web.archive.org 快照记 ARCHIVE（不阻断），既失败又无快照记 DEAD。
- 退出码即 SOP 决策：**0** 全过可继续 / **1** 失效或虚构链接必须修 / **2** 离线未验活须联网重跑、禁止当作已验证（预警而非静默放过）。

### 删除（彻底重构）
- 移除 `scripts/find_urls.py`：仅抽取 URL 列表，功能已被 `reader.py` / `track_materials.py` 的正则覆盖，属冗余；无任何脚本再引用它。

---

## V1.1.0
> 提升脚本鲁棒性、日志检测精度、引用/链接校验能力，统一文档占位符规范。

- **路径与调用模式**：引入统一源文件/模板定位（CWD 优先、脚本目录兜底）；调用带全路径，禁止项目内可漂移副本。
- **检测精度**：`check_overflow.py` 改为精确匹配 `\hbox`/`\vbox` 溢出并修正计数；`check_balance.py` 兼容 `\bibitem[label]{key}`、检测孤儿 bibitem / 悬空 cite、剥离 `\verb` 内容防误判。
- **fix.py**：移除内联 preamble，改为读取 `assets/templates/_tmp.tex` 模板替换占位符，消除双源漂移。
- **cleanup.py**：清理范围限定为章节文件与 `_tmp.*`，所有 py 脚本保留。

---

## V1.0.0
> 工程化与开源标准化。

- 脚本清理与统一（单一职责、`pathlib`、UTF-8 输出、统一 docstring）；删除与 `reader.py` 重复的 `reader_bulk.py` 等。
- 文档通用化，踩坑记录归类分点；补齐 `README`/`LICENSE`(MIT)/`CONTRIBUTING`/`CHANGELOG`。
- 模板去除版本注释与具体章节引用，保留「为什么这么做」的 why 注释。

### 保留的核心能力
- 单章独立编译 ↔ 整书合并双模式工作流。
- `fix.py` 预处理：`\url{}` → `\href{raw}{display}` 规范化、图片 `adjustbox` 宽度上限、生成 `chN.tex` + `_tmp.tex`。
- 素材强制阅读三阶段（`reader.py`）+ 跨会话状态追踪（`track_materials.py`）。
- 编译日志体检（`check_overflow.py`）拦截 Overfull / Missing character / multiply-defined / undefined references / Fatal。
- 参考文献降级 + 不跳页 + 不改页眉；fancyhdr 页眉页脚统一；代码块浅灰打底自动换行；`emergencystretch` 防溢出。

---

## 维护原则

1. 升级前过一遍 `SKILL.md` 红线与 `references/SOP.md` 踩坑速查。
2. 新增踩坑归入 `references/SOP.md` 对应主题，归类分点。
3. 新增 SOP 步骤插入到合适位置，不「贴一段在末尾」。
4. 脚本改动保持单一职责，避免引入跨脚本隐藏依赖（共享逻辑进 `common.py`）。
5. 模板改动同步 `main.tex` 与 `_tmp.tex`（同类配置不能两份漂移）。
6. 文档与示例保持通用，不出现具体项目/路径/日期等敏感信息。
