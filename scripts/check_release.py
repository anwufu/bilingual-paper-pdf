# -*- coding: utf-8 -*-
"""check_release.py — 双语对照 PDF 质量验收门 (交付/CI 前必跑)

对 build_solo.py 的产出做机器自检, 全部通过 (退出码 0) 才算合格:

  1. 标记配对   cn 字段里 [[ ]] / ** / $ / ^{} / _{} 计数配对, 无残留 LaTeX 命令
  2. 槽位覆盖   worksheet 的每个待翻译槽位要么有 cn, 要么落在 keep_ranges 内
  3. 中文叠印   右半中文行两两相交 = 0 (与构建期碰撞检测同一规则)
  4. 中文×保留英文 = 0   保留区/公式里的英文行不允许被中文压住
  5. 缺字形     中文文本里的每个字符都能被字体链画出 (无豆腐块)
  6. 链接数     成品链接数 >= 原文链接数 (左半全量重建)
  7. 构建日志   (可选 --log) 不含 [警告]

用法:
  python scripts/check_release.py --src 原文.pdf --content content.json \
      --pdf 双语版.pdf [--build-log build.log]
退出码: 0 = 全部通过, 1 = 存在失败项
"""
import argparse
import json
import re
import sys

import fitz

sys.path.insert(0, __file__.rsplit('/', 1)[0].rsplit('\\', 1)[0])
from solo_worksheet import build_worksheet, get_lines, detect_zones, classify_lines  # noqa: E402
from fontconfig import resolve_fonts, default_fonts_dir  # noqa: E402

FF, _ = resolve_fonts(default_fonts_dir())
CHAIN = ('NSR', 'SYM', 'CMI', 'TMR')

results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(f'  [{"通过" if ok else "失败"}] {name}' + (f' — {detail}' if detail else ''))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--content', required=True)
    ap.add_argument('--pdf', required=True)
    ap.add_argument('--build-log', default='')
    args = ap.parse_args()

    src = fitz.open(args.src)
    doc = fitz.open(args.pdf)
    content = json.load(open(args.content, encoding='utf-8'))
    W = src[0].rect.width
    H = src[0].rect.height

    # ---- 1. 标记配对 ----
    bad = []
    for s in content['slots']:
        t = s.get('cn', '')
        if (t.count('[[') != t.count(']]') or t.count('**') % 2
                or t.count('$') % 2
                or t.count('^{') != len(re.findall(r'\^\{[^}]*\}', t))
                or t.count('_{') != len(re.findall(r'_\{[^}]*\}', t))):
            bad.append(s['id'] + ':标记不配对')
        if '\\' in t:
            bad.append(s['id'] + ':残留反斜杠(LaTeX命令?)')
    check('标记配对', not bad, ' '.join(bad[:4]))

    # ---- 2. 槽位覆盖 (keep_ranges 视为合法的"保留英文") ----
    trims = content.get('zone_trim', [])
    extra = content.get('extra_zones', [])
    SW_MEX = content.get('math_exclude_stems', [])
    sys.path.insert(0, __file__.rsplit('/', 1)[0].rsplit('\\', 1)[0])
    import solo_worksheet as SW
    SW.MATH_EXCLUDE = set(SW_MEX)
    ws, _ = build_worksheet(args.src, list(range(len(src))), trims, extra)
    keep = content.get('keep_ranges', [])

    def kept_by_range(pno, x0, x1, y0, size):
        # 按槽位**起始行**判定 (gap 到页底会把中点推出区间)
        for kr in keep:
            if kr['page'] != pno:
                continue
            cx = (x0 + x1) / 2
            cy = y0 + 0.4 * size
            if kr['y0'] <= cy <= kr['y1'] and kr.get('x0', 0) <= cx <= kr.get('x1', W):
                return True
        return False

    cn_ids = {s['id'] for s in content['slots'] if s.get('cn', '').strip()}
    # 合并感知 (pitfall 14e/14f): agent 可能把碎片行并进前槽后删掉独立槽,
    # 重建的 worksheet 仍会生成它。判定覆盖: 碎片行落在某已译内容槽的
    # [y0, y0+gap) 排版跨度内 (同页同栏), 或其 en_text 被某已译槽完整包含
    norm = lambda t: re.sub(r'\s+', '', t or '')
    cn_slots = [t for t in content['slots'] if t.get('cn', '').strip()]
    merged_en = [(norm(t.get('en_text', '')), t['page']) for t in cn_slots]

    def covered_by_merge(s):
        key = norm(s.get('en_text', ''))[:60]
        if len(key) >= 12 and any(key in en and pg == s['page'] for en, pg in merged_en):
            return True
        for t in cn_slots:
            # 自定义槽（只给 id/page/col/cn，无几何字段）无法做 y 跨度判定 -> 跳过
            if 'y0' not in t or t['page'] != s['page'] or t.get('col') != s.get('col'):
                continue
            if t['y0'] - 2 <= s['y0'] < t['y0'] + t.get('gap', 0):
                return True
        return False

    missing = []
    for s in ws:
        if s['id'] in cn_ids:
            continue
        if kept_by_range(s['page'], s['x0'], s['x1'], s['y0'], s.get('size', 10.0)):
            continue
        if covered_by_merge(s):
            continue
        missing.append(s['id'])
    check('槽位覆盖', not missing, f'未翻译且未保留: {missing[:6]}' if missing else
          f'{len(cn_ids)} 槽位已译')

    # ---- 3/4/5. 从成品 PDF 逐页检查 ----
    collide = 0
    overlap_en = 0
    tofu = set()
    n_cn = 0
    for i in range(len(src)):
        pno = i + 1
        page = doc[i]
        cn = []
        for b in page.get_text('dict')['blocks']:
            if b.get('type'):
                continue
            for l in b['lines']:
                if l['bbox'][0] < W:
                    continue
                f = l['spans'][0]['font']
                if 'NotoSerif' in f or f in ('NSR', 'NSB'):
                    txt = ''.join(sp['text'] for sp in l['spans'])
                    cn.append({'bbox': l['bbox'], 'text': txt})
                    for ch in txt:
                        if ch.strip() and not any(FF[k].has_glyph(ord(ch)) for k in CHAIN):
                            tofu.add(ch)
        n_cn += len(cn)
        # 3. 中文两两相交
        # 墨迹框: NotoSerif 行 bbox 的上升部含字体级 ascent (~0.24em 虚高), 剪掉再比
        def ink(bb, sz):
            return [bb[0], bb[1] + 0.24 * sz, bb[2], bb[3] - 0.05 * sz]
        boxes = sorted(cn, key=lambda b: (b['bbox'][0], b['bbox'][1]))
        for a, b2 in zip(boxes, boxes[1:]):
            a_sz = a['bbox'][3] - a['bbox'][1]
            b_sz = b2['bbox'][3] - b2['bbox'][1]
            ai, bi = ink(a['bbox'], a_sz), ink(b2['bbox'], b_sz)
            ox = min(ai[2], bi[2]) - max(ai[0], bi[0])
            oy = min(ai[3], bi[3]) - max(ai[1], bi[1])
            if ox > 3 and oy > 1.5:
                collide += 1
        # 4. 中文 × 保留英文 (重建分类; overlay 目标不算冲突)
        sp = src[i]
        lines = [ln for ln in get_lines(sp) if ln['x1'] >= 0.075 * W]
        zones = detect_zones(sp, W) + [[z['x0'], z['y0'], z['x1'], z['y1']]
                                       for z in extra if z['page'] == pno]
        # 复现构建侧 --trim (content['zone_trim']: [{'page':3,'y1':280}]),
        # 否则被 trim 救回的图注/正文行在重建里仍落在旧区域内 -> 假阳性
        zt = [t for t in content.get('zone_trim', []) if t.get('page') == pno]
        if zt:
            trimmed = []
            for z in zones:
                z = list(z)
                for t in zt:
                    if 'y1' in t:
                        z[3] = min(z[3], t['y1'])
                    if 'y0' in t:
                        z[1] = max(z[1], t['y0'])
                if z[3] > z[1] and z[2] > z[0]:
                    trimmed.append(z)
            zones = trimmed
        cols = {0: [], 1: []}
        for ln in lines:
            cols[SW.line_col(ln, W)].append(ln)
        edges = {0: SW.col_edges(cols[0], 0, W, (0, W / 2)),
                 1: SW.col_edges(cols[1], 0, W, (W / 2, W))}
        _, kept, _ = classify_lines(lines, zones, edges, W)
        keptset = [ln for c in (0, 1) for ln in kept[c]]
        for kr in keep:
            if kr['page'] == pno:
                keptset += [ln for ln in lines
                            if kr['y0'] <= (ln['y0'] + ln['y1']) / 2 <= kr['y1']
                            and kr.get('x0', 0) <= (ln['x0'] + ln['x1']) / 2 <= kr.get('x1', W)]
        ovset = {re.sub(r'\s+', '', o['find']) for o in content.get('overlays', [])
                 if o['page'] == pno}
        for a in cn:
            # 与"中文叠印"检查同族的 ink-box 修正: NotoSerif 行框 ascent 膨胀
            # (视觉验证过的假阳性: 公式下伸部/轴刻度与中文行框贴边, 墨迹实际不接触)
            a_sz = a['bbox'][3] - a['bbox'][1]
            ai = [a['bbox'][0], a['bbox'][1] + 0.24 * a_sz,
                  a['bbox'][2], a['bbox'][3] - 0.05 * a_sz]
            for k in keptset:
                if re.sub(r'\s+', '', k['text']) in ovset:
                    continue
                bb = [k['x0'] + W, k['y0'], k['x1'] + W, k['y1']]
                ox = min(ai[2], bb[2]) - max(ai[0], bb[0])
                oy = min(ai[3], bb[3]) - max(ai[1], bb[1])
                if ox > 2.5 and oy > 2.0:
                    overlap_en += 1

    check('中文叠印', collide == 0, f'{collide} 处' if collide else f'{n_cn} 个中文行')
    check('中文×保留英文', overlap_en == 0, f'{overlap_en} 处' if overlap_en else '无')
    check('缺字形', not tofu, f'字符 {sorted(tofu)}' if tofu else '无')

    # ---- 6. 链接数 ----
    n_src = sum(len(p.get_links()) for p in src)
    n_out = sum(len(p.get_links()) for p in doc)
    check('链接数', n_out >= n_src, f'原文 {n_src} -> 成品 {n_out}')

    # ---- 7. 构建日志 (可选) ----
    if args.build_log:
        log = open(args.build_log, encoding='utf-8', errors='ignore').read()
        warns = [l.strip() for l in log.splitlines() if '[警告]' in l]
        check('构建日志无警告', not warns, '; '.join(warns[:3]) if warns else '干净')

    n_fail = sum(1 for _, ok, _ in results if not ok)
    print(f'\n{"=" * 46}\n验收: {len(results) - n_fail}/{len(results)} 项通过'
          f'{" — 存在失败项, 禁止交付" if n_fail else " — 全部通过, 可交付"}')
    sys.exit(1 if n_fail else 0)


if __name__ == '__main__':
    main()
