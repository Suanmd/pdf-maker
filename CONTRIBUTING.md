# 贡献指南（CONTRIBUTING）

感谢你考虑为 `pdf-maker` 做出贡献。本文件说明参与方式与代码约定。

## 行为准则

- 以建设性、尊重的方式交流。
- 讨论聚焦在「如何让中文 LaTeX 报告工程化更稳、更省心」。

## 项目布局

代码是标准 Python 包，位于 `src/pdfmaker/`：

- `pdfmaker/core/` —— 被多个命令复用的纯函数（路径定位 / 文本统计 / 规范化 / 章节枚举 / 编译前 lint）。
- `pdfmaker/commands/` —— 每个子命令一个模块，统一暴露 `main(argv: list[str] | None = None) -> int`，自行用 argparse 解析参数。
- `pdfmaker/templates/` —— 包内 LaTeX 模板（`main.tex` / `_tmp.tex`），以包数据形式随包分发。

## 如何贡献

### 报告问题（Issue）

请尽量包含：

1. **复现步骤**：哪一步流程、用了哪个子命令、输入是什么。
2. **期望 vs 实际**：日志片段、报错信息（尤其是 `Overfull` / `Missing character` / `multiply-defined` / `undefined references` / `Fatal`）。
3. **环境**：TeX Live 版本、Python 版本、操作系统。

### 提交改动（Pull Request）

1. Fork 本仓库并创建特性分支（`feat/...` 或 `fix/...`）。
2. 保持模块**单一职责**、**风格统一**：
   - 文件头 `# -*- coding: utf-8 -*-`；
   - 统一用 `pathlib.Path` 处理路径；
   - 需要在 Windows 下打印中文的命令模块，统一 `from pdfmaker.core.paths import setup_utf8` 并在模块顶层调用一次（幂等，已包 try/except），不要在模块里重复 `sys.stdout.reconfigure`；
   - 每个命令模块顶部用 docstring 说明**用途 / 处理或检查项 / 是否调用 / 调用时机 / 退出码**；
   - 函数写 docstring（用途 / 参数 / 返回 / 异常 / 说明），关键参数加类型标注（`Python 3.10+` 可用 `X | None`）。
3. **共享逻辑进 `pdfmaker/core/`**：源文件定位、UTF-8 输出、中文字数统计、规范化、lint 等被多命令复用的纯函数，只允许在 `core/` 定义一份，禁止在各命令里再写副本。
4. **CLI 统一用 argparse**：子命令或位置参数 + `-h` epilog 示例；不要手写 `sys.argv` 取参（硬编码 `int(sys.argv[1])` 这类写法不支持附录）。
5. 新加子命令时：在 `pdfmaker/commands/` 新增模块（暴露 `main`），并在 `pdfmaker/cli.py` 的 import 与 `_SUBCOMMANDS` 中登记；同步更新 `README.md` 命令参考与 `SKILL.md` 命令清单。
6. **模板改动同步两份**：`templates/main.tex` 与 `templates/_tmp.tex` 的关键补丁保持一致（同类配置不能两份漂移）。
7. 提交前确保：
   - 所有模块能通过 `python -m py_compile`；
   - 不引入跨模块的隐藏依赖（模块间 `import` 必须显式）；
   - 不残留具体项目名、具体路径、具体日期等敏感信息（内容保持通用）。
8. 在 PR 描述中说明「改了什么、为什么、影响哪个流程步骤」。

## 本地开发

```bash
pip install -e .               # 可编辑安装
python -m pdfmaker --help      # 冒烟测试 CLI
```

## 内容通用化约定

本工具以「通用中文 LaTeX 报告」为对象，撰写文档与示例时：

- **不**出现具体项目名、具体人名、具体绝对路径、具体日期/版本号。
- 排版约定以**规则为主**；对几何敏感的图与表格提供可复制样例作为基线。

## 版本记录

重大变更请写入 [CHANGELOG.md](CHANGELOG.md)，按里程碑组织（不要求精确到具体日期，但应体现「为什么改」）。

## 许可证

提交贡献即表示你同意以 [MIT 许可证](LICENSE) 发布你的改动。
