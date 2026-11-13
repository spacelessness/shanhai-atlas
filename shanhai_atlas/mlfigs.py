# -*- coding: utf-8 -*-
"""机器学习图件：训练曲线 / 混淆矩阵 / ROC-PR / 消融表 / 注意力热图 / 结构图。

设计取舍
--------
* **不引入 sklearn**：ROC/PR 的全部指标用 numpy 手算（`roc_from_scores` / `pr_from_scores`），
  只在排序与阈值扫描上花几十行——换来的是"装完 matplotlib 就能画"，而不是多一个百兆依赖。
* **不新造视觉语言**：坐标轴、刻度、配色全部复用 `charts.style_axes` 与 `theme`，
  所以 ML 图和地理图、示意图放在同一份稿子里不会打架。
* **图注写结论，不写"图 3. 训练曲线"**：每个函数都能返回关键读数（`info`），方便直接拼进 caption。
"""
from __future__ import annotations

import numpy as np

from .charts import panel_label, style_axes
from .fonts import FONT
from .theme import C, CMAPS, SERIES, Tokens

__all__ = ["training_curves", "confusion_matrix", "roc_from_scores", "pr_from_scores",
           "roc_curves", "pr_curves", "ablation_table", "attention_map", "arch_diagram",
           "sparkline"]

def _panel(ax, letter):
    """面板编号：比 `charts.panel_label` 的默认位置再往左上一档。

    实测默认的 (-0.02, 1.02) 会撞上最高的那个 y 刻度标签（`audit(full=True)` 直接报
    overlap），所以这里固定放 (-0.13, 1.04)——足够躲开刻度，又不会跑出画布。
    """
    return panel_label(ax, letter, x=-0.13, y=1.04, size=TYPE.panel)


#: numpy 2.x 把 trapz 改名为 trapezoid（1.x 没有新名字）——本地锁 1.26、云端 2.x，两头都要能跑
_trapz = getattr(np, "trapezoid", None) or getattr(np, "trapz")

LW = Tokens(hair=0.45, thin=0.6, base=0.8, strong=1.3)
TYPE = Tokens(tick=6.0, label=6.6, note=5.6, panel=8.0)


# --------------------------------------------------------------------------- #
# 指标（纯 numpy）
# --------------------------------------------------------------------------- #
def roc_from_scores(y_true, y_score):
    """返回 ``(fpr, tpr, auc)``。任意阈值下的阶梯曲线，含 (0,0) 与 (1,1) 端点。"""
    y = np.asarray(y_true).astype(bool).ravel()
    s = np.asarray(y_score, dtype=float).ravel()
    if y.size != s.size:
        raise ValueError(f"y_true / y_score 长度不一致：{y.size} vs {s.size}")
    if y.all() or not y.any():
        raise ValueError("y_true 只有一个类别，ROC 无定义")
    order = np.argsort(-s, kind="mergesort")
    y, s = y[order], s[order]
    tp = np.cumsum(y)
    fp = np.cumsum(~y)
    # 只在分数发生变化处取样（tie 一起跳，避免锯齿）
    keep = np.r_[np.diff(s) != 0, True]
    tpr = np.r_[0.0, tp[keep] / y.sum()]
    fpr = np.r_[0.0, fp[keep] / (~y).sum()]
    auc = float(_trapz(tpr, fpr))
    return fpr, tpr, auc


def pr_from_scores(y_true, y_score):
    """返回 ``(recall, precision, ap)``；AP 用阶梯积分（与 sklearn 的 average_precision 同义）。"""
    y = np.asarray(y_true).astype(bool).ravel()
    s = np.asarray(y_score, dtype=float).ravel()
    if y.all() or not y.any():
        raise ValueError("y_true 只有一个类别，PR 无定义")
    order = np.argsort(-s, kind="mergesort")
    y, s = y[order], s[order]
    tp = np.cumsum(y)
    fp = np.cumsum(~y)
    keep = np.r_[np.diff(s) != 0, True]
    prec = tp[keep] / np.maximum(tp[keep] + fp[keep], 1)
    rec = tp[keep] / y.sum()
    ap = float(np.sum(np.diff(np.r_[0.0, rec]) * prec))
    return rec, prec, ap


# --------------------------------------------------------------------------- #
# 训练曲线
# --------------------------------------------------------------------------- #
def training_curves(ax, history, metric="loss", val=None, *, smooth=0, mark_best=True,
                    best="min", logy=False, label=None, panel=None, note=None):
    """训练/验证曲线。

    Parameters
    ----------
    history : dict[str, sequence] | sequence
        形如 ``{"loss": [...], "val_loss": [...], "acc": [...], "val_acc": [...]}``；
        也接受直接给一条曲线序列。
    smooth : int
        移动平均窗口（0 = 不平滑）。只影响**画出来的线**，`info` 里的读数始终用原始值。
    best : {"min", "max"}
        最优轮次取最小值（loss）还是最大值（acc/AUC）。
    """
    if isinstance(history, dict):
        series = {metric: history[metric]}
        vkey = val or f"val_{metric}"
        if vkey in history:
            series[vkey] = history[vkey]
    else:
        series = {metric: np.asarray(history, dtype=float)}
        vkey = None

    ax_curves, info = {}, {}
    for i, (name, ys) in enumerate(series.items()):
        ys = np.asarray(ys, dtype=float)
        xs = np.arange(1, ys.size + 1)
        is_val = name == vkey
        color = SERIES[1] if is_val else SERIES[0]
        plot = ys
        if smooth and smooth > 1 and ys.size >= smooth:
            k = np.ones(int(smooth)) / smooth
            plot = np.convolve(ys, k, mode="valid")
            xs_plot = xs[smooth - 1:]
        else:
            xs_plot = xs
        (ln,) = ax.plot(xs_plot, plot, color=color, lw=LW.base if is_val else LW.strong,
                        ls="--" if is_val else "-", label=label or name,
                        marker="o" if ys.size <= 12 else None, ms=2.2, mfc="white", mew=LW.thin)
        ax_curves[name] = ln
        idx = int(np.argmin(ys) if best == "min" else np.argmax(ys))
        info[name] = {"best_epoch": idx + 1, "best": float(ys[idx]), "final": float(ys[-1])}

    if mark_best and vkey in series:
        ys = np.asarray(series[vkey], dtype=float)
        idx = int(np.argmin(ys) if best == "min" else np.argmax(ys))
        ax.scatter([idx + 1], [ys[idx]], s=16, color=SERIES[1], zorder=5,
                   edgecolor="white", linewidth=0.6)
        ax.annotate(f"最佳 #{idx + 1}\n{ys[idx]:.3f}", (idx + 1, ys[idx]),
                    textcoords="offset points", xytext=(6, 6), fontsize=TYPE.note,
                    color=C.gray, family=FONT.cjk)
        info["best_epoch"] = idx + 1

    if logy:
        ax.set_yscale("log")
    ax.set_xlabel("轮次 epoch", fontsize=TYPE.label, family=FONT.cjk)
    ax.set_ylabel(metric, fontsize=TYPE.label)
    style_axes(ax, grid="y")
    if panel:
        _panel(ax, panel)
    if note:
        ax.text(0.98, 0.04, note, transform=ax.transAxes, ha="right", va="bottom",
                fontsize=TYPE.note, color=C.gray, family=FONT.cjk)
    return {"lines": ax_curves, "info": info}


# --------------------------------------------------------------------------- #
# 混淆矩阵
# --------------------------------------------------------------------------- #
def confusion_matrix(ax, cm, labels=None, *, normalize=False, show_counts=True,
                     cmap="navy", panel=None, title=None, threshold=0.5):
    """混淆矩阵热图：对角=正确（深），非对角=错误（用陶土橙描边标出）。"""
    m = np.asarray(cm, dtype=float)
    if m.ndim != 2 or m.shape[0] != m.shape[1]:
        raise ValueError(f"混淆矩阵必须是方阵，收到 {m.shape}")
    n = m.shape[0]
    labels = list(labels) if labels is not None else [str(i) for i in range(n)]
    if len(labels) != n:
        raise ValueError("labels 数量与矩阵阶数不一致")
    disp = m / np.maximum(m.sum(axis=1, keepdims=True), 1) if normalize else m

    im = ax.imshow(disp, cmap=CMAPS[cmap], vmin=0, vmax=disp.max() if disp.max() else 1,
                   aspect="equal")
    ax.set_xticks(range(n), labels, fontsize=TYPE.tick, family=FONT.cjk)
    ax.set_yticks(range(n), labels, fontsize=TYPE.tick, family=FONT.cjk)
    ax.set_xlabel("预测", fontsize=TYPE.label, family=FONT.cjk)
    ax.set_ylabel("真实", fontsize=TYPE.label, family=FONT.cjk)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0, colors=C.gray)

    vmax = disp.max() or 1
    for i in range(n):
        for j in range(n):
            v = disp[i, j]
            txt = f"{v:.2f}" if normalize else f"{int(m[i, j])}"
            if show_counts and normalize:
                txt = f"{txt}\n({int(m[i, j])})"
            ax.text(j, i, txt, ha="center", va="center", fontsize=TYPE.tick,
                    color="white" if v > vmax * 0.55 else C.ink,
                    weight=700 if i == j else 400)
            if i != j and v > 0:
                ax.add_patch(__import__("matplotlib").patches.Rectangle(
                    (j - 0.5, i - 0.5), 1, 1, fill=False, ec=SERIES[2], lw=LW.strong, zorder=3))

    total = m.sum()
    acc = float(np.trace(m) / total) if total else float("nan")
    if title:
        ax.set_title(title, fontsize=TYPE.label, color=C.ink, family=FONT.cjk, pad=4)
    if panel:
        _panel(ax, panel)
    return {"acc": acc, "n": int(total), "errors": int(total - np.trace(m)),
            "image": im, "normalized": bool(normalize)}


# --------------------------------------------------------------------------- #
# ROC / PR
# --------------------------------------------------------------------------- #
def _draw_curve(ax, x, y, name, color, area, area_label, step):
    if step:
        ax.step(x, y, where="post", color=color, lw=LW.strong,
                label=f"{name} ({area_label} = {area:.3f})")
    else:
        ax.plot(x, y, color=color, lw=LW.strong, label=f"{name} ({area_label} = {area:.3f})")


def roc_curves(ax, curves, *, panel=None, diagonal=True, step=False, legend=True,
               title=None):
    """ROC 曲线。

    ``curves`` 可为 ``{name: (fpr, tpr, auc)}``，也可为 ``{name: (y_true, y_score)}``
    （自动算 AUC）。
    """
    out = {}
    for i, (name, val) in enumerate(curves.items()):
        if len(val) == 3:
            fpr, tpr, auc = (np.asarray(v, dtype=float) for v in val)
        else:
            fpr, tpr, auc = roc_from_scores(val[0], val[1])
        _draw_curve(ax, fpr, tpr, name, SERIES[i % len(SERIES)], float(auc), "AUC", step)
        out[name] = float(auc)
    if diagonal:
        ax.plot([0, 1], [0, 1], color=C.axis, lw=LW.thin, ls=(0, (2, 3)), zorder=0)
    ax.set_xlim(-0.01, 1.01)
    ax.set_ylim(-0.01, 1.01)
    ax.set_xlabel("假阳性率 FPR", fontsize=TYPE.label, family=FONT.cjk)
    ax.set_ylabel("真阳性率 TPR", fontsize=TYPE.label, family=FONT.cjk)
    style_axes(ax, grid=None)
    if legend:
        ax.legend(loc="lower right", fontsize=TYPE.note, frameon=False, handlelength=1.4)
    if title:
        ax.set_title(title, fontsize=TYPE.label, color=C.ink, family=FONT.cjk, pad=4)
    if panel:
        _panel(ax, panel)
    return {"auc": out}


def pr_curves(ax, curves, *, panel=None, baseline=None, step=True, legend=True, title=None):
    """PR 曲线（默认阶梯画法，符合"阈值扫描"语义）。``baseline`` 给正类比例画水平虚线。"""
    out = {}
    for i, (name, val) in enumerate(curves.items()):
        if len(val) == 3:
            rec, prec, ap = (np.asarray(v, dtype=float) for v in val)
        else:
            rec, prec, ap = pr_from_scores(val[0], val[1])
        _draw_curve(ax, rec, prec, name, SERIES[i % len(SERIES)], float(ap), "AP", step)
        out[name] = float(ap)
    if baseline is not None:
        ax.axhline(float(baseline), color=C.axis, lw=LW.thin, ls=(0, (2, 3)), zorder=0)
    ax.set_xlim(-0.01, 1.01)
    ax.set_ylim(-0.01, 1.05)
    ax.set_xlabel("召回率 Recall", fontsize=TYPE.label, family=FONT.cjk)
    ax.set_ylabel("精确率 Precision", fontsize=TYPE.label, family=FONT.cjk)
    style_axes(ax, grid="y")
    if legend:
        ax.legend(loc="lower left", fontsize=TYPE.note, frameon=False, handlelength=1.4)
    if title:
        ax.set_title(title, fontsize=TYPE.label, color=C.ink, family=FONT.cjk, pad=4)
    if panel:
        _panel(ax, panel)
    return {"ap": out}


# --------------------------------------------------------------------------- #
# 消融表（画在 Canvas 上，而不是 ax.table）
# --------------------------------------------------------------------------- #
def ablation_table(cv, x, y, w, rows, *, columns=None, row_h=None, size=6.4,
                   highlight="max", highlight_col=None, rule=True, panel=None):
    """消融实验表：直接用画布排版（`ax.table` 的中文字距与线宽都调不动）。

    Parameters
    ----------
    rows : sequence[dict] | sequence[sequence]
        每行一条实验；dict 形式按键取列；list 形式按 ``columns`` 顺序。
    highlight : {"max", "min", None}
        用哪一列（``highlight_col``）判定"最优"，最优行加粗 + 古铜金左标。
    """
    data = [list(r.values()) if isinstance(r, dict) else list(r) for r in rows]
    ncol = len(data[0])
    columns = list(columns) if columns else (
        list(rows[0].keys()) if isinstance(rows[0], dict) else [f"列{i}" for i in range(ncol)])
    if len(columns) != ncol:
        raise ValueError(f"columns 数量 {len(columns)} 与行宽 {ncol} 不一致")
    if isinstance(highlight_col, str):            # 允许直接给列名
        if highlight_col not in columns:
            raise KeyError(f"highlight_col={highlight_col!r} 不在 {columns} 里")
        highlight_col = columns.index(highlight_col)

    row_h = row_h or (size / 72.0 * 2.05)
    head_h = row_h * 1.15
    num = [i for i, c in enumerate(columns) if all(
        isinstance(r[i], (int, float, np.floating, np.integer)) for r in data)]
    best_row = None
    if highlight and num:
        col = highlight_col if highlight_col is not None else num[-1]
        vals = [float(r[col]) for r in data]
        best_row = int(np.argmax(vals) if highlight == "max" else np.argmin(vals))

    # 列宽：数字列按最长串估宽，其余等比
    cv.fig.canvas.draw()

    def tw(s, sz=size, weight=400):
        return cv.adv(str(s), sz, weight=weight)

    widths = []
    for j, c in enumerate(columns):
        need = max([tw(c, size, 700)] + [tw(r[j]) for r in data])
        widths.append(max(need, tw("0.000")))
    pad = 0.09
    total = sum(widths) + pad * (ncol + 1)
    if total > w:                                  # 超宽就等比压缩
        k = (w - pad * (ncol + 1)) / sum(widths)
        widths = [x_ * k for x_ in widths]
    col_x, cx = [], x + pad
    for wj in widths:
        col_x.append(cx)
        cx += wj + pad

    # 表头
    yy = y
    for j, c in enumerate(columns):
        ha = "right" if j in num else "left"
        tx = col_x[j] + widths[j] if ha == "right" else col_x[j]
        cv.text(tx, yy, c, size=size, weight=700, color=C.navy, ha=ha, va="baseline",
                family=FONT.cjk)
    yy += head_h * 0.55
    if rule:
        cv.line([x, x + min(total, w)], [yy, yy], color=C.navy, lw=LW.base)
    yy += row_h * 0.55

    ys = []
    for i, r in enumerate(data):
        bold = best_row == i
        if bold:
            cv.rect(x - 0.02, yy - row_h * 0.72, min(total, w) + 0.04, row_h * 0.92,
                    fc=C.gold_pale, ec="none", r=0.02, z=0.5)
            # 用矩形当"最优行"标记，不用 ▍ 之类的装饰字符：换字体就可能变豆腐块
            cv.rect(x - 0.05, yy - row_h * 0.32, 0.035, row_h * 0.62, r=0.008,
                    fc=C.gold, ec="none", z=1)
        for j, v in enumerate(r):
            if isinstance(v, (int, float, np.floating, np.integer)):
                s = f"{v:.3f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)
                cv.text(col_x[j] + widths[j], yy, s, size=size, weight=700 if bold else 400,
                        color=C.ink, ha="right", va="baseline")
            else:
                cv.text(col_x[j], yy, str(v), size=size, weight=700 if bold else 400,
                        color=C.ink if bold else C.gray if j == 0 else C.ink, va="baseline",
                        family=FONT.cjk)
        ys.append(yy)
        yy += row_h
        if rule:
            cv.line([x, x + min(total, w)], [yy - row_h * 0.35, yy - row_h * 0.35],
                    color=C.hair, lw=LW.hair)
    if panel:
        cv.text(x - 0.12, y, panel, size=TYPE.panel, weight=700, color=C.navy)
    return {"rows_y": ys, "best_row": best_row, "columns": columns,
            "bottom": yy, "width": min(total, w)}


# --------------------------------------------------------------------------- #
# 注意力 / 特征图
# --------------------------------------------------------------------------- #
def attention_map(ax, weights, tokens=None, *, query=None, cmap="gold", topk=3,
                  panel=None, title=None, row_labels=None, colorbar=True):
    """注意力热图：行=查询，列=被关注的 token，前 k 个用框标出。"""
    m = np.asarray(weights, dtype=float)
    if m.ndim == 1:
        m = m[None, :]
    if m.ndim != 2:
        raise ValueError(f"weights 需为 1D/2D，收到 {m.shape}")
    r, c = m.shape
    im = ax.imshow(m, cmap=CMAPS[cmap], aspect="auto")
    if r == 1 and not row_labels:
        ax.set_yticks([])                      # 单行热图不需要 "query" 这种占位标签
    else:
        labels = row_labels or (
            [str(q) for q in query] if isinstance(query, (list, tuple))
            else [f"q{i}" for i in range(r)])
        ax.set_yticks(range(r), labels, fontsize=TYPE.tick, family=FONT.cjk)
    step = max(1, c // 12) if tokens is not None else 1
    if tokens is not None:
        ax.set_xticks(range(0, c, step), [str(tokens[i]) for i in range(0, c, step)],
                      fontsize=TYPE.tick, rotation=0, family=FONT.cjk)
    ax.tick_params(length=0, colors=C.gray)
    for s in ax.spines.values():
        s.set_visible(False)

    picks = []
    for i in range(r):
        idx = np.argsort(-m[i])[:topk]
        picks.append(idx.tolist())
        for j in idx:
            ax.add_patch(__import__("matplotlib").patches.Rectangle(
                (j - 0.5, i - 0.5), 1, 1, fill=False, ec=C.clay, lw=LW.strong, zorder=3))
    if colorbar:
        cb = ax.figure.colorbar(im, ax=ax, fraction=0.032, pad=0.015)
        cb.outline.set_visible(False)
        cb.ax.tick_params(labelsize=TYPE.tick - 0.6, length=0, colors=C.gray)
    if title:
        ax.set_title(title, fontsize=TYPE.label, color=C.ink, family=FONT.cjk, pad=4)
    if panel:
        _panel(ax, panel)
    return {"top": picks, "shape": (r, c), "image": im}


def sparkline(ax, ys, *, color=None, fill=True, panel=None):
    """极简趋势线（用于表格/指标卡旁边的小图）。"""
    ys = np.asarray(ys, dtype=float)
    xs = np.arange(ys.size)
    color = color or SERIES[0]
    ax.plot(xs, ys, color=color, lw=LW.strong)
    if fill:
        ax.fill_between(xs, ys.min(), ys, color=color, alpha=0.10, lw=0)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.margins(x=0.02, y=0.15)
    if panel:
        _panel(ax, panel)
    return {"min": float(ys.min()), "max": float(ys.max()), "last": float(ys[-1])}


# --------------------------------------------------------------------------- #
# 模型结构图（画布坐标，复用 rect/arrow）
# --------------------------------------------------------------------------- #
def arch_diagram(cv, blocks, edges=None, *, x=None, y=None, w=None, h=None, gap=0.0,
                 size=6.2, group_gap=None, panel=None):
    """模型结构图：``blocks`` 按列给出，自动排布方块 + 箭头。

    Parameters
    ----------
    blocks : list[list[dict]]
        每一列一个 list，元素形如 ``{"label": "Encoder", "sub": "×6", "fc": ..., "ec": ...}``。
        一列内自上而下排列，列间用箭头连。
    edges : sequence[(i, j)]
        自定义连边（列索引对）；默认相邻列全连（每列第一块连下一列第一块）。

    返回 ``{label: (x, y, w, h)}``，方便外面再补注释。
    """
    ncol = len(blocks)
    nrow = max(len(c) for c in blocks)
    x = 0.5 if x is None else x
    y = 0.6 if y is None else y
    w = w or (cv.W - 2 * x) / max(ncol, 1) * 0.72
    h = h or min(0.62, (cv.H - 2 * y) / max(nrow, 1) * 0.62)
    col_gap = group_gap if group_gap is not None else (cv.W - 2 * x - ncol * w) / max(ncol - 1, 1)
    pos = {}
    for ci, col in enumerate(blocks):
        n = len(col)
        total = n * h + (n - 1) * gap
        top = y + (cv.H - 2 * y - total) / 2
        for ri, b in enumerate(col):
            bx = x + ci * (w + col_gap)
            by = top + (n - 1 - ri) * (h + gap)
            fc = b.get("fc", C.card)
            ec = b.get("ec", C.navy if b.get("hl") else C.frame)
            cv.rect(bx, by, w, h, r=0.04, fc=fc, ec=ec,
                    lw=LW.strong if b.get("hl") else LW.base, z=2)
            label = b.get("label", "")
            sub = b.get("sub")
            cv.text(bx + w / 2, by + h / 2 + (0.09 if sub else 0),
                    label, size=size, weight=700 if b.get("hl") else 400,
                    color=b.get("tc", C.ink), ha="center", va="center", family=FONT.cjk)
            if sub:
                cv.text(bx + w / 2, by + h / 2 - 0.1, sub, size=size - 0.9, color=C.gray,
                        ha="center", va="center", family=FONT.cjk)
            pos[label or f"{ci}-{ri}"] = (bx, by, w, h)

    pairs = edges or [(ci, ci + 1) for ci in range(ncol - 1)]
    for a, b in pairs:
        a_name = blocks[a][0].get("label")
        b_name = blocks[b][0].get("label")
        if a_name not in pos or b_name not in pos:
            continue
        ax_, ay_, aw_, ah_ = pos[a_name]
        bx_, by_, bw_, bh_ = pos[b_name]
        cv.arrow((ax_ + aw_, ay_ + ah_ / 2), (bx_, by_ + bh_ / 2),
                 color=C.navy, lw=LW.base, ms=6, z=1)
    if panel:
        cv.text(x - 0.18, cv.H - y + 0.06, panel, size=TYPE.panel, weight=700, color=C.navy)
    return pos
