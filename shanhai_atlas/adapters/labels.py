# -*- coding: utf-8 -*-
"""标签避让：装了 `adjustText` 就用它，没装就用内置的贪心推开。

内置实现只做**竖直方向的推开**：学术图上重叠的标签九成是"同一列散点的注释挤在一起"，
上下错开比四处乱飞更可读，也不会把标签甩到图外。真需要全方向优化再装 adjustText。
"""
from __future__ import annotations

__all__ = ["spread_labels", "backend", "count_overlaps"]


def backend() -> str:
    try:
        import adjustText  # noqa: F401
        return "adjustText"
    except Exception:
        return "native"


def count_overlaps(texts, r=None) -> int:
    """统计互相重叠的文本对数（用显示坐标，和 `Canvas.audit` 同一套口径）。"""
    import itertools
    fig = texts[0].figure if texts else None
    if fig is None:
        return 0
    r = r or fig.canvas.get_renderer()
    bbs = []
    for t in texts:
        try:
            bb = t.get_window_extent(r)
        except Exception:
            continue
        if bb.width > 0 and bb.height > 0:
            bbs.append(bb)
    n = 0
    for a, b in itertools.combinations(bbs, 2):
        if (min(a.x1, b.x1) - max(a.x0, b.x0) > 0.5
                and min(a.y1, b.y1) - max(a.y0, b.y0) > 0.5):
            n += 1
    return n


def spread_labels(texts, *, max_iter=200, only_move=("y",), force=0.06, arrow=False):
    """让一组文本互不重叠。

    返回 ``{"backend": ..., "before": n, "after": m, "moved": k}``。
    ``before > 0 and after == 0`` 才算成功；内置实现不保证收敛到 0（复杂图交给 adjustText）。
    """
    texts = [t for t in texts if (t.get_text() or "").strip()]
    if not texts:
        return {"backend": backend(), "before": 0, "after": 0, "moved": 0}
    fig = texts[0].figure
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    before = count_overlaps(texts, r)

    if backend() == "adjustText":
        from adjustText import adjust_text
        adjust_text(texts, only_move={"text": "y", "static": "y", "explode": "y",
                                      "pull": "y"} if "y" in only_move else None,
                    force_text=(0, force), arrowprops=None)
        fig.canvas.draw()
        return {"backend": "adjustText", "before": before,
                "after": count_overlaps(texts, r), "moved": len(texts)}

    # ---- 内置贪心：按 y 从小到大，遇到重叠就往上顶一格 ----
    def _get_y(t):
        xy = getattr(t, "xy", None)              # Annotation 的真实位置在 .xy 上
        if xy is not None:
            return float(xy[1])
        return float(t.get_position()[1])

    def _set_y(t, v):
        if getattr(t, "xy", None) is not None:
            t.xy = (t.xy[0], v)
        else:
            x_, _ = t.get_position()
            t.set_position((x_, v))

    moved = 0
    step_pt = 7.0
    for _ in range(int(max_iter)):
        fig.canvas.draw()
        bbs = [(t, t.get_window_extent(r)) for t in texts]
        bbs.sort(key=lambda p: p[1].y0)
        fixed = True
        for i in range(len(bbs) - 1):
            (t1, a), (t2, b) = bbs[i], bbs[i + 1]
            if (min(a.x1, b.x1) - max(a.x0, b.x0) > 0.5
                    and min(a.y1, b.y1) - max(a.y0, b.y0) > 0.5):
                # 把上面那个再往上顶：1 pt 换算成数据坐标
                y0 = _get_y(t2)
                if t2.axes is not None:
                    ax_ = t2.axes
                    inv = ax_.transData.inverted()
                    p0 = inv.transform((0, 0))
                    p1 = inv.transform((0, step_pt * fig.dpi / 72.0))
                    _set_y(t2, y0 + (p1[1] - p0[1]))
                else:
                    _set_y(t2, y0 + 0.01)
                moved += 1
                fixed = False
        if fixed:
            break
    fig.canvas.draw()
    return {"backend": "native", "before": before, "after": count_overlaps(texts, r),
            "moved": moved}
