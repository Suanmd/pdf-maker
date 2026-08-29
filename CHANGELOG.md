# Changelog

本技能的所有重要变更记录。版本号遵循 [SemVer](https://semver.org/)。

---

## v2.0.0

将此前累积的内部迭代版本整体归一为 `v2.0.0` 对外发布，清理全部内部迭代版本痕迹，统一版本声明位置（`pyproject.toml` 为单一真源，`__init__.py` 兜底常量同步），并将章节阅读笔记模板归档至 `src/pdfmaker/templates/`。

本版本即首个对外开源的中文 LaTeX 报告/书籍工程化工具，核心能力：

### 单章 ↔ 整书双模式
- **单章编译**（`fix` / `chapter`）：从素材生成合规富骨架，URL 规范化 + TikZ 图宽上限，单章独立 `xelatex` 编译。
- **整书合并**（`build`）：跨章 `\label` 去重 → 引用预检 → 统一规范化 → `xelatex×2` → 编译日志体检 → 落盘 `main.pdf`。

### 关键节点质量关卡
- **素材强制阅读**（`reader`）：`ingest` / `index` / `chunk` / `verify` / `toc` 五字段校验。
- **URL 联网验活**（`verify`）：重试/退避 + 瞬时错误二次退避 + archive 兜底 + 软 404 内容指纹 `SUSPECT` 告警；退出码 0/1/2。
- **编译日志体检**（`overflow`）：拦截 Overfull / Missing character / 断链 / 缺字符 / Fatal，并给出「根因→修复」建议。
- **跨章 `\label` 去重**（`labels`）。

### 排版规范门禁（阻断级，编译前暴露）
- 三线表：禁用裸 `\hline` 与列格式竖线 `|`，且必须含 `\toprule`/`\bottomrule`。
- 表题在上 / 图题在下（覆盖 `table*` / `figure*` 星号变体）。
- 伪代码/代码块强制共享 preamble 的 `codeblock` 环境，禁用裸 `verbatim` / `lstlisting`。
- 风险预检（warning 级不阻断）：缺字字符 / 截断 URL / 跨章 `\ref` / TikZ `&` / 代码块非 ASCII。
- 反向引用预检 `scan_cite_undef`：cite 键无对应 `\bibitem` 即阻断。
- 字数硬门禁（下限 `--min-chars`、上限 `--max-chars`，可阻断；visible 口径含表格单元格）。
- 参考文献数量下限（建议级，无上限）；bibitem 数 = 链接数 = cite 数。

### 整书合并稳健性预检（非阻断）
- 前置部分（摘要/序言/术语表）存在性预检，避免静默出货无前置部分的书。
- `main.tex` 与共享补丁源 `_preamble_shared.tex` 漂移预检，避免单章/整书行为不一致。
- `main.tex` 纳入字形安全网（`fix_glyphs`），补齐主控绕过规范化的缺口。

### 工程化
- 标准 Python 包（`src/pdfmaker/`），零第三方依赖，仅依赖系统 TeX 工具链（xelatex）。
- 模板随包分发（`pdfmaker.templates`），单一规范化真源消除双源漂移。
- 源码与文档内容保持通用，不含任何项目专属痕迹与硬编码路径。
