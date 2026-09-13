# -*- coding: utf-8 -*-
"""build_from_plan.py — 模式A(有参考版): plan.json → 双语对照 PDF

右页 = 英文原页整页克隆 + 抹白文字区 + 中文逐行精排:
  - 每行按参考版自己的 span 原点绘制 (行首位置分毫不差)
  - 行内两端对齐: 我的字体排出的自然宽度 vs 参考版行宽, 差值均摊到字符步进
  - 逐字符字形回退: 缺字形就地把该字符路由到有它的字体
  - MSBM 字体的 'R' 实为黑板体 ℝ (PDF 映射表的谎言), 特判转回

用法: python build_from_plan.py --src <英文原文.pdf> --plan plan.json --out 双语版.pdf
"""
import argparse
import json
import os

import fitz

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS_DIR = os.path.join(SKILL_DIR, '_fonts')


def resolve_fonts():
    win = os.environ.get('WINDIR', r'C:\Windows') + r'\Fonts'
    spec = {
        'NSR': [os.path.join(FONTS_DIR, 'NotoSerifSC-Regular.ttf')],
        'NSB': [os.path.join(FONTS_DIR, 'NotoSerifSC-Bold.ttf')],
        'CMI': [os.path.join(FONTS_DIR, 'CMU-Italic.otf')],
        'SYM': [os.path.join(win, 'seguisym.ttf'),
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'],
        'TMR': [os.path.join(win, 'times.ttf'),
                '/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf'],
        'TMB': [os.path.join(win, 'timesbd.ttf'),
                '/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf'],
        'TMI': [os.path.join(win, 'timesi.ttf'),
                '/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf'],
        'TMBI': [os.path.join(win, 'timesbi.ttf'),
                 '/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf'],
    }
    fonts, files, missing = {}, {}, []
    for k, cands in spec.items():
        for p in cands:
            if os.path.exists(p):
                try:
                    fonts[k] = fitz.Font(fontfile=p)
                    files[k] = p
                    break
                except Exception:
                    continue
        else:
            missing.append(k)
    if missing:
        raise SystemExit(f'字体缺失: {missing} — 先运行 setup_fonts.py (见 references/pitfalls.md)')
    return fonts, files


FF, FFILE = resolve_fonts()


def map_font(fname):
    """参考版字体名 -> 我的字体键"""
    if fname.startswith('CMMI'):
        return 'CMI'
    if fname.startswith(('MSBM', 'MSAM')):
        return 'SYM'
    if 'Italic' in fname and 'Bold' in fname:
        return 'TMBI'
    if 'Italic' in fname:
        return 'TMI'
    if 'Bold' in fname:
        return 'NSB' if ('Han' in fname or 'Sans' in fname or 'LXGW' in fname
                         or 'CN' in fname or 'SC' in fname) else 'TMB'
    if ('Han' in fname or 'Sans' in fname or 'LXGW' in fname or 'CN' in fname
            or 'SC' in fname or 'Song' in fname or 'Kai' in fname or 'Hei' in fname):
        return 'NSR'
    return 'TMR'


def col_tuple(c):
    return ((c >> 16 & 255) / 255, (c >> 8 & 255) / 255, (c & 255) / 255)


TOFU_FALLBACK = ('SYM', 'CMI', 'TMR')


def draw_spans(page, spans, inserted, half=612.0):
    for s in spans:
        t = s['t']
        if not t.strip():
            continue
        if s['f'].startswith('MSBM'):
            t = t.replace('R', '\u211d')   # MSBM 的 'R' 实为黑板体 ℝ
        fk = map_font(s['f'])
        color = col_tuple(s['c'])
        ox, oy = half + s['ox'], s['oy']
        sz = s['sz']
        runs = []
        cur_fk, buf = fk, ''
        for ch in t:
            k = fk
            if ch.strip() and not FF[fk].has_glyph(ord(ch)):
                k = next((c for c in TOFU_FALLBACK
                          if c in FF and FF[c].has_glyph(ord(ch))), fk)
            if k == cur_fk:
                buf += ch
            else:
                if buf:
                    runs.append((cur_fk, buf))
                cur_fk, buf = k, ch
        if buf:
            runs.append((cur_fk, buf))
        natural = sum(FF[k].text_length(tx, sz) for k, tx in runs)
        target = s['x1'] - s['x0']
        n = len(t)
        if n > 1 and abs(target - natural) > 0.06:
            extra = max(-0.22, min(2.5, (target - natural) / (n - 1)))
        else:
            extra = 0.0
        cur = ox
        for k, tx in runs:
            if k not in inserted:
                page.insert_font(fontname=k, fontfile=FFILE[k])
                inserted.add(k)
            if abs(extra) < 0.045:
                page.insert_text((cur, oy), tx, fontname=k, fontsize=sz, color=color)
                cur += FF[k].text_length(tx, sz)
            else:
                for ch in tx:
                    page.insert_text((cur, oy), ch, fontname=k, fontsize=sz, color=color)
                    cur += FF[k].text_length(ch, sz) + extra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--plan', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--half', type=float, default=None,
                    help='右半页宽 (默认取 plan 里的值或 612)')
    args = ap.parse_args()

    SRC = fitz.open(args.src)
    plan = json.load(open(args.plan, encoding='utf-8'))
    half = args.half or plan.get('half') or 612.0

    out = fitz.open()
    for pg in plan['pages']:
        pno = pg['pno']
        page = out.new_page(width=half * 2, height=SRC[pno - 1].rect.height)
        page.show_pdf_page(fitz.Rect(0, 0, half, page.rect.height), SRC, pno - 1)
        page.show_pdf_page(fitz.Rect(half, 0, half * 2, page.rect.height), SRC, pno - 1)
        inserted = set()
        for w in pg['whites']:
            page.draw_rect(fitz.Rect(half + w[0] - 1.0, w[1] - 0.7,
                                     half + w[2] + 1.0, w[3] + 0.7),
                           color=None, fill=(1, 1, 1))
        for ln in pg['lines']:
            draw_spans(page, ln['spans'], inserted, half)
        print(f'p{pno}: white={len(pg["whites"])} cnlines={len(pg["lines"])}')
    out.save(args.out, garbage=3, deflate=True)
    print(f'saved {args.out}, {len(out.tobytes()) / 1e6:.1f} MB')
    print('>>> 下一步必须跑 audit.py 两遍审核, 未过审不得交付 <<<')


if __name__ == '__main__':
    main()
