---
name: bilingual-paper-pdf
description: 论文级中英双语对照 PDF 生产工具。当需要把英文学术论文做成左英右中、镜像对齐的双语 PDF，或维护/扩展本仓库引擎时，先读 SKILL.md。
---

# Agent 指引

本仓库同时是**人用的工具**和**agent 可加载的技能**。

- 产线工作流、铁律、模式选择：读 [SKILL.md](SKILL.md)（canonical，勿在别处复述）。
- 踩坑先查 [references/pitfalls.md](references/pitfalls.md)——每条都是真实返工换来的。
- 译文格式与交付自检：[references/content-format.md](references/content-format.md)。
- 人类向的流程详解：[docs/workflow.md](docs/workflow.md)；
  审核纪律：[docs/audit-protocol.md](docs/audit-protocol.md)。

## Always

- 改引擎代码后跑 `python scripts/check_release.py --src example/sample_paper.pdf --content example/content.json --pdf <产出>`，7 项必须全过。
- 构建日志出现 `[警告]` 时必须处理完才算完成。
- 动工前先读 pitfalls.md 相关条目，禁止目测估计坐标/字号。

## Ask first

- 修改 `references/pitfalls.md` 的既有条目编号或含义。
- 更换/新增字体（涉及授权，见 LICENSE-FONTS.md）。

## Never

- 在渲染/排版代码中裁剪或复制原文 PDF 的像素与文字对象；每个字形必须由脚本现画。
- 使用 `doc.subset_fonts()`（损坏 CFF 字体，见 pitfalls 3）。
- 在没跑 check_release.py 的情况下声称产出合格。
