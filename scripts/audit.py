# -*- coding: utf-8 -*-
"""audit.py — 两遍审核的机器辅助: 像素差分定位差异区域 + 生成对照条

对每个差异聚类输出 [我的输出 / 参考版] 上下对照条图, 供视觉复核。
审核协议 (不得跳过):
  第一遍: 逐页全检 (每页 render 后与参考版同页对照目检)
  第二遍: 跑本脚本, 对所有差异聚类逐一放大复核, 每个都要定性

用法:
  python audit.py --mine <我的输出.pdf> --ref <参考版.pdf> --outdir <目录> [--pages 1-8]
无参考版时 (模式B自洽性校验):
  python audit.py --mine <我的输出.pdf> --outdir <目录>   # 只渲染 + 基础检查
"""
import argparse
import os

import fitz
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def render(pdf, outdir, tag, pages):
    d = fitz.open(pdf)
    paths = {}
    for pno1 in pages:
        if pno1 >= len(d):
            continue
        p = d[pno1]
        path = os.path.join(outdir, f'{tag}_p{pno1 + 1}.png')
        p.get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).save(path)
        paths[pno1 + 1] = path
    return paths


def hot_cells(pa, pb):
    a = Image.open(pa).convert('L')
    b = Image.open(pb).convert('L')
    if a.size != b.size:
        b = b.resize(a.size)
    aa = np.asarray(a, dtype=np.int16)
    bb = np.asarray(b, dtype=np.int16)
    d = np.abs(aa - bb)
    d = np.asarray(Image.fromarray(d.astype(np.uint8)).filter(ImageFilter.BoxBlur(2)))
    mask = d > 70
    H, W = mask.shape
    cells = []
    for gy in range(0, H, 28):
        for gx in range(0, W, 28):
            if mask[gy:gy + 28, gx:gx + 28].mean() > 0.10:
                cells.append((gx, gy))
    return cells, round(float(mask.mean()) * 100, 2), mask


def cluster(cells):
    groups = []
    for c in sorted(cells):
        placed = False
        for g in groups:
            if any(abs(c[0] - x) < 100 and abs(c[1] - y) < 60 for x, y in g):
                g.append(c)
                placed = True
                break
        if not placed:
            groups.append([c])
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mine', required=True)
    ap.add_argument('--ref', default='')
    ap.add_argument('--outdir', required=True)
    ap.add_argument('--pages', default='')
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    md = fitz.open(args.mine)
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
        pages = list(range(len(md)))

    mine = render(args.mine, args.outdir, 'mine', pages)
    ref = render(args.ref, args.outdir, 'ref', pages) if args.ref else {}

    summary = []
    for pno in sorted(mine):
        if not ref:
            summary.append(f'p{pno}: rendered {mine[pno]}')
            continue
        cells, pct, _ = hot_cells(mine[pno], ref[pno])
        groups = cluster(cells)
        summary.append(f'p{pno}: diff={pct}%  clusters={len(groups)} (cells={len(cells)})')
        vis = Image.open(mine[pno]).convert('RGB')
        dr = ImageDraw.Draw(vis)
        for g in groups:
            xs = [c[0] for c in g]
            ys = [c[1] for c in g]
            dr.rectangle([min(xs), min(ys), max(xs) + 28, max(ys) + 28],
                         outline=(255, 0, 0), width=2)
        vis.save(os.path.join(args.outdir, f'diff_p{pno}.png'))
        # 对照条: 每个聚类 [mine 上下 ref]
        A = Image.open(mine[pno])
        B = Image.open(ref[pno])
        strips = []
        for g in groups[:8]:
            cx = sum(c[0] for c in g) // len(g)
            cy = sum(c[1] for c in g) // len(g)
            x0, x1 = max(0, cx - 170), min(A.size[0], cx + 170)
            y0, y1 = max(0, cy - 26), min(A.size[1], cy + 58)
            ca = A.crop((x0, y0, x1, y1))
            cb = B.crop((x0, y0, x1, y1))
            w, h = ca.size
            st = Image.new('RGB', (w, h * 2 + 12), (255, 200, 200))
            st.paste(ca, (0, 0))
            st.paste(cb, (0, h + 12))
            strips.append(st)
        if strips:
            W = max(s.size[0] for s in strips)
            H = sum(s.size[1] + 10 for s in strips)
            sheet = Image.new('RGB', (W, H), (255, 255, 255))
            y = 0
            for s in strips:
                sheet.paste(s, (0, y))
                y += s.size[1] + 10
            sheet.save(os.path.join(args.outdir, f'zooms_p{pno}.png'))

    print('\n'.join(summary))
    print(f'输出目录: {args.outdir}')
    if ref:
        print('审核协议: 1) 逐页看 mine_pN.png vs ref_pN.png 全页对照')
        print('          2) 看 diff_pN.png 红框区域, 逐个打开 zooms_pN.png 定性每个差异')
        print('          3) 内容级差异必须为0; 渲染级亚像素漂移可接受但要逐个确认')
    else:
        print('自洽校验: 逐页检查 无豆腐块/无叠印/无英文残留/中文完整')


if __name__ == '__main__':
    main()
