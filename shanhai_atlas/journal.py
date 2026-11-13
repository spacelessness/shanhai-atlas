"""期刊图件规范：preset 表 + 可执行的体检函数。

设计原则
--------
* **规范值必须能追到出处**。每条 preset 带 ``source``（指南名）与 ``verified`` 标记：
  ``verified=False`` 表示"值来自公开指南的通行版本，但本环境无法联网核对最新版"，
  本地落地前请对照期刊官网复核（`check_journal()` 会把这个标记一并返回）。
* **检查项只做能程序化判定的**：尺寸、字号、字形覆盖、色盲可辨、位图 DPI、文字是否可编辑。
  审美判断（留白比例、配色是否高级）不在这里假装能自动化。
* **给建议而不是只报错**：每条 issue 都带 ``fix``（怎么改）。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

__all__ = ["PRESETS", "JournalPreset", "journal_preset", "check_journal",
           "check_export", "delta_e", "colorblind_report", "MM_PER_INCH"]

MM_PER_INCH = 25.4


@dataclass
class JournalPreset:
    key: str
    name: str
    single_mm: float                 # 单栏宽
    double_mm: float                 # 双栏（整版）宽
    min_font_pt: float
    max_font_pt: float
    line_art_dpi: int
    halftone_dpi: int
    formats: tuple[str, ...]
    color: str                       # RGB / CMYK / 皆可
    fonts: tuple[str, ...]           # 允许/推荐的字体
    source: str                      # 出处（指南名）
    verified: bool = False           # False = 待本地核对官网最新版
    notes: str = ""
    tolerance_mm: float = 2.0

    @property
    def single_in(self) -> float:
        return self.single_mm / MM_PER_INCH

    @property
    def double_in(self) -> float:
        return self.double_mm / MM_PER_INCH

    def fits_width(self, width_mm: float) -> bool:
        return (abs(width_mm - self.single_mm) <= self.tolerance_mm
                or abs(width_mm - self.double_mm) <= self.tolerance_mm)


#: 8 家常见出版方/期刊族的图件硬指标。
#: ``verified=False`` 的一律需要本地对照官网复核——这里只保证"数量级与项目取向正确"。
PRESETS: dict[str, JournalPreset] = {
    "nature": JournalPreset(
        key="nature", name="Nature 系列",
        single_mm=89, double_mm=183, min_font_pt=5, max_font_pt=8,
        line_art_dpi=1000, halftone_dpi=300,
        formats=("ai", "eps", "pdf", "svg"), color="RGB", fonts=("Arial", "Helvetica"),
        source="Nature Figure guidelines（投稿图件规格）",
        notes="正文标签 5–7 pt；线图要求矢量；位图 ≥300 dpi"),
    "science": JournalPreset(
        key="science", name="Science / AAAS",
        single_mm=55, double_mm=183, min_font_pt=5, max_font_pt=9,
        line_art_dpi=1000, halftone_dpi=300,
        formats=("pdf", "eps", "ai"), color="RGB", fonts=("Helvetica", "Arial"),
        source="Science Information for Authors（figure preparation）",
        notes="单栏 55 mm、满栏 183 mm；字号 ≥5 pt"),
    "cell": JournalPreset(
        key="cell", name="Cell Press / Elsevier",
        single_mm=85, double_mm=174, min_font_pt=6, max_font_pt=8,
        line_art_dpi=1000, halftone_dpi=300,
        formats=("pdf", "eps", "ai", "tif"), color="RGB", fonts=("Arial", "Helvetica", "Times"),
        source="Elsevier Artwork guidelines（Cell Press 版式）",
        notes="Elsevier 建议正文 7 pt 上下；单栏 85 mm、双栏 174 mm"),
    "ieee": JournalPreset(
        key="ieee", name="IEEE Transactions",
        single_mm=88.9, double_mm=181.9, min_font_pt=6, max_font_pt=10,
        line_art_dpi=600, halftone_dpi=300,
        formats=("eps", "pdf", "png", "tif"), color="RGB/CMYK", fonts=("Times New Roman", "Arial"),
        source="IEEE Author Center（Artwork guidelines）",
        notes="栏宽 3.5 in / 7.16 in；照片 300 dpi、线条 600 dpi"),
    "acs": JournalPreset(
        key="acs", name="ACS Publications",
        single_mm=82.6, double_mm=177.8, min_font_pt=4.5, max_font_pt=12,
        line_art_dpi=1200, halftone_dpi=300,
        formats=("tif", "eps", "pdf"), color="RGB", fonts=("Arial", "Helvetica", "Times"),
        source="ACS Publications（Graphics / Author guidelines）",
        notes="单栏 3.25 in、双栏 7 in；线稿分辨率要求较高"),
    "plos": JournalPreset(
        key="plos", name="PLOS ONE",
        single_mm=83, double_mm=173, min_font_pt=5, max_font_pt=12,
        line_art_dpi=600, halftone_dpi=300,
        formats=("tif", "eps", "pdf"), color="RGB", fonts=("Arial", "Times", "Helvetica"),
        source="PLOS Figure Guidelines",
        notes="宽度 789–2250 px（300–600 dpi）；推荐 TIFF/EPS"),
    "agu": JournalPreset(
        key="agu", name="AGU / Wiley",
        single_mm=95, double_mm=190, min_font_pt=6, max_font_pt=10,
        line_art_dpi=600, halftone_dpi=300,
        formats=("pdf", "eps", "tif"), color="RGB/CMYK", fonts=("Arial", "Helvetica", "Times"),
        source="AGU Publications（Figure requirements）",
        notes="地球科学常用；地图类建议比例尺与指北针齐全"),
    "mnras": JournalPreset(
        key="mnras", name="MNRAS / OUP",
        single_mm=80, double_mm=165, min_font_pt=5, max_font_pt=9,
        line_art_dpi=600, halftone_dpi=300,
        formats=("eps", "pdf"), color="RGB", fonts=("Times", "Helvetica"),
        source="MNRAS Instructions to Authors（figures）",
        notes="天文/地学常见；要求 EPS/PDF 矢量"),
}


def journal_preset(name: str) -> JournalPreset:
    key = (name or "nature").strip().lower()
    if key not in PRESETS:
        raise KeyError(f"未知期刊预设 {name!r}，可选：{sorted(PRESETS)}")
    return PRESETS[key]


# --------------------------------------------------------------------------- #
# 颜色：sRGB → Lab，算 CIE76 色差（判断色盲/灰度下是否可分）
# --------------------------------------------------------------------------- #
def _srgb_to_lab(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))

    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = lin(r), lin(g), lin(b)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 1.00000
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(c1: str, c2: str) -> float:
    """CIE76 色差（≈2 人眼刚可辨，>10 明显不同）。"""
    return math.dist(_srgb_to_lab(c1), _srgb_to_lab(c2))


def _to_gray(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b


def colorblind_report(colors, min_de: float = 10.0, gray_min: float = 12.0) -> dict:
    """检查一组颜色在正常视觉/灰度下是否两两可辨。

    色盲模拟（红绿色盲）用简化的 Brettel 近似；这里只给"最小可辨色差"这一可执行的
    指标，不假装能替代真正的色盲模拟器。
    """
    cols = [c for c in colors if isinstance(c, str) and c.startswith("#")]
    worst, pair = 999.0, None
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            d = delta_e(cols[i], cols[j])
            if d < worst:
                worst, pair = d, (cols[i], cols[j])
    grays = [_to_gray(c) for c in cols]
    worst_gray = min((abs(a - b) for i, a in enumerate(grays) for b in grays[i + 1:]),
                     default=999.0)
    return {
        "ok": worst >= min_de,
        "gray_ok": worst_gray >= gray_min,
        "color_pairs": len(cols) * (len(cols) - 1) // 2,
        "min_delta_e": round(worst, 1),
        "worst_pair": pair,
        "min_gray_step": round(worst_gray, 1),
        "thresholds": {"delta_e": min_de, "gray": gray_min},
    }


# --------------------------------------------------------------------------- #
# 体检
# --------------------------------------------------------------------------- #
def _nonempty_texts(fig):
    from matplotlib.text import Text
    return [t for t in fig.findobj(Text) if (t.get_text() or "").strip() and t.get_visible()]


def check_journal(cv, preset: str | JournalPreset = "nature", raster_dpi: int | None = None,
                  colors=None, strict: bool = False) -> dict:
    """按期刊规范体检一张画布，返回 ``{ok, errors, warnings, metrics, preset}``。

    检查项：
      1. 画布宽度是否落在单栏/双栏（±2 mm）
      2. 最小/最大字号（含刻度标签、面板编号）
      3. 内嵌位图 DPI（``raster_dpi``，SVG/PDF 里的 imshow 重采样率）
      4. 字形覆盖（缺字 = 到出版社那边变豆腐块）
      5. 配色：色差与灰度可辨性
      6. 是否还有未转 Unicode 的 ``$...$``（会在 SVG 里炸成逐字符 tspan）

    ``strict=True`` 时：有 error 就抛 ``RuntimeError``。
    """
    from . import textnorm

    p = preset if isinstance(preset, JournalPreset) else journal_preset(preset)
    errors: list[dict] = []
    warns: list[dict] = []
    texts = _nonempty_texts(cv.fig)
    width_mm = cv.W * MM_PER_INCH
    height_mm = cv.H * MM_PER_INCH

    # 1) 尺寸
    if not p.fits_width(width_mm):
        errors.append({"check": "width", "value": round(width_mm, 1),
                       "expect": f"{p.single_mm} 或 {p.double_mm} ±{p.tolerance_mm} mm",
                       "fix": f"Canvas(width={p.single_in:.2f}) 或 Canvas(width={p.double_in:.2f})"})

    # 2) 字号
    sizes = []
    for t in texts:
        try:
            sizes.append((float(t.get_fontsize()), t.get_text()[:24]))
        except Exception:
            pass
    if sizes:
        lo, lo_txt = min(sizes)
        hi, hi_txt = max(sizes)
        if lo < p.min_font_pt:
            errors.append({"check": "font_min", "value": round(lo, 2), "where": lo_txt,
                           "expect": f"≥ {p.min_font_pt} pt",
                           "fix": f"把「{lo_txt}」的字号抬到 ≥{p.min_font_pt} pt（缩图后仍要可读）"})
        if hi > p.max_font_pt + 0.01:
            warns.append({"check": "font_max(提示)", "value": round(hi, 2), "where": hi_txt,
                          "expect": f"正文 ≤ {p.max_font_pt} pt，标题可更大",
                          "fix": f"确认「{hi_txt}」确实是标题/强调，而不是正文标签"})

    # 3) 位图 DPI
    if raster_dpi is not None and raster_dpi < p.halftone_dpi:
        errors.append({"check": "raster_dpi", "value": int(raster_dpi),
                       "expect": f"≥ {p.halftone_dpi} dpi",
                       "fix": f"canvas.save(..., raster_dpi={p.halftone_dpi})"})

    # 4) 字形覆盖：能靠"追加回退族"解决的算提示，谁都补不了的才算错
    fixable, hopeless = set(), set()
    for t in texts:
        s = t.get_text()
        fams = list(t.get_fontfamily() or [])
        if not fams:
            continue
        bad = textnorm.missing_glyphs(s, fams[:1])
        if not bad:
            continue
        miss = next(iter(bad.values()))
        pool = [f for f in (getattr(textnorm, "_CJK_HINT", None) or []) + ["DejaVu Sans"] if f]
        if any(not textnorm.missing_glyphs("".join(miss), [f]) for f in pool if f not in fams):
            fixable.update(miss)
        else:
            hopeless.update(miss)
    if hopeless:
        errors.append({"check": "glyphs", "value": "".join(sorted(hopeless))[:20],
                       "expect": "全部字形可用（且没有哪一族能补）",
                       "fix": "换字体族，或把该字符改写成 mathtext / Unicode 等价写法"})
    elif fixable:
        warns.append({"check": "glyphs_fixable", "value": "".join(sorted(fixable))[:20],
                      "expect": "由回退族补齐",
                      "fix": "canvas.save() 会自动追加回退族；也可显式 textnorm.repair_missing_glyphs()"})

    # 5) 配色
    if colors is None:
        from .theme import SERIES
        colors = list(SERIES)[:8]
    crep = colorblind_report(list(colors)[:8])
    if not crep["ok"]:
        warns.append({"check": "color_contrast", "value": crep["min_delta_e"],
                      "worst_pair": crep["worst_pair"],
                      "expect": "任意两色 ΔE ≥ 10",
                      "fix": "换用 theme.SERIES 的默认序列，或减少同时出现的颜色数"})
    if not crep["gray_ok"]:
        warns.append({"check": "grayscale(提示)", "value": crep["min_gray_step"],
                      "expect": f"黑白印刷时灰度步长 ≥ {crep['thresholds']['gray']}",
                      "fix": "若期刊可能黑白印刷，同图内避免用两个明度接近的色（如古铜金两档）"})

    # 6) 未转 Unicode 的公式
    math_left = [t.get_text() for t in texts if "$" in t.get_text()]
    if math_left:
        warns.append({"check": "mathtext", "value": len(math_left),
                      "expect": "0（公式已转 Unicode）",
                      "fix": "save() 会自动归一化；若仍存在说明该公式无法无损转换，"
                             "需手写成 Unicode 或接受在 SVG 里被拆成 tspan"})

    ok = not errors
    result = {
        "ok": ok,
        "preset": {k: v for k, v in asdict(p).items()
                   if k in ("key", "name", "single_mm", "double_mm", "min_font_pt",
                            "max_font_pt", "halftone_dpi", "formats", "color", "fonts",
                            "source", "verified", "notes")},
        "metrics": {"width_mm": round(width_mm, 1), "height_mm": round(height_mm, 1),
                    "texts": len(texts), "font_min": round(lo, 2) if sizes else None,
                    "font_max": round(hi, 2) if sizes else None,
                    "raster_dpi": raster_dpi, "colors": crep},
        "errors": errors,
        "warnings": warns,
    }
    if strict and not ok:
        raise RuntimeError("journal check failed: " +
                           "; ".join(f"{e['check']}={e['value']}" for e in errors))
    return result


def check_export(path, preset: str | JournalPreset = "nature") -> dict:
    """对**已经导出的文件**做体检（文字是否真文字、字体是否内嵌、PDF 有无豆腐块）。"""
    from . import exporter

    p = preset if isinstance(preset, JournalPreset) else journal_preset(preset)
    path = Path(path)
    suffix = path.suffix.lower().lstrip(".")
    issues, info = [], {}
    if suffix == "svg":
        info = exporter.svg_report(path)
        if info["text_elements"] == 0:
            issues.append({"check": "editable", "value": 0,
                           "fix": "用 text_mode='editable' 重新导出（svg.fonttype='none'）"})
        if info["font_face"] == 0:
            issues.append({"check": "font_embedded", "value": 0,
                           "fix": "exporter.embed_svg_fonts(path)，否则对方没装字体会被替换"})
        fams = info.get("families") or {}
        if fams:
            primary = max(fams, key=lambda f: len(fams[f]))     # 承载字符最多的族
            if not any(a.lower() in primary.lower() for a in p.fonts):
                issues.append({"check": "font_family", "value": primary,
                               "fix": f"{p.name} 推荐 {p.fonts}；"
                                      "非推荐字体请确认出版社接受（回退族不算）"})
    elif suffix == "pdf":
        info = exporter.pdf_report(path)
        if info["type3"] and not info["fontfile2"]:
            issues.append({"check": "editable", "value": "Type3",
                           "fix": "用 text_mode='editable'（pdf.fonttype=42）"})
        if info["last_resort"]:
            issues.append({"check": "tofu", "value": info["last_resort"],
                           "fix": "先跑 textnorm.repair_missing_glyphs() 再导出"})
    else:
        issues.append({"check": "format", "value": suffix,
                       "fix": f"{p.name} 接收 {p.formats}；位图请确认 dpi ≥ {p.halftone_dpi}"})
    return {"ok": not issues, "issues": issues, "info": info,
            "preset": p.key, "verified": p.verified}
