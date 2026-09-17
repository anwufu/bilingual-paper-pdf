# -*- coding: utf-8 -*-
"""build_solo.py — 模式B(无参考版): 英文原文 + content.json → 双语对照 PDF

右页 = 英文原页整页克隆 + 抹白正文(图/公式/印章保留) + 中文段落锚定重排:
  - 每段中文起点 = 左页对应英文段的起点 (镜像锚定)
  - 中英长度差用段内行距微调吸收 (参考版工艺: ±2pt)
  - 行内两端对齐由我的字距计算完成
  - 标记: **粗体**  ^{上标}  _{下标}  $数学$ (字母斜体, ∈⊙ℝ 自动走符号字体)

用法: python build_solo.py --src <英文原文.pdf> --content content.json --out 双语版.pdf
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

import fitz

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import solo_worksheet as SW  # noqa: E402
from solo_worksheet import build_worksheet, get_lines, detect_zones, classify_lines, col_edges, apply_trim, is_folio, line_col  # noqa: E402


def resolve_fonts(fonts_dir):
    from fontconfig import resolve_fonts as _rf
    return _rf(fonts_dir)


def _system_font_candidates():
    from fontconfig import system_font_candidates
    return system_font_candidates()



ap = argparse.ArgumentParser()
ap.add_argument('--src', required=True)
ap.add_argument('--content', required=True)
ap.add_argument('--out', required=True)
ap.add_argument('--fonts-dir', default=None,
                help='字体目录 (默认: <仓库>/fonts, 其次 <仓库>/_fonts)')
args = ap.parse_args()
from fontconfig import default_fonts_dir  # noqa: E402
FF, FFILE = resolve_fonts(args.fonts_dir or default_fonts_dir(SKILL_DIR))


def col_tuple(c):
    if isinstance(c, str):
        c = int(c.lstrip('#'), 16)
    return ((c >> 16 & 255) / 255, (c >> 8 & 255) / 255, (c & 255) / 255)


# 文本染色规则 (content['text_colors']): [{'re': 正则, 'color': '#rrggbb'}]
COLOR_RULES = []
# 引用/链接色 (content['cite_color'], 如 hyperref 的 '#0000ff'): 标记 [[...]] 内的文字用该色
CITE_COLOR = None
CITE_RX = re.compile(r'\[\[.+?\]\]', re.S)


def color_of_seg(s):
    """按规则给片段每个字符标注颜色 -> list[(idx, coltuple)]"""
    marks = {}
    for rx, col in COLOR_RULES:
        for m in rx.finditer(s):
            for i in range(m.start(), m.end()):
                marks[i] = col
    return marks


# ---------- 标记解析: -> 字符列表 [{ch, font, mult, dy, color}] ----------
TOKEN = re.compile(r'(\*\*.+?\*\*|\$.+?\$|\^\{[^}]*\}|_\{[^}]*\}|\[\[.+?\]\])', re.S)


def parse_markup(text):
    chars = []
    bold = False

    def emit(s, math=False, force=None):
        marks = color_of_seg(s)
        i = 0
        while i < len(s):
            m = re.match(r'\^\{([^}]*)\}', s[i:])
            m2 = re.match(r'_\{([^}]*)\}', s[i:])
            if m:
                for ch in m.group(1):
                    chars.append({'ch': ch, 'bold': bold, 'math': math,
                                  'mult': 0.72, 'dy': -0.33})
                i += m.end()
            elif m2:
                for ch in m2.group(1):
                    chars.append({'ch': ch, 'bold': bold, 'math': math,
                                  'mult': 0.72, 'dy': 0.22})
                i += m2.end()
            else:
                chars.append({'ch': s[i], 'bold': bold, 'math': math,
                              'mult': 1.0, 'dy': 0.0, 'color': force or marks.get(i)})
                i += 1

    for tok in TOKEN.split(text):
        if not tok:
            continue
        if tok.startswith('**') and tok.endswith('**'):
            bold = True
            emit(tok[2:-2])
            bold = False
        elif tok.startswith('$') and tok.endswith('$'):
            emit(tok[1:-1], math=True)
        elif tok.startswith('[[') and tok.endswith(']]'):
            emit(tok[2:-2], force=CITE_COLOR)
        else:
            emit(tok)
    return chars


def char_font(c):
    ch = c['ch']
    if c['math'] and ch.isalpha() and ch.isascii():
        return 'CMI'
    if c['bold']:
        return 'NSB'
    return 'NSR'


def char_width(c, size):
    k = char_font(c)
    return FF[k].text_length(c['ch'], size * c['mult'])


# 中文避头尾 (禁则): 这些符号不得出现在行首, 换行时挂到上一行末尾
NO_LINE_START = set('，。、；：？！）】》」』〉…—～·%‰℃”’』」')


# ---------- 换行: CJK 逐字可断, 西文单词不断 ----------
def wrap(chars, width, size):
    words = []
    cur = []
    for c in chars:
        if c['ch'] == ' ':
            if cur:
                words.append(cur)
                cur = []
            words.append([dict(c, ch=' ')])
        elif ord(c['ch']) > 0x2E80:
            if cur:
                words.append(cur)
                cur = []
            words.append([c])
        else:
            cur.append(c)
    if cur:
        words.append(cur)
    lines = []
    line = []
    w = 0.0
    for word in words:
        ww = sum(char_width(c, size) for c in word)
        if line and w + ww > width + 1.0:
            while line and line[-1]['ch'] == ' ':
                line.pop()
            if len(word) == 1 and word[0]['ch'] in NO_LINE_START and line:
                line += word          # 禁则: 收尾标点随上一行 (允许轻微出界)
                lines.append(line)
                line = []
                w = 0.0
                continue
            lines.append(line)
            line = []
            w = 0.0
            if word and word[0]['ch'] == ' ':
                word = word[1:]
            ww = sum(char_width(c, size) for c in word)
        line += word
        w += ww
    if line:
        lines.append(line)
    return lines


def draw_line(page, line, x, baseline, size, justify_to=None, inserted=None, center_at=None,
              color=None):
    natural = sum(char_width(c, size) for c in line)
    n = len(line)
    extra = 0.0
    if center_at is not None:
        x = center_at - natural / 2
    elif justify_to and n > 1:
        delta = justify_to - natural
        if abs(delta) > 0.06:
            extra = max(-0.22, min(2.5, delta / (n - 1)))
    cur = x
    for c in line:
        k = char_font(c)
        if c['ch'].strip() and not FF[k].has_glyph(ord(c['ch'])):
            k = next((t for t in ('SYM', 'CMI', 'TMR') if t in FF and FF[t].has_glyph(ord(c['ch']))), k)
        if k not in inserted:
            page.insert_font(fontname=k, fontfile=FFILE[k])
            inserted.add(k)
        sz = size * c['mult']
        if c['ch'].strip():
            page.insert_text((cur, baseline + c['dy'] * size), c['ch'],
                             fontname=k, fontsize=sz,
                             color=c.get('color') or color)
        cur += char_width(c, size) + extra


def main():
    SRC = fitz.open(args.src)
    content = json.load(open(args.content, encoding='utf-8'))
    # 正文字体族排除 (LaTeX 类论文正文字体即 CM 家族时, 防止被误判为数学行)
    SW.MATH_EXCLUDE = set(content.get('math_exclude_stems', []))
    # 文本染色规则注入 (引用蓝/链接/红色/蓝色等)
    for rule in content.get('text_colors', []):
        COLOR_RULES.append((re.compile(rule['re']), col_tuple(rule['color'])))
    global CITE_COLOR
    if content.get('cite_color'):
        CITE_COLOR = col_tuple(content['cite_color'])
    slots = {s['id']: s for s in content['slots']}
    overlays = content.get('overlays', [])
    half = SRC[0].rect.width
    pages = sorted({s['page'] for s in content['slots']} | {o['page'] for o in overlays})
    all_pages = list(range(len(SRC)))

    # 重建英文结构 (分类必须与 worksheet 一致; zone_trim 需与生成工作表时相同)
    trims = content.get('zone_trim', [])
    extra = content.get('extra_zones', [])
    ws, _ = build_worksheet(args.src, all_pages, trims, extra)
    ws_by_id = {s['id']: s for s in ws}

    out = fitz.open()
    cn_boxes = {pno1 + 1: [] for pno1 in all_pages}   # 中文行框 (碰撞检测)
    col_cursor = {}                                    # (page, col) -> 中文流游标 y
    W0 = SRC[0].rect.width
    missing = []
    for pno1 in all_pages:
        page = SRC[pno1]
        W, H = page.rect.width, page.rect.height
        pno = pno1 + 1
        op = out.new_page(width=W * 2, height=H)
        op.show_pdf_page(fitz.Rect(0, 0, W, H), SRC, pno1)
        op.show_pdf_page(fitz.Rect(W, 0, W * 2, H), SRC, pno1)
        inserted = set()

        lines = [ln for ln in get_lines(page)
                 if ln['x1'] >= 0.075 * W and not is_folio(ln, W, H)]
        zones = apply_trim(detect_zones(page, W), trims, pno)
        for z in extra:
            if z['page'] == pno:
                zones.append([z['x0'], z['y0'], z['x1'], z['y1']])
        cols = {0: [], 1: []}
        for ln in lines:
            cols[line_col(ln, W)].append(ln)
        edges = {0: col_edges(cols[0], 0, W, (0, W / 2)),
                 1: col_edges(cols[1], 0, W, (W / 2, W))}

        # 抹白: 正文行 (印章/图表格区/公式及其碎片 保留) — 分类与 worksheet 完全一致
        whites = []
        prose, kept, _ = classify_lines(lines, zones, edges, W)
        prose_set = {id(ln) for c in (0, 1) for ln in prose[c]}
        # keep_ranges: 指定 y (可含 x0/x1) 区间的行不抹白 (如参考文献列表、整页图)
        for kr in content.get('keep_ranges', []):
            if kr['page'] != pno:
                continue
            for ln in lines:
                cy = (ln['y0'] + ln['y1']) / 2
                cx = (ln['x0'] + ln['x1']) / 2
                in_y = kr['y0'] <= cy <= kr['y1']
                in_x = ('x0' not in kr or kr['x0'] <= cx <= kr.get('x1', W))
                if in_y and in_x:
                    prose_set.discard(id(ln))
        for ln in lines:
            if id(ln) in prose_set:
                whites.append(ln)

        # overlay 替换 v2 (图表内文字汉化): 精确匹配 + y 消歧 + 底色采样 + 符号保护
        def norm_eq(t):
            return re.sub(r'\s+', '', t)

        def sample_bg(pg, bb):
            cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
            h2 = (bb[3] - bb[1]) / 2
            pts = []
            for dx in (-3, 0, 3):
                pts.append((cx + dx, bb[1] - min(2.5, h2 * 0.4)))
                pts.append((cx + dx, bb[3] + min(2.5, h2 * 0.4)))
            pts += [(bb[0] - 2, cy), (bb[2] + 2, cy)]
            zoom = 4
            clip = fitz.Rect(min(p[0] for p in pts) - 2, min(p[1] for p in pts) - 2,
                             max(p[0] for p in pts) + 2, max(p[1] for p in pts) + 2)
            cols = []
            try:
                pix = pg.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
                for (px, py) in pts:
                    ix, iy = int((px - clip.x0) * zoom), int((py - clip.y0) * zoom)
                    if 0 <= ix < pix.width and 0 <= iy < pix.height:
                        off = (iy * pix.width + ix) * pix.n
                        cols.append(tuple(pix.samples[off:off + 3]))
            except Exception:
                pass
            if not cols:
                return (1, 1, 1)
            q = Counter((c[0] // 8, c[1] // 8, c[2] // 8) for c in cols)
            best = q.most_common(1)[0][0]
            grp = [c for c in cols if (c[0] // 8, c[1] // 8, c[2] // 8) == best]
            return (sum(c[0] for c in grp) / len(grp) / 255,
                    sum(c[1] for c in grp) / len(grp) / 255,
                    sum(c[2] for c in grp) / len(grp) / 255)

        for ov in [o for o in overlays if o['page'] == pno]:
            key = norm_eq(ov['find'])
            # 匹配池用**未过滤**的行: 页码(folio)行不在 lines 里, 但它可能正是要抹掉的目标
            # (如栏右侧页底游离的段末英文短词)。overlay 是显式指令, 不应被分类过滤挡住。
            matches = [ln for ln in get_lines(page) if norm_eq(ln['text']) == key]
            if 'y' in ov and len(matches) > 1:
                matches.sort(key=lambda ln: abs((ln['y0'] + ln['y1']) / 2 - ov['y']))
            picks = matches if ov.get('all') else matches[:1]
            if not picks:
                print(f'  [警告] p{pno} overlay 未找到: {ov["find"]!r}')
                continue
            for hit in picks:
                # 抹白: 从首个"字母≥2"的 span 到行尾 (保护行首图形符号, 覆盖尾部数学记号)
                spans = hit['spans']
                if any(k in ov for k in ('x0', 'y0', 'x1', 'y1')):
                    # 显式抹白框 (源页坐标): 整行残留的公式碎片可能以 '(' 或单个字母开头,
                    # 行首符号保护规则会留下残字 "(M" -> 按给定范围整行抹白 (cn 通常为空)
                    bb = [ov.get('x0', hit['x0']), ov.get('y0', hit['y0']),
                          ov.get('x1', hit['x1']), ov.get('y1', hit['y1'])]
                    text_spans = spans
                else:
                    i0 = next((i for i, s in enumerate(spans)
                               if sum(ch.isalpha() for ch in s['t']) >= 2), len(spans) - 1)
                    text_spans = spans[i0:]
                    bb = [min(s['x0'] for s in text_spans), min(s['y0'] for s in text_spans),
                          max(s['x1'] for s in text_spans), max(s['y1'] for s in text_spans)]
                # 底色采样必须采**源页**同一坐标: 右半是 1:1 克隆, 但输出文档在 save 之前
                # get_pixmap 渲染为空白 (PyMuPDF 行为), 采输出页只会得到白 -> 底色丢失
                bg = ov.get('bg') or sample_bg(page, bb)
                op.draw_rect(fitz.Rect(W + bb[0] - 0.8, bb[1] - 0.6, W + bb[2] + 0.8, bb[3] + 0.6),
                             color=None, fill=bg)
                sz = ov.get('size', text_spans[0]['sz'])
                color = col_tuple(text_spans[0]['c'])
                bold = any(('Bold' in s['f'] or 'Medi' in s['f'] or 'BX' in s['f'])
                           for s in text_spans)
                runs = [{'ch': ch, 'bold': bold, 'math': False, 'mult': 1.0, 'dy': 0.0}
                        for ch in ov['cn']]
                oy = text_spans[0]['oy']
                ldir = hit.get('dir', (1.0, 0.0))
                if abs(ldir[1]) > 0.5:
                    # 纵轴标题等旋转文字: insert_textbox 的 rotate 仍沿矩形宽度排版 (塞不下),
                    # 改为逐字 insert_text(rotate=90) 自下而上叠排
                    kk = 'NSR'
                    if kk not in inserted:
                        op.insert_font(fontname=kk, fontfile=FFILE[kk])
                        inserted.add(kk)
                    ct = ['NSR', 'SYM', 'CMI', 'TMR']
                    step = sz * 1.05
                    nch = len(ov['cn'])
                    ycur = (bb[1] + bb[3]) / 2 + nch * step / 2
                    for ch in (ov['cn'] if ldir[1] < 0 else reversed(ov['cn'])):
                        kx = next((t for t in ct if t in FF and
                                   (not ch.strip() or FF[t].has_glyph(ord(ch)))), 'NSR')
                        if kx not in inserted:
                            op.insert_font(fontname=kx, fontfile=FFILE[kx])
                            inserted.add(kx)
                        if ch.strip():
                            op.insert_text((W + bb[2], ycur), ch, fontname=kx,
                                           fontsize=sz, color=color, rotate=90)
                        ycur -= step
                    continue
                if ov.get('align', 'center') == 'left':
                    draw_line(op, runs, W + text_spans[0]['x0'], oy, sz,
                              inserted=inserted, color=color)
                else:
                    cx = (W + bb[0] + W + bb[2]) / 2
                    draw_line(op, runs, 0, oy, sz, center_at=cx, inserted=inserted, color=color)

        for ln in whites:
            op.draw_rect(fitz.Rect(W + ln['x0'] - 1.0, ln['y0'] - 0.7,
                                   W + ln['x1'] + 1.0, ln['y1'] + 0.7),
                         color=None, fill=(1, 1, 1))

        # 中文槽位渲染 (每栏维护游标: 锚点被前槽咬住时顺接续排, 结构上杜绝叠印)
        # 槽序按"重建 worksheet 的真实 y0"排 (pitfall 64): 自定义槽可以不带几何字段,
        # 若按 content 自带 y0 排会落到 0 而被排到最前 -> 列游标顺接把中文一路推到栏底。
        def _slot_key(s):
            ws_s = ws_by_id.get(s['id'])
            y = ws_s['y0'] if ws_s and 'y0' in ws_s else s.get('y0')
            return (s['page'], s.get('col', 0), y if y is not None else 0.0)

        for s in sorted(content['slots'], key=_slot_key):
            if s['page'] != pno:
                continue
            if not s.get('cn', '').strip():
                continue
            ws_s = ws_by_id.get(s['id'], s)
            size = s.get('size', ws_s.get('size', 10.0))
            x0 = ws_s['x0']
            width = ws_s['x1'] - ws_s['x0']
            if 'box' in s:
                # 显式排版框 [x0, x1] (源页坐标): 栏右界取的是"行右端众数", 参考文献页
                # 的窄条目会把众数拉偏, 页眉/整宽块跟着变窄并折行 -> 与栏宽解耦
                x0 = float(s['box'][0])
                width = float(s['box'][1]) - x0
            y0 = ws_s['y0']
            gap = s.get('gap', ws_s.get('gap', 770 - y0))
            # 游标顺接: 若本槽锚点已被前一槽的中文流越过, 从游标处续排 (防咬合叠印)
            ckey = (pno, ws_s.get('col', 0))
            draw_y0 = max(y0, col_cursor.get(ckey, 0.0))
            if draw_y0 > y0 + 0.5:
                gap = max(gap - (draw_y0 - y0), size * 1.4)
                print(f'  [顺接] {s["id"]} 锚点 {y0:.0f} -> 游标 {draw_y0:.0f}')
            # 多段落: cn 中的 \n 分段, 每个后续段首行缩进 10pt (镜像原文段首缩进)
            seq = []
            for pi, ptxt in enumerate(s['cn'].split('\n')):
                chars = parse_markup(ptxt.strip())
                if not chars:
                    continue
                for wl in wrap(chars, width, size):
                    seq.append((wl, pi > 0))
            lh = None
            mult = 1.0
            for cand, cm in ((1.50, 1.0), (1.46, 1.0), (1.42, 1.0), (1.38, 1.0),
                             (1.34, 1.0), (1.30, 1.0), (1.34, 0.95), (1.30, 0.95), (1.30, 0.90)):
                if (len(seq) - 1) * cand * size * cm + size * cm * 1.15 <= gap + 0.5:
                    lh, mult = cand, cm
                    break
            if mult < 1.0:
                size = size * mult
                print(f'  [缩排] {s["id"]} 字号 x{mult} 行距 {lh} (nlines={len(seq)} gap={gap:.0f})')
            elif lh is None:
                lh = 1.24
                print(f'  [警告] {s["id"]} 行距压到 1.24 仍可能溢出 (nlines={len(seq)} gap={gap:.0f})')
            baseline = draw_y0 + 0.80 * size
            align = s.get('align', '')
            indent = 10.0 if len(s['cn'].split('\n')) > 1 else 0.0
            for i, (ln_c, ind) in enumerate(seq):
                xoff = indent if ind else 0.0
                if align == 'center':
                    draw_line(op, ln_c, W + x0, baseline, size,
                              center_at=W + x0 + width / 2, inserted=inserted)
                else:
                    jt = (width - xoff) if i < len(seq) - 1 else None
                    draw_line(op, ln_c, W + x0 + xoff, baseline, size,
                              justify_to=jt, inserted=inserted)
                # 记录中文行框 (碰撞检测用)
                lw = sum(char_width(c, size) for c in ln_c)
                cn_boxes[pno].append({'id': s['id'], 'x0': W + x0 + xoff, 'x1': W + x0 + xoff + lw,
                                      'y0': baseline - size * 0.88, 'y1': baseline + size * 0.22})
                baseline += lh * size
            col_cursor[ckey] = baseline - lh * size + size * 0.25

    # 画后碰撞检测: 不同槽位的中文行两两相交 = 叠印缺陷, 机器自检
    n_collide = 0
    for p, boxes in cn_boxes.items():
        if not boxes:
            continue
        boxes = sorted(boxes, key=lambda b: (b['x0'], b['y0']))
        for a, b in zip(boxes, boxes[1:]):
            if a['id'] == b['id']:
                continue
            ox = min(a['x1'], b['x1']) - max(a['x0'], b['x0'])
            oy = min(a['y1'], b['y1']) - max(a['y0'], b['y0'])
            if ox > 3 and oy > 1.5:
                n_collide += 1
                print(f'  [碰撞] p{p}: {a["id"]} ({a["y0"]:.0f}-{a["y1"]:.0f}) × '
                      f'{b["id"]} ({b["y0"]:.0f}-{b["y1"]:.0f}) 重叠 {oy:.1f}pt')
    if n_collide:
        print(f'[警告] 检测到 {n_collide} 处中文叠印 — 必须修复 (合并碎片槽/精简译文/修 gap) 后重构建')
    else:
        print('[碰撞检测] 通过: 无中文叠印')

    # ---------- 链接层 (linkify) ----------
    # 左半: 重建原版链接注释; 右半: 中文里的引用/URL 自动建跳转
    lk = content.get('linkify') or {}
    if lk.get('apply'):
        n_link = 0
        # 右半引用/URL 目标索引: 在参考区(右侧)找 '[n]' 首现位置
        ref_target = {}

        def find_ref_target(n):
            if n in ref_target:
                return ref_target[n]
            # 参考文献在文末: 倒序搜右半的 '[n]' 条目 (避免命中正文里的残片)
            for pj in range(len(out) - 1, -1, -1):
                pg = out[pj]
                hits = pg.search_for(f'[{n}]')
                for r in hits:
                    if r.x0 > SRC[0].rect.width:      # 右半
                        ref_target[n] = (pj, fitz.Point(r.x0, r.y0))
                        return ref_target[n]
            ref_target[n] = None
            return None

        cite_rx = re.compile(r'\[\s*\d[\d,\s\u2013-]*\]')
        url_rx = re.compile(r'https?://[^\s，。]+')
        for pno1 in all_pages:
            op = out[pno1]
            W = SRC[pno1].rect.width
            # 左半: 重建原页链接 (URI 原样, GOTO 目标页号 1:1 对应)
            for a in SRC[pno1].get_links():
                kind = a.get('kind')
                if kind == fitz.LINK_URI:
                    op.insert_link({'kind': fitz.LINK_URI, 'from': fitz.Rect(a['from']),
                                    'uri': a.get('uri', '')})
                    n_link += 1
                elif kind in (fitz.LINK_GOTO, fitz.LINK_NAMED) and a.get('page', -1) >= 0:
                    # LINK_NAMED (kind=4): LaTeX hyperref 的具名目标。PyMuPDF 已解析出 page/to,
                    # 直接按 GOTO 重建 —— 漏掉这一类会丢掉全部引用跳转。
                    op.insert_link({'kind': fitz.LINK_GOTO, 'from': fitz.Rect(a['from']),
                                    'page': a['page'], 'to': fitz.Point(a.get('to', fitz.Point(0, 0)))})
                    n_link += 1
            # 右半: 引用与 URL
            words_hits = []
            for w in op.get_text('rawdict')['blocks']:
                if w.get('type'):
                    continue
                for l in w['lines']:
                    for sp in l['spans']:
                        if sp['bbox'][0] < W:
                            continue
                        txt = ''.join(c['c'] for c in sp['chars'])
                        for rx in (cite_rx, url_rx):
                            for m in rx.finditer(txt):
                                xs = [sp['chars'][i]['bbox'][0] for i in range(m.start(), m.end())]
                                x1s = [sp['chars'][i]['bbox'][2] for i in range(m.start(), m.end())]
                                ys = [sp['chars'][i]['bbox'][1] for i in range(m.start(), m.end())]
                                y1s = [sp['chars'][i]['bbox'][3] for i in range(m.start(), m.end())]
                                words_hits.append((rx is url_rx, m.group(),
                                                   fitz.Rect(min(xs), min(ys), max(x1s), max(y1s))))
            for is_url, tok, rect in words_hits:
                if is_url:
                    op.insert_link({'kind': fitz.LINK_URI, 'from': rect, 'uri': tok})
                    n_link += 1
                    continue
                for n in re.findall(r'\d+', tok):
                    tgt = find_ref_target(n)
                    if tgt:
                        op.insert_link({'kind': fitz.LINK_GOTO, 'from': rect,
                                        'page': tgt[0], 'to': tgt[1]})
                        n_link += 1
        print(f'[链接层] 建立 {n_link} 个链接 (左半原版重建 + 右半引用/URL)')

    out.save(args.out, garbage=3, deflate=True)
    print(f'saved {args.out}, {len(out.tobytes()) / 1e6:.1f} MB')
    # 空槽告警: keep_ranges 覆盖的空槽是合法留白(参考文献等), 不计入告警
    keep = content.get('keep_ranges', [])

    def kept_by_range(pno, x0, x1, y0, size):
        for kr in keep:
            if kr.get('page') != pno:
                continue
            cy = y0 + 0.4 * size
            cx = (x0 + x1) / 2
            if kr['y0'] <= cy <= kr['y1'] and kr.get('x0', 0) <= cx <= kr.get('x1', 1e9):
                return True
        return False

    missing = []
    for s in content['slots']:
        if s.get('cn', '').strip():
            continue
        if 'y0' in s and kept_by_range(s['page'], s.get('x0', 0), s.get('x1', 0),
                                       s['y0'], s.get('size', 10.0)):
            continue
        missing.append(s['id'])
    if missing:
        print(f'[警告] 未填写的槽位 ({len(missing)}): {missing[:10]}{"..." if len(missing) > 10 else ""}')
    # id 回退提示: content 槽 id 不在重建 worksheet 时, 引擎会用 content 自带坐标。
    # 自带几何(x0/x1/y0 齐全) = 有意的自定义槽(如跨栏拆槽), 属正常;
    # 几何缺失 = 极可能因 zone/trim 重分类导致 id 顺移后的残留, 会静默错位 (pitfall 63)。
    stray = [s['id'] for s in content['slots'] if s['id'] not in ws_by_id]
    stray_bad = [s['id'] for s in content['slots'] if s['id'] not in ws_by_id
                 and not all(k in s for k in ('x0', 'x1', 'y0'))]
    if stray:
        print(f'  [提示] 自定义槽 (不在重建 worksheet, 使用自带几何): {len(stray)} 个 '
              f'{stray[:6]}{"..." if len(stray) > 6 else ""}')
    if stray_bad:
        print(f'[警告] 槽 id 不在重建 worksheet 且缺几何 (会静默错位, 见 pitfalls 63): '
              f'{stray_bad[:10]}{"..." if len(stray_bad) > 10 else ""}')
    print('>>> 下一步必须跑 audit.py + 逐页目检, 未过审不得交付 <<<')


if __name__ == '__main__':
    main()
