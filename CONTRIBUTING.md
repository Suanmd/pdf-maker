# 贡献指南（CONTRIBUTING）

感谢你考虑为 `pdf-maker` 做出贡献。本文件说明参与方式与代码约定。

## 行为准则

- 以建设性、尊重的方式交流。
- 讨论聚焦在「如何让中文 LaTeX 报告工程化更稳、更省心」。

## 如何贡献

### 报告问题（Issue）

请尽量包含：

1. **复现步骤**：哪一步 SOP、用了哪个脚本、输入是什么。
2. **期望 vs 实际**：日志片段、报错信息（尤其是 `Overfull` / `Missing character` / `multiply-defined` / `undefined references` / `Fatal`）。
3. **环境**：TeX Live 版本、Python 版本、操作系统。

### 提交改动（Pull Request）

1. Fork 本仓库并创建特性分支（`feat/...` 或 `fix/...`）。
2. 保持脚本**单一职责**、**风格统一**：
   - 文件头 `# -*- coding: utf-8 -*-`；
   - 统一用 `pathlib.Path` 处理路径；
   - 需要在 Windows 下打印中文的脚本，统一 `from common import setup_utf8` 并在 `main()` 开头调用（幂等，已包 try/except），不要在脚本里重复 `sys.stdout.reconfigure`；
   - 每个脚本顶部用 docstring 说明**用途 / 处理或检查项 / 是否调用 / 调用时机 / 退出码**；
   - 函数写五段式 docstring（用途 / 参数 / 返回 / 异常 / 说明），关键参数加类型标注（`Python 3.10+` 可用 `X | None`）。
3. **共享逻辑进 `common.py`**：源文件定位、UTF-8 输出、中文字数统计等被多脚本复用的纯函数，只允许在 `scripts/common.py` 定义一份，禁止在各脚本里再写副本（历史教训：四份 `resolve_source` 漂移导致指向不清）。
4. **CLI 统一用 argparse**：子命令或位置参数 + `-h` epilog 示例；不要手写 `sys.argv` 取参（历史 `int(sys.argv[1])` 不支持附录）。
5. 同步更新文档：
   - 脚本行为变化 → 更新 `SKILL.md` 脚本表 + `references/SOP.md` 命令参考；
   - 新增/修改踩坑 → 更新 `references/SOP.md` 踩坑速查；
   - 模板/约定变化 → 同时改 `assets/templates/main.tex` 与 `_tmp.tex`（同类配置不能两份漂移）。
6. 提交前确保：
   - 所有 `scripts/*.py` 能通过 `python -m py_compile`；
   - 不引入跨脚本的隐藏依赖（模块间 `import` 必须显式）；
   - 不残留具体项目名、具体路径、具体日期等敏感信息（内容保持通用）。
7. 在 PR 描述中说明「改了什么、为什么、影响哪个 SOP 步骤」。

## 内容通用化约定

本 skill 以「通用中文 LaTeX 报告」为对象，撰写文档与示例时：

- **不**出现具体项目名、具体人名、具体绝对路径、具体日期/版本号。
- 排版约定以**规则为主**；对几何敏感的图与表格提供可复制样例作为基线，降低踩坑概率。
- 踩坑记录**归类分点**，不要堆成一条没有结构的扁平长表。

## 版本记录

重大变更请写入 [CHANGELOG.md](CHANGELOG.md)，按里程碑组织（不要求精确到具体日期，但应体现「为什么改」）。

## 许可证

提交贡献即表示你同意以 [MIT 许可证](LICENSE) 发布你的改动。
