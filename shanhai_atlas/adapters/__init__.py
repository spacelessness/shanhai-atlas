# -*- coding: utf-8 -*-
"""开源工具适配层：**借用**成熟轮子，而不是重写，也不是换掉 matplotlib。

三条原则
--------
1. **装了就用自己的，没装就用内置实现**（`backend()` 会告诉你当前用的是哪个）。
   所以这些模块不会给核心依赖加负担——`pyproject` 里它们是 extras。
2. **只借"能力"，不借"坐标系"**：适配器最终仍然往 matplotlib 的 Axes 上画，
   这样配色、字号、导出链路（可编辑 SVG/PDF）跟全库其它图完全一致。
3. 不引入 GPL 依赖，避免把整库拖进传染性许可（见 `30-opensource-survey.md`）。
"""
from .labels import backend as labels_backend, count_overlaps, spread_labels
from .scalebar import add_scalebar, backend as scalebar_backend
from .signif import backend as signif_backend, significance_brackets, stars

__all__ = ["add_scalebar", "spread_labels", "significance_brackets", "stars",
           "count_overlaps",
           "backends", "scalebar_backend", "labels_backend", "signif_backend"]


def backends() -> dict:
    """当前每个适配器实际使用的后端（`"native"` = 内置实现）。"""
    return {"scalebar": scalebar_backend(), "labels": labels_backend(),
            "signif": signif_backend()}
