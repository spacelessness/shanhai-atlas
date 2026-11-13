# -*- coding: utf-8 -*-
"""版面画布：以“英寸”为坐标的整页排版引擎（左上角为原点，y 向下）。

核心能力
--------
* 精确定位：所有元素用英寸坐标摆放，和排版软件一样思考版面。
* 实测排版：按真实字形宽度断行——中文逐字、西文按词、``$…$`` 公式整体不拆、
  避头尾（行首不出现 “，。）%” 等，行尾不留 “（《“”）。
* 两个图层：``ax``（底层）与 ``top``（覆盖在所有小图之上的标注层）。
* 小图：``inset()`` 在任意英寸矩形内嵌入 matplotlib 坐标轴，画真实数据。
* 版面自检：``audit()`` 检查每个登记过容器的文字是否越界、是否互相压字。
* 可复现输出：``save()`` 写 SVG（文字转曲）/ PNG / PDF，相同输入逐字节一致。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402
from matplotlib.patches import (Circle, FancyArrowPatch, FancyBboxPatch,  # noqa: E402
                                Polygon)

from . import fonts  # noqa: E402
from .fonts import FONT  # noqa: E402
from .theme import C  # noqa: E402

#: Ghostscript 可执行文件候选（先 PATH，后常见安装位）
GHOSTSCRIPT_CANDIDATES = ("gswin64c", "gswin32c", "gs")


def ghostscript() -> str | None:
    """定位 Ghostscript；没有则返回 None。可用环境变量 ``SHANHAI_GHOSTSCRIPT`` 指定。"""
    import os
    env = os.environ.get("SHANHAI_GHOSTSCRIPT")
    if env and Path(env).is_file():
        return env
    for name in GHOSTSCRIPT_CANDIDATES:
        got = shutil.which(name)
        if got:
            return got
    pats = [r"C:\Program Files\gs\*\bin\gswin64c.exe",
            r"C:\Program Files\gs\*\bin\gs.exe",
            r"C:\Program Files (x86)\gs\*\bin\gswin32c.exe",
            r"C:\gmt6\bin\gswin64c.exe"]
    for pat in pats:
        for hit in _glob(pat):
            if hit.is_file():
                return str(hit)
    return None


def _glob(pat: str):
    import glob
    return [Path(p) for p in glob.glob(pat)]


def outline_pdf(src, dst) -> bool:
    """把带文字层的 PDF 转成**文字全部转曲**的 PDF；成功返回 True。

    用 Ghostscript ``-dNoOutputFonts`` 把每个字形画成路径——不依赖任何字体，
    Adobe Illustrator 打开绝不会乱码，是给交付件兜底的最终保险。

    走一遍 ASCII 临时目录：Windows 下 Ghostscript 对非 ASCII 路径不可靠。
    """
    exe = ghostscript()
    if exe is None:
        return False
    src, dst = Path(src), Path(dst)
    with tempfile.TemporaryDirectory(prefix="saol_") as td:
        tdir = Path(td)
        tin, tout = tdir / "in.pdf", tdir / "out.pdf"
        shutil.copyfile(src, tin)
        cmd = [exe, "-dNoOutputFonts", "-dBATCH", "-dNOPAUSE", "-dQUIET",
               "-dPDFSETTINGS=/prepress", "-sDEVICE=pdfwrite",
               f"-sOutputFile={tout}", str(tin)]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=600)
        except (OSError, subprocess.SubprocessError):
            return False
        if r.returncode != 0 or not tout.is_file() or tout.stat().st_size < 100:
            return False
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tout, dst)
    return True


def pdf_embeds_fonts(path) -> bool:
    """PDF 是否仍内嵌字体（转曲成功应为 False）。"""
    try:
        blob = Path(path).read_bytes()
    except OSError:
        return True
    return b"/FontFile2" in blob or b"/FontFile3" in blob or b"/FontFile " in blob


class Canvas:
    """整页画布。

    >>> cv = Canvas(16, 9)                     # 16×9 英寸
    >>> cv.text(0.4, 0.8, "标题", size=17.5, weight=700, color=C.navy)
    >>> cv.para(0.4, 1.0, 5.0, "自动断行的中文段落……", size=7.2)
    >>> ax = cv.inset(0.4, 2.0, 4.0, 3.0)      # 在英寸矩形里画真实数据
    >>> cv.save("figures/demo")                # → demo.svg + demo.png
    """

    def __init__(self, width=16.0, height=9.0, dpi=300, facecolor="white"):
        fonts.ensure()
        self.W, self.H = float(width), float(height)
        self.dpi = dpi
        self.fig = plt.figure(figsize=(self.W, self.H), dpi=dpi, facecolor=facecolor)
        self.ax = self._layer(0)
        self.top = self._layer(50)          # 位于全部小图之上的标注层
        self.r = self.fig.canvas.get_renderer()
        self.boxes = []                     # (name, artist, container) 版面自检
        self.issues = []                    # 其他自检问题（组件写入）
        self._wcache = {}
        self.report = None
        self.warnings = []                  # 导出/规范化过程中的提示（公式、缺字、字体子集）

    @property
    def page(self):
        return (0.0, 0.0, self.W, self.H)

    def _layer(self, z):
        a = self.fig.add_axes([0, 0, 1, 1], zorder=z)
        a.set_xlim(0, self.W)
        a.set_ylim(self.H, 0)
        a.axis("off")
        a.patch.set_alpha(0)
        return a

    # ------------------------------------------------------------ 字体 / 测量
    @staticmethod
    def fp(size, weight=400, style="normal", family=None):
        return fm.FontProperties(family=family or FONT.cjk, size=size, weight=weight,
                                 style=style)

    def _w(self, s, size, weight, style, family):
        key = (s, size, weight, style, family)
        if key not in self._wcache:
            fp = self.fp(size, weight, style, family)
            ismath = s.count("$") >= 2
            w = self.r.get_text_width_height_descent(s, fp, ismath=ismath)[0]
            self._wcache[key] = w / self.fig.dpi
        return self._wcache[key]

    def adv(self, s, size, weight=400, style="normal", family=None):
        """文字前进宽度（英寸，含左右字距）。"""
        if not s:
            return 0.0
        return (self._w("|" + s + "|", size, weight, style, family)
                - self._w("||", size, weight, style, family))

    def fit_size(self, s, width, size, min_size=None, weight=400, style="normal", family=None,
                 step=0.1):
        """把单行文字缩到 width 以内（不低于 min_size）；返回字号。"""
        min_size = min_size or size * 0.75
        while self.adv(s, size, weight, style, family) > width and size > min_size:
            size -= step
        return round(size, 2)

    # ------------------------------------------------------------ 基本图元
    def _a(self, top):
        return self.top if top else self.ax

    def rect(self, x, y, w, h, r=0.06, fc="none", ec="none", lw=0.6, z=1, alpha=1.0, ls="-",
             top=False):
        p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                           fc=fc, ec=ec, lw=lw, zorder=z, alpha=alpha, ls=ls)
        self._a(top).add_patch(p)
        return p

    def circle(self, x, y, radius, fc=C.navy, ec="none", lw=0.6, z=3, top=False):
        p = Circle((x, y), radius, fc=fc, ec=ec, lw=lw, zorder=z)
        self._a(top).add_patch(p)
        return p

    def poly(self, xy, fc=C.navy, ec="none", lw=0.6, z=3, closed=True, top=False, **kw):
        p = Polygon(xy, closed=closed, fc=fc, ec=ec, lw=lw, zorder=z, **kw)
        self._a(top).add_patch(p)
        return p

    def text(self, x, y, s, size=8, weight=400, color=C.ink, ha="left", va="baseline",
             style="normal", family=None, z=5, name=None, container=None, top=False, **kw):
        """单行文字。container=(x0, y0, x1, y1) 时登记版面自检。"""
        t = self._a(top).text(x, y, s, fontproperties=self.fp(size, weight, style, family),
                              color=color, ha=ha, va=va, zorder=z, **kw)
        if container is not None:
            self.boxes.append((name or str(s)[:18], t, container))
        return t

    def line(self, xs, ys, color=C.line, lw=0.6, z=2, top=False, **kw):
        return self._a(top).plot(xs, ys, color=color, lw=lw, zorder=z, **kw)

    def inset(self, x, y, w, h, z=3):
        """在英寸矩形 (x, y, w, h) 内新建坐标轴（透明底），用于画真实数据小图。"""
        a = self.fig.add_axes([x / self.W, 1 - (y + h) / self.H, w / self.W, h / self.H],
                              zorder=z)
        a.patch.set_alpha(0)
        return a

    def arrow(self, p0, p1, color=C.navy, lw=1.0, ms=8, style="-|>", rad=0.0, z=6, shrink=0,
              top=False, **kw):
        a = FancyArrowPatch(p0, p1, arrowstyle=style, mutation_scale=ms, color=color, lw=lw,
                            connectionstyle=f"arc3,rad={rad}", zorder=z, shrinkA=shrink,
                            shrinkB=shrink, joinstyle="miter", capstyle="butt", **kw)
        self._a(top).add_patch(a)
        return a

    # ------------------------------------------------------------ 富文本段落
    _TOK = re.compile(r"\$[^$]*\$|[A-Za-z0-9\u00C0-\u024F\u0370-\u03FF\u00A0.,:%°±×·'’_+=<>/~\-–]+"
                      r"|[ \t]+|\n|.", re.S)
    NO_START = set("，。、；：？！）》」』”’%°…,.;:!?)]}·～")
    NO_END = set("（《「『“‘([{")

    def _units(self, runs, base):
        """runs: [(text, style)] → 不可断开单元 [[(piece, style), ...], ...]。"""
        units, glue_next = [], False
        for text, st in runs:
            st = {**base, **(st or {})}
            for tok in self._TOK.findall(text):
                if tok == "\n":
                    units.append("BR")
                    glue_next = False
                    continue
                if tok.isspace():
                    units.append(("SP", st))
                    glue_next = False
                    continue
                piece = (tok.replace("\u00A0", " "), st)
                if (units and isinstance(units[-1], list)
                        and (glue_next or tok[0] in self.NO_START)):
                    units[-1].append(piece)
                else:
                    units.append([piece])
                glue_next = tok[-1] in self.NO_END
        return units

    def _pw(self, piece):
        s, st = piece
        return self.adv(s, st["size"], st["weight"], st["style"], st["family"])

    def _lines(self, width, runs, size, color, weight, style, family):
        if isinstance(runs, str):
            runs = [(runs, None)]
        base = dict(size=size, color=color, weight=weight, style=style, family=family)
        lines, cur, cur_w, pend = [], [], 0.0, None
        for u in self._units(runs, base):
            if u == "BR":
                lines.append(cur)
                cur, cur_w, pend = [], 0.0, None
                continue
            if isinstance(u, tuple):            # 空格
                pend = (" ", u[1]) if cur else None
                continue
            uw = sum(self._pw(p) for p in u)
            sw = self._pw(pend) if pend else 0.0
            if cur and cur_w + sw + uw > width + 1e-6:
                lines.append(cur)
                cur, cur_w = list(u), uw
            else:
                if pend:
                    cur.append(pend)
                cur.extend(u)
                cur_w += sw + uw
            pend = None
        if cur:
            lines.append(cur)
        return lines

    def measure(self, width, runs, size=7.5, leading=1.52, weight=400, style="normal",
                family=None):
        """不绘制，只计算段落高度（英寸）与行数。"""
        lines = self._lines(width, runs, size, C.ink, weight, style, family)
        return len(lines) * size / 72.0 * leading, len(lines)

    def para(self, x, y, width, runs, size=7.5, color=C.ink, weight=400, style="normal",
             family=None, leading=1.52, name=None, container=None, z=5, top=False,
             align="left"):
        """排版段落：y 为首行顶部；runs 可为字符串或 [(文字, 样式 dict)]；
        返回 (段落底 y, 行数)。"""
        lines = self._lines(width, runs, size, color, weight, style, family)
        pitch = size / 72.0 * leading
        base_y = y + size / 72.0 * 1.02
        for i, ln in enumerate(lines):
            merged = []
            for s, st in ln:
                if merged and merged[-1][1] == st:
                    merged[-1] = (merged[-1][0] + s, st)
                else:
                    merged.append((s, st))
            lw_ = sum(self._pw(m) for m in merged)
            cx = x + {"left": 0.0, "center": (width - lw_) / 2, "right": width - lw_}[align]
            for s, st in merged:
                self.text(cx, base_y + i * pitch, s, size=st["size"], weight=st["weight"],
                          color=st["color"], style=st["style"], family=st["family"], z=z,
                          name=name, container=container, top=top)
                cx += self._pw((s, st))
        return y + len(lines) * pitch, len(lines)

    # ------------------------------------------------------------ 版面自检
    def audit(self, overlap=True, tol=0.012, verbose=True, full=False):
        """版面自检：越界（overflow）+ 压字（overlap）。返回问题总数。

        ``full=True`` 会把**图里所有** ``Text`` 都纳入检查，而不只是经
        ``cv.text()`` 登记过的那几个。此前的实现只审登记文本（实测一张普通图：
        受审 3 个 / 实际 124 个），轴标签、刻度、标题、``ax.text()`` 注记全在盲区里，
        SKILL.md 要求的 "0 overflow / 0 overlap" 因此形同虚设。

        默认仍是 ``full=False``（与旧版行为一致，不会让存量图形突然报错）；
        ``save(strict=True)`` 会自动切到 ``full=True``，交稿前的体检请显式写
        ``cv.audit(full=True)``。
        """
        from matplotlib.text import Text as _Text

        self.fig.canvas.draw()
        dpi = self.fig.dpi
        W, H = self.W, self.H
        bbs, bad_over, bad_lap = [], 0, 0
        seen = set()

        for name, t, (x0, y0, x1, y1) in self.boxes:
            bb = t.get_window_extent(self.r)
            bx0, bx1 = bb.x0 / dpi, bb.x1 / dpi
            by0, by1 = H - bb.y1 / dpi, H - bb.y0 / dpi
            bbs.append((name, bx0, by0, bx1, by1, True, id(t.axes) if t.axes is not None else -1))
            seen.add(id(t))
            if bx0 < x0 - 0.01 or bx1 > x1 + 0.01 or by0 < y0 - 0.01 or by1 > y1 + 0.01:
                bad_over += 1
                if verbose:
                    print(f"  [overflow] {name!r}: text=({bx0:.2f},{by0:.2f})–({bx1:.2f},{by1:.2f})"
                          f" box=({x0:.2f},{y0:.2f})–({x1:.2f},{y1:.2f})")

        if full:
            # 未登记的文本：容器退化为整张画布（越界 = 会被裁掉），
            # 只在**跨坐标区/跨图层**之间查压字，避免刻度标签彼此的正常贴近被误报。
            for t in self.fig.findobj(_Text):
                if id(t) in seen or not (t.get_text() or "").strip():
                    continue
                if not t.get_visible():
                    continue
                try:
                    bb = t.get_window_extent(self.r)
                except Exception:
                    continue
                if bb.width <= 0 or bb.height <= 0:
                    continue
                bx0, bx1 = bb.x0 / dpi, bb.x1 / dpi
                by0, by1 = H - bb.y1 / dpi, H - bb.y0 / dpi
                owner = getattr(t, "axes", None)
                label = f"<text:{t.get_text()[:14]!r}>"
                bbs.append((label, bx0, by0, bx1, by1, False,
                            id(owner) if owner is not None else -1))
                if bx0 < -0.02 or by0 < -0.02 or bx1 > W + 0.02 or by1 > H + 0.02:
                    bad_over += 1
                    if verbose:
                        print(f"  [overflow] {label} 超出画布 "
                              f"({bx0:.2f},{by0:.2f})–({bx1:.2f},{by1:.2f}) / {W:.2f}×{H:.2f}"
                              f"{'' if owner is None else ' @axes'}")

        if overlap:
            order = sorted(range(len(bbs)), key=lambda i: bbs[i][1])
            for a_i, i in enumerate(order):
                n1, ax0, ay0, ax1, ay1, reg1, own1 = bbs[i]
                for j in order[a_i + 1:]:
                    n2, bx0, by0, bx1, by1, reg2, own2 = bbs[j]
                    if bx0 >= ax1 - tol:
                        break
                    if not (reg1 or reg2) and own1 == own2 and own1 != -1:
                        continue              # 同一坐标区内的刻度/标签彼此贴近属正常
                    if (min(ax1, bx1) - max(ax0, bx0) > tol
                            and min(ay1, by1) - max(ay0, by0) > tol):
                        bad_lap += 1
                        if verbose:
                            print(f"  [overlap] {n1!r} × {n2!r}")

        for msg in self.issues:
            if verbose:
                print("  [issue]", msg)
        total = bad_over + bad_lap + len(self.issues)
        total_texts = len([t for t in self.fig.findobj(_Text)
                           if (t.get_text() or "").strip() and t.get_visible()])
        self.report = dict(texts=len(bbs), overflow=bad_over, overlap=bad_lap,
                           issues=len(self.issues), mode="full" if full else "registered",
                           texts_total=total_texts)
        if verbose:
            unc = "" if full or total_texts == len(bbs) else f"（未审 {total_texts - len(bbs)} 个）"
            print(f"layout audit[{self.report['mode']}]: {len(bbs)} text items{unc}, "
                  f"{bad_over} overflow(s), {bad_lap} overlap(s), "
                  f"{len(self.issues)} other issue(s)")
        return total

    # ------------------------------------------------------------ 输出
    def save(self, path, formats=None, dpi=None, check=True, strict=False,
             raster_dpi=160, text_mode=None, font_embed="subset", strict_text=False):
        """写出 ``path.{pdf,svg,png}`` 等格式，默认**同时给 PDF + SVG + PNG**。

        Parameters
        ----------
        formats : 序列或 None
            None（默认）= ``("pdf", "svg", "png")``。可选 ``svg`` / ``png`` / ``pdf`` /
            ``pdf-outline``（Ghostscript 转曲）/ ``tif`` / ``eps``。
        text_mode : {"editable", "outline", "both"} | None
            ``editable``（默认）：SVG 保留 ``<text>`` 并内嵌字体子集，PDF 保留文字层
            → Illustrator 里可以直接改字。
            ``outline``：文字转曲（旧行为），零字体依赖。
            ``both``：两种都给，转曲版另存 ``<stem>.outline.svg`` / ``<stem>.outline.pdf``。
            None = 跟随 ``fonts.setup(text_mode=...)``，默认 ``editable``。
        font_embed : {"subset", "none"}
            是否把用到的字形做成 base64 子集写进 SVG（实测一份论文级字符集 ≈30 KB）。
        strict_text : bool
            导出后跑 ``assert_editable()``：不是真文字就抛错（CI / 交稿前用）。
        raster_dpi : SVG/PDF 内嵌位图的采样率；默认 160，投稿建议 ≥300。

        返回写出的路径列表（顺序与 ``formats`` 一致）。
        """
        from . import exporter, textnorm

        mode = text_mode or getattr(fonts, "TEXT_MODE", "editable")
        if mode not in exporter.TEXT_MODES:
            raise ValueError(f"text_mode 只支持 {exporter.TEXT_MODES}，收到 {mode!r}")
        if formats is None:
            formats = ("pdf", "svg", "png")
        formats = tuple(formats)

        # ① 公式 → Unicode：否则整句会被拆成逐字符 <tspan>，AI 里没法整句改
        if mode in ("editable", "both"):
            noun = textnorm.normalize_figure(self.fig)
            if noun["converted"]:
                self.warnings.append(
                    f"{noun['converted']} 处公式已转成 Unicode（如 R²、α、p < 0.05），"
                    "保证仍是整句可编辑文字")
            for s_ in noun["skipped"][:5]:
                self.warnings.append(f"公式无法无损转 Unicode，仍按矢量/逐字符绘制：{s_[:40]}")
            # ② 缺字 → 换族：消掉 LastResort 豆腐块
            fixed = textnorm.repair_missing_glyphs(self.fig, cjk_family=FONT.cjk)
            for f_ in fixed[:5]:
                act = {"append": "补一个回退族", "replace": "换族",
                       "unresolved": "无族可补，可能显示豆腐块"}[f_["mode"]]
                self.warnings.append(
                    f"「{f_['text'][:16]}」{act}：{f_['was']} 缺 {''.join(f_['missing'][:6])}"
                    f" → {f_['now']}")
            if noun["converted"] or fixed:
                self.fig.canvas.draw()

        # ③ 版面自检（strict 时有问题直接拒绝出图，且绝不复用旧结果）
        bad = self.audit(full=bool(strict)) if (check or strict) else 0
        if strict and bad:
            raise RuntimeError(f"layout audit failed: {self.report}")

        p = Path(path)
        stem = p.with_suffix("") if p.suffix.lower() in (".svg", ".png", ".pdf") else p
        stem.parent.mkdir(parents=True, exist_ok=True)
        written = []

        def _emit(fmt, target, rc_mode):
            with exporter.text_mode_context(rc_mode):
                kw = {}
                if fmt == "png":
                    kw["dpi"] = dpi or self.dpi
                elif fmt == "svg":
                    kw.update(metadata={"Date": None}, dpi=raster_dpi)
                elif fmt == "pdf":
                    kw.update(metadata={"CreationDate": None}, dpi=raster_dpi)
                self.fig.savefig(target, **kw)
            return target

        for fmt in formats:
            fmt = fmt.lower().strip(".")
            if fmt in ("pdf-outline", "outline-pdf", "pdf.outline"):
                # strict_text 要"真文字"，pdf-outline 交付"全是路径"——语义互斥，
                # 无论本机 Ghostscript 在不在都应明确失败（否则有 gs 的机器上会
                # 悄悄产出无文字层的 PDF，strict 形同虚设）。
                if strict_text:
                    raise RuntimeError(
                        "pdf-outline 是转曲 PDF（文字全变路径、无文字层），与 strict_text=True 互斥；"
                        "要可编辑文字请用 formats=('pdf',)。")
                # 真·转曲：交给 Ghostscript。失败就**明确失败**，不再偷偷退回带字体 PDF
                # 却仍叫 *.outline.pdf（交付时极易被误认为转曲版）。
                f = stem.with_name(stem.name + ".outline.pdf")
                tmp = stem.with_name(stem.name + ".text.tmp.pdf")
                _emit("pdf", tmp, "editable")
                if ghostscript() and outline_pdf(tmp, f):
                    if pdf_embeds_fonts(f):
                        print("[save] ⚠ 转曲后仍含字体：Ghostscript 未按预期工作")
                    tmp.unlink(missing_ok=True)
                    written.append(f)
                else:
                    tmp.unlink(missing_ok=True)
                    print("[save] ✗ 找不到可用的 Ghostscript（设 SHANHAI_GHOSTSCRIPT 可指定）："
                          "pdf-outline 未生成。要纯矢量可改用 text_mode='editable'，"
                          "或安装 Ghostscript 后重试。")
                    raise RuntimeError("pdf-outline 需要 Ghostscript；未生成任何文件")
                continue
            if fmt == "svg":
                f = stem.with_name(stem.name + ".svg")
                if mode in ("editable", "both"):
                    _emit("svg", f, "editable")
                    if font_embed != "none":
                        rep = exporter.embed_svg_fonts(f)
                        for e in rep["embedded"]:
                            self.warnings.append(
                                f"SVG 内嵌字体子集：{e['family']} w{e['weight']} "
                                f"{e['bytes'] / 1024:.0f} KB")
                        for m in rep["missing"]:
                            self.warnings.append(f"字体族 {m} 找不到字体文件，未能内嵌")
                    written.append(f)
                    if mode == "both":
                        written.append(_emit("svg", stem.with_name(stem.name + ".outline.svg"),
                                             "outline"))
                else:
                    written.append(_emit("svg", f, "outline"))
                if strict_text:
                    exporter.assert_editable(f, "svg")
                continue
            if fmt == "pdf":
                f = stem.with_name(stem.name + ".pdf")
                written.append(_emit("pdf", f, "editable" if mode != "outline" else "outline"))
                if strict_text and mode != "outline":
                    exporter.assert_editable(f, "pdf")
                continue
            # png / tif / eps / jpg：与文字模式无关
            target = stem.with_name(stem.name + "." + fmt)
            kw = {}
            if fmt in ("png", "tif", "tiff", "jpg", "jpeg"):
                kw["dpi"] = dpi or self.dpi
            self.fig.savefig(target, **kw)
            written.append(target)
        return written

    def close(self):
        plt.close(self.fig)
