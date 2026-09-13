# -*- coding: utf-8 -*-
"""links_ay.py — 给双语版右半（中文）里的作者-年份引用加跳转链接

左半的原版链接由 build_solo.py 的 linkify 重建；右半的中文引用是新画的文字，
原链接不存在，需按 "姓氏 + 年份" 在参考文献条目里定位再建 LINK_GOTO。
仅适用于**作者-年份引用风格**的论文（Springer sn-jnl 等）；数字引用风格
[1] 的跳转 build_solo 的 linkify 已处理，无需本脚本。

用法:
    python scripts/links_ay.py <双语版.pdf>          # 就地改写
    python scripts/links_ay.py <双语版.pdf> --dry    # 只统计不写回
"""
import argparse
import os
import re

import fitz

AY_RX = re.compile(r"([A-Z][A-Za-z\u00c0-\u024f\u0100-\u017f\u02bc'\-]{2,})"
                   r"(?:\s*等)?(?:\s*and\s+[A-Z][A-Za-z\-]+)?\s*\(?\s*(\d{4})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf', help='build_solo 产出的双语对照 PDF')
    ap.add_argument('--dry', action='store_true', help='只统计, 不写回')
    args = ap.parse_args()

    doc = fitz.open(args.pdf)
    W2 = doc[0].rect.width / 2          # 单页宽度 (整幅是左右两页拼接)

    # 1. 参考文献索引: 右半行首 "姓氏 (年份)" -> (页, 坐标)
    ref_index = {}
    for pj in range(len(doc)):
        pg = doc[pj]
        for blk in pg.get_text('dict')['blocks']:
            if blk.get('type'):
                continue
            for l in blk['lines']:
                r = l['bbox']
                if r[0] < W2:
                    continue
                t = ''.join(x['text'] for x in l['spans']).strip()
                m = re.match(r"([A-Z][A-Za-z\u00c0-\u024f\u0100-\u017f\u02bc'\-]{2,})", t)
                if not m:
                    continue
                ym = re.search(r'\((\d{4})[a-z]?\)', t)
                if not ym:
                    continue
                ref_index.setdefault((m.group(1), ym.group(1)), (pj, fitz.Point(r[0], r[1])))

    # 2. 右半中文里的作者-年份引用 -> 建链接
    n = 0
    for pj in range(len(doc)):
        pg = doc[pj]
        hits = []
        for blk in pg.get_text('rawdict')['blocks']:
            if blk.get('type'):
                continue
            for l in blk['lines']:
                for sp in l['spans']:
                    if sp['bbox'][0] < W2:
                        continue
                    txt = ''.join(c['c'] for c in sp['chars'])
                    for m in AY_RX.finditer(txt):
                        tgt = ref_index.get((m.group(1), m.group(2)))
                        if not tgt:
                            continue
                        bs = [sp['chars'][i]['bbox'] for i in range(m.start(), m.end())]
                        hits.append((fitz.Rect(min(b[0] for b in bs), min(b[1] for b in bs),
                                               max(b[2] for b in bs), max(b[3] for b in bs)),
                                     tgt))
        for rect, tgt in hits:
            if not args.dry:
                pg.insert_link({'kind': fitz.LINK_GOTO, 'from': rect,
                                'page': tgt[0], 'to': tgt[1]})
            n += 1

    print(f'参考文献条目索引 {len(ref_index)} 条, 右半作者-年份引用 {n} 个')
    if args.dry:
        return
    tmp = args.pdf + '.tmp'
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    os.replace(tmp, args.pdf)
    print(f'-> {args.pdf} 已更新')


if __name__ == '__main__':
    main()
