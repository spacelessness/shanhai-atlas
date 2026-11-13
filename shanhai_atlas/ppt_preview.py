# -*- coding: utf-8 -*-
"""PPT 版面预览（无 PowerPoint / LibreOffice 环境下的近似渲染，用于 QA）。

按 python-pptx 读到的几何绘制：背景、矩形 / 圆角矩形、连线、文本框（用 Shanhai Atlas 排版引擎按
真实字形断行，中文用思源黑体近似微软雅黑）、图片（PNG 回退图）。只用于检查版面几何、
文字是否溢出文本框，不代表 PowerPoint 的最终渲染。

    python -m shanhai_atlas preview deck.pptx out_dir/
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN

from .canvas import Canvas
from .fonts import FONT

EMU_IN = 914400.0


def _in(v):
    return (v or 0) / EMU_IN


def _hex(c, default=None):
    try:
        if c is not None and c.type is not None:
            return "#" + str(c.rgb)
    except Exception:
        pass
    return default


def _fill(shape):
    try:
        f = shape.fill
        if f.type == 1:                      # MSO_FILL.SOLID
            return _hex(f.fore_color)
    except Exception:
        pass
    return None


def _line(shape):
    try:
        ln = shape.line
        if ln.fill.type == 1:
            return _hex(ln.color), (ln.width.pt if ln.width else 0.75)
    except Exception:
        pass
    return None, 0


def _text(cv, shape, x, y, w, h, overflow):
    tf = shape.text_frame
    ml, mr = _in(tf.margin_left), _in(tf.margin_right)
    mt, mb = _in(tf.margin_top), _in(tf.margin_bottom)
    bx, bw = x + ml, max(w - ml - mr, 0.05)
    paras = []
    for p in tf.paragraphs:
        runs, size = [], None
        for r in p.runs:
            f = r.font
            sz = f.size.pt if f.size else 18.0
            size = size or sz
            col = _hex(f.color, "#2A3342") if f.color and f.color.type else "#2A3342"
            fam = FONT.serif if (f.name or "") in ("Georgia", "Times New Roman") else None
            runs.append((r.text, dict(size=sz, weight=700 if f.bold else 400, color=col,
                                      style="italic" if f.italic else "normal", family=fam)))
        size = size or 12.0
        ls = p.line_spacing if isinstance(p.line_spacing, float) else 1.0
        sa = p.space_after.pt / 72 if p.space_after is not None else 0.0
        al = {PP_ALIGN.CENTER: "center", PP_ALIGN.RIGHT: "right"}.get(p.alignment, "left")
        paras.append((runs, size, ls, sa, al))
    total = 0.0
    heights = []
    for runs, size, ls, sa, al in paras:
        txt = [(t, st) for t, st in runs if t] or [(" ", dict(size=size))]
        hh, _ = cv.measure(bw, txt, size=size, leading=1.2 * ls) if tf.word_wrap is not False \
            else (size / 72 * 1.2 * ls, 1)
        heights.append(hh)
        total += hh + sa
    anchor = tf.vertical_anchor
    yy = y + mt
    if anchor == MSO_ANCHOR.MIDDLE:
        yy = y + (h - total) / 2
    elif anchor == MSO_ANCHOR.BOTTOM:
        yy = y + h - mb - total
    if total > h + 0.02 and tf.word_wrap is not False:
        overflow.append((shape.name, round(total, 2), round(h, 2)))
    for (runs, size, ls, sa, al), hh in zip(paras, heights):
        txt = [(t, st) for t, st in runs if t]
        if txt:
            width = bw if tf.word_wrap is not False else 99.0
            if tf.word_wrap is False and al != "left":
                width = bw
            cv.para(bx, yy, width, txt, size=size, leading=1.2 * ls, align=al, z=6)
        yy += hh + sa


def render_slide(slide, out_png, prs_w=13.333, prs_h=7.5, dpi=110):
    cv = Canvas(prs_w, prs_h, dpi=dpi)
    overflow = []
    try:
        bg = slide.background.fill
        if bg.type == 1:
            cv.rect(0, 0, prs_w, prs_h, r=0, fc=_hex(bg.fore_color), z=0)
    except Exception:
        pass
    for z, shp in enumerate(slide.shapes):
        x, y, w, h = _in(shp.left), _in(shp.top), _in(shp.width), _in(shp.height)
        zz = 1 + z * 0.01
        if shp.shape_type == MSO_SHAPE_TYPE.PICTURE:
            img = np.asarray(Image.open(io.BytesIO(shp.image.blob)).convert("RGB"))
            cv.ax.imshow(img, extent=(x, x + w, y + h, y), zorder=zz, aspect="auto",
                         interpolation="bilinear")
            continue
        if shp.shape_type == MSO_SHAPE_TYPE.LINE or shp.__class__.__name__ == "Connector":
            col, lw = _line(shp)
            cv.line([_in(shp.begin_x), _in(shp.end_x)], [_in(shp.begin_y), _in(shp.end_y)],
                    color=col or "#D9DEE5", lw=lw, z=zz)
            continue
        fc = _fill(shp)
        ec, lw = _line(shp)
        if fc or ec:
            r = 0.0
            try:
                if "ROUNDED" in str(shp.auto_shape_type):
                    r = shp.adjustments[0] * min(w, h)
            except Exception:
                pass
            cv.rect(x, y, w, h, r=r, fc=fc or "none", ec=ec or "none", lw=lw, z=zz)
        if shp.has_text_frame and shp.text_frame.text.strip():
            _text(cv, shp, x, y, w, h, overflow)
    cv.ax.set_xlim(0, prs_w)
    cv.ax.set_ylim(prs_h, 0)
    cv.fig.savefig(out_png, dpi=dpi)
    cv.close()
    return overflow


def preview(pptx_path, out_dir, dpi=110):
    """渲染全部页面为 PNG；返回 {页码: 溢出文本框列表}。"""
    prs = Presentation(str(pptx_path))
    W, H = prs.slide_width / EMU_IN, prs.slide_height / EMU_IN
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = {}
    for i, s in enumerate(prs.slides, 1):
        ov = render_slide(s, out / f"p{i:02d}.png", W, H, dpi)
        if ov:
            report[i] = ov
    return report
