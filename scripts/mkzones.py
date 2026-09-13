# -*- coding: utf-8 -*-
"""mkzones.py — 生成补充保留区 (extra_zones) for 模式B

自动检测 (detect_zones) 只认"聚得成区域的矢量绘图/大光栅图", 下面三类会漏:
  1. 只有几条横线的书板表格 (booktabs): 每条线是独立 cluster, 面积太小
  2. 拼图式插图: 由很多小位图拼成, 没有单张大图
  3. 曲线型结果图 (多面板散点/曲线): 稀疏矢量聚不成区域
漏掉的后果很严重: 表格单元格/图内标签会被当成正文翻译、原文被抹白。

本脚本用 **图注/表注锚定法** 补齐:
  表注在表**上方** -> 区域 = [表注末行底, 下一段正文顶]
  图注在图**下方** -> 区域 = [上一段正文底, 图注首行顶]
  x 外延 = 带内"实体绘图(高度>3) + 光栅图"的外延; 表格另取"带内横线"的外延;
           再把带内"非正文文本行"并入 (坐标轴刻度/轴标题是文字, 不是绘图)
最后逐区**减去正文字号行与图注行**的 y 带, 保证绝不吞正文/图注。

用法:
  python mkzones.py --src 原文.pdf --out zones.json [--body-size 9.4]
                    [--cols 66.9,282.3,305.0,528.4] [--ref-pages 20,21,22]
  # 区域人工核对: 脚本会打出每页区域与其中文本行数; 建议再打框渲染一张对照图目检
下一步:
  python solo_worksheet.py --src 原文.pdf --out worksheet.json --zones zones.json \\
      --math-exclude <正文字体族>      # 见 pitfalls 39
  content.json 里加 "extra_zones": <zones.json 的内容>
"""
import argparse
import json
import re
import sys

import fitz

CAP = re.compile(r'^(Fig\.|Table)\s*(\d+)')
BODY_SZ = 9.4


def build(src_path, body_sz, cols, ref_pages):
    d = fitz.open(src_path)
    W0 = d[0].rect.width
    H0 = d[0].rect.height
    sys.path.insert(0, __file__.rsplit('/', 1)[0].rsplit('\\', 1)[0] + '/scripts')
    from solo_worksheet import detect_zones, get_lines, is_folio  # noqa

    def cidx(x):
        return 0 if x < W0 / 2 else 1

    zones = []
    for i, p in enumerate(d):
        W, H = p.rect.width, p.rect.height
        lines = [ln for ln in get_lines(p)
                 if ln['x1'] >= 0.075 * W and not is_folio(ln, W, H)]
        gfx = [list(inf['bbox']) for inf in p.get_image_info()
               if (inf['bbox'][2] - inf['bbox'][0]) > 6 and (inf['bbox'][3] - inf['bbox'][1]) > 6]
        solid = [list(dr['rect']) for dr in p.get_drawings() if dr['rect'].height > 3]
        rules = [list(dr['rect']) for dr in p.get_drawings()
                 if dr['rect'].height <= 1.5 and dr['rect'].width >= 60]
        allg = solid + gfx + rules

        def cap_extent(ln):
            """图注/表注可能多行: 吸收同 x0、行距<=5.5pt 的续行"""
            cur = ln
            cc = cidx((ln['x0'] + ln['x1']) / 2)
            for k in sorted([x for x in lines if x['y0'] > cur['y1'] - 1],
                            key=lambda x: x['y0']):
                if cidx((k['x0'] + k['x1']) / 2) != cc:
                    continue
                if (k['size'] > body_sz or abs(k['x0'] - ln['x0']) > 3
                        or k['y0'] - cur['y1'] > 5.5):
                    break
                cur = k
            return cur

        # 图注行集合 (含续行): 这些行要翻译, 必须挡在区域之外
        capset = set()
        for ln in lines:
            if CAP.match(ln['text'].strip()) and ln['size'] <= body_sz:
                e = cap_extent(ln)
                for k in lines:
                    if (k['y0'] >= ln['y0'] - 1 and k['y1'] <= e['y1'] + 1
                            and abs(k['x0'] - ln['x0']) < 3):
                        capset.add(id(k))

        cand = []
        for ln in lines:
            m = CAP.match(ln['text'].strip())
            if not m or ln['size'] > body_sz:
                # 字号判据: 正文里以 "Table 2 and in ..." 开头的句子不是表注
                continue
            c = cidx((ln['x0'] + ln['x1']) / 2)
            cx0, cx1 = cols[2 * c], cols[2 * c + 1]

            def isref(k):
                return (k['size'] >= body_sz
                        or (CAP.match(k['text'].strip()) and k['size'] <= body_sz))

            if m.group(1) == 'Fig.':
                above = [k for k in lines if k is not ln and k['y1'] <= ln['y0'] + 1
                         and cidx((k['x0'] + k['x1']) / 2) == c]
                top = max([k['y1'] for k in above if isref(k)] + [0.078 * H])
                bot = ln['y0'] - 2
                inb = [g for g in solid + gfx if g[3] > top + 2 and g[1] < bot - 2]
            else:
                end = cap_extent(ln)
                below = [k for k in lines if k is not ln and k['y0'] >= end['y1'] - 1
                         and cidx((k['x0'] + k['x1']) / 2) == c]
                bot = min([k['y0'] for k in below if isref(k)] + [0.92 * H]) - 2
                top = end['y1'] + 1
                inb = [g for g in rules if g[3] > top + 2 and g[1] < bot - 2]
                if not inb:
                    inb = [g for g in solid + gfx if g[3] > top + 2 and g[1] < bot - 2
                           and (g[2] - g[0]) <= (cx1 - cx0) + 90]
            if bot - top < 10:
                continue
            if inb:
                x0 = max(0.09 * W, min(g[0] for g in inb) - 2)
                x1 = min(W - 0.09 * W, max(g[2] for g in inb) + 2)
            else:
                x0, x1 = cx0, cx1
            tin = [k for k in lines if k['size'] <= body_sz
                   and top - 2 <= (k['y0'] + k['y1']) / 2 <= bot + 2
                   and cidx((k['x0'] + k['x1']) / 2) == c]
            if tin:
                x0 = max(0.09 * W, min(x0, min(k['x0'] for k in tin) - 2))
                x1 = min(W - 0.09 * W, max(x1, max(k['x1'] for k in tin) + 2))
            cand.append([x0, top, x1, bot])

        if not cand:                      # 无图注页兜底
            cand += [list(z) for z in detect_zones(p, W)]
        cand = [z for z in cand if any(g[3] > z[1] + 2 and g[1] < z[3] - 2
                                       and g[2] > z[0] + 2 and g[0] < z[2] - 2 for g in allg)]

        # 同栏纵向相邻 (<6pt) 才合并 —— 绝不跨栏
        cand.sort(key=lambda z: (cidx((z[0] + z[2]) / 2), z[1]))
        zs = []
        for z in cand:
            hit = None
            for o in zs:
                if (cidx((o[0] + o[2]) / 2) == cidx((z[0] + z[2]) / 2)
                        and z[1] - o[3] < 6 and z[1] > o[3] - 6):
                    hit = o
                    break
            if hit is None:
                zs.append(list(z))
            else:
                hit[0] = min(hit[0], z[0]); hit[1] = min(hit[1], z[1])
                hit[2] = max(hit[2], z[2]); hit[3] = max(hit[3], z[3])

        # 跨栏区间按中缝切两片 (裁剪才不会用左栏正文误删右栏表格)
        pieces = []
        for z in zs:
            if z[0] < W / 2 - 4 and z[2] > W / 2 + 4:
                pieces.append([z[0], z[1], min(z[2], W / 2 - 1), z[3]])
                pieces.append([max(z[0], W / 2 + 1), z[1], z[2], z[3]])
            else:
                pieces.append(list(z))

        final = []
        for z in pieces:
            col_lines = [ln for ln in lines
                         if z[0] - 2 <= (ln['x0'] + ln['x1']) / 2 <= z[2] + 2]
            bad = sorted([ln for ln in col_lines
                          if z[1] - 2 <= (ln['y0'] + ln['y1']) / 2 <= z[3] + 2
                          and (ln['size'] >= body_sz or id(ln) in capset)],
                         key=lambda l: l['y0'])
            bands = [[z[1], z[3]]]
            for b in bad:
                nxt = []
                for a in bands:
                    if b['y1'] < a[0] or b['y0'] > a[1]:
                        nxt.append(a)
                        continue
                    if b['y0'] - a[0] >= 10:
                        nxt.append([a[0], b['y0'] - 2])
                    if a[1] - b['y1'] >= 10:
                        nxt.append([b['y1'] + 2, a[1]])
                bands = nxt
            for a in bands:
                pc = [z[0], a[0], z[2], a[1]]
                if any(g[3] > pc[1] + 2 and g[1] < pc[3] - 2
                       and g[2] > pc[0] + 2 and g[0] < pc[2] - 2 for g in allg):
                    final.append(pc)

        info = []
        for z in sorted(final, key=lambda z: (z[1], z[0])):
            inside = [ln for ln in lines
                      if z[0] - 2 <= (ln['x0'] + ln['x1']) / 2 <= z[2] + 2
                      and z[1] - 2 <= (ln['y0'] + ln['y1']) / 2 <= z[3] + 2]
            zones.append({'page': i + 1, 'x0': round(z[0] - 1, 1), 'y0': round(z[1] - 1, 1),
                          'x1': round(z[2] + 1, 1), 'y1': round(z[3] + 1, 1)})
            bad = [ln for ln in inside if ln['size'] >= body_sz]
            info.append(f"[{z[0]:.0f},{z[1]:.0f},{z[2]:.0f},{z[3]:.0f}]n={len(inside)}"
                        + (f' !!正文={bad[0]["text"][:26]!r}' if bad else ''))
        print(f'p{i+1}: ' + ' | '.join(info))
    return zones


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', default='zones.json')
    ap.add_argument('--body-size', type=float, default=BODY_SZ)
    ap.add_argument('--cols', default='',
                    help='栏 x 范围: 左栏x0,左栏x1,右栏x0,右栏x1 (缺省按页宽估算)')
    ap.add_argument('--ref-pages', default='',
                    help='参考文献页 (整页保留, 逗号分隔)')
    args = ap.parse_args()
    d = fitz.open(args.src)
    W, H = d[0].rect.width, d[0].rect.height
    if args.cols:
        cols = [float(x) for x in args.cols.split(',')]
    else:
        cols = [0.11 * W, 0.475 * W, 0.51 * W, 0.89 * W]
    zones = build(args.src, args.body_size, cols, args.ref_pages)
    if args.ref_pages:      # 参考文献整页保留 (英文原样)
        for pno in (int(x) for x in args.ref_pages.split(',')):
            zones = [z for z in zones if z['page'] != pno]
            zones.append({'page': pno, 'x0': 0.1 * W, 'y0': 0.07 * H,
                          'x1': W - 0.1 * W, 'y1': 0.93 * H})
    json.dump(zones, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'-> {args.out}  {len(zones)} 个保留区')
    print('注意: 逐页目检区域是否正确 (建议打框渲染一张对照图); 区域不得吞正文或图注')


if __name__ == '__main__':
    main()
