# Changelog

本 skill 的所有重要变更记录。版本号遵循 [SemVer](https://semver.org/)。

---

## V1.1.0
> 提升脚本鲁棒性、日志检测精度、引用/链接校验能力，统一文档占位符规范。

### 📂 路径与调用模式（核心重构）
1. **脚本相对路径规范**
    - 引入统一占位符：`<PDF_MAKER>`=skill真实安装根目录、`<PROJECT>`=书稿项目根目录。
    - 调用范式统一：在书稿项目根目录执行 `python <PDF_MAKER>/scripts/fix.py N`，不再要求复制脚本、模板到书稿项目内。
    - 脚本定位规则：源文件从**当前工作目录(CWD)**查找；模板、内部资源从**skill自身安装目录**读取。
2. **全脚本路径解析统一补齐**
    - `verify_urls.py` / `cleanup.py` / `find_urls.py` 废弃旧 workaround，对齐 `fix.py/check.py/check_balance.py` 逻辑：**当前工作目录优先，脚本所在目录兜底**。解决从项目根目录运行找不到章节tex文件的历史问题。

### 🔍 检测逻辑精度 & 健壮性修复
1. **排版溢出日志 `check_overflow.py`**
    - 修复正则缺陷：旧正则无法捕获 `\hbox`/`\vbox` 溢出行，替换为多行模式 `^Overfull.*$`，完整输出行号明细。
    - 修复捕获组缺失导致 `IndexError` 崩溃，改用完整匹配 `m.group(0)`。
    - 计数逻辑改为精确匹配：`Overfull \hbox` / `Overfull \vbox` / `Underfull \hbox` / `Underfull \vbox`，过滤日志描述语句（如 `No Overfull or Underfull boxes reported.`），避免统计虚高。
2. **引用与参考文献检测 `check.py` / `check_balance.py`**
    - `\bibitem` 改用正则解析，同时兼容 `\bibitem{key}`、`\bibitem[label]{key}` 带标签写法，不再漏计数。
    - 新增检测：**孤儿bibitem（有定义无引用）、悬空\cite（有引用无条目）**，提前发现参考文献断链。
    - 增加 `\verb|...|` 内容剥离：统计链接、引用前剔除verb环境，防止样例代码内 `\cite{}`、`\url{}` 被误判为真实命令，消除误报孤儿/悬空引用。
3. **链接校验 `verify_urls.py`**
    - 增加 `archive.org` 快照自动兜底：遇到202、SSL EOF等访问失败，自动查询网页存档镜像，修复大量DOI、IEEE、ACM死链。
    - 补全缺失 `import json`，增加模块级SSL上下文。
4. **清理脚本 `cleanup.py`**
    - 修复误删除常驻脚本 `find_urls.py` 的bug；清理范围限定为章节文件 `chN.tex` 与临时文件 `_tmp.*`，所有py脚本保留。

### 🧩 fix.py 编译模板逻辑优化
- 移除fix.py内置preamble硬编码，改为读取模板文件 `assets/templates/_tmp.tex`，替换占位符生成编译临时文件，消除双源不一致问题。
- 更新模板内部注释，同步更新 README、SKILL.md 文档描述。

### 📖 文档同步更新
- README、SKILL.md 多处替换为 `<PDF_MAKER>` / `<PROJECT>` 占位符，删除旧相对路径示例。
- SKILL.md 补充说明：
  - `verify_urls` 需要联网，沙箱环境需放行网络访问
  - `archive.org` 镜像兜底机制
  - `find_urls.py` 属于常驻脚本，不属于清理目标

---

## v1.0.0

### 工程化与开源标准化

- **脚本清理与统一**
  - 删除 `check_figure_geometry.py`：图的排版规范已在 SKILL.md § 11 作为**前置约定**明确，写作即遵守，无需事后检查图节点几何重叠。
  - 删除 `reader_bulk.py`：与 `reader.py chunk` 能力重复，且会向仓库写入 `chunks_out/` 污染目录；保留 `reader.py` 作为阅读校验唯一入口。
  - 删除 `fix_figure_chain_spacing.py` 及其在 `fix.py` 中的调用：竖向 level 链路间距由图排版约定（§ 11）在前置阶段规定，不再做构建期自动改写。
  - 所有脚本统一文件头、路径处理（`pathlib`）、Windows 中文输出的 `reconfigure(encoding="utf-8")`，以及「用途 / 检查或处理项 / 是否调用 / 调用时机 / 退出码」的 docstring 约定。
  - `track_materials.py` 移除写死的章节↔素材映射与具体路径，改为读同目录 `materials.map.json`（可选）或在 `materials.json` 中手工维护。

- **文档通用化**
  - SKILL.md 去除具体项目名、人名、绝对路径、具体日期与版本号；内容泛化为「通用中文 LaTeX 报告」。
  - 踩坑记录由扁平长表改为**按主题归类分点**（编译/中文编码/表格/图/引用/URL/溢出/环境/工作流）。
  - 表格/图/URL 约定只讲**规则与注意事项**，不提供可直接复制的整表/整图样例，避免降低通用性；深化 SOP 使其对大模型友好（每步明确工具是否调用、调用时机）。
  - 补齐开源标准化内容：`README.md`、`LICENSE`（MIT）、`CONTRIBUTING.md`，以及本 `CHANGELOG.md`。

- **模板清理**
  - `main.tex` / `_tmp.tex` / `url-href.tex` 去除内部版本注释与具体章节引用，保留「为什么这么做」的 why 注释。
  - 移除具体可复制的 `table_example.tex` / `figure_example.tex` / `example_chapter.tex`（避免照抄失真），保留通用化的 `chapter_init_notes_template.md`。

### 保留的核心能力

- 单章独立编译 ↔ 整书合并双模式工作流。
- `fix.py` 预处理：`\url{}` → `\href{raw}{display}` 规范化、显示文本特殊字符转义、图片 `adjustbox` 宽度上限、生成 `chN.tex` + `_tmp.tex`。
- 素材强制阅读三阶段（`reader.py`）+ 跨会话状态追踪（`track_materials.py`）。
- 编译日志体检（`check_overflow.py`）拦截 Overfull / Missing character / multiply-defined / undefined references / Fatal。
- 参考文献降级 + 不跳页 + 不改页眉（etoolbox patch）；fancyhdr 页眉页脚统一；代码块浅灰打底自动换行；`emergencystretch` 防溢出。

---

## 维护原则

1. 升级前过一遍 [SKILL.md § 1 强制规范](SKILL.md#1-强制规范红线) 与 [§ 17 反例](SKILL.md#17-反例清单)。
2. 新增踩坑归入 [SKILL.md § 16](SKILL.md#16-踩坑分类速查) 对应主题。
3. 新增 SOP 步骤插入到 [§ 5–§ 7](SKILL.md#5-素材阅读-sop) 合适位置，不要「贴一段在末尾」。
4. 脚本改动保持单一职责，避免引入跨脚本隐藏依赖。
5. 模板改动同步 `main.tex` 与 `_tmp.tex`（同类配置不能两份漂移）。
6. 文档与示例保持通用，不出现具体项目/路径/日期等敏感信息。
