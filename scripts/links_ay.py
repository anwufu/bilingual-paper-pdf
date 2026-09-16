# -*- coding: utf-8 -*-
"""links_ay.py — 给双语版右半（中文）里的作者-年份引用加跳转链接

左半的原版链接由 build_solo.py 的 linkify 重建；右半的中文引用是新画的文字，
原链接不存在，需按 "姓氏 + 年份" 在参考文献条目里定位再建 LINK_GOTO。
仅适用于**作者-年份引用风格**的论文；数字引用风格 [1] 的跳转 build_solo
的 linkify 已处理，无需本脚本。

支持三种条目风格（按悬挂缩进分组，条目 = 栏左界的首行 + 缩进续行）：
  姓在前:   Blei, D. M., Ng, A. Y., ... In ICML, 2020.        -> Blei
  名在前:   Yuki Markus Asano, Christian Rupprecht, ... 2021. -> Asano
  缩写在前: A. Radford, J. Wu, ... 2021.                      -> Radford
年份取条目内最后一个 (19|20)xx[a-z]?（天然跳过 arXiv 编号里的数字）。

用法:
    python scripts/links_ay.py <双语版.pdf>          # 就地改写
    python scripts/links_ay.py <双语版.pdf> --dry    # 只统计不写回
"""
import argparse
import os
import re

import fitz

NAME = r"[A-Za-z\u00c0-\u024f\u0100-\u017f\u02bc'\-]"
YEAR_RX = re.compile(r"(?:19|20)\d{2}[a-z]?")
# 中文绘制文本的字体前缀 (build_solo 画出的一侧); 其余字体是左半克隆的幽灵文本
DRAWN_FONTS = ('NotoSerifSC', 'CMUSerif', 'SegoeUI', 'TimesNewRoman')
# 中文引用: 姓氏(保留拉丁原文) + [等/et al./& X/and X/和 X] + [,，] + [（(] + 年份
CITE_RX = re.compile(
    r"([A-Z][A-Za-z\u00c0-\u024f\u0100-\u017f\u02bc'\-]{1,})"
    r"(?:\s*(?:等|et\s+al\.?|和)|\s*(?:&|和|and)\s+[A-Z][A-Za-z\u00c0-\u024f\u0100-\u017f\u02bc'\-]+)?"
    r"\s*[，,]?\s*[（(]?\s*((?:19|20)\d{2}[a-b]?)")


def surname_of(text):
    """从条目首段提取姓氏: 兼容 姓在前/名在前/缩写在前 三种风格"""
    seg = re.split(r"[，,]", text)[0]
    toks = seg.split()
    if not toks:
        return None
    if re.fullmatch(r"[A-Z]\.", toks[0]):          # 缩写在前: A. Radford
        return toks[1].strip(".,") if len(toks) > 1 else None
    if len(toks) >= 2:                             # 名在前: Yuki Markus Asano
        return toks[-1].strip(".,")
    return toks[0].strip(".,")                     # 姓在前: Blei


def build_ref_index(doc, W2):
    """右半的参考文献条目索引: (姓氏, 年份) -> (页, 条目首行坐标)"""
    ref_index = {}
    for pj in range(len(doc)):
        pg = doc[pj]
        lines = []
        for blk in pg.get_text('dict')['blocks']:
            if blk.get('type'):
                continue
            for l in blk['lines']:
                r = l['bbox']
                if r[0] < W2 or r[1] < 55:          # 只看右半, 跳过页眉
                    continue
                t = ''.join(x['text'] for x in l['spans']).strip()
                if t:
                    lines.append((r[0] - W2, t, fitz.Point(r[0], r[1])))
        if not lines:
            continue
        margins = {}
        for x, t, pt in lines:
            k = 0 if x < W2 / 2 else 1
            margins[k] = min(margins.get(k, 1e9), x)
        entries, cur = [], None
        for x, t, pt in lines:
            k = 0 if x < W2 / 2 else 1
            if x <= margins[k] + 3:                 # 栏左界 -> 新条目
                if cur:
                    entries.append(cur)
                cur = [pt, t]
            elif cur:
                cur[1] += ' ' + t
        if cur:
            entries.append(cur)
        for pt, text in entries:
            if len(text) > 900:                     # 过长的不是单个条目
                continue
            ys = YEAR_RX.findall(text)
            if not ys:
                continue
            ym = None
            for m in YEAR_RX.finditer(text):
                ym = m.group(0)
            sn = surname_of(text)
            if sn:
                ref_index.setdefault((sn, ym), (pj, pt))
    return ref_index


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf', help='build_solo 产出的双语对照 PDF')
    ap.add_argument('--dry', action='store_true', help='只统计, 不写回')
    args = ap.parse_args()

    doc = fitz.open(args.pdf)
    W2 = doc[0].rect.width / 2          # 单页宽度 (整幅是左右两页拼接)

    ref_index = build_ref_index(doc, W2)

    # 右半中文里的作者-年份引用 -> 建链接。
    # 引用的姓氏/等/年份分属不同字体 span, 必须在**整行**拼接后的文本上匹配,
    # 再把命中区间映射回字符 bbox。
    n = 0
    samples = []
    for pj in range(len(doc)):
        pg = doc[pj]
        hits = []
        for blk in pg.get_text('rawdict')['blocks']:
            if blk.get('type'):
                continue
            for l in blk['lines']:
                # 只扫中文绘制层 (我方字体); 被抹白的英文幽灵层同坐标也含引用,
                # 但链接必须落在中文实际绘制处
                chars = [c for sp in l['spans']
                         if sp['font'].startswith(DRAWN_FONTS)
                         for c in sp.get('chars', []) if c['bbox'][0] >= W2 - 1]
                if len(chars) < 6:
                    continue
                txt = ''.join(c['c'] for c in chars)
                if not any(ch.isascii() and ch.isalpha() for ch in txt):
                    continue
                for m in CITE_RX.finditer(txt):
                    tgt = ref_index.get((m.group(1), m.group(2)))
                    if not tgt:
                        continue
                    bs = [chars[i]['bbox'] for i in range(m.start(), m.end())
                          if i < len(chars)]
                    if not bs:
                        continue
                    hits.append((fitz.Rect(min(b[0] for b in bs), min(b[1] for b in bs),
                                           max(b[2] for b in bs), max(b[3] for b in bs)),
                                 tgt, m.group(1), m.group(2)))
        for rect, tgt, sn, yr in hits:
            if not args.dry:
                pg.insert_link({'kind': fitz.LINK_GOTO, 'from': rect,
                                'page': tgt[0], 'to': tgt[1]})
            if len(samples) < 6:
                samples.append(f'{sn} {yr} -> p{tgt[0]+1}')
            n += 1

    print(f'参考文献条目索引 {len(ref_index)} 条, 右半作者-年份引用 {n} 个')
    for s in samples:
        print('   ', s)
    if args.dry:
        return
    tmp = args.pdf + '.tmp'
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    os.replace(tmp, args.pdf)
    print(f'-> {args.pdf} 已更新')


if __name__ == '__main__':
    main()
