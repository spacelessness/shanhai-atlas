# -*- coding: utf-8 -*-
"""字体发现 / 下载 / matplotlib 全局设置。

默认字体组合（中文思源黑体 / 英文 Source Serif 4 / 公式 STIX）：
    中文 & 正文    Noto Sans SC（思源黑体）  → 回退 思源黑体 / 微软雅黑 / 苹方 …
    英文副题      Source Serif 4 斜体       → 回退 Georgia / Times New Roman
    公式          STIX（matplotlib 自带）
    等宽          DejaVu Sans Mono（matplotlib 自带）

``fetch_fonts()`` 从 npm 公共仓库（@expo-google-fonts，SIL OFL 许可）下载所需字重
（约 35 MB），缓存到 ``~/.cache/shanhai_atlas/fonts``（可用环境变量 SHANHAI_FONT_DIR 改）。
排版引擎按实际字形测量断行，换字体不会越界，但行数可能变化——出图后看审计结果。
"""

from __future__ import annotations

import glob
import io
import os
import tarfile
import urllib.request
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

from .theme import Tokens

FONT = Tokens(cjk="DejaVu Sans", serif="DejaVu Serif", mono="DejaVu Sans Mono", math="stix")

CJK_CANDIDATES = ["Noto Sans SC", "Source Han Sans SC", "Source Han Sans CN", "Noto Sans CJK SC",
                  "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", "SimHei",
                  "WenQuanYi Micro Hei"]
SERIF_CANDIDATES = ["Source Serif 4", "Source Serif Pro", "Georgia", "Times New Roman",
                    "DejaVu Serif"]
MONO_CANDIDATES = ["JetBrains Mono", "Source Code Pro", "DejaVu Sans Mono"]

#: npm 包 → (版本, 需要的字重目录)
NPM_FONTS = {
    "noto-sans-sc": ("0.4.4", ("400Regular", "500Medium", "700Bold")),
    "source-serif-4": ("0.4.2", ("400Regular", "400Regular_Italic", "600SemiBold", "700Bold")),
}
NPM_URL = "https://registry.npmjs.org/@expo-google-fonts/{pkg}/-/{pkg}-{ver}.tgz"

_STATE = {"ready": False}

#: PDF 合规实例需要覆盖的常用字重（对应排版用到的 400 / 500 / 700）
DEFAULT_WEIGHTS = (400, 500, 700)


def font_flavor(path) -> str:
    """字体轮廓类型：``'glyf'``（TrueType）或 ``'CFF'``（PostScript）。其余返回 ``'unknown'``。

    matplotlib 的 PDF 后端（``pdf.fonttype=42``）**无条件**把字体写成 ``/FontFile2``，
    而 PDF 规范规定 ``/FontFile2`` 只能装 TrueType。CFF 轮廓的 OTF 这样嵌进去是**违规的**：
    Acrobat / 浏览器这类宽松阅读器能渲染，Adobe Illustrator 这类严格解析器则会把文字显示成乱码。
    因此导出前需要确认 CJK 字面是 glyf 轮廓。
    """
    p = str(path)
    try:
        from fontTools.ttLib import TTCollection, TTFont
        if p.lower().endswith(".ttc"):
            f = TTCollection(p, lazy=True).fonts[0]
        else:
            f = TTFont(p, lazy=True)
        flavor = "CFF" if ("CFF " in f or "CFF2" in f) else "glyf"
        f.close()
        return flavor
    except Exception:
        pass
    try:
        with open(p, "rb") as fh:
            tag = fh.read(4)
    except OSError:
        return "unknown"
    if tag == b"OTTO":
        return "CFF"
    if tag in (b"\x00\x01\x00\x00", b"true", b"ttcf"):
        return "glyf"
    return "unknown"


def _is_variable(path) -> bool:
    try:
        from fontTools.ttLib import TTFont
        f = TTFont(str(path), lazy=True)
        has = "fvar" in f
        f.close()
        return has
    except Exception:
        return False


def _as_weight(v) -> int:
    if isinstance(v, (int, float)):
        return int(v)
    return {"normal": 400, "regular": 400, "book": 400, "medium": 500,
            "demibold": 600, "bold": 700, "heavy": 800, "black": 900,
            "light": 300}.get(str(v).lower(), 400)


def _family_entries(family: str):
    return [e for e in fm.fontManager.ttflist if e.name == family]


def _find_variable_source(family: str):
    """找到同族的 glyf 可变字体（VF），用于按字重实例化。"""
    for e in _family_entries(family):
        p = Path(e.fname)
        if font_flavor(p) == "glyf" and _is_variable(p):
            return p
    for d in (font_cache_dir(), Path(os.environ.get("SHANHAI_FONT_DIR", "")),
              # 兼容 0.1.x 的字体缓存目录，避免历史用户重复下载约 35 MB 字体
              Path.home() / ".cache" / "jingtu" / "fonts",
              Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"):
        if not d.is_dir():
            continue
        for p in sorted(d.glob("**/*.[ot]tf")):
            try:
                from fontTools.ttLib import TTFont
                f = TTFont(str(p), lazy=True)
                names = {f["name"].getDebugName(i) for i in (1, 16)}
                f.close()
            except Exception:
                continue
            if family in names and font_flavor(p) == "glyf" and _is_variable(p):
                return p
    return None


def _static_instance(src: Path, family: str, weight: int) -> Path:
    """按字重实例化 VF 并缓存；返回 glyf 静态 TTF 路径。"""
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    safe = "".join(ch if ch.isalnum() else "_" for ch in family)
    out = static_dir() / f"{safe}-{weight}.ttf"
    if out.is_file() and font_flavor(out) == "glyf":
        try:
            chk = TTFont(str(out), lazy=True)
            ok = int(chk["OS/2"].usWeightClass) == int(weight)
            chk.close()
            if ok:
                return out
        except Exception:
            pass
    out.parent.mkdir(parents=True, exist_ok=True)
    f = TTFont(str(src))
    axes = {a.axisTag: a for a in f["fvar"].axes} if "fvar" in f else {}
    if "wght" in axes:
        w = min(max(float(weight), axes["wght"].minValue), axes["wght"].maxValue)
        inst = instancer.instantiateVariableFont(f, {"wght": w}, updateFontNames=True)
    else:                                   # 没有 wght 轴：直接原样落地
        inst = f
    inst.save(str(out))
    f.close()
    return out


def ensure_truetype_faces(families=(), weights=DEFAULT_WEIGHTS, quiet=True):
    """把会让 PDF 内嵌违规的 CFF 字面换成 glyf 静态实例；返回处理过的 (族, 文件) 列表。

    只在**该族确实存在 CFF 字面**时才动它：先找同族 glyf VF，按字重实例化到
    ``static_dir()``，再把该族其余字面从 fontManager 移除（避免 findfont 选回 CFF 或
    VF 的默认细体实例），最后清 findfont 缓存。找不到 VF 时保持原样并告警——那种情况
    要靠 ``save(formats=("pdf-outline",))`` 转曲版兜底。
    """
    handled = []
    for family in families:
        if not family:
            continue
        entries = _family_entries(family)
        if not entries:
            continue
        cff = [e for e in entries if font_flavor(e.fname) == "CFF"]
        if not cff:
            continue                        # 本来就是 glyf，无需干预
        src = _find_variable_source(family)
        if src is None:
            if not quiet:
                print(f"  [fonts] {family}: 只有 CFF 字面且没有同族 glyf VF，"
                      f"PDF 文字层可能在 Illustrator 中乱码（用 pdf-outline 兜底）")
            continue
        need = sorted({400} | {_as_weight(e.weight) for e in cff} | set(weights))
        built = {}
        for w in need:
            try:
                built[w] = _static_instance(src, family, w)
            except Exception as exc:
                if not quiet:
                    print(f"  [fonts] {family} wght={w} 实例化失败: {exc}")
        if not built:
            continue
        keep = {str(Path(p).resolve()) for p in built.values()}
        # 静态目录可能已被 register_dirs 预先扫入：先按路径归一，只补没登记过的
        fm.fontManager.ttflist = [
            e for e in fm.fontManager.ttflist
            if e.name != family or str(Path(e.fname).resolve()) in keep]
        for p in built.values():
            if str(Path(p).resolve()) not in {str(Path(e.fname).resolve())
                                              for e in fm.fontManager.ttflist}:
                fm.fontManager.addfont(str(p))
        cached = getattr(fm.fontManager, "_findfont_cached", None)
        if cached is not None and hasattr(cached, "cache_clear"):
            cached.cache_clear()
        handled.append((family, sorted(built.values())))
        if not quiet:
            print(f"  [fonts] {family}: CFF {len(cff)} 个字面 → glyf 实例 {len(built)} 个 "
                  f"({', '.join(f'{w}' for w in sorted(built))})  源 {Path(src).name}")
    return handled



def font_cache_dir() -> Path:
    return Path(os.environ.get("SHANHAI_FONT_DIR") or Path.home() / ".cache" / "shanhai_atlas" / "fonts")


def static_dir() -> Path:
    """glyf 静态实例的缓存目录（VF 按字重实例化后落在这里）。"""
    return font_cache_dir() / "static"



def fetch_fonts(dest=None, quiet=False, timeout=120) -> Path:
    """下载默认字体到缓存目录（已存在则跳过）；返回目录。需要联网（registry.npmjs.org）。"""
    dest = Path(dest) if dest else font_cache_dir()
    for pkg, (ver, weights) in NPM_FONTS.items():
        out = dest / pkg
        if out.is_dir() and len(list(out.glob("*.ttf"))) >= len(weights):
            continue
        url = NPM_URL.format(pkg=pkg, ver=ver)
        if not quiet:
            print(f"downloading {pkg}@{ver} …")
        with urllib.request.urlopen(url, timeout=timeout) as r:
            blob = r.read()
        out.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
            for m in tf.getmembers():
                parts = Path(m.name).parts
                if (m.isfile() and m.name.endswith(".ttf") and len(parts) >= 3
                        and parts[-2] in weights):
                    (out / parts[-1]).write_bytes(tf.extractfile(m).read())
    if not quiet:
        print(f"fonts ready: {dest}")
    return dest


def register_dirs(dirs):
    n = 0
    for d in dirs:
        if d and os.path.isdir(d):
            for f in glob.glob(os.path.join(str(d), "**", "*.[ot]tf"), recursive=True):
                try:
                    fm.fontManager.addfont(f)
                    n += 1
                except Exception:
                    pass
    return n


#: 当前文字导出模式（``editable`` = SVG 保留 <text> 并内嵌字体子集；``outline`` = 转曲）
TEXT_MODE = "editable"


def setup(font_dirs=(), fetch=False, hashsalt="shanhai-atlas", quiet=False,
          text_mode="editable", preset=None):
    """注册字体并设置 matplotlib 全局参数；返回 FONT（cjk / serif / mono / math）。

    Parameters
    ----------
    font_dirs : 额外字体目录（递归扫描 .ttf/.otf）。环境变量 SHANHAI_FONT_DIR 与
                缓存目录总会被扫描。
    fetch     : 找不到中文字体时自动下载默认字体（需联网）。
    hashsalt  : SVG 内部 id 的固定盐值 → 相同输入输出逐字节一致（可复现）。
    preset    : ``None`` 用内置候选顺序；``"noto"`` / ``"source-han"`` /
                ``"system-win"`` / ``"serif-academic"`` 见 ``FONT_PRESETS``。
    text_mode : ``editable``（默认）→ ``svg.fonttype="none"``，文字在 Illustrator 里
                可直接编辑（字体由 ``Canvas.save()`` 内嵌子集带走）；
                ``outline`` → 旧行为 ``svg.fonttype="path"``，文字转曲、零字体依赖。
                单次导出可用 ``Canvas.save(text_mode=...)`` 覆盖。
    """
    dirs = [str(font_cache_dir()), os.environ.get("SHANHAI_FONT_DIR", "")] + [str(d) for d in
                                                                           font_dirs]
    register_dirs(dirs)
    names = {f.name for f in fm.fontManager.ttflist}

    def first(cands, default):
        return next((c for c in cands if c in names), default)

    pr = font_preset(preset) if preset else None
    if pr:
        CJK_CANDIDATES_LOCAL = pr["cjk"] + [c for c in CJK_CANDIDATES if c not in pr["cjk"]]
    else:
        CJK_CANDIDATES_LOCAL = CJK_CANDIDATES
    cjk = first(CJK_CANDIDATES_LOCAL, None)
    if cjk is None and fetch:
        register_dirs([str(fetch_fonts(quiet=quiet))])
        names = {f.name for f in fm.fontManager.ttflist}
        cjk = first(CJK_CANDIDATES_LOCAL, None)
    if cjk is None:
        raise RuntimeError("未找到中文字体。运行 `python -m shanhai_atlas fonts` 下载思源黑体等默认字体，"
                           "或用 setup(font_dirs=[...]) 指定含 Noto Sans SC / 思源黑体 / 微软雅黑 的目录。")
    FONT.cjk = cjk
    if pr:
        FONT.latin = first(pr["latin"], FONT.cjk)
        FONT.serif = first(pr["serif"], "DejaVu Serif")
        FONT.mono = first(pr["mono"], "DejaVu Sans Mono")
    else:
        FONT.latin = None
        FONT.serif = first(SERIF_CANDIDATES, "DejaVu Serif")
        FONT.mono = first(MONO_CANDIDATES, "DejaVu Sans Mono")
    # PDF 合规：CFF 字面 → glyf 静态实例（仅当该族确实有 CFF 字面时干预）
    ensure_truetype_faces((FONT.cjk, FONT.serif, FONT.mono), quiet=quiet)
    global TEXT_MODE
    if text_mode not in ("editable", "outline"):
        raise ValueError(f"text_mode 只支持 editable / outline，收到 {text_mode!r}")
    TEXT_MODE = text_mode
    # mpl ≤3.10 的 SVG 后端走 fm.weight_dict[prop.get_weight()]，只认字符串字重
    # （'bold'…），数字字重（400/700）直接 KeyError；mpl ≥3.11 已修。editable 模式
    # （svg.fonttype="none"）必须逐字画 text 才会踩到，所以垫片放在这里、与模式
    # 同时生效。按 name→value 补 int 自映射：CSS font-weight 数字与名称都合法，
    # 3.11 上 setdefault 是 no-op。工具只用 400/500/700，全部落在 weight_dict 值域。
    for _wname, _wval in list(fm.weight_dict.items()):
        if isinstance(_wval, int):
            fm.weight_dict.setdefault(_wval, _wval)
    plt.rcParams.update({
        "font.family": [FONT.cjk], "mathtext.fontset": "stix",
        # editable：文字保留 <text>（体积更小、AI 里能改）；outline：转曲（零字体依赖）
        "svg.fonttype": "none" if text_mode == "editable" else "path",
        "svg.hashsalt": hashsalt,
        "pdf.fonttype": 42, "ps.fonttype": 42, "axes.unicode_minus": False,
        "text.hinting": "no_hinting", "savefig.facecolor": "white",
        "axes.edgecolor": "#AEB7C2", "axes.linewidth": 0.6,
        "xtick.color": "#66717E", "ytick.color": "#66717E",
        "axes.labelcolor": "#2A3342", "text.color": "#2A3342",
    })
    _STATE["ready"] = True
    if not quiet:
        print(f"fonts: CJK={FONT.cjk} | serif={FONT.serif} | mono={FONT.mono} | "
              f"math=STIX | text_mode={TEXT_MODE}")
    return FONT


def ensure():
    """组件内部调用：若用户尚未 setup()，以静默方式按默认参数初始化。"""
    if not _STATE["ready"]:
        setup(quiet=True)


# --------------------------------------------------------------------------- #
# 字体预设：一个中文族 + 一个拉丁族（+ 衬线/等宽），全部 SIL OFL 或系统自带
# --------------------------------------------------------------------------- #
#: 每个预设给出的是**优先顺序**，setup(preset=...) 取第一个本机可用的族。
#: ``license`` 只描述这套组合的授权来源，不代替对该字体实际许可文件的核对。
FONT_PRESETS: dict[str, dict] = {
    "noto": {
        "name": "Noto 组合（默认，SIL OFL）",
        "cjk": ["Noto Sans SC", "Source Han Sans SC", "Source Han Sans CN", "Microsoft YaHei"],
        "latin": ["DejaVu Sans", "Inter", "Arial"],
        "serif": ["Source Serif 4", "Source Serif Pro", "DejaVu Serif", "Times New Roman"],
        "mono": ["DejaVu Sans Mono", "JetBrains Mono"],
        "license": "SIL OFL 1.1（Noto / Source Serif 4）＋ Bitstream Vera 系（DejaVu）",
        "note": "字形覆盖最全，拉丁小字用 DejaVu 兜底；缺字时自动追加回退族",
    },
    "source-han": {
        "name": "思源黑体 + Inter（SIL OFL）",
        "cjk": ["Source Han Sans SC", "Source Han Sans CN", "Noto Sans SC"],
        "latin": ["Inter", "DejaVu Sans", "Arial"],
        "serif": ["Source Serif 4", "Source Serif Pro", "DejaVu Serif"],
        "mono": ["JetBrains Mono", "DejaVu Sans Mono"],
        "license": "SIL OFL 1.1（Source Han Sans / Inter / Source Serif 4）",
        "note": "思源黑体是 Source Han Sans 的同一字体，西文集采用 Inter，观感更现代",
    },
    "system-win": {
        "name": "Windows 系统字号（投稿/评审通用）",
        "cjk": ["Microsoft YaHei", "SimHei", "SimSun", "Noto Sans SC"],
        "latin": ["Arial", "Times New Roman", "DejaVu Sans"],
        "serif": ["Times New Roman", "SimSun", "DejaVu Serif"],
        "mono": ["Consolas", "Courier New", "DejaVu Sans Mono"],
        "license": "随 Windows 分发，**不可随稿件再分发字体文件**（仅字名引用）",
        "note": "本机一定有、但受版权限制；SVG/PDF 里内嵌子集前请确认期刊允许",
    },
    "serif-academic": {
        "name": "Noto Serif SC + Source Serif 4（书刊/学位论文）",
        "cjk": ["Noto Serif SC", "Source Han Serif SC", "SimSun", "Noto Sans SC"],
        "latin": ["Source Serif 4", "Source Serif Pro", "Times New Roman", "DejaVu Serif"],
        "serif": ["Source Serif 4", "Source Serif Pro", "Noto Serif SC", "DejaVu Serif"],
        "mono": ["DejaVu Sans Mono"],
        "license": "SIL OFL 1.1；SimSun 为系统字体",
        "note": "正文式排版（图注、图版说明）更耐看，线图标签仍建议无衬线",
    },
}


def font_preset(name: str = "noto") -> dict:
    """取一套字体预设（返回副本，改它不影响全局）。"""
    key = (name or "noto").strip().lower()
    if key not in FONT_PRESETS:
        raise KeyError(f"未知字体预设 {name!r}，可选：{sorted(FONT_PRESETS)}")
    return {**FONT_PRESETS[key], "key": key}


def check_fonts(preset: str | None = None) -> dict:
    """体检当前字体：是否装上、是不是 glyf（PDF/AI 内嵌才合规）、授权提示。

    ``pdf.fonttype=42`` 只能嵌 TrueType(glyf) 轮廓；CFF/OTF 会退化成 Type3
    （= 文字变图形，Illustrator 里改不了）。所以这里专门标 ``glyf``。
    """
    from matplotlib import font_manager as _fm

    targets = {}
    if preset:
        pr = font_preset(preset)
        for slot in ("cjk", "latin", "serif", "mono"):
            for fam in pr.get(slot, []):
                targets.setdefault(fam, slot)
    else:
        targets = {FONT.cjk: "cjk", FONT.serif: "serif", FONT.mono: "mono"}

    rows, ok = [], True
    for fam, slot in targets.items():
        paths = [f.fname for f in _fm.fontManager.ttflist if f.name == fam]
        if not paths:
            rows.append({"family": fam, "slot": slot, "installed": False,
                         "flavor": None, "glyf": None, "path": None})
            ok = False
            continue
        flav = font_flavor(paths[0])
        rows.append({"family": fam, "slot": slot, "installed": True,
                     "flavor": flav, "glyf": flav == "glyf", "path": paths[0]})
        ok = ok and flav == "glyf"
    missing = [r["family"] for r in rows if not r["installed"]]
    cff = [r["family"] for r in rows if r["installed"] and not r["glyf"]]
    hints = []
    if missing:
        hints.append(f"未安装：{missing}（预设会顺延到下一候选）")
    if cff:
        hints.append(f"CFF 轮廓：{cff} —— pdf.fonttype=42 下会退化成 Type3，"
                     "先 ensure_truetype_faces() 生成静态 glyf 实例")
    return {"ok": ok and not missing, "preset": preset, "fonts": rows,
            "missing": missing, "cff": cff, "hint": "；".join(hints)}
