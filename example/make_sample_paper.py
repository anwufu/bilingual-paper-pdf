# -*- coding: utf-8 -*-
"""make_sample_paper.py — 生成仓库自带的样例论文 example/sample_paper.pdf

这是一篇**合成的**玩具论文 (内容为虚构, 由本脚本生成, 版权随仓库分发),
专门设计成"引擎考点全覆盖"的测试卷:
  - Springer 式双栏排版 (栏宽/边距与真实 sn-jnl 一致)
  - 整宽摘要 + 关键词, 正文段首缩进, 段内行内粗体/斜体, 上标脚注标记
  - 编号公式 (1): 用改名为 CMMI10 的字体排印, 触发引擎的数学字体判定 (保持不翻)
  - 图 1: 矢量框图, 带黄色底色框 + 两个面板的同名标签 (考 overlay 底色采样/all 模式)
  - 表 1: booktabs 式 (只有三条横线, 考 mkzones 图注锚定)
  - 蓝色作者-年份引用 (hyperref 色) + 跳转链接 + 一个 URL
  - 上标脚注, 底部页码, 左侧竖排 arXiv 式印章

用法: python example/make_sample_paper.py
"""
import os

import fitz
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'sample_paper.pdf')
SRC = os.path.join(HERE, 'src')
os.makedirs(SRC, exist_ok=True)

W, H = 595.276, 841.89
COL = {0: (67.0, 282.0), 1: (305.0, 520.0)}
BODY, LH = 9.96, 12.0
TOP = 75.0
WIN = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')
T_TTF = os.path.join(WIN, 'times.ttf')
TB_TTF = os.path.join(WIN, 'timesbd.ttf')
TI_TTF = os.path.join(WIN, 'timesi.ttf')

BLUE = (0, 0, 1)
BLACK = (0, 0, 0)
FNT = {}


def font(k):
    if k not in FNT:
        FNT[k] = fitz.Font(fontfile=FONTS[k])
    return FNT[k]


def tlen(t, f, sz):
    return font(f).text_length(t, sz)


def _rename(src, newname):
    """复制字体并改名 (仅用于样例公式: CMMI10/CMR10 触发引擎数学字体判定)"""
    out = os.path.join(SRC, newname + '.ttf')
    if os.path.exists(out):
        return out
    f = TTFont(src)
    name = f['name']
    for nid in (1, 3, 4, 6):
        name.setName(newname, nid, 3, 1, 0x409)
        name.setName(newname, nid, 1, 0, 0)
    f.save(out)
    return out


# 真实 LaTeX 里: 字母用数学斜体 (CMMI), 数字/运算符用数学正体 (CMR)。
# 两者都由 Times 改名而来 —— 既让引擎按 CM 数学字体识别公式行, 又不引入版权字体。
FONTS = {'TMR': T_TTF, 'TMB': TB_TTF, 'TMI': TI_TTF,
         'CMMI10': _rename(TI_TTF, 'CMMI10'), 'CMR10': _rename(T_TTF, 'CMR10')}


class Drawer:
    def __init__(self, page, pno):
        self.page = page
        self.pno = pno                # 页号: 1.27 的页对象引用会失效, 建链接时按号重取
        self.inserted = set()
        self.blue_rects = []          # 蓝色 (引用/URL) 词的 (页号, 矩形), 供建链接

    def font(self, f):
        if f not in self.inserted:
            self.page.insert_font(fontname=f, fontfile=FONTS[f])
            self.inserted.add(f)

    def text(self, x, y, t, f='TMR', sz=BODY, color=BLACK):
        self.font(f)
        self.page.insert_text((x, y), t, fontname=f, fontsize=sz, color=color)
        return tlen(t, f, sz)

    def centered(self, y, segs, sz):
        """居中一行; segs 支持 (t,f,c) 或 (t,f,c,dy,mult)"""
        total = sum(tlen(s[0], s[1], sz * (s[4] if len(s) > 4 else 1.0)) for s in segs)
        cur = (W - total) / 2
        for s in segs:
            t, f, c = s[0], s[1], s[2]
            dy = s[3] if len(s) > 3 else 0.0
            mult = s[4] if len(s) > 4 else 1.0
            self.font(f)
            self.page.insert_text((cur, y + dy * sz), t, fontname=f,
                                  fontsize=sz * mult, color=c)
            cur += tlen(t, f, sz * mult)


class Flow:
    """一个栏内的逐词排版流: 自动换行 + 两端对齐"""

    def __init__(self, drawer, page, col, y):
        self.d = drawer
        self.page = page
        self.col = col
        self.y = y

    def par(self, segs, size=BODY, lh=LH, indent=10.0, align='justify'):
        x0, x1 = COL[self.col]
        width = x1 - x0
        words = []
        for seg in segs:
            t, f, c = seg[0], seg[1], seg[2]
            dy = seg[3] if len(seg) > 3 else 0.0
            mult = seg[4] if len(seg) > 4 else 1.0
            for w in t.split(' '):
                if w:
                    words.append({'t': w, 'f': f, 'c': c, 'dy': dy, 'mult': mult})

        def wlen(w):
            return tlen(w['t'], w['f'], size * w['mult'])

        lines = [[]]
        wsum = 0.0
        for wd in words:
            wl = wlen(wd)
            lim = width - (indent if len(lines) == 1 else 0.0)
            if lines[-1] and wsum + wl > lim + 0.5:
                lines.append([])
                wsum = 0.0
            lines[-1].append(wd)
            wsum += wl + tlen(' ', wd['f'], size)
        for li, line in enumerate(lines):
            base = self.y + 0.8 * size
            ind = indent if li == 0 else 0.0
            nat = (sum(wlen(w) for w in line)
                   + tlen(' ', line[0]['f'], size) * (len(line) - 1))
            extra = 0.0
            if align == 'justify' and li < len(lines) - 1 and len(line) > 1:
                extra = max(0.0, min(3.0, (width - ind - nat) / (len(line) - 1)))
            cur = x0 + ind
            for w in line:
                sz = size * w['mult']
                self.d.font(w['f'])
                self.page.insert_text((cur, base + w['dy'] * size), w['t'],
                                      fontname=w['f'], fontsize=sz, color=w['c'])
                if w['c'] == BLUE:
                    self.d.blue_rects.append((self.d.pno, fitz.Rect(
                        cur, base + w['dy'] * size - sz * 0.25,
                        cur + wlen(w), base + w['dy'] * size + sz * 0.25)))
                cur += wlen(w) + tlen(' ', w['f'], size) + extra
            self.y += lh
        self.y += 0.45 * size

    def heading(self, text, size=14.0):
        self.y += 6.0
        self.d.text(COL[self.col][0], self.y, text, 'TMB', size)
        self.y += size * 1.35


def main():
    doc = fitz.open()

    # ---------------- 第 1 页 ----------------
    doc.new_page(width=W, height=H)
    p1 = doc[0]          # 1.27 起 new_page 返回的页对象引用会失效, 必须按索引重取
    d1 = Drawer(p1, 0)

    # arXiv 式竖排印章 (引擎必须原样保留)
    d1.font('TMR')
    p1.insert_text((27.0, 560.0), 'arXiv:2601.00001v1  [cs.CV]  13 Sep 2026',
                   fontname='TMR', fontsize=9, rotate=90)

    d1.centered(132.0, [('SampleTrack: A Minimal Fixture Paper for Paper Translation',
                         'TMR', BLACK)], 15.0)
    d1.centered(158.0, [('Zhang San', 'TMR', BLACK),
                        ('1', 'TMR', BLACK, -0.33, 0.72),
                        (',  Si Li', 'TMR', BLACK),
                        ('1', 'TMR', BLACK, -0.33, 0.72),
                        ('  and  Wu Wang', 'TMR', BLACK),
                        ('1', 'TMR', BLACK, -0.33, 0.72)], 12.0)
    d1.centered(177.0, [('1', 'TMR', BLACK, -0.33, 0.72),
                        ('Department of Computer Vision, Sample University, Exampleville 100000',
                         'TMR', BLACK)], 9.0)

    d1.centered(203.0, [('Abstract', 'TMB', BLACK)], 9.0)

    class WideFlow(Flow):
        """整宽摘要"""
        def par(self, segs, **k):
            old = COL[self.col]
            COL[self.col] = (91.0, 497.0)
            super().par(segs, size=9.0, lh=11.0, indent=0.0, **k)
            COL[self.col] = old

    wf = WideFlow(d1, p1, 0, 214.0)
    wf.par([
        ('This fixture paper exists to exercise every feature of the bilingual-paper-pdf '
         'engine: two-column typesetting, a booktabs table, a numbered equation, a vector '
         'figure with colored boxes, author-year citations in hyperref blue, footnotes and '
         'a vertical side stamp. We propose SampleTrack ', 'TMR', BLACK),
        ('(Chen et al. 2021;', 'TMR', BLUE),
        (' Li et al. 2018)', 'TMR', BLUE),
        (', a minimal memory-based tracker that localizes targets by nearest-neighbor '
         'lookup in a tiny memory bank. On three synthetic benchmarks SampleTrack improves '
         'the tracking quality by 12% over the baseline while using 6.5\u00d7 fewer parameters. '
         'The paper is generated by example/make_sample_paper.py and can be regenerated at '
         'any time. Code at ', 'TMR', BLACK),
        ('https://github.com/example/sampletrack', 'TMR', BLUE),
        ('.', 'TMR', BLACK),
    ])
    d1.text(91.0, wf.y + 8.0, 'Keywords: ', 'TMB', 8.0)
    d1.text(91.0 + 38.0, wf.y + 8.0,
            'object tracking, bilingual translation, reproducible fixtures', 'TMR', 8.0)

    # 左栏: 1 Introduction
    c0 = Flow(d1, p1, 0, 320.0)
    c0.heading('1  Introduction', 14.0)
    c0.par([
        ('General visual object tracking is a core task in computer vision. '
         'Memory-based methods', 'TMR', BLACK),
        ('1', 'TMR', BLACK, -0.33, 0.72),
        (' store past frames and localize the target by pixel association '
         '(Chen et al. 2021; Li et al. 2018). Over the past decade this family '
         'of methods has grown steadily stronger.', 'TMR', BLACK),
    ])
    c0.par([
        ('A key challenge is the', 'TMR', BLACK),
        (' distractor', 'TMI', BLACK),
        (': a nearby object that visually resembles the target. Distractors '
         'increase localization uncertainty and mislead the tracker into '
         'irreversible drift (Li et al. 2018).', 'TMR', BLACK),
    ])
    c0.par([
        ('In this paper we make three contributions. First, we formulate a '
         'minimal memory model that is small enough to inspect by eye. Second, '
         'we design this fixture so that every layout feature of a real paper '
         'appears at least once. Third, we release everything under a permissive '
         'license so that the fixture can travel with the toolchain.', 'TMR', BLACK),
    ])

    # 脚注 (考脚注槽位)
    p1.draw_line((67.0, 708.0), (200.0, 708.0), width=0.6)
    d1.text(67.0, 718.0, '1', 'TMR', 7.0)
    d1.text(72.0, 718.0, 'This fixture paper is synthetic; all numbers are placeholders '
            'and carry no scientific meaning.', 'TMR', 7.0)

    # 右栏 (两栏正文都在摘要块下方开始, 与左栏同一起点)
    c1 = Flow(d1, p1, 1, 320.0)
    c1.par([
        ('Nevertheless, a substantial source of failures remains nearby objects '
         'that visually resemble the tracked one. These regions increase the '
         'localization uncertainty and mislead the tracker. Distractors can be '
         'classified as external, or internal when only a part of the target is '
         'being tracked (Chen et al. 2021).', 'TMR', BLACK),
    ])
    c1.heading('2  Related work', 14.0)
    c1.par([
        ('Early deep trackers fine-tuned pre-trained networks during inference '
         '(Danelljan et al. 2019). Siamese trackers removed online training by '
         'template matching (Li et al. 2018), trading robustness for speed.', 'TMR', BLACK),
    ])
    c1.par([
        ('Memory-based frameworks localize the target by associating current '
         'features with stored past frames (Chen et al. 2021). Our fixture '
         'follows this line while keeping the memory tiny.', 'TMR', BLACK),
    ])

    # 页码 (考 folio 过滤)
    d1.text(W / 2 - 3.0, 792.0, '1', 'TMR', BODY)

    # ---------------- 第 2 页 ----------------
    doc.new_page(width=W, height=H)
    p2 = doc[1]
    d2 = Drawer(p2, 1)
    d2.font('TMR')
    p2.insert_text((27.0, 560.0), 'arXiv:2601.00001v1  [cs.CV]  13 Sep 2026',
                   fontname='TMR', fontsize=9, rotate=90)

    # ---- 图 1: 矢量框图 (两个面板, 黄底框, 同名标签) ----
    def panel(x0):
        p2.draw_rect(fitz.Rect(x0, 84, x0 + 100, 148), color=(0.2, 0.2, 0.2), width=0.8)
        p2.draw_rect(fitz.Rect(x0 + 8, 94, x0 + 44, 116), fill=(0.85, 0.93, 0.85),
                     color=(0.2, 0.4, 0.2), width=0.7)
        p2.insert_text((x0 + 13, 107.5), 'Encoder', fontname='helv', fontsize=6.3)
        p2.draw_rect(fitz.Rect(x0 + 58, 94, x0 + 94, 116), fill=(1, 1, 0.8),
                     color=(0.2, 0.2, 0.2), width=0.7)
        p2.insert_text((x0 + 61, 103.5), 'Memory', fontname='helv', fontsize=6.3)
        p2.insert_text((x0 + 61, 112.5), 'bank', fontname='helv', fontsize=6.3)
        p2.draw_line((x0 + 44, 105), (x0 + 58, 105), color=(0.2, 0.2, 0.2), width=0.8)
        p2.draw_line((x0 + 26, 116), (x0 + 26, 132), color=(0.2, 0.2, 0.2), width=0.8)
        p2.draw_line((x0 + 26, 132), (x0 + 76, 132), color=(0.2, 0.2, 0.2), width=0.8)
        p2.draw_line((x0 + 76, 132), (x0 + 76, 116), color=(0.2, 0.2, 0.2), width=0.8)
        p2.insert_text((x0 + 40, 143.5), 'Mask', fontname='helv', fontsize=6.3)

    panel(75.0)
    panel(190.0)
    p2.insert_text((147.0, 70.0), 'SampleTrack pipeline', fontname='helv', fontsize=6.3)

    fl2 = Flow(d2, p2, 0, 160.0)
    fl2.par([('Fig. 1', 'TMB', BLACK),
             ('  Overview of the SampleTrack pipeline. Both panels contain an Encoder '
              'and a Memory bank; the yellow box is always updated while the green box '
              'is written once.', 'TMR', BLACK)], size=8.0, lh=9.5, indent=0.0)

    # ---- 3 Method + 编号公式 ----
    c0 = Flow(d2, p2, 0, 205.0)
    c0.heading('3  Method', 14.0)
    c0.par([
        ('SampleTrack keeps the most recent frame and a fixed prototype in a '
         'tiny memory bank. The tracking quality is scored by a weighted mix '
         'of robustness and accuracy:', 'TMR', BLACK),
    ])
    # 公式: 居中, CMMI10 (改名斜体) + 尾部编号 (1) —— 引擎判为公式行, 原样保留
    eq_pieces = [('Q', 'CMMI10'), (' = ', 'TMR'), ('\u03b1', 'CMMI10'),
                 (' \u00b7 R + (1 \u2212 ', 'TMR'), ('\u03b1', 'CMMI10'),
                 (') \u00b7 A', 'TMR')]
    eq_w = sum(tlen(t, f, 9.96) for t, f in eq_pieces)
    x0, x1 = COL[0]
    cur = (x0 + x1) / 2 - eq_w / 2
    eq_base = c0.y + 12.0
    for t, f in eq_pieces:
        d2.font(f)
        p2.insert_text((cur, eq_base), t, fontname=f, fontsize=9.96)
        cur += tlen(t, f, 9.96)
    d2.font('CMR10')
    p2.insert_text((x1 - 24.0, eq_base), '(1)', fontname='CMR10', fontsize=9.96)
    c0.y = eq_base + 6.0
    c0.par([
        ('where R is the fraction of successfully tracked frames and A is the '
         'average overlap during successful tracking. The weight is fixed to '
         '0.2 in all experiments, and no per-dataset tuning is performed '
         '(Chen et al. 2021).', 'TMR', BLACK),
    ])

    # ---- 右栏: 4 Experiments + 表 1 + 5 Conclusion + References ----
    c1 = Flow(d2, p2, 1, TOP)
    c1.heading('4  Experiments', 14.0)
    c1.par([
        ('We evaluate on three synthetic benchmarks. Table 1 reports the '
         'tracking quality; the best result of each column is marked in bold.', 'TMR', BLACK),
    ])

    # 表注在表上方 (Springer 风格)
    tflow = Flow(d2, p2, 1, c1.y + 4.0)
    tflow.par([('Table 1', 'TMB', BLACK),
               ('  Tracking quality on synthetic benchmarks. Best in bold.', 'TMR', BLACK)],
              size=8.0, lh=9.5, indent=0.0)
    ty0 = tflow.y + 4.0
    rx0, rx1 = COL[1]
    p2.draw_line((rx0 + 6, ty0), (rx1 - 6, ty0), width=0.8)
    hdr_y = ty0 + 9.6
    d2.text(rx0 + 12, hdr_y, 'Method', 'TMB', 8.0)
    d2.text(rx1 - 66, hdr_y, 'Quality', 'TMB', 8.0)
    d2.text(rx1 - 26, hdr_y, 'EAO', 'TMB', 8.0)
    p2.draw_line((rx0 + 6, hdr_y + 2.6), (rx1 - 6, hdr_y + 2.6), width=0.5)
    rows = [('Baseline', '0.610', '0.590'), ('Ours-S', '0.673', '0.648'),
            ('Ours-B', '0.694', '0.671'), ('Ours-L', '0.701', '0.680')]
    ry = hdr_y + 10.5
    for i, (m, q, e) in enumerate(rows):
        f = 'TMB' if i >= 2 else 'TMR'
        d2.text(rx0 + 12, ry, m, f, 8.0)
        d2.text(rx1 - 66, ry, q, f, 8.0)
        d2.text(rx1 - 26, ry, e, f, 8.0)
        ry += 9.9
    p2.draw_line((rx0 + 6, ry - 1.0), (rx1 - 6, ry - 1.0), width=0.8)
    table_y1 = ry - 1.0

    c1 = Flow(d2, p2, 1, ry + 12.0)
    c1.heading('5  Conclusion', 14.0)
    c1.par([
        ('We introduced SampleTrack, a minimal fixture for exercising the '
         'bilingual-paper-pdf engine. The fixture is regenerated by a single '
         'script and ships with a reference Chinese translation.', 'TMR', BLACK),
    ])

    # References (右栏底部, 引擎用 keep_ranges 原样保留)
    c1.heading('References', 14.0)
    ref_y0 = c1.y
    refs = [
        'Chen X, Yan B, Zhu J, et al (2021) Transformer tracking. In: CVPR, pp 8126-8135',
        'Danelljan M, Bhat G, Khan FS, et al (2019) ATOM: Accurate tracking by overlap '
        'maximization. In: CVPR',
        'Li P, Wang D, Wang L, et al (2018) Deep visual tracking: review and experimental '
        'comparison. Pattern Recognit 76:323-338',
        'Zhang S, Li S, Wang W (2026) SampleTrack: a minimal fixture paper. arXiv:2601.00001',
    ]
    rf = Flow(d2, p2, 1, ref_y0)
    for r in refs:
        rf.par([(r, 'TMR', BLACK)], size=8.5, lh=10.0, indent=0.0, align='left')
    ref_y1 = rf.y

    # 链接: 蓝色引用 -> 参考文献; d1 最后一个蓝色词是 URL -> 外链
    # (页对象引用在 1.27 会失效, 一律按页号重取)
    target = fitz.Point(305, ref_y0 + 4)
    for pno, r in d1.blue_rects[:-1] + d2.blue_rects:
        doc[pno].insert_link({'kind': fitz.LINK_GOTO, 'from': r, 'page': 1, 'to': target})
    url_pno, url_r = d1.blue_rects[-1]
    doc[url_pno].insert_link({'kind': fitz.LINK_URI, 'from': url_r,
                              'uri': 'https://github.com/example/sampletrack'})

    d2.text(W / 2 - 3.0, 792.0, '2', 'TMR', BODY)

    doc.save(OUT)
    print(f'-> {OUT}  {len(doc)} 页')
    print(f'布局参考 (给 content.json 用):')
    print(f'  公式基线 y={eq_base:.1f}  表格 y=[{ty0:.1f},{table_y1:.1f}]  '
          f'参考文献 y=[{ref_y0:.1f},{ref_y1:.1f}]')


if __name__ == '__main__':
    main()
