# Font Licenses / 字体授权说明

本仓库 `fonts/` 目录中的字体文件均以 **SIL Open Font License 1.1 (OFL-1.1)** 授权，
允许自由使用、研究、修改与再分发（含内嵌进 PDF 交付物）。OFL 全文见本目录
[`OFL-1.1.txt`](OFL-1.1.txt)。

| 文件 | 字体家族 | 来源 | 授权 |
|---|---|---|---|
| `NotoSerifSC-Regular.ttf` | Noto Serif SC | [Google Fonts (github.com/google/fonts)](https://github.com/google/fonts/tree/main/ofl/notoserifsc) | OFL-1.1 |
| `NotoSerifSC-Bold.ttf` | Noto Serif SC (wght=700 实例) | 同上，由可变字体实例化 | OFL-1.1 |
| `CMU-Italic.otf` | CMU Serif Italic (Computer Modern 斜体同形) | [CTAN cm-unicode](https://ctan.org/pkg/cm-unicode) | OFL-1.1 |

OFL 要求：随字体分发时**保留上述版权声明与许可文本**；不得单独出售字体文件本身；
若修改字体再分发，须改用其他保留名（保留名 Reserved Font Name 规则见 OFL 正文）。

## 未随仓库分发的系统字体

构建引擎在 Windows 上还会使用系统自带的 **Times New Roman**（西文衬线）与
**Segoe UI Symbol**（数学符号），这两者是微软专有字体、随 Windows 分发，
**不在本仓库分发**。在 Linux/macOS 上，引擎自动改用等价的可再分发字体：

| 用途 | Windows | Linux | macOS |
|---|---|---|---|
| 西文衬线 | Times New Roman | Liberation Serif / DejaVu Serif | Times New Roman / Liberation Serif |
| 数学符号 | Segoe UI Symbol | DejaVu Sans | Arial Unicode |

缺失时引擎的字形回退链（SYM→CMI→TMR）会兜底，建议 Linux 用户安装
`fonts-liberation` 与 `fonts-dejavu-core` 以获得与 Windows 一致的观感。

## 本仓库代码授权

代码部分的授权（Apache-2.0）与字体授权相互独立，见仓库根目录 [`LICENSE`](../LICENSE)。
