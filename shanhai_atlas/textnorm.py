"""文字规范化：把 ``$...$`` 公式无损折成 Unicode，并修掉"字体缺字 → 豆腐块"。

为什么需要这个模块
------------------
1. **公式会毁掉可编辑性**。matplotlib 的 SVG/PDF 后端遇到 ``$...$`` 就不再把整句当
   一个文本对象，而是**逐字符绝对定位**（SVG 里是一堆 ``<tspan x=...>``）。在
   Illustrator 里那就不是"可编辑文字"，而是一串碎片。实测：``时间 $t$ (s)`` 会变成
   8 个 tspan。把简单公式换成 Unicode 后，整句回到单个 ``<text>``。

2. **matplotlib 不做逐字回退**。某个文本的字体族没有某个字形时，它会直接落到
   ``LastResort``（豆腐块）。实测：中文落进 ``Source Serif 4`` 槽位时，导出的 PDF 里
   真的嵌入了 ``LastResortHE-Regular``。这里做 cmap 级别的字形覆盖检查，
   缺字就把该文本切到覆盖最全的字体族。

原则：**宁可不动，也不改意思**。一段公式里只要有一处无法无损表达，整段保持原样，
交给调用方记 warning。
"""
from __future__ import annotations

import re
from functools import lru_cache

import matplotlib
from matplotlib.text import Text

__all__ = [
    "math_to_unicode",
    "normalize_figure",
    "missing_glyphs",
    "repair_missing_glyphs",
    "GREEK", "SYMBOLS", "FUNCS",
]

# --------------------------------------------------------------------------- #
# LaTeX -> Unicode 映射表
# --------------------------------------------------------------------------- #
GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ϵ", "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
    "pi": "π", "varpi": "ϖ", "rho": "ρ", "varrho": "ϱ", "sigma": "σ",
    "varsigma": "ς", "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "ϕ",
    "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}

SYMBOLS = {
    "pm": "±", "mp": "∓", "times": "×", "div": "÷", "cdot": "·", "ast": "∗",
    "star": "⋆", "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "neq": "≠",
    "ne": "≠", "approx": "≈", "sim": "∼", "simeq": "≃", "cong": "≅",
    "equiv": "≡", "propto": "∝", "infty": "∞", "partial": "∂", "nabla": "∇",
    "sum": "∑", "prod": "∏", "int": "∫", "oint": "∮", "degree": "°",
    "circ": "∘", "rightarrow": "→", "to": "→", "leftarrow": "←",
    "leftrightarrow": "↔", "Rightarrow": "⇒", "Leftarrow": "⇐",
    "Leftrightarrow": "⇔", "mapsto": "↦", "uparrow": "↑", "downarrow": "↓",
    "in": "∈", "notin": "∉", "ni": "∋", "subset": "⊂", "subseteq": "⊆",
    "supset": "⊃", "supseteq": "⊇", "cup": "∪", "cap": "∩", "emptyset": "∅",
    "forall": "∀", "exists": "∃", "neg": "¬", "wedge": "∧", "vee": "∨",
    "otimes": "⊗", "oplus": "⊕", "perp": "⊥", "parallel": "∥",
    "angle": "∠", "triangle": "△", "square": "□", "diamond": "⋄",
    "cdots": "⋯", "ldots": "…", "dots": "…", "vdots": "⋮", "ddots": "⋱",
    "prime": "′", "hbar": "ℏ", "ell": "ℓ", "dagger": "†", "ddagger": "‡",
    "checkmark": "✓", "surd": "√", "mid": "∣", "vert": "|", "Vert": "‖",
    "top": "ᵀ", "bot": "⊥",
}

#: 二元运算符两侧补空格，贴近 mathtext 的排版观感
BINARY = {
    "pm", "mp", "times", "div", "cdot", "ast", "star", "le", "leq", "ge", "geq",
    "neq", "ne", "approx", "sim", "simeq", "cong", "equiv", "propto", "in",
    "notin", "ni", "subset", "subseteq", "supset", "supseteq", "cup", "cap",
    "rightarrow", "to", "leftarrow", "leftrightarrow", "Rightarrow",
    "Leftarrow", "Leftrightarrow", "mapsto", "otimes", "oplus", "perp",
    "parallel", "mid", "wedge", "vee",
}

#: 正体函数名（``\log``、``\max`` 之类）
FUNCS = {
    "log", "ln", "lg", "exp", "max", "min", "argmax", "argmin", "sin", "cos",
    "tan", "cot", "sec", "csc", "arcsin", "arccos", "arctan", "sinh", "cosh",
    "tanh", "det", "dim", "ker", "gcd", "lim", "sup", "inf", "std", "var",
    "softmax", "sigmoid", "relu", "tr", "rank", "diag", "median", "mean", "mod",
}

SUP = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶",
    "7": "⁷", "8": "⁸", "9": "⁹", "+": "⁺", "-": "⁻", "−": "⁻", "=": "⁼",
    "(": "⁽", ")": "⁾", "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ",
    "f": "ᶠ", "g": "ᵍ", "h": "ʰ", "i": "ⁱ", "j": "ʲ", "k": "ᵏ", "l": "ˡ",
    "m": "ᵐ", "n": "ⁿ", "o": "ᵒ", "p": "ᵖ", "r": "ʳ", "s": "ˢ", "t": "ᵗ",
    "u": "ᵘ", "v": "ᵛ", "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ", "T": "ᵀ",
    "A": "ᴬ", "B": "ᴮ", "D": "ᴰ", "E": "ᴱ", "I": "ᴵ", "K": "ᴷ", "L": "ᴸ",
    "M": "ᴹ", "N": "ᴺ", "O": "ᴼ", "P": "ᴾ", "R": "ᴿ", "U": "ᵁ", "V": "ⱽ",
    "W": "ᵂ", "′": "′", "θ": "ᶿ", "γ": "ᵞ", "φ": "ᵠ",
}

SUB = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆",
    "7": "₇", "8": "₈", "9": "₉", "+": "₊", "-": "₋", "−": "₋", "=": "₌",
    "(": "₍", ")": "₎", "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ",
    "k": "ₖ", "l": "ₗ", "m": "ₘ", "n": "ₙ", "o": "ₒ", "p": "ₚ", "r": "ᵣ",
    "s": "ₛ", "t": "ₜ", "u": "ᵤ", "v": "ᵥ", "x": "ₓ",
    "β": "ᵦ", "γ": "ᵧ", "ρ": "ᵨ", "φ": "ᵩ", "χ": "ᵪ",
}

#: 带语义、无法无损展开的命令 → 整段放弃
UNSUPPORTED = {
    "sqrt", "binom", "underline", "overbrace", "underbrace", "stackrel",
    "overset", "underset", "begin", "end", "left", "right", "big", "Big",
    "bigl", "bigr", "Bigl", "Bigr", "substack", "limits", "displaystyle",
    "textstyle", "quad", "qquad", "hspace", "vspace",
}

#: 只影响字形、可以安全丢掉样式的命令
STYLE_ONLY = {
    "mathrm", "mathit", "mathbf", "mathsf", "mathtt", "mathcal", "boldsymbol",
    "text", "textrm", "textit", "textbf", "operatorname", "mathnormal", "rm",
    "bf", "it", "textup", "textnormal",
}

ACCENTS = {
    "hat": "\u0302", "widehat": "\u0302", "tilde": "\u0303", "widetilde": "\u0303",
    "bar": "\u0304", "overline": "\u0304", "dot": "\u0307", "ddot": "\u0308",
    "vec": "\u20d7",
}

SPACES = {" ", ",", ";", ":", "!", "enspace", "thinspace", "medspace"}

_GLYPHS = set(GREEK.values()) | set(SYMBOLS.values()) | set(SUP.values()) | set(SUB.values())


class _Unsupported(Exception):
    """该公式无法无损表达成 Unicode。"""


# --------------------------------------------------------------------------- #
# 解析
# --------------------------------------------------------------------------- #
def _map_run(chars: str, table: dict[str, str]) -> str:
    out = []
    for c in chars:
        if c in table:
            out.append(table[c])
        elif c.isspace():
            out.append(" ")
        elif c in _GLYPHS:
            out.append(c)
        elif c.isascii() and (c.isalnum() or c in ",.;:/|'()[]<>-+="):
            out.append(c)          # 没有上/下标字形，退化成原字符（仍是文字）
        else:
            raise _Unsupported(c)
    return "".join(out)


def _group(s: str, i: int) -> tuple[str, int]:
    """从 i 读一个 ``{...}`` 组或单个 token。"""
    if i >= len(s):
        raise _Unsupported("eof")
    if s[i] == "{":
        depth = 0
        for j in range(i, len(s)):
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0:
                    return s[i + 1:j], j + 1
        raise _Unsupported("unbalanced {")
    if s[i] == "\\":
        m = re.match(r"\\([A-Za-z]+|.)", s[i:])
        if not m:
            raise _Unsupported("bad escape")
        return m.group(0), i + len(m.group(0))
    return s[i], i + 1


def _unwrap(s: str) -> str:
    """只有当整串被一对配对的 ``{}`` 包住时才脱壳——``strip("{}")`` 会误伤 ``10^{-3}``。"""
    if not (s.startswith("{") and s.endswith("}")):
        return s
    depth = 0
    for i, ch in enumerate(s):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and i != len(s) - 1:
                return s          # 外壳在中间就闭合了 → 不是整体包住
    return s[1:-1]


def _wrap(s: str) -> str:
    return s if len(s) <= 1 or all(c.isalnum() or c in ".'" for c in s) else f"({s})"


def _segment(seg: str) -> str:
    out: list[str] = []
    i, n = 0, len(seg)
    while i < n:
        ch = seg[i]
        if ch == "\\":
            m = re.match(r"\\([A-Za-z]+|.)\s*", seg[i:])
            if not m:
                raise _Unsupported("bad escape")
            name = m.group(1)
            i += len(m.group(0))
            if name in SPACES:
                out.append(" ")
                continue
            if name in UNSUPPORTED:
                raise _Unsupported("\\" + name)
            if name in STYLE_ONLY:
                body, i = _group(seg, i)
                out.append(_segment(_unwrap(body)))
                continue
            if name in ("frac", "dfrac", "tfrac"):
                num, i = _group(seg, i)
                den, i = _group(seg, i)
                a = _segment(_unwrap(num)).strip()
                b = _segment(_unwrap(den)).strip()
                if not a or not b:
                    raise _Unsupported("frac")
                out.append(f"{_wrap(a)}/{_wrap(b)}")
                continue
            if name in ACCENTS:
                body, i = _group(seg, i)
                base = _segment(_unwrap(body)).strip()
                if len(base) != 1:
                    raise _Unsupported("accent")
                out.append(base + ACCENTS[name])
                continue
            if name in FUNCS:
                out.append(name)
                continue
            if name in GREEK:
                out.append(GREEK[name])
                continue
            if name in SYMBOLS:
                sym = SYMBOLS[name]
                out.append(f" {sym} " if name in BINARY else sym)
                continue
            if name in ("_", "^", "{", "}", "%", "&", "#", "$"):
                out.append(name)
                continue
            raise _Unsupported("\\" + name)
        if ch in "^_":
            table = SUP if ch == "^" else SUB
            body, i = _group(seg, i + 1)
            out.append(_map_run(_segment(_unwrap(body)), table))
            continue
        if ch == "{":
            body, i = _group(seg, i)
            out.append(_segment(body))
            continue
        if ch == "}":
            raise _Unsupported("unbalanced }")
        if ch == "~":
            out.append(" ")
            i += 1
            continue
        if ch == "-":
            out.append("−")        # 数学减号
            i += 1
            continue
        if ch == "'":
            out.append("′")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def math_to_unicode(text: str) -> str | None:
    """整串里的 ``$...$`` → Unicode；**任何一段转不了就返回 None**（不改语义）。"""
    if not isinstance(text, str) or "$" not in text:
        return text
    if "\\$" in text:                       # 转义的美元符，不碰
        return None
    parts = text.split("$")
    if len(parts) % 2 == 0:                 # 落单的 $
        return None
    out = [parts[0]]
    for k in range(1, len(parts), 2):
        seg = parts[k]
        if not seg.strip():
            return None
        try:
            out.append(_segment(_unwrap(seg)))
        except _Unsupported:
            return None
        out.append(parts[k + 1])
    return re.sub(r"[ \t]{2,}", " ", "".join(out))


# --------------------------------------------------------------------------- #
# 作用于 Figure
# --------------------------------------------------------------------------- #
def _texts(fig):
    return [t for t in fig.findobj(Text) if (t.get_text() or "").strip()]


def normalize_figure(fig, enabled=True) -> dict:
    """把图里所有可转的公式换成 Unicode。

    返回 ``{"converted": n, "skipped": [原串...]}``；``skipped`` 里是**转不了**的公式，
    它们仍是矢量/逐字符绘制，必须让调用方知道（否则"可编辑"是空话）。
    """
    report = {"converted": 0, "skipped": []}
    if not enabled:
        return report
    for t in _texts(fig):
        cur = t.get_text()
        if "$" not in cur:
            continue
        got = math_to_unicode(cur)
        if got is None:
            if cur not in report["skipped"]:
                report["skipped"].append(cur)
        elif got != cur:
            t.set_text(got)
            report["converted"] += 1
    return report


# --------------------------------------------------------------------------- #
# 字形覆盖
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=64)
def _cmap_of(path: str) -> frozenset[int]:
    from fontTools.ttLib import TTFont
    with TTFont(path, lazy=True) as f:
        return frozenset(f.getBestCmap() or {})


def _font_path(family: str, weight=None) -> str | None:
    from matplotlib import font_manager as fm
    try:
        prop = fm.FontProperties(family=family, weight=weight)
        path = fm.findfont(prop, fallback_to_default=False)
    except Exception:
        return None
    return path or None


def missing_glyphs(text: str, families) -> dict[str, list[str]]:
    """返回 ``{字体族: [缺的字符]}``；族名找不到字体文件时记 ``['<font not found>']``。"""
    if isinstance(families, str):
        families = [families]
    out: dict[str, list[str]] = {}
    for fam in families or []:
        path = _font_path(fam)
        if not path:
            out[fam] = ["<font not found>"]
            continue
        cmap = _cmap_of(path)
        miss = sorted({c for c in text if not c.isspace() and ord(c) not in cmap})
        if miss:
            out[fam] = miss
    return out


def repair_missing_glyphs(fig, cjk_family: str | None = None,
                          fallback=("DejaVu Sans",)) -> list[dict]:
    """修掉"当前字体缺字 → 豆腐块"。

    matplotlib ≥3.6 支持**字体族列表 + 逐字回退**：列表里第一个族缺某个字形时，
    会自动去后面的族里找。所以最稳的修法不是"整段换字体"（中英混排常常没有哪个
    单一字族能全覆盖），而是**把能补上缺字的那一族追加到列表里**：

    * 首选：保持主字体不变，追加一个能覆盖缺失字符的族（``mode="append"``）；
    * 兜底：只有当某一族能覆盖**整段**文本时，才整体换族（``mode="replace"``）；
    * 都不行：记进 ``unresolved``，由调用方决定（通常是提醒换写成 mathtext/Unicode）。

    返回修复清单，例如
    ``[{"text": "PROBE · 导出层", "was": "Noto Sans SC", "now": ["Noto Sans SC", "DejaVu Sans"],
        "missing": ["·"], "mode": "append"}]``。
    """
    fixed: list[dict] = []
    for t in _texts(fig):
        s = t.get_text()
        fams = list(t.get_fontfamily() or [])
        if not fams:
            continue
        bad = missing_glyphs(s, [fams[0]])
        if not bad:
            continue
        missing = bad[fams[0]]
        pool = [f for f in ([cjk_family] if cjk_family else []) + list(fallback) if f]
        # ① 追加能覆盖缺失字符的族（保留主字体，样式不变）
        for cand in pool:
            if cand in fams:
                continue
            if not missing_glyphs("".join(missing), [cand]):
                t.set_fontfamily(fams + [cand])
                fixed.append({"text": s, "was": fams[0], "now": fams + [cand],
                              "missing": missing, "mode": "append"})
                break
        else:
            # ② 整体换族：找第一个能覆盖全部字符的
            for cand in pool:
                if cand in fams:
                    continue
                if not missing_glyphs(s, [cand]):
                    t.set_fontfamily([cand] + [f for f in fams if f != cand])
                    fixed.append({"text": s, "was": fams[0], "now": [cand],
                                  "missing": missing, "mode": "replace"})
                    break
            else:
                fixed.append({"text": s, "was": fams[0], "now": fams,
                              "missing": missing, "mode": "unresolved"})
    return fixed
