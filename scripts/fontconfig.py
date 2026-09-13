# -*- coding: utf-8 -*-
"""fontconfig.py — 字体定位与解析 (build_solo / setup_fonts / check_release 共用)

仓库 fonts/ 内是可再分发的 OFL 字体 (见 LICENSE-FONTS.md); Times 系与符号字体
是系统自带的专有字体, 按平台候选列表探测, 找不到时由字形回退链兜底。
"""
import os

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_fonts_dir(repo_dir=REPO_DIR):
    """仓库字体目录优先 fonts/, 兼容旧布局 _fonts/"""
    for name in ('fonts', '_fonts'):
        p = os.path.join(repo_dir, name)
        if os.path.isdir(p):
            return p
    return os.path.join(repo_dir, 'fonts')


def _win_fonts_dir():
    return os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')


def system_font_candidates():
    win = _win_fonts_dir()
    return {
        'SYM': [os.path.join(win, 'seguisym.ttf'),
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                '/System/Library/Fonts/Supplemental/Arial Unicode.ttf'],
        'TMR': [os.path.join(win, 'times.ttf'),
                '/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf',
                '/System/Library/Fonts/Supplemental/Times New Roman.ttf',
                '/System/Library/Fonts/Supplemental/Liberation Serif.ttf'],
        'TMB': [os.path.join(win, 'timesbd.ttf'),
                '/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf',
                '/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf'],
        'TMI': [os.path.join(win, 'timesi.ttf'),
                '/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf',
                '/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf'],
        'TMBI': [os.path.join(win, 'timesbi.ttf'),
                 '/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf',
                 '/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf',
                 '/System/Library/Fonts/Supplemental/Times New Roman Bold Italic.ttf'],
    }


def font_spec(fonts_dir):
    return {
        'NSR': [os.path.join(fonts_dir, 'NotoSerifSC-Regular.ttf')],
        'NSB': [os.path.join(fonts_dir, 'NotoSerifSC-Bold.ttf')],
        'CMI': [os.path.join(fonts_dir, 'CMU-Italic.otf')],
        **system_font_candidates()
    }


def resolve_fonts(fonts_dir):
    """-> ({key: fitz.Font}, {key: path}); 缺关键字体时抛 SystemExit"""
    import fitz
    fonts, files, missing = {}, {}, []
    for k, cands in font_spec(fonts_dir).items():
        for p in cands:
            if os.path.exists(p):
                try:
                    fonts[k] = fitz.Font(fontfile=p)
                    files[k] = p
                    break
                except Exception:
                    continue
        else:
            missing.append(k)
    if missing:
        raise SystemExit(f'字体缺失: {missing} — 先运行 scripts/setup_fonts.py')
    return fonts, files
