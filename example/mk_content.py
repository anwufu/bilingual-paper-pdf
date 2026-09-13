# -*- coding: utf-8 -*-
"""mk_content.py — 由 worksheet + zones + 译文 生成 example/content.json"""
import json

ws = json.load(open('example/src/_tmp/worksheet.json', encoding='utf-8'))
zones = json.load(open('example/src/_tmp/zones.json', encoding='utf-8'))

CN = {
 'p1-c0-0': 'SampleTrack：一篇用于论文翻译测试的最小样张',
 'p1-c0-1': '张三^{1}、李四^{1} 和 王五^{1}',
 'p1-c0-2': '^{1}示例大学计算机视觉系，示例市 100000',
 'p1-c0-3': '摘要',
 'p1-c0-4': ('本文这篇样张的存在目的，是让 bilingual-paper-pdf 引擎的每一项特性都得到演练：'
             '双栏排版、书板表格、编号公式、带彩色框的矢量插图、hyperref 蓝色的作者-年份引用、'
             '脚注以及竖排侧边印章。我们提出 SampleTrack [[（Chen 等 2021; Li 等 2018）]]，'
             '一个极小的基于记忆的跟踪器，它通过在一个微型记忆库中做最近邻查找来定位目标。'
             '在三个合成基准上，SampleTrack 以少 6.5 倍的参数量将跟踪质量比基线提升 12%。'
             '本文由 example/make_sample_paper.py 生成，可随时重新生成。代码见 '
             '[[https://github.com/example/sampletrack]]。'),
 'p1-c0-5': '**关键词：** 目标跟踪、双语翻译、可复现样张',
 'p1-c0-6': '1  引言',
 'p1-c0-7': ('通用视觉目标跟踪是计算机视觉中的一项核心任务。基于记忆的方法^{1}存储过往帧，'
             '并通过像素关联来定位目标[[（Chen 等 2021; Li 等 2018）]]。过去十年间，'
             '这一方法家族稳步壮大。'),
 'p1-c0-8': ('一个关键挑战是干扰物——视觉上与目标相似的邻近物体。干扰物会增大定位的不确定性，'
             '并误导跟踪器发生不可逆的漂移[[（Li 等 2018）]]。'),
 'p1-c0-9': ('本文做出三点贡献。第一，我们提出一个肉眼即可审查的极小记忆模型。'
             '第二，我们把这份样张设计成真实论文的每一种版面特性都至少出现一次。'
             '第三，我们以宽松许可发布全部内容，让样张能随工具链一同传播。'),
 'p1-c0-10': '^{1}本样张论文为合成产物；所有数字均为占位符，不含任何科学含义。',
 'p1-c1-0': ('然而，跟踪失败的一个主要来源，仍然是那些在视觉上与被跟踪目标相似的邻近物体。'
             '这些区域会增大定位的不确定性并误导跟踪器。干扰物可分为外部干扰物，'
             '以及仅跟踪目标一部分时出现的内部干扰物[[（Chen 等 2021）]]。'),
 'p1-c1-1': '2  相关工作',
 'p1-c1-2': ('早期的深度跟踪器在推理阶段微调预训练网络[[（Danelljan 等 2019）]]。'
             '孪生跟踪器以模板匹配取消了在线训练[[（Li 等 2018）]]，用鲁棒性换取了速度。'),
 'p1-c1-3': ('基于记忆的框架通过把当前特征与存储的历史帧相关联来定位目标[[（Chen 等 2021）]]。'
             '本文样张沿用这一路线，但把记忆做得极小。'),
 'p2-c0-0': ('图 1  SampleTrack 流程概览。两个面板都包含一个编码器和一个记忆库；'
             '黄色框始终更新，绿色框只写入一次。'),
 'p2-c0-1': '3  方法',
 'p2-c0-2': ('SampleTrack 在一个微型记忆库中保留最近一帧和一个固定原型。'
             '跟踪质量由鲁棒性与准确度的加权混合来评分：'),
 'p2-c0-3': ('其中 R 是成功跟踪帧的占比，A 是成功跟踪期间的平均重叠。所有实验中权重固定为 0.2，'
             '不做任何按数据集的调优[[（Chen 等 2021）]]。'),
 'p2-c1-0': '4  实验',
 'p2-c1-1': '我们在三个合成基准上做评估。表 1 报告跟踪质量；每列最优结果以粗体标出。',
 'p2-c1-2': '表 1  合成基准上的跟踪质量。最优以粗体标出。',
 'p2-c1-3': '5  结论',
 'p2-c1-4': '我们提出了 SampleTrack——一个用于演练本引擎的最小样张。它由单个脚本再生成，并随附参考中文译文。',
 'p2-c1-5': '参考文献',
}

OVERLAYS = [
    # 图 1 内标签 (两个面板 → all)
    {'page': 2, 'find': 'SampleTrack pipeline', 'cn': 'SampleTrack 流程图'},
    {'page': 2, 'find': 'Encoder', 'cn': '编码器', 'all': True, 'align': 'left'},
    {'page': 2, 'find': 'Memory', 'cn': '记忆', 'all': True, 'align': 'left'},
    {'page': 2, 'find': 'bank', 'cn': '库', 'all': True, 'align': 'left'},
    {'page': 2, 'find': 'Mask', 'cn': '掩码', 'all': True},
    # 表 1 表头 (EAO 为缩写, 保留)
    {'page': 2, 'find': 'Method', 'cn': '方法'},
    {'page': 2, 'find': 'Quality', 'cn': '质量'},
]

slots = []
for s in ws['slots']:
    if s['id'] in ('p2-c1-6', 'p2-c1-7', 'p2-c1-8', 'p2-c1-9'):
        continue                      # 参考文献条目保留英文
    slots.append(dict(s, cn=CN[s['id']]))

content = {
    'src': 'example/sample_paper.pdf',
    'extra_zones': zones,
    'cite_color': '#0000ff',
    'text_colors': [
        {'re': r'https?://[^\s，。、；]+', 'color': '#0000ff'},
    ],
    'keep_ranges': [
        # 参考文献区 (右下): 条目按惯例保留英文原样, 不抹白
        {'page': 2, 'y0': 325.0, 'y1': 445.0, 'x0': 300.0, 'x1': 530.0},
    ],
    'slots': slots,
    'overlays': OVERLAYS,
    'linkify': {'apply': True},
}
json.dump(content, open('example/content.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print(f"example/content.json: {len(slots)} 槽位, {len(OVERLAYS)} overlays, "
      f"{len(zones)} 保留区")
