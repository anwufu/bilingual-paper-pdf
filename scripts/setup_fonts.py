# -*- coding: utf-8 -*-
"""setup_fonts.py — 双语对照版字体配置 (clone 后跑一次)

仓库 fonts/ 目录已随仓库分发可再分发的字体 (Noto Serif SC / CMU Italic, 见
LICENSE-FONTS.md)。本脚本负责:
  1. 校验仓库字体存在且可用 (缺失时从官方源下载)
  2. 定位各平台的系统字体 (符号字体 / Times 系), 找不到就报告替代方案
  3. 生成字体测试卡 fonts_test.pdf —— 必须打开肉眼确认每个字形正确

用法: python scripts/setup_fonts.py [--repo-dir PATH]
"""
import argparse
import os
import sys
import urllib.request

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fontconfig import system_font_candidates  # noqa: E402
FONTS_DIR = os.path.join(REPO_DIR, 'fonts')

VF_URL = ('https://raw.githubusercontent.com/google/fonts/main/'
          'ofl/notoserifsc/NotoSerifSC%5Bwght%5D.ttf')
CMU_URL = 'https://mirrors.ctan.org/fonts/cm-unicode/fonts/otf/cmunti.otf'


def download(url, path):
    print(f'  下载 {os.path.basename(path)} ...')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=300) as r, open(path, 'wb') as f:
        f.write(r.read())
    print(f'  完成 {os.path.getsize(path) // 1024} KB')


def locate_system_fonts():
    found = {}
    missing = []
    for key, cands in system_font_candidates().items():
        for p in cands:
            if os.path.exists(p):
                found[key] = p
                break
        else:
            missing.append(key)
    return found, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo-dir', default=REPO_DIR)
    args = ap.parse_args()
    fonts_dir = os.path.join(args.repo_dir, 'fonts')
    os.makedirs(fonts_dir, exist_ok=True)

    try:
        import fitz
    except ImportError:
        print('需要 PyMuPDF: pip install pymupdf')
        sys.exit(1)

    # 1) 仓库字体: Noto Serif SC (可变字体实例化两个字重, 或直接下载实例)
    vf = os.path.join(fonts_dir, 'NotoSerifSC-vf.ttf')
    reg = os.path.join(fonts_dir, 'NotoSerifSC-Regular.ttf')
    bold = os.path.join(fonts_dir, 'NotoSerifSC-Bold.ttf')
    if not (os.path.exists(reg) and os.path.exists(bold)):
        if not os.path.exists(vf):
            download(VF_URL, vf)
        try:
            from fontTools.ttLib import TTFont
            from fontTools.varLib.instancer import instantiateVariableFont
        except ImportError:
            print('需要 fontTools: pip install fonttools')
            sys.exit(1)
        for w, out in ((400, reg), (700, bold)):
            f = TTFont(vf)
            instantiateVariableFont(f, {'wght': w}, inplace=True)
            f.save(out)
            print(f'  实例化 wght={w} -> {os.path.basename(out)}')

    # 2) CMU Serif Italic (Computer Modern 数学斜体同形)
    cmu = os.path.join(fonts_dir, 'CMU-Italic.otf')
    if not os.path.exists(cmu):
        download(CMU_URL, cmu)

    # 3) 系统字体定位 (Times 系 / 符号字体)
    found, missing = locate_system_fonts()
    if missing:
        print(f'  [提示] 系统字体缺失: {missing}')
        print('         中文排版不受影响; 西文/数学符号会走字形回退链, 观感可能退化。')
        print('         Linux 可安装: sudo apt install fonts-liberation fonts-dejavu-core')

    # 4) 字形验证
    checks = [
        ('NSR', reg, '跟'), ('NSB', bold, '鲁'),
        ('CMI', cmu, 'f'),
    ]
    ok = True
    for key, path, ch in checks:
        try:
            f = fitz.Font(fontfile=path)
            has = f.has_glyph(ord(ch))
            print(f'  {key}: {f.name}  {ch!r}={"✓" if has else "✗"}')
            ok = ok and bool(has)
        except Exception as e:
            print(f'  {key}: 加载失败 {e}')
            ok = False
    if 'SYM' in found:
        f = fitz.Font(fontfile=found['SYM'])
        for ch in ('ℝ', '∈', '⊙'):
            print(f'  SYM({os.path.basename(found["SYM"])}): {ch!r}='
                  f'{"✓" if f.has_glyph(ord(ch)) else "✗"}')

    # 5) 字体测试卡 (必须肉眼查看! MuPDF 对某些 CFF 字体会画出错字形, 机器检查不出来)
    doc = fitz.open()
    page = doc.new_page(width=560, height=340)
    samples = [
        ('NSR', reg, '视觉语言跟踪：目标-上下文对齐实现鲁棒跟踪 0123456789'),
        ('NSB', bold, '粗体：为了实现鲁棒的跟踪，特别是在跟踪场景中 0123'),
        ('CMI', cmu, 'f h t z V Norm FFN LaSOT (math italic)'),
    ]
    y = 40
    for key, path, text in samples:
        try:
            page.insert_font(fontname=key, fontfile=path)
            page.insert_text((30, y), f'{key}: {text}', fontname=key, fontsize=12)
        except Exception as e:
            print(f'  测试卡 {key} 失败: {e}')
        y += 34
    if 'SYM' in found:
        page.insert_font(fontname='SYM', fontfile=found['SYM'])
        page.insert_text((30, y), 'SYM: ℝ ℕ ∈ ⊙ ⊕ ×', fontname='SYM', fontsize=12)
        y += 34
    else:
        page.insert_text((30, y), 'SYM: 缺失, 数学符号将回退到其他字体', fontsize=12)
        y += 34
    if 'TMR' in found:
        page.insert_font(fontname='TMR', fontfile=found['TMR'])
        page.insert_text((30, y),
                         f'TMR({os.path.basename(found["TMR"])}): The quick brown fox 0123456789 [9]',
                         fontname='TMR', fontsize=12)
    card = os.path.join(fonts_dir, 'fonts_test.pdf')
    doc.save(card)
    print(f'  字体测试卡: {card}')
    print('>>> 必须打开 fonts_test.pdf 用眼睛确认每个字形正确 (无错字/豆腐块/乱码) <<<')
    print('全部就绪' if ok else '字体存在问题, 见上方输出')


if __name__ == '__main__':
    main()
