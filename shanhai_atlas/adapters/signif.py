# -*- coding: utf-8 -*-
"""显著性括号：装了 `statannotations` 就用它，没装就用内置的括号 + 星号。

约定（与论文正文一致，避免"图上一颗星、正文一个 p"）：
    p < 0.001 → *** ;  p < 0.01 → ** ;  p < 0.05 → * ;  否则 ns
星号规则可以在调用处覆盖，但**默认值只此一套**，不随期刊变。
"""
from __future__ import annotations

__all__ = ["significance_brackets", "backend", "stars"]


def backend() -> str:
    try:
        import statannotations  # noqa: F401
        return "statannotations"
    except Exception:
        return "native"


def stars(p) -> str:
    if p is None:
        return ""
    if isinstance(p, str):
        return p                      # 直接给 "***" / "ns" 就原样用
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "ns"


def significance_brackets(ax, pairs, *, y=None, h=None, text_size=6.0, lw=0.6,
                          color="#2A3342", show_label=True, extend=0.02):
    """在轴上画显著性括号。

    Parameters
    ----------
    pairs : sequence[(x1, x2, p) | (x1, x2, p, y)]
        比较的两组 x 位置 + p 值（或直接给星号字符串）。``y`` 省略时自动叠放在数据顶部。
    h : float
        括号高度（数据坐标）；省略时按 y 轴跨度取 2.5%。
    """
    ylim = ax.get_ylim()
    span = ylim[1] - ylim[0]
    h = h if h is not None else span * 0.025
    if y is None:
        y = ylim[1] + span * 0.02
    out = []
    for item in pairs:
        x1, x2, p = item[0], item[1], item[2]
        yy = item[3] if len(item) > 3 else y
        ax.plot([x1, x1, x2, x2], [yy, yy + h, yy + h, yy], color=color, lw=lw,
                solid_capstyle="butt", clip_on=False, zorder=10)
        if show_label:
            ax.text((x1 + x2) / 2, yy + h * 1.12, stars(p), ha="center", va="bottom",
                    fontsize=text_size, color=color, clip_on=False, zorder=11)
        out.append({"x1": x1, "x2": x2, "y": yy, "p": p, "label": stars(p)})
        y = max(y, yy) + h * 1.6                 # 下一组自动往上叠
    ax.set_ylim(ylim[0], max(ylim[1], y + span * extend))
    return {"backend": backend(), "brackets": out}
