"""可编辑导出层：文字模式、字体子集内嵌、导出后体检。

三个问题，一个模块解决
----------------------
1. ``svg.fonttype="path"``（现默认）把字**画成轮廓** → AI 里不可编辑，而且**体积更大**
   （实测同一张图：转曲 77.7 KB vs 文字 15.3 KB）。
2. 切到 ``"none"`` 后 matplotlib **只写字体名、不内嵌字体**（``@font-face`` 计数 0）——
   收图方没装同名同版本字体就会替换、跑版。这里按"图里真正出现的字符"做子集，
   base64 塞进 ``<defs><style>@font-face`` 里（实测一份论文级字符集 ≈30 KB / base64 40 KB）。
3. 导出后没人验证。``svg_report`` / ``pdf_report`` / ``assert_editable`` 把
   "文字是否还是文字""字体是否真嵌进去了""有没有 LastResort 豆腐块"变成可断言的事实。
"""
from __future__ import annotations

import base64
import contextlib
import io
import re
import xml.etree.ElementTree as ET
from pathlib import Path

__all__ = [
    "TEXT_MODES",
    "text_mode_context",
    "svg_report",
    "pdf_report",
    "embed_svg_fonts",
    "subset_font_b64",
    "assert_editable",
]

#: ``editable`` = 文字保留文字层（默认）；``outline`` = 转曲（出版社硬要求时）；
#: ``both`` = 两份都给（``<stem>.svg`` 可编辑 + ``<stem>.outline.svg`` 转曲）
TEXT_MODES = ("editable", "outline", "both")


# --------------------------------------------------------------------------- #
# 模式切换
# --------------------------------------------------------------------------- #
@contextlib.contextmanager
def text_mode_context(mode: str = "editable"):
    """临时把 matplotlib 的文字导出模式切到 ``mode``。

    ``editable`` → ``svg.fonttype="none"`` + ``pdf.fonttype=42``（TrueType 子集，可编辑）
    ``outline``  → ``svg.fonttype="path"`` + ``pdf.fonttype=3``（Type3 轮廓，零字体依赖）
    """
    import matplotlib
    if mode not in ("editable", "outline"):
        raise ValueError(f"text_mode 只支持 editable / outline，收到 {mode!r}")
    keys = {
        "editable": {"svg.fonttype": "none", "pdf.fonttype": 42, "ps.fonttype": 42},
        "outline": {"svg.fonttype": "path", "pdf.fonttype": 3, "ps.fonttype": 3},
    }[mode]
    with matplotlib.rc_context(keys):
        yield keys


# --------------------------------------------------------------------------- #
# SVG 解析
# --------------------------------------------------------------------------- #
_SVG_NS = "http://www.w3.org/2000/svg"
_FAMILY_RE = re.compile(r"font-family:\s*'?\"?([^;'\"]+)'?\"?")
_WEIGHT_RE = re.compile(r"font-weight:\s*(\d+|bold|normal)")


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _iter_local(root, name):
    for el in root.iter():
        if _strip_ns(el.tag) == name:
            yield el


def _norm_weight(w) -> int:
    """``font-weight`` 归一成数值：不写 = 400，``bold`` = 700。"""
    if w in (None, "", "normal"):
        return 400
    if w == "bold":
        return 700
    try:
        return int(float(w))
    except (TypeError, ValueError):
        return 400


def _text_of(el) -> str:
    return "".join(el.itertext())


def _parse_style(el) -> dict:
    style = el.get("style") or ""
    fam = _FAMILY_RE.search(style)
    wt = _WEIGHT_RE.search(style)
    return {
        "family": (fam.group(1).strip() if fam else None) or el.get("font-family"),
        "weight": wt.group(1) if wt else None,
    }


def svg_report(path) -> dict:
    """SVG 体检：文字是不是文字、有没有内嵌字体、各字体族用了哪些字符。"""
    raw = Path(path).read_text(encoding="utf-8")
    root = ET.fromstring(raw)
    families: dict[str, set[str]] = {}
    weights: dict[str, set[int]] = {}
    text_els = 0
    plain_text_els = 0
    for el in _iter_local(root, "text"):
        text_els += 1
        if len(list(_iter_local(el, "tspan"))) == 0:
            plain_text_els += 1
        chars = set(_text_of(el))
        own = _parse_style(el)
        if own["family"]:
            families.setdefault(own["family"], set()).update(chars)
            weights.setdefault(own["family"], set()).add(_norm_weight(own["weight"]))
        for sp in _iter_local(el, "tspan"):
            st = _parse_style(sp)
            if st["family"]:
                families.setdefault(st["family"], set()).update(set(_text_of(sp)))
                weights.setdefault(st["family"], set()).add(_norm_weight(st["weight"]))
    return {
        "bytes": len(raw.encode("utf-8")),
        "text_elements": text_els,
        "plain_text_elements": plain_text_els,     # 没有 tspan 包裹 = 能整句编辑
        "tspans": sum(1 for _ in _iter_local(root, "tspan")),
        "paths": sum(1 for _ in _iter_local(root, "path")),
        "font_face": raw.count("@font-face"),
        "embedded_b64": raw.count("data:font/"),
        "families": {k: "".join(sorted(v)) for k, v in families.items()},
        "family_weights": {k: sorted(v) for k, v in weights.items()},
    }


def pdf_report(path) -> dict:
    """PDF 体检：字体流类型、是否子集化、有没有 LastResort 豆腐块。"""
    raw = Path(path).read_bytes()
    basefonts = sorted({m.decode("latin-1")
                        for m in re.findall(rb"/BaseFont\s*/([#A-Za-z0-9+\-_]+)", raw)})
    return {
        "bytes": len(raw),
        "fontfile2": raw.count(b"/FontFile2"),      # TrueType 子集（合规、可编辑）
        "fontfile3": raw.count(b"/FontFile3"),      # CFF/OpenType
        "type3": raw.count(b"/Type3"),              # 轮廓化字形（不可编辑）
        "tounicode": raw.count(b"/ToUnicode"),
        "basefonts": basefonts,
        "subsetted": [f for f in basefonts if re.match(r"^[A-Z]{6}\+", f)],
        "last_resort": [f for f in basefonts if "LastResort" in f],   # 豆腐块！
    }


# --------------------------------------------------------------------------- #
# 字体子集 → base64
# --------------------------------------------------------------------------- #
def _font_file(family: str, weight=None) -> str | None:
    from matplotlib import font_manager as fm
    try:
        return fm.findfont(fm.FontProperties(family=family, weight=weight),
                           fallback_to_default=False) or None
    except Exception:
        return None


def subset_font_b64(font_path: str, chars: str, fmt: str = "ttf") -> tuple[str, str, int]:
    """把字体按字符集做子集并 base64。返回 ``(b64, mime, 原始字节数)``。

    刻意关掉时间戳重算与 hinting 差异，保证**同样的输入给同样的字节**——
    现有测试 ``test_svg_is_byte_reproducible`` 依赖这一点。
    """
    from fontTools import subset
    opts = subset.Options()
    opts.flavor = "woff2" if fmt == "woff2" else None
    opts.recalc_timestamp = False
    opts.drop_tables += ["FFTM", "DSIG"]
    font = subset.load_font(font_path, opts)
    sub = subset.Subsetter(options=opts)
    sub.populate(text=chars)
    sub.subset(font)
    buf = io.BytesIO()
    subset.save_font(font, buf, opts)
    data = buf.getvalue()
    mime = {"woff2": "font/woff2", "woff": "font/woff"}.get(fmt, "font/ttf")
    return base64.b64encode(data).decode("ascii"), mime, len(data)


def _insert_style(root, css: str) -> None:
    """把 ``@font-face`` 写进 ``<defs><style>``（没有 defs 就新建，放在根节点最前）。"""
    defs = None
    for el in _iter_local(root, "defs"):
        defs = el
        break
    if defs is None:
        defs = ET.Element(f"{{{_SVG_NS}}}defs")
        root.insert(0, defs)
    style = ET.SubElement(defs, f"{{{_SVG_NS}}}style")
    style.set("type", "text/css")
    style.text = "\n" + css + "\n"


def embed_svg_fonts(path, families: dict[str, str] | None = None,
                    fmt: str = "ttf", quiet: bool = True) -> dict:
    """按 SVG 里实际用到的字符，给每个字体族内嵌 base64 子集。

    参数
    ----
    path      : 已导出的 SVG（原地改写）
    families  : ``{族名: 字符集}``；省略则自动从 SVG 里解析
    fmt       : ``ttf``（兼容性最好）或 ``woff2``（体积更小，需 brotli）

    返回 ``{"embedded": [{family, chars, bytes}], "missing": [族名]}``。
    """
    path = Path(path)
    raw = path.read_text(encoding="utf-8")
    info = svg_report(path)
    use = families if families is not None else info["families"]
    if not use:
        return {"embedded": [], "missing": []}
    rules, embedded, missing = [], [], []
    used_weights = info.get("family_weights") or {}
    for fam in sorted(use):
        chars = "".join(sorted(set(use[fam]) - {"\n", "\t"}))
        if not chars.strip():
            continue
        # 只嵌真的出现过的字重：一份图通常 400（必要时再加 700），少嵌一半体积
        weight_set = sorted(set(used_weights.get(fam) or [400]))
        got_any = False
        for w in weight_set:
            src = _font_file(fam, w)
            if not src:
                continue
            try:
                b64, mime, n = subset_font_b64(src, chars, fmt=fmt)
            except Exception:
                continue
            rules.append(
                "@font-face{font-family:'%s';font-style:normal;font-weight=%d;"
                "src:url(data:%s;base64,%s) format('%s');}"
                % (fam, w, mime, b64, "woff2" if fmt == "woff2" else "truetype"))
            embedded.append({"family": fam, "weight": w, "bytes": n, "file": Path(src).name})
            got_any = True
        if not got_any:
            missing.append(fam)
    if not rules:
        return {"embedded": [], "missing": missing}
    if "@font-face" in raw:                      # 已有内嵌，避免重复
        return {"embedded": embedded, "missing": missing}
    root = ET.fromstring(raw)
    _insert_style(root, "\n".join(rules))
    ET.register_namespace("", _SVG_NS)
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    out = ET.tostring(root, encoding="unicode")
    path.write_text('<?xml version="1.0" encoding="utf-8"?>\n' + out, encoding="utf-8")
    if not quiet:
        for e in embedded:
            print(f"  [font] {e['family']} w{e['weight']} ← {e['file']} "
                  f"({e['bytes'] / 1024:.0f} KB 子集)")
    return {"embedded": embedded, "missing": missing}


# --------------------------------------------------------------------------- #
# 断言（给测试 / CI / strict 模式用）
# --------------------------------------------------------------------------- #
def assert_editable(path, kind: str | None = None, allow_outline_fallback: bool = False) -> dict:
    """确认产物里的文字是"真文字"。不是就抛 ``RuntimeError``（信息带体检数据）。"""
    path = Path(path)
    kind = (kind or path.suffix.lstrip(".")).lower()
    if kind == "svg":
        rep = svg_report(path)
        if rep["text_elements"] == 0:
            raise RuntimeError(
                f"{path.name}: 没有 <text> 元素（文字被转曲了）—— "
                f"检查 svg.fonttype 是否为 'none'。体检：{rep}")
        if rep["font_face"] == 0 and not allow_outline_fallback:
            raise RuntimeError(
                f"{path.name}: 有 {rep['text_elements']} 个 <text> 但没有内嵌字体 "
                f"(@font-face=0)——收图方没装 {list(rep['families'])} 就会替换字体。"
                "用 embed_svg_fonts() 补子集，或显式 allow_outline_fallback=True。")
        return rep
    if kind == "pdf":
        rep = pdf_report(path)
        if rep["type3"] and rep["fontfile2"] == 0:
            raise RuntimeError(f"{path.name}: 只有 Type3 轮廓，文字不可编辑。体检：{rep}")
        if rep["last_resort"]:
            raise RuntimeError(
                f"{path.name}: PDF 里出现了 LastResort 兜底字体 {rep['last_resort']}——"
                "说明有字符在当前字体族里缺字形（会显示成豆腐块）。"
                "先跑 textnorm.repair_missing_glyphs()。")
        return rep
    raise ValueError(f"不支持的格式：{kind}")
