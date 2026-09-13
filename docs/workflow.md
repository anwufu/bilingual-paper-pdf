# 工作流详解

本文是 SKILL.md 的人类版展开。两条产线共用同一套克隆工艺：

- **Mode B（主推）**：只有英文原文 PDF，锚点自生成、译文自写。
- **Mode A**：手里另有一份别人做好的双语版 PDF 作为工艺参考，逐行差分复刻。

---

## Mode B：从零生产（推荐）

### B0. 环境

```bash
pip install -r requirements.txt
python scripts/setup_fonts.py
```

打开 `fonts/fonts_test.pdf` **用眼睛确认每个字形正确**（错字/豆腐块 = 字体坏了）。
`fitz.Font.has_glyph` 返回 True 不代表画出来是对的（pitfalls 1/19）。

### B1. 生成翻译工作表

```bash
python scripts/mkzones.py --src 论文.pdf --out zones.json       # 补充保留区
python scripts/solo_worksheet.py --src 论文.pdf --out worksheet.json \
    --zones zones.json [--math-exclude CMR,CMBX,CMTI,CMSS,CMTT,SF]
```

自动分类规则：印章/光栅图/矢量图区 → 保留；独立公式行（数学字体主导 + 短行 +
列内近居中）→ 保留；其余正文 → 待翻译槽位。

**两个关键参数**（判断依据见 pitfalls 39–41）：

- `--math-exclude`：Springer/LaTeX 论文的**正文本身**就是 Computer Modern 家族
  （CMR10 等），不排除会把每个正文行都判成"数学行"而漏翻。判断方法：全页 span
  字体按字符数取众数，把正文族名传入。
- `--zones`：自动检测漏掉的保留区——只有几条横线的 booktabs 表格、拼图式插图、
  多面板曲线图。`mkzones.py` 用**图注锚定法**补齐（表注在表上方→区域在下方；
  图注在图下方→区域在上方；x 外延取带内绘图实体 + 非正文文本行）。

生成后**逐页核对分类**：渲染一张打框对照图（保留区红框、槽位蓝框叠在原页上）目检
最快。公式被吞了？图注被保留了？表格单元格被当正文了？回到对应 pitfalls 调条件。

### B2. 翻译（质量的所在）

复制 `worksheet.json` 为 `content.json`，逐槽位填 `cn`。硬性要求：

1. **先建术语表再动笔**，全文术语严格一致；基准/方法名不译。
2. 忠实：不增译不漏译；语义单元一个不能丢。
3. 人名不臆造汉字。
4. 粗体对齐：英文加粗的词组，中文对应词组加粗。
5. 引用/URL 保留并用 `[[…]]` 标蓝（`cite_color`）。
6. 图表**内部**文字用 overlays 汉化，只动英文标签行，数字/方法名不动。

标记语法：`**粗体**`、`^{上标}`、`_{下标}`、`$数学$`、`\n` 分段（段首自动缩进，
项目符号列表靠它）。格式规范与自检见
[references/content-format.md](../references/content-format.md)。

### B3. 构建

```bash
python scripts/build_solo.py --src 论文.pdf --content content.json --out 双语版.pdf
python scripts/links_ay.py 双语版.pdf      # 作者-年份引用风格才需要
```

构建日志必须处理完再进审核：`[警告]`（行距压底/溢出）= 0；`[缩排]`/`[顺接]` 逐条
确认可接受；`[碰撞检测] 通过`。

### B4. 验收

```bash
python scripts/check_release.py --src 论文.pdf --content content.json \
    --pdf 双语版.pdf --build-log build.log
```

7 项机器自检全过 + 逐页目检（见 [audit-protocol.md](audit-protocol.md)）后才可交付。
交付物如约 35MB 是完整字体内嵌所致；要压缩用 fontTools 按码点子集化，
**禁用 `doc.subset_fonts()`**（会损坏 CFF 字体）。

---

## Mode A：有参考样例（复刻工艺）

```bash
python scripts/prep_reference.py --src 原文.pdf --ref 参考双语版.pdf --out plan.json
python scripts/build_from_plan.py --src 原文.pdf --plan plan.json --out 双语版.pdf
python scripts/audit.py --mine 双语版.pdf --ref 参考双语版.pdf --outdir _audit
```

prep 的原理：对英文原页每个文字行，到参考版右半同一坐标找——同位置同文字=保留
（克隆物），同位置没文字=抹白，同位置不同文字=抹白并由参考版中文行接管。
跑完检查 prep 报告：keep 应集中在图/表/公式区；若表格数字出现在 anomaly 里 = 差分
有 bug。审核用 `audit.py` 的差异聚类对照条，逐条定性（见 audit-protocol.md）。

---

## 常见故障速查

| 症状 | 大概率原因 | 去处 |
|---|---|---|
| 正文大面积没翻译 | 正文字体是 CM 家族没排除 | pitfalls 39 |
| 表格变成待翻译槽位 | booktabs 表格检测不到 | pitfalls 40, 用 mkzones |
| 图注/表注被保留成英文 | 图注没挡在区域外 | pitfalls 41 |
| 中文横跨中缝 | 栏边界被整宽块污染 | pitfalls 42–43 |
| 彩色框上盖出白块 | overlay 底色采了未保存的输出页 | pitfalls 47 |
| 引用跳转全丢 | LINK_NAMED 没重建 | pitfalls 49 |
| 中文出现字面 `[[` | 标记未闭合 | content-format 自检 1 |
