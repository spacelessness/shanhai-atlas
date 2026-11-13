# -*- coding: utf-8 -*-
"""同风格 PPT：python-pptx 原生页面 + 矢量图嵌入（需 pip install python-pptx）。

* 页面模板：封面 / 章节 / 图页 / 卡片页 / 要点页 / 表格页 / KPI 页 / 结束页，
  页眉（古铜金小标 + 黛蓝标题 + 金色题线）与页脚（页码 Georgia 金色）同 HXM 汇报设计系统。
* 图：``add_image()`` 把 Shanhai Atlas 输出的 SVG 以矢量形式嵌入（PowerPoint 2016/365 原生 svgBlip），
  同时附 PNG 回退（旧版 Office / WPS 显示 PNG）；按 contain 等比放入指定框。
* 讲稿：每页可写入演讲者备注（notes），图、文、讲稿一次生成。

    from shanhai_atlas.ppt import Deck
    deck = Deck(footer="项目名称 · 结题汇报")
    deck.cover("主标题", "副标题", meta="单位 · 2026 年 10 月")
    deck.figure("模型结构", "gallery/ex01.svg", kicker="技术路线", notes="讲稿……")
    deck.save("output/demo.pptx")
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import Part
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

from .theme import C

SVG_EXT_URI = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}"
SVG_NS = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"

SLIDE_W, SLIDE_H = 13.333, 7.5
MARGIN = 0.55
CONTENT_W = SLIDE_W - 2 * MARGIN
TAG_Y, TAG_H = 0.30, 0.24
TITLE_Y, TITLE_H = 0.56, 0.55
RULE_Y = 1.13
CT, CB = 1.36, 6.50                 # 内容区顶 / 底（英寸）
SRC_Y = 6.58
FOOT_LN_Y, FOOT_Y = 7.00, 7.07


def rgb(hex_color):
    h = hex_color.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


K = {k: rgb(v) for k, v in C.items()}
CREAM, CREAM_DIM = rgb("#E8E4D8"), rgb("#9FA8BC")
DEFAULT_FONTS = dict(ea="微软雅黑", latin="微软雅黑", serif="Georgia")


# ================================================================ 基础图元
class Kit:
    """底层图元（字体可配置）：tx / tb / rect / line_h / chip / bullets / card / table。"""

    def __init__(self, fonts=None):
        self.f = {**DEFAULT_FONTS, **(fonts or {})}

    def style_run(self, r, size=12, color=K["ink"], bold=False, italic=False, ea=None,
                  latin=None, spc=None):
        f = r.font
        f.size = Pt(size)
        f.bold = bold
        f.italic = italic
        f.color.rgb = color
        f.name = latin or self.f["latin"]
        rPr = r._r.get_or_add_rPr()
        el = rPr.find(qn("a:ea"))
        if el is None:
            el = rPr.makeelement(qn("a:ea"), {})
            rPr.append(el)
        el.set("typeface", ea or self.f["ea"])
        if spc is not None:
            rPr.set("spc", str(int(spc)))

    def tb(self, slide, x, y, w, h, paras, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, wrap=True,
           line_spacing=1.0, space_after=0.0):
        """文本框：paras = [runs | (runs, align, space_after, line_spacing)]；
        runs = [dict(t=, size=, color=, bold=, italic=, latin=, ea=, spc=)]。"""
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = box.text_frame
        tf.word_wrap = wrap
        tf.vertical_anchor = anchor
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        for i, p in enumerate(paras):
            if isinstance(p, tuple):
                runs = p[0]
                p_al = p[1] if len(p) > 1 else align
                p_sp = p[2] if len(p) > 2 else space_after
                p_ls = p[3] if len(p) > 3 else line_spacing
            else:
                runs, p_al, p_sp, p_ls = p, align, space_after, line_spacing
            para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            para.alignment = p_al
            para.space_after = Pt(p_sp)
            if p_ls:
                para.line_spacing = p_ls
            for rd in runs:
                r = para.add_run()
                r.text = rd["t"]
                self.style_run(r, size=rd.get("size", 12), color=rd.get("color", K["ink"]),
                               bold=rd.get("bold", False), italic=rd.get("italic", False),
                               ea=rd.get("ea"), latin=rd.get("latin"), spc=rd.get("spc"))
        return box

    def tx(self, slide, x, y, w, h, text, size=12, color=K["ink"], bold=False, italic=False,
           align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, latin=None, wrap=True, line_spacing=1.0,
           spc=None):
        return self.tb(slide, x, y, w, h, [[dict(t=text, size=size, color=color, bold=bold,
                                                  italic=italic, latin=latin, spc=spc)]],
                       align=align, anchor=anchor, wrap=wrap, line_spacing=line_spacing)

    def rect(self, slide, x, y, w, h, fill=None, line=None, lw=0.75, round_=None):
        shp = MSO_SHAPE.ROUNDED_RECTANGLE if round_ else MSO_SHAPE.RECTANGLE
        s = slide.shapes.add_shape(shp, Inches(x), Inches(y), Inches(w), Inches(h))
        if round_ is not None:
            try:
                s.adjustments[0] = round_
            except Exception:
                pass
        if fill is None:
            s.fill.background()
        else:
            s.fill.solid()
            s.fill.fore_color.rgb = fill
        if line is None:
            s.line.fill.background()
        else:
            s.line.color.rgb = line
            s.line.width = Pt(lw)
        s.shadow.inherit = False
        return s

    def line_h(self, slide, x, y, w, color=K["line"], weight=0.75):
        ln = slide.shapes.add_connector(1, Inches(x), Inches(y), Inches(x + w), Inches(y))
        ln.line.color.rgb = color
        ln.line.width = Pt(weight)
        return ln

    def chip(self, slide, x, y, w, h, text, size=9, fg=K["navy"], bg=None, line_c=None,
             bold=False, round_=0.5):
        s = self.rect(slide, x, y, w, h, fill=bg, line=line_c, round_=round_)
        tf = s.text_frame
        tf.word_wrap = False
        tf.margin_left = tf.margin_right = Inches(0.02)
        tf.margin_top = tf.margin_bottom = 0
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = text
        self.style_run(r, size=size, color=fg, bold=bold)
        return s

    def bullets(self, slide, x, y, w, h, items, size=12.5, gap=7.5, color=K["ink"], mark="◆",
                mark_color=K["gold"], lead_color=K["navy"], line_spacing=1.12):
        """菱形要点：item 为 str 或 (加粗引导语, 正文)。"""
        paras = []
        for it in items:
            runs = [dict(t=mark + "  ", size=size - 3.5, color=mark_color, bold=True)]
            if isinstance(it, tuple):
                runs += [dict(t=it[0], size=size, color=lead_color, bold=True),
                         dict(t=it[1], size=size, color=color)]
            else:
                runs.append(dict(t=it, size=size, color=color))
            paras.append((runs, PP_ALIGN.LEFT, gap, line_spacing))
        return self.tb(slide, x, y, w, h, paras, line_spacing=line_spacing)

    def card(self, slide, x, y, w, h, title=None, body=None, fill=K["card"], accent=K["gold"],
             title_size=13.5, body_size=11):
        self.rect(slide, x, y, w, h, fill=fill, round_=0.045)
        self.line_h(slide, x + 0.16, y + 0.14, 0.34, accent, 2.0)
        yy = y + 0.24
        if title:
            self.tx(slide, x + 0.16, yy, w - 0.32, 0.32, title, size=title_size, color=K["navy"],
                    bold=True)
            yy += 0.38
        if body is not None:
            if isinstance(body, (list, tuple)):
                self.bullets(slide, x + 0.16, yy, w - 0.32, y + h - yy - 0.1, body, size=body_size,
                             gap=4.5)
            else:
                self.tx(slide, x + 0.16, yy, w - 0.32, y + h - yy - 0.1, body, size=body_size,
                        line_spacing=1.15)
        return yy

    def table(self, slide, x, y, w, cols, rows, row_h=0.42, head_size=10.5, cell_size=10,
              zebra=True, aligns=None):
        """学术表格：表头金色细线 + 行分隔细线 + 隔行浅底；cols = [(表头, 宽占比)]。"""
        total = sum(c[1] for c in cols)
        xs = [x]
        for _, cw in cols:
            xs.append(xs[-1] + w * cw / total)
        if zebra:
            for i in range(len(rows)):
                if i % 2 == 1:
                    self.rect(slide, x, y + 0.40 + i * row_h, w, row_h, fill=K["card"])
        for j, (name, _) in enumerate(cols):
            al = aligns[j] if aligns else PP_ALIGN.LEFT
            self.tx(slide, xs[j] + 0.08, y, xs[j + 1] - xs[j] - 0.12, 0.36, name, size=head_size,
                    color=K["navy"], bold=True, align=al, anchor=MSO_ANCHOR.MIDDLE)
        self.line_h(slide, x, y + 0.40, w, K["gold"], 1.5)
        cy = y + 0.40
        for row in rows:
            for j, cell in enumerate(row):
                text, opt = (cell if isinstance(cell, tuple) else (cell, {}))
                al = opt.get("align", aligns[j] if aligns else PP_ALIGN.LEFT)
                self.tx(slide, xs[j] + 0.08, cy + 0.02, xs[j + 1] - xs[j] - 0.12, row_h - 0.04,
                        str(text), size=opt.get("size", cell_size), color=opt.get("color", K["ink"]),
                        bold=opt.get("bold", False), align=al, anchor=MSO_ANCHOR.MIDDLE,
                        line_spacing=1.05)
            self.line_h(slide, x, cy + row_h, w, K["line"], 0.75)
            cy += row_h
        return cy


# ================================================================ 图片（SVG 矢量 + PNG 回退）
def _pair(path):
    p = Path(path)
    svg = p if p.suffix.lower() == ".svg" else p.with_suffix(".svg")
    png = p if p.suffix.lower() == ".png" else p.with_suffix(".png")
    return (svg if svg.exists() else None), (png if png.exists() else None)


def add_image(slide, path, x, y, w, h, fit="contain", align="center", vector=True,
              fallback_px=2400):
    """把图放进 (x, y, w, h) 英寸框：contain 等比、居中。

    path 可给 .svg 或 .png；同名的另一种格式存在时自动配对：SVG 作为矢量主图（svgBlip），
    PNG 作为回退。只有 SVG 而无 PNG 时报错（PowerPoint 规范要求位图回退）。
    有 SVG 时 PNG 回退图长边压到 fallback_px 像素以内（控制文件体积）；无 SVG 时保持原图。
    """
    import io
    from PIL import Image
    svg, png = _pair(path)
    if png is None:
        raise FileNotFoundError(f"需要 PNG 回退图：{Path(path).with_suffix('.png')}"
                                "（Canvas.save(formats=('svg','png')) 会同时生成）")
    im = Image.open(png)
    iw, ih = im.size
    src = str(png)
    if vector and svg is not None and max(iw, ih) > fallback_px:
        k = fallback_px / max(iw, ih)
        buf = io.BytesIO()
        im.convert("RGB").resize((int(iw * k), int(ih * k)), Image.LANCZOS).save(buf, "PNG",
                                                                                optimize=True)
        buf.seek(0)
        src = buf
    if fit == "contain":
        s = min(w / iw, h / ih)
        pw, ph = iw * s, ih * s
        px = x + {"left": 0, "center": (w - pw) / 2, "right": w - pw}[align]
        py = y + (h - ph) / 2
    else:
        px, py, pw, ph = x, y, w, h
    pic = slide.shapes.add_picture(src, Inches(px), Inches(py), Inches(pw), Inches(ph))
    if vector and svg is not None:
        pkg = slide.part.package
        part = Part(pkg.next_image_partname("svg"), "image/svg+xml", pkg, svg.read_bytes())
        rid = slide.part.relate_to(part, RT.IMAGE)
        blip = pic._element.blipFill.find(qn("a:blip"))
        ext_lst = blip.find(qn("a:extLst"))
        if ext_lst is None:
            ext_lst = etree.SubElement(blip, qn("a:extLst"))
        ext = etree.SubElement(ext_lst, qn("a:ext"))
        ext.set("uri", SVG_EXT_URI)
        sb = etree.SubElement(ext, f"{{{SVG_NS}}}svgBlip", nsmap={"asvg": SVG_NS})
        sb.set(qn("r:embed"), rid)
    pic.name = f"shanhai_atlas::{Path(path).stem}"
    return pic


# ================================================================ 演示文稿
class Deck:
    """同风格演示文稿。所有页面方法返回 slide，可继续用 ``deck.kit`` 图元自由加内容。"""

    def __init__(self, footer="", org="", fonts=None, template=None):
        self.prs = Presentation(template) if template else Presentation()
        self.prs.slide_width = Emu(12192000)
        self.prs.slide_height = Emu(6858000)
        self.kit = Kit(fonts)
        self.footer_text = footer
        self.org = org
        self._pages = []                 # (slide, 页码文本框)

    # ------------------------------------------------------------ 基础
    def _blank(self):
        layout = self.prs.slide_layouts[6]
        return self.prs.slides.add_slide(layout)

    def _bg(self, slide, color):
        bg = slide.background.fill
        bg.solid()
        bg.fore_color.rgb = color

    def notes(self, slide, text):
        if text:
            slide.notes_slide.notes_text_frame.text = text

    def header(self, slide, title, kicker=None, subtitle=None):
        k = self.kit
        if kicker:
            k.tx(slide, MARGIN, TAG_Y, 8.5, TAG_H, kicker, size=10.5, color=K["gold"], bold=True,
                 spc=120, anchor=MSO_ANCHOR.MIDDLE)
        if self.org:
            k.tx(slide, 9.0, TAG_Y, SLIDE_W - MARGIN - 9.0, TAG_H, self.org, size=9,
                 color=K["gray_lite"], align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
        k.tx(slide, MARGIN, TITLE_Y, 12.2, TITLE_H, title, size=25, color=K["navy"], bold=True,
             anchor=MSO_ANCHOR.MIDDLE)
        if subtitle:
            k.tx(slide, MARGIN + 7.0, TITLE_Y, CONTENT_W - 7.0, TITLE_H, subtitle, size=10.5,
                 color=K["gray"], align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.BOTTOM)
        k.line_h(slide, MARGIN, RULE_Y, 0.85, K["gold"], 2.5)
        k.line_h(slide, MARGIN + 0.85, RULE_Y + 0.008, CONTENT_W - 0.85, K["line"], 0.9)

    def footer(self, slide):
        k = self.kit
        k.line_h(slide, MARGIN, FOOT_LN_Y, CONTENT_W, K["line"], 0.9)
        if self.footer_text:
            k.tx(slide, MARGIN, FOOT_Y, 9.5, 0.26, self.footer_text, size=8, color=K["gray_lite"])
        box = k.tx(slide, SLIDE_W - MARGIN - 1.5, FOOT_Y, 1.5, 0.26, "", size=9, color=K["gold"],
                   latin=self.kit.f["serif"], align=PP_ALIGN.RIGHT)
        self._pages.append((slide, box))

    def source(self, slide, text, x=4.6):
        """右下来源标注。"""
        self.kit.tx(slide, x, SRC_Y, SLIDE_W - MARGIN - x, 0.34, text, size=8.5, color=K["gray"],
                    align=PP_ALIGN.RIGHT)

    def banner(self, slide, text, y=None, h=0.62, size=13.0):
        """通栏结论条：黛蓝底 + 金色短线 + 白色加粗文字。默认贴内容区底部。"""
        k = self.kit
        y = CB - h if y is None else y
        k.rect(slide, MARGIN, y, CONTENT_W, h, fill=K["navy"], round_=0.10)
        k.line_h(slide, MARGIN + 0.22, y + h / 2, 0.30, K["gold_lite"], 2.0)
        k.tx(slide, MARGIN + 0.68, y, CONTENT_W - 0.9, h, text, size=size, color=K["white"],
             bold=True, anchor=MSO_ANCHOR.MIDDLE)

    def page(self, title, kicker=None, subtitle=None, notes=None):
        """空白内容页（页眉 + 页脚）；内容区 y ∈ [CT, CB] = [1.36, 6.50] 英寸。"""
        s = self._blank()
        self.header(s, title, kicker, subtitle)
        self.footer(s)
        self.notes(s, notes)
        return s

    # ------------------------------------------------------------ 页面模板
    def cover(self, title, subtitle=None, meta=None, kicker=None, notes=None):
        s = self._blank()
        self._bg(s, K["navy_deep"])
        k = self.kit
        k.rect(s, 0, 0, 0.18, SLIDE_H, fill=K["gold"])
        if kicker:
            k.tx(s, 1.0, 2.05, 10, 0.35, kicker, size=12, color=K["gold_lite"], bold=True, spc=200)
        k.tx(s, 1.0, 2.50, 11.3, 1.4, title, size=36, color=K["white"], bold=True,
             anchor=MSO_ANCHOR.TOP, line_spacing=1.1)
        k.line_h(s, 1.0, 4.10, 1.2, K["gold"], 2.5)
        if subtitle:
            k.tx(s, 1.0, 4.30, 11.3, 0.9, subtitle, size=16, color=CREAM, line_spacing=1.2)
        if meta:
            k.tx(s, 1.0, 6.30, 11.3, 0.4, meta, size=11, color=CREAM_DIM)
        self.notes(s, notes)
        return s

    def section(self, number, title, subtitle=None, notes=None):
        s = self._blank()
        k = self.kit
        k.rect(s, 0, 0, 4.6, SLIDE_H, fill=K["navy_deep"])
        k.tx(s, 0.9, 2.2, 3.2, 2.0, str(number), size=96, color=K["gold_lite"],
             latin=self.kit.f["serif"], anchor=MSO_ANCHOR.MIDDLE)
        k.line_h(s, 5.3, 3.05, 0.85, K["gold"], 2.5)
        k.tx(s, 5.3, 3.25, 7.4, 0.9, title, size=32, color=K["navy"], bold=True)
        if subtitle:
            k.tx(s, 5.3, 4.15, 7.4, 1.2, subtitle, size=14, color=K["gray"], line_spacing=1.25)
        self.notes(s, notes)
        return s

    def full_figure(self, image, notes=None, vector=True, page_number=False):
        """整页图：自带标题的 16:9 图件（模型结构图、地图）铺满整页，1:1 不缩字。"""
        s = self._blank()
        add_image(s, image, 0, 0, SLIDE_W, SLIDE_H, vector=vector)
        if page_number:
            box = self.kit.tx(s, SLIDE_W - MARGIN - 1.5, FOOT_Y + 0.12, 1.5, 0.26, "", size=8,
                              color=K["gold"], latin=self.kit.f["serif"], align=PP_ALIGN.RIGHT)
            self._pages.append((s, box))
        self.notes(s, notes)
        return s

    def figure(self, title, image, kicker=None, subtitle=None, caption=None, source=None,
               takeaways=None, notes=None, vector=True):
        """图页：图在内容区内等比最大化；takeaways（要点列表）给定时右侧放结论卡。"""
        s = self.page(title, kicker, subtitle, notes)
        top, bottom = CT + 0.08, (CB - 0.36 if caption else CB)
        if takeaways:
            fw = CONTENT_W - 3.55
            pic = add_image(s, image, MARGIN, top, fw, bottom - top, vector=vector)
            chars = int((3.30 - 0.5) / (11.5 / 72 * 1.02))
            lines = sum(max(1, -(-len(str(t)) // chars)) for t in takeaways)
            ch = min(bottom - top, 0.95 + lines * 11.5 * 1.55 / 72 + 0.08 * len(takeaways))
            self.kit.card(s, MARGIN + fw + 0.25, pic.top / 914400.0, 3.30, ch, title="要点",
                          body=list(takeaways), body_size=11.5)
        else:
            add_image(s, image, MARGIN, top, CONTENT_W, bottom - top, vector=vector)
        if caption:
            self.kit.tx(s, MARGIN, CB - 0.30, CONTENT_W, 0.3, caption, size=10, color=K["gray"],
                        align=PP_ALIGN.CENTER)
        if source:
            self.source(s, source)
        return s

    def cards(self, title, items, kicker=None, subtitle=None, cols=None, notes=None, source=None,
              banner=None, body_size=11.5, card_h=None):
        """卡片页：items = [(卡片标题, 要点列表或段落)]，自动分列（≤ 4 列 × 2 行）。

        card_h 缺省时按要点条数估算卡片高度（不留大片空白）；banner 给定时底部加结论条。"""
        s = self.page(title, kicker, subtitle, notes)
        n = len(items)
        cols = cols or (n if n <= 4 else (n + 1) // 2)
        rows = (n + cols - 1) // cols
        gap = 0.25
        cw = (CONTENT_W - gap * (cols - 1)) / cols
        avail = CB - CT - 0.1 - (0.85 if banner else 0.0)
        if card_h is None:
            per_line = body_size * 1.55 / 72
            chars = max(1, int((cw - 0.5) / (body_size / 72 * 1.02)))
            lines = max(sum(max(1, -(-len(str(b)) // chars)) for b in
                            (body if isinstance(body, (list, tuple)) else [body]))
                        for _, body in items)
            card_h = min((avail - gap * (rows - 1)) / rows, 0.95 + lines * per_line)
        for i, (t, body) in enumerate(items):
            r, c = divmod(i, cols)
            self.kit.card(s, MARGIN + c * (cw + gap), CT + 0.1 + r * (card_h + gap), cw, card_h,
                          title=t, body=body, body_size=body_size)
        if banner:
            self.banner(s, banner, y=CT + 0.1 + rows * card_h + (rows - 1) * gap + 0.30)
        if source:
            self.source(s, source)
        return s

    def bullets(self, title, items, kicker=None, subtitle=None, notes=None, image=None):
        s = self.page(title, kicker, subtitle, notes)
        if image:
            self.kit.bullets(s, MARGIN, CT + 0.2, 5.4, CB - CT - 0.3, items, size=14, gap=10)
            add_image(s, image, MARGIN + 5.8, CT + 0.08, CONTENT_W - 5.8, CB - CT - 0.1)
        else:
            self.kit.bullets(s, MARGIN, CT + 0.2, CONTENT_W, CB - CT - 0.3, items, size=15, gap=12)
        return s

    def table(self, title, columns, rows, kicker=None, subtitle=None, note=None, notes=None,
              aligns=None):
        s = self.page(title, kicker, subtitle, notes)
        end = self.kit.table(s, MARGIN, CT + 0.2, CONTENT_W, columns, rows, aligns=aligns)
        if note:
            self.kit.tx(s, MARGIN, end + 0.15, CONTENT_W, 0.3, note, size=9.5, color=K["gray"])
        return s

    def kpis(self, title, items, kicker=None, subtitle=None, notes=None, banner=None):
        """大数字页：items = [(数值, 单位, 标签, 注释)]；卡片在内容区垂直居中，可加结论条。"""
        s = self.page(title, kicker, subtitle, notes)
        n = len(items)
        gap = 0.3
        w = (CONTENT_W - gap * (n - 1)) / n
        k = self.kit
        h = 2.4
        span = h + (1.0 if banner else 0.0)
        y0 = CT + (CB - CT - span) / 2
        if banner:
            self.banner(s, banner, y=y0 + h + 0.38)
        for i, (val, unit, label, note) in enumerate(items):
            x = MARGIN + i * (w + gap)
            y = y0
            k.rect(s, x, y, w, h, fill=K["card"], round_=0.05)
            k.line_h(s, x + 0.2, y + 0.2, 0.34, K["gold"], 2.0)
            runs = [dict(t=str(val), size=40, color=K["gold"], latin=k.f["serif"])]
            if unit:
                runs.append(dict(t=" " + unit, size=15, color=K["gray"]))
            k.tb(s, x + 0.2, y + 0.45, w - 0.4, 0.9, [(runs, PP_ALIGN.LEFT, 0, 1.0)],
                 anchor=MSO_ANCHOR.MIDDLE)
            k.tx(s, x + 0.2, y + 1.45, w - 0.4, 0.35, label, size=13, color=K["navy"], bold=True)
            if note:
                k.tx(s, x + 0.2, y + 1.85, w - 0.4, 0.45, note, size=10, color=K["gray"],
                     line_spacing=1.1)
        return s

    def closing(self, text="谢谢", sub=None, notes=None):
        s = self._blank()
        self._bg(s, K["navy_deep"])
        k = self.kit
        k.tx(s, 0, 2.7, SLIDE_W, 1.2, text, size=44, color=K["white"], bold=True,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        k.line_h(s, SLIDE_W / 2 - 0.6, 4.05, 1.2, K["gold"], 2.5)
        if sub:
            k.tx(s, 0, 4.25, SLIDE_W, 0.6, sub, size=14, color=CREAM, align=PP_ALIGN.CENTER)
        self.notes(s, notes)
        return s

    # ------------------------------------------------------------ 输出
    def save(self, path):
        total = len(self.prs.slides)
        index = {s.slide_id: i + 1 for i, s in enumerate(self.prs.slides)}
        for slide, box in self._pages:
            tf = box.text_frame
            r = tf.paragraphs[0].runs[0] if tf.paragraphs[0].runs else tf.paragraphs[0].add_run()
            r.text = f"{index[slide.slide_id]:02d} / {total:02d}"
            self.kit.style_run(r, size=9, color=K["gold"], latin=self.kit.f["serif"])
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self.prs.save(str(p))
        return p
