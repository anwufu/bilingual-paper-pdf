# -*- coding: utf-8 -*-
"""solo_worksheet.py — 模式B(无参考版) 第一步: 英文原文 → 翻译工作表

从英文原文提取需要翻译的段落槽位 (自动识别保留区):
  - 印章/页边注      保留 (x < 7.5% 页宽)
  - 插图/表格区      保留 (光栅图 bbox + 矢量绘图聚类自动检测)
  - 独立公式行       保留 (CM 数学字体主导 + 列内近居中 + 短行)
  - 其余正文         -> 待翻译槽位, 中文将锚定在英文段起点重排

用法: python solo_worksheet.py --src <英文原文.pdf> --out worksheet.json [--pages 1-8]
下一步: 按 references/content-format.md 填写 content.json 的 "cn" 字段, 再跑 build_solo.py
"""
import argparse
from collections import Counter
import json
import re

import fitz

CM_FONTS = ('CMMI', 'CMSY', 'CMR', 'CMEX', 'MSBM', 'MSAM', 'CMU', 'Math')

# 正文所用字体族 (字体名去掉结尾数字, 如 CMR10 -> CMR)。LaTeX 类论文的正文字体本身就是
# Computer Modern 家族 (CMR/CMBX/CMTI...), 此时 "CM 前缀即数学字体" 的判定会把**每一个正文行**
# 都当成数学行 (短行 + 列内近居中 -> 被误保留、正文被漏抹)。由调用方 (content.json 的
# math_exclude_stems) 注入该论文的正文族名即可修复。默认空 = 保持旧行为 (适用于正文用
# Times/Helvetica、只有公式用 CM 的会议模板)。
MATH_EXCLUDE = set()


def font_stem(f):
    return re.sub(r'\d+$', '', f)


def line_col(ln, W):
    """栏归属按**行左缘**判定, 不按中心 (跨栏整宽行/整宽图注若按中心判会被劈成两栏,
    图注被拆成互不相连的三个槽)"""
    return 0 if ln['x0'] < W / 2 else 1


def is_folio(ln, W, H):
    """页码 (Springer 把 folio 排在版面底部的栏缝正中): 既不抹白也不翻译, 保留克隆原物。
    **必须是短标** — 单栏论文的整宽正文行中心也正好落在页心, 只按"居中+底部"判会把
    页面底部约 20% 的正文行全部当成页码(既不翻译也不抹白, 右半留下整段英文)。"""
    cx = (ln['x0'] + ln['x1']) / 2
    return (abs(cx - W / 2) < 12 and ln['y0'] > 0.80 * H
            and (ln['x1'] - ln['x0']) < 0.15 * W)


def get_lines(page):
    out = []
    for b in page.get_text('dict')['blocks']:
        if b.get('type') != 0:
            continue
        for l in b['lines']:
            spans = [{'t': s['text'], 'f': s['font'], 'sz': round(s['size'], 2),
                      'c': s['color'],
                      'ox': round(s['origin'][0], 2), 'oy': round(s['origin'][1], 2),
                      'x0': round(s['bbox'][0], 2), 'x1': round(s['bbox'][2], 2),
                      'y0': round(s['bbox'][1], 2), 'y1': round(s['bbox'][3], 2)}
                     for s in l['spans'] if s['text']]
            b_ = l['bbox']
            text = ''.join(s['t'] for s in spans)
            if text.strip():
                out.append({'x0': round(b_[0], 2), 'y0': round(b_[1], 2),
                            'dir': l.get('dir', (1.0, 0.0)),
                            'x1': round(b_[2], 2), 'y1': round(b_[3], 2),
                            'spans': spans, 'text': text,
                            'size': round(max((s['sz'] for s in spans), default=10.0), 2)})
    return out


def cm_dominant(ln):
    """行内字母数字是否以数学字体为主。
    数学字体 = CM*/MS* 前缀 (Computer Modern 全家桶: CMBX/CMMI/CMSY/CMEX/CMR/MSBM...)
    或 正文字体的小字号字符 (公式上下标常用正文字体排, 如 AAAI 的 concat/RGB/adj)"""
    body = max(s['sz'] for s in ln['spans']) if ln['spans'] else 10.0
    tot = cm = 0
    for s in ln['spans']:
        stem = font_stem(s['f'])
        mathish = (('Math' in s['f'] or s['f'].startswith(('CM', 'MS')))
                   and stem not in MATH_EXCLUDE)
        sub = s['sz'] <= body * 0.85
        for ch in s['t']:
            if ch.isalnum():
                tot += 1
                if mathish or sub:
                    cm += 1
    return tot > 0 and cm / tot >= 0.5


def detect_zones(page, half_w):
    """自动检测图/表保留区: 光栅图 bbox + 矢量绘图聚类 (含细线, 如表格规则线)"""
    zones = []
    try:
        for info in page.get_image_info():
            b = info['bbox']
            if (b[2] - b[0]) > 60 and (b[3] - b[1]) > 30:
                zones.append(list(b))
    except Exception:
        pass
    rects = [fitz.Rect(d['rect']) for d in page.get_drawings()]
    clusters = []
    for r in rects:
        rp = fitz.Rect(r.x0 - 1, r.y0 - 1, r.x1 + 1, r.y1 + 1)
        hit = None
        for c in clusters:
            if fitz.Rect(c[0] - 8, c[1] - 8, c[2] + 8, c[3] + 8).intersects(rp):
                hit = c
                break
        if hit is None:
            clusters.append([r.x0, r.y0, r.x1, r.y1])
        else:
            hit[0] = min(hit[0], r.x0)
            hit[1] = min(hit[1], r.y0)
            hit[2] = max(hit[2], r.x1)
            hit[3] = max(hit[3], r.y1)
    # 两轮合并 (链式: 竖线桥接横线)
    for _ in range(3):
        out = []
        for c in clusters:
            m = False
            for o in out:
                if fitz.Rect(o[0] - 8, o[1] - 8, o[2] + 8, o[3] + 8).intersects(
                        fitz.Rect(c[0] - 1, c[1] - 1, c[2] + 1, c[3] + 1)):
                    o[0] = min(o[0], c[0])
                    o[1] = min(o[1], c[1])
                    o[2] = max(o[2], c[2])
                    o[3] = max(o[3], c[3])
                    m = True
                    break
            if not m:
                out.append(list(c))
        clusters = out
    for c in clusters:
        if (c[2] - c[0]) * (c[3] - c[1]) > 15000 and (c[2] - c[0]) > 80 and (c[3] - c[1]) > 30:
            zones.append(c)
    # 消重: 互相包含的合并
    out = []
    for z in zones:
        keep = True
        for o in out:
            if fitz.Rect(o).contains(fitz.Rect(z)):
                keep = False
                break
            if fitz.Rect(z).contains(fitz.Rect(o)):
                o[:] = z
                keep = False
                break
        if keep:
            out.append(z)
    return out


def in_zone(ln, zones, pad=2):
    cx, cy = (ln['x0'] + ln['x1']) / 2, (ln['y0'] + ln['y1']) / 2
    for z in zones:
        if z[0] - pad <= cx <= z[2] + pad and z[1] - pad <= cy <= z[3] + pad:
            return True
    return False


def is_equation(ln, zones, col_x0, col_x1):
    if in_zone(ln, zones):
        return False
    w = ln['x1'] - ln['x0']
    c = (ln['x0'] + ln['x1']) / 2
    colw = col_x1 - col_x0
    if cm_dominant(ln) and re.search(r'\(\d{1,2}\)\s*$', ln['text']):
        return True   # 行尾带公式编号 (1)~(99) 且 CM 主导 -> 公式主体行
    return (cm_dominant(ln) and w < 0.72 * colw
            and abs(c - (col_x0 + col_x1) / 2) < 0.28 * colw)


def col_edges(lines, lo, hi, colrange=None):
    """栏边界 = 顶格行的众数 (分位数会被标题/作者等宽行污染)。
    colrange: 本栏的 x 范围; 只统计**完全落在本栏内**的行, 否则整宽块 (摘要/整宽图注)
    的 x0 会污染众数, 把排版框拉到跨栏 (中文就会横跨中缝压在另一栏上)。"""
    if not lines:
        return lo, hi
    if colrange:
        local = [l for l in lines if l['x0'] >= colrange[0] - 3 and l['x1'] <= colrange[1] + 3]
        if local:
            lines = local
    cx0 = Counter(round(l['x0']) for l in lines)
    cx1 = Counter(round(l['x1']) for l in lines)
    x0 = cx0.most_common(1)[0][0]
    x1 = cx1.most_common(1)[0][0]
    if cx0[x0] < 3:   # 无明显顶格行 -> 回退分位数
        xs = sorted(l['x0'] for l in lines)
        x0 = xs[int(0.08 * len(xs))]
    if cx1[x1] < 3:
        x1s = sorted(l['x1'] for l in lines)
        x1 = x1s[min(len(x1s) - 1, int(0.94 * len(x1s)))]
    return float(x0), float(x1)


def classify_lines(lines, zones, edges, W):
    """共享分类: 印章/图表区/独立公式 -> kept; 公式邻域生长吸收碎片; 其余 -> prose"""
    prose = {0: [], 1: []}
    kept = {0: [], 1: []}
    nkeep = 0
    for ln in lines:
        c = line_col(ln, W)
        if in_zone(ln, zones):
            nkeep += 1
            kept[c].append(ln)
        elif is_equation(ln, zones, *edges[c]):
            nkeep += 1
            kept[c].append(ln)
        else:
            prose[c].append(ln)

    # 公式邻域生长: 与保留公式行垂直相邻(<=6pt)的碎片行一并保留; 迭代 3 轮链式吸收
    #   a) CM 主导行 (矩阵行/上下标行/编号)
    #   b) 非顶格且不满宽的行 (分段函数分支, 如 'if (i,j) is inside B,')
    for _ in range(3):
        moved = 0
        for c in (0, 1):
            colx0, colx1 = edges[c]
            colw = colx1 - colx0
            stay = []
            for ln in prose[c]:
                gaps = [max(0, max(ln['y0'], k['y0']) - min(ln['y1'], k['y1']))
                        for k in kept[c]]
                near = (not gaps) is False and min(gaps) <= 6
                frag = (cm_dominant(ln)
                        or (ln['x0'] > colx0 + 0.15 * colw
                            and (ln['x1'] - ln['x0']) < 0.7 * colw))
                if near and frag:
                    kept[c].append(ln)
                    moved += 1
                else:
                    stay.append(ln)
            prose[c] = stay
        if not moved:
            break
        nkeep += moved
    return prose, kept, nkeep


def apply_trim(zones, trims, pno):
    """zone_trim: [{'page':3,'y1':280}] — 该页所有区域裁掉 y > y1 的部分 (救回被区域吞掉的图注)"""
    out = []
    for z in zones:
        for t in trims:
            if t['page'] == pno:
                z = list(z)
                if 'y1' in t:
                    z[3] = min(z[3], t['y1'])
                if 'y0' in t:
                    z[1] = max(z[1], t['y0'])
        if z[3] > z[1] and z[2] > z[0]:
            out.append(z)
    return out


def build_worksheet(src_path, pages, trims=None, extra=None):
    SRC = fitz.open(src_path)
    slots = []
    keepstats = []
    for pno1 in pages:
        page = SRC[pno1]
        W, H = page.rect.width, page.rect.height
        half_w = W
        lines = [ln for ln in get_lines(page)
                 if ln['x1'] >= 0.075 * half_w and not is_folio(ln, W, H)]
        zones = apply_trim(detect_zones(page, half_w), trims or [], pno1 + 1)
        # extra_zones: 自动检测漏掉的保留区 (书板表格只有横线、拼图式插图等), 由调用方给定
        for z in (extra or []):
            if z['page'] == pno1 + 1:
                zones.append([z['x0'], z['y0'], z['x1'], z['y1']])
        cols = {0: [], 1: []}
        for ln in lines:
            cols[line_col(ln, W)].append(ln)
        edges = {0: col_edges(cols[0], 0, W, (0, W / 2)),
                 1: col_edges(cols[1], 0, W, (W / 2, W))}

        prose = {0: [], 1: []}
        kept = {0: [], 1: []}
        nkeep = 0
        prose, kept, nkeep = classify_lines(lines, zones, edges, W)

        for c in (0, 1):
            lns = sorted(prose[c], key=lambda l: (l['y0'], l['x0']))
            if not lns:
                continue
            colx0, colx1 = edges[c]
            colw = colx1 - colx0
            blocks = []
            cur = None

            def flush():
                nonlocal cur
                if cur is None:
                    return
                blocks.append(list(cur))
                cur = None

            for idx, ln in enumerate(lns):
                nxt = lns[idx + 1] if idx + 1 < len(lns) else None
                if cur is None:
                    cur = [ln]
                    continue
                p = cur[-1]
                # 同一视觉行被拆成多个 line 对象 (图注的粗体 "Fig. 1" + 正文) -> 必为同段
                # 上标脚注标记 ("1" 抬高 3pt) 与原行 y0 差几 pt, 也必须算同一视觉行
                same_visual_line = abs(ln['y0'] - p['y0']) < 0.6 * max(ln['size'], p['size'])
                # 段首缩进 (如 AAAI 首行缩进 ~10pt) 或间距拉大或字号变化 -> 新段
                # 真·段首缩进: 该缩进行之后应回到栏左缘; 若后一行同样缩进 (项目符号的续行),
                # 那是列表悬挂缩进而非新段, 不拆
                indented = (not same_visual_line
                            and ln['x0'] > colx0 + 0.3 * ln['size']
                            and p['x0'] <= colx0 + 0.3 * p['size']
                            and not (nxt is not None and abs(nxt['x0'] - ln['x0']) < 1.0))
                # 字号变化要排除"公式上标/分母碎片" (如分数分子 '1' 只有 1 个字符)
                size_changed = (len(ln['text'].strip()) >= 5
                                and abs(ln['size'] - max(x['size'] for x in cur)) > 0.6)
                if (not same_visual_line
                        and (ln['y0'] - p['y1'] > 0.45 * ln['size']
                             or size_changed or indented)):
                    flush()
                    cur = [ln]
                else:
                    cur.append(ln)
            flush()
            for i, blk in enumerate(blocks):
                y0b = blk[0]['y0']
                ybot = blk[-1]['y1']
                # gap = 下一个"段落槽"的锚点 (中文从那里开始画, 这才是真边界);
                # 保留行(公式/图)与区域顶也作为边界
                cands = [0.965 * H]
                if i + 1 < len(blocks):
                    cands.append(blocks[i + 1][0]['y0'])
                for ln2 in kept[c]:
                    if ln2['y0'] > ybot + 0.5:
                        cands.append(ln2['y0'])
                for z in zones:
                    if z[1] > ybot and min(z[2], colx1) - max(z[0], colx0) > 30:
                        cands.append(z[1])
                gap = min(cands) - y0b - 2
                # 排版框: 常规段用栏边界; 跨栏宽块 (标题/作者, 宽 > 1.3 栏宽) 用自身范围
                bx0 = min(l['x0'] for l in blk)
                bx1 = max(l['x1'] for l in blk)
                if bx1 - bx0 <= 1.3 * colw:
                    bx0, bx1 = colx0, colx1
                slots.append({
                    'id': f'p{pno1 + 1}-c{c}-{i}',
                    'page': pno1 + 1, 'col': c,
                    'x0': round(bx0, 1), 'x1': round(bx1, 1),
                    'y0': round(y0b, 1), 'gap': round(gap, 1),
                    'size': round(max(l['size'] for l in blk), 1),
                    'en_first': blk[0]['text'][:48],
                    'en_text': ' '.join(l['text'] for l in blk)[:200],
                    'nlines': len(blk),
                    'cn': '',
                })
        keepstats.append((pno1 + 1, len(lines), nkeep, len(zones)))
    return slots, keepstats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--pages', default='')
    ap.add_argument('--trim', action='append', default=[],
                    help='页:y上限, 如 3:280 — 该页自动区域裁到 y<=y上限 (救回被吞的图注)')
    ap.add_argument('--math-exclude', default='',
                    help='正文所用字体族 (逗号分隔, 如 CMR,CMBX) — LaTeX 类论文正文即 CM 家族时必须给, '
                         '否则每个正文行都会被当作数学行')
    ap.add_argument('--zones', default='',
                    help='补充保留区的 json 文件: [{"page":7,"x0":..,"y0":..,"x1":..,"y1":..}]')
    args = ap.parse_args()
    trims = [{'page': int(s.split(':')[0]), 'y1': float(s.split(':')[1])}
             for s in args.trim]
    extra = json.load(open(args.zones, encoding='utf-8')) if args.zones else []
    if args.math_exclude:
        MATH_EXCLUDE.update(x.strip() for x in args.math_exclude.split(',') if x.strip())
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
        pages = list(range(len(fitz.open(args.src))))
    slots, keepstats = build_worksheet(args.src, pages, trims, extra)
    json.dump({'src': args.src, 'slots': slots},
              open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for p, n, k, z in keepstats:
        print(f'p{p}: lines={n} keep={k} (zones={z}) prose_slots={sum(1 for s in slots if s["page"] == p)}')
    print(f'worksheet -> {args.out}  共 {len(slots)} 个待翻译槽位')
    print('下一步: 复制为 content.json, 按 references/content-format.md 填 "cn" 字段')
    print('注意: 逐个核对 keep 分类是否正确 (打开原PDF对照), 尤其是公式和图内标签')


if __name__ == '__main__':
    main()
