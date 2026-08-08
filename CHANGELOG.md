# Changelog

本 skill 的所有重要变更记录。版本号遵循 [SemVer](https://semver.org/)。

---

## 当前版本（开源重构版）

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
