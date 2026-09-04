# 贡献指南（CONTRIBUTING）

感谢你考虑为 `pdf-maker` 做出贡献。

## 行为准则

以建设性、尊重的方式交流，讨论聚焦「如何让中文 LaTeX 报告工程化更稳、更省心」。

## 项目布局

代码是标准 Python 包，位于 `src/pdfmaker/`：

- `pdfmaker/core/` —— 被多个命令复用的纯函数（路径 / 文本 / 规范化 / 章节 / lint / 配置 / 看门狗）。
- `pdfmaker/commands/` —— 每个子命令一个模块，统一暴露 `main(argv) -> int`，自行用 argparse 解析。
- `pdfmaker/templates/` —— 包内 LaTeX 模板，以包数据形式随包分发。

## 报告问题（Issue）

请尽量包含：复现步骤（哪个子命令、什么输入）；期望 vs 实际（日志片段，尤其是 `Overfull` / `Missing character` / `Fatal`）；环境（TeX Live 版本、Python 版本、操作系统）。

## 提交改动（Pull Request）

1. Fork 后建特性分支（`feat/...` 或 `fix/...`）。
2. 风格统一：文件头 `# -*- coding: utf-8 -*-`；路径用 `pathlib.Path`；打印中文的模块在顶层调一次 `setup_utf8()`；模块顶部 docstring 写清用途 / 检查项 / 退出码；函数写 docstring，关键参数加类型标注。
3. **共享逻辑进 `core/`**，禁止在命令里再写副本；模块间 `import` 必须显式。
4. **CLI 统一用 argparse**，不要手写 `sys.argv` 取参。
5. **正则防指数回溯**：量词分组内的各分支在任意输入位置必须互斥（暗坑示例：`(\\.|[^$])*?` 中 `\\.` 与 `[^$]` 在反斜杠处重叠，匹配失败时回溯空间 2^N 爆炸；写法是让通配分支排除另一分支的首字符）。新扫描器须通过 `tests/test_refactor_regressions.py` 的对抗语料。
6. 新加子命令：在 `commands/` 新增模块并在 `cli.py` 登记；同步更新 `README.md` 与 `SKILL.md`。
7. 模板改动同步两份：`main.tex` 与 `_tmp.tex` 的关键补丁保持一致。
8. 提交前：所有模块通过 `python -m py_compile`；`python3 -m pytest tests/ -q` 全过；不残留具体项目名、路径、日期。
9. PR 描述说明「改了什么、为什么、影响哪个流程步骤」。

## 本地开发

```bash
pip install -e .               # 可编辑安装
python -m pdfmaker --help      # 冒烟测试 CLI
python3 -m pytest tests/ -q    # 跑测试套件
```

## 内容通用化约定

文档与示例不出现具体项目名、人名、绝对路径、日期；排版约定以规则为主，对几何敏感的图与表格提供可复制样例。

## 版本记录与许可证

重大变更写入 [CHANGELOG.md](CHANGELOG.md)，体现「为什么改」。提交贡献即表示同意以 [MIT 许可证](LICENSE) 发布。
