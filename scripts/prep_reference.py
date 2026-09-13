# -*- coding: utf-8 -*-
"""prep_reference.py — 模式A(有参考版): 参考版 → 排版计划 plan.json

差分分类 (整个方法的枢纽):
  对英文原页的每个文字行, 到参考版右半的同一坐标找答案:
  - 同位置有相同文字   -> keep   (克隆保留: 图/公式/表格数字/印章)
  - 同位置没有文字     -> white  (参考版抹掉了 -> 中文要住进来的空间)
  - 同位置有不同文字   -> white  (参考版做了替换 -> 内容由参考版自己排的中文行承担)
参考版自己排的中文行 (CJK 字符占比高) 全部按原坐标输出, 构建时逐行精排。

用法: python prep_reference.py --src <英文原文.pdf> --ref <双语参考版.pdf> --out plan.json
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

import fitz

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from solo_worksheet import detect_zones  # noqa: E402  图/表区自动检测

CJK = re.compile(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]')
FIXES = {'\x01': ' ', '\x03': '/', '\x02': ' ', '\x04': ' '}


def fix_text(t):
    for k, v in FIXES.items():
        t = t.replace(k, v)
    return t


def cjk_ratio(t):
    if not t:
        return 0.0
    return len(CJK.findall(t)) / len(t)


def mk_line(l, dx=0.0):
    spans = []
    for s in l['spans']:
        t = fix_text(s['text'])
        if not t:
            continue
        spans.append({'t': t, 'f': s['font'], 'sz': round(s['size'], 2),
                      'c': s['color'],
                      'ox': round(s['origin'][0] - dx, 2), 'oy': round(s['origin'][1], 2),
                      'x0': round(s['bbox'][0] - dx, 2), 'x1': round(s['bbox'][2] - dx, 2),
                      'y0': round(s['bbox'][1], 2), 'y1': round(s['bbox'][3], 2)})
    b = l['bbox']
    text = ''.join(s['t'] for s in spans)
    return {'x0': round(b[0] - dx, 2), 'y0': round(b[1], 2),
            'x1': round(b[2] - dx, 2), 'y1': round(b[3], 2),
            'spans': spans, 'text': text,
            'size': round(max((s['sz'] for s in spans), default=10.0), 2)}


def get_lines(page, dx=0.0, drop_slivers=True):
    out = []
    for b in page.get_text('dict')['blocks']:
        if b.get('type') != 0:
            continue
        for l in b['lines']:
            ln = mk_line(l, dx)
            if drop_slivers:
                ln['spans'] = [s for s in ln['spans']
                               if (s['y1'] - s['y0']) >= 0.5 * s['sz'] or not s['t'].strip()]
            if ln['text'].strip():
                out.append(ln)
    return out


def xov(a, b):
    ov = min(a['x1'], b['x1']) - max(a['x0'], b['x0'])
    return ov / max(1e-3, min(a['x1'] - a['x0'], b['x1'] - b['x0']))


DASH_VARIANTS = {'\u2010': '-', '\u2011': '-', '\u2012': '-',
                 '\u2013': '-', '\u2014': '-', '\u2212': '-',
                 '\uff0d': '-', '\u2043': '-'}


def norm(t):
    """同文本比对前的折叠: 空白剥离 + 连字符变体统一 (参考版克隆常用 U+2011)"""
    t = ''.join(DASH_VARIANTS.get(c, c) for c in t)
    return re.sub(r'\s+', '', t)


def same_text(a, b):
    """同文本: 相等 / 双向前缀 / 包含 (参考版克隆常把一行拆成不同分段的短线)"""
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    if len(short) >= 6 and long_.startswith(short):
        return True
    return len(short) >= 3 and short in long_


CJK_FONT_HINTS = ('Han', 'Song', 'Kai', 'Hei', 'Ming', 'CJK', 'WenKai',
                  'YaHei', 'SimSun', 'Noto', 'Source', 'CN', 'SC')


def is_typed(ln):
    """参考版自己排的行: CJK 字符占比高, 或任何 span 用了 CJK 字体家族
    (参考版重排的纯拉丁行——如表格外引文号——常以中文字体嵌入, 靠字体提示抓出)"""
    if cjk_ratio(ln['text']) > 0.25:
        return True
    return any(any(h in s['f'] for h in CJK_FONT_HINTS)
               for s in ln['spans'] if s['t'].strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True, help='英文原文 PDF')
    ap.add_argument('--ref', required=True, help='双语参考版 PDF (跨页, 右半为参考译文)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--pages', default='', help='页范围如 1-8 或 1,3,5 (默认全部)')
    args = ap.parse_args()

    SRC = fitz.open(args.src)
    REF = fitz.open(args.ref)
    if args.pages:
        parts = []
        for p in args.pages.split(','):
            if '-' in p:
                a, b = p.split('-')
                parts += list(range(int(a) - 1, int(b)))
            else:
                parts.append(int(p) - 1)
        pages = parts
    else:
        pages = list(range(len(REF)))

    plan = {'src': args.src, 'half': None, 'pages': []}
    rep = []
    for pno1 in pages:
        pno = pno1 + 1
        half = REF[pno1].rect.width / 2.0
        plan['half'] = half
        src_page = SRC[pno - 1]
        en_lines = [ln for ln in get_lines(src_page) if ln['x1'] >= 0.075 * half]
        ref_lines = get_lines(REF[pno1], dx=half)
        ref_typed = [ln for ln in ref_lines if is_typed(ln)]
        zones = detect_zones(src_page, half)

        def in_zone(ln):
            cx, cy = (ln['x0'] + ln['x1']) / 2, (ln['y0'] + ln['y1']) / 2
            return any(z[0] - 2 <= cx <= z[2] + 2 and z[1] - 2 <= cy <= z[3] + 2
                       for z in zones)

        whites, keeps, drawn_ids, anomalies = [], 0, set(), []
        for en in en_lines:
            if in_zone(en):
                # 图/表内: 配对到参考版 typed 行 -> 替换 (抹白EN, typed 行稍后绘制);
                # 配不上 -> 保留克隆 (数字/方法名/图内未译标签)
                best, bo = None, 0.0
                for r in ref_typed:
                    if not in_zone(r):
                        continue
                    if abs((r['y0'] + r['y1']) / 2 - (en['y0'] + en['y1']) / 2) > 3.6:
                        continue
                    ov = xov(en, r)
                    if ov > 0.2 and ov > bo:
                        best, bo = r, ov
                if best is not None:
                    whites.append([en['x0'], en['y0'], en['x1'], en['y1']])
                    drawn_ids.add(id(best))
                elif any(xov(en, r) > 0.2 and abs((r['y0'] + r['y1']) / 2 - (en['y0'] + en['y1']) / 2) < 3.6
                         for r in ref_lines):
                    keeps += 1
                else:
                    keeps += 1
                continue
            cands = [r for r in ref_lines
                     if abs((r['y0'] + r['y1']) / 2 - (en['y0'] + en['y1']) / 2) < 3.2
                     and xov(en, r) > 0.35]
            if not cands:
                whites.append([en['x0'], en['y0'], en['x1'], en['y1']])
            elif any(same_text(r['text'], en['text']) for r in cands):
                keeps += 1
            else:
                anomalies.append((en['text'][:30], cands[0]['text'][:30]))
                whites.append([en['x0'], en['y0'], en['x1'], en['y1']])

        # 绘制集合: 栏外全部 typed 行 + 图/表内被配对的 typed 行 (避免重排行与克隆双写)
        typed_draw = []
        for r in ref_typed:
            if in_zone(r) and id(r) not in drawn_ids:
                continue
            typed_draw.append({'x0': r['x0'], 'y0': r['y0'], 'x1': r['x1'], 'y1': r['y1'],
                               'size': r['size'], 'spans': r['spans']})
        plan['pages'].append({'pno': pno, 'whites': whites, 'lines': typed_draw})
        rep.append(f'p{pno}: en={len(en_lines)} white={len(whites)} keep={keeps} '
                   f'cnlines={len(typed_draw)} anomaly={len(anomalies)} zones={len(zones)}')
        for a in anomalies[:5]:
            rep.append(f'   ! {a[0]!r} <-> {a[1]!r}')

    json.dump(plan, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False)
    print('\n'.join(rep))
    print(f'plan saved -> {args.out}')
    print('检查: keep 数应集中在图表/公式区; anomaly 应为图注/正文重叠(正常), 不应有表格数字')


if __name__ == '__main__':
    main()
