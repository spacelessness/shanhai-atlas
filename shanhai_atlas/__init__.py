# -*- coding: utf-8 -*-
"""Shanhai Atlas（山海图）—— 面向地理 / 地质 / 地震的科研出图工具包。

用 Python 代码生成"黛蓝 × 古铜金"学术风格的图件与同风格 PPT：
区域地理底图、地形晕渲与剖面、断层面与震源机制、震中分布与震级–频度、
期刊多面板数据图，以及可编辑的 SVG / PDF / PNG 导出。

    import shanhai_atlas as sha
    sha.setup()                                  # 字体 + 可编辑矢量 + 可复现 SVG
    cv = sha.Canvas(16, 9)                       # 英寸坐标整页画布
    sha.header(cv, "KICKER", "主标题", "English subtitle")
    ...
    cv.save("figures/my_figure")                 # → .pdf + .svg + .png

模块地图
--------
theme       设计令牌：配色 C、分类色 SERIES、色带 CMAPS（sha.depth / sha.terrain …）、字号 TYPE
fonts       字体发现 / 下载（python -m shanhai_atlas fonts）/ matplotlib 全局设置
canvas      Canvas：英寸版面、实测断行（中英混排 + 公式 + 避头尾）、版面自检、可复现输出
components  页眉、卡片、公式框、要点、数据对象 / 参数标签、流程箭头、分组框、表格、图例
charts      学术坐标轴样式、面板编号、引线标注
proj3d      正交三维点云 / 面片 / 坐标盒
stereonet   下半球等面积投影（极点、小圆、大圆）
geo         经纬度地图：GSHHG 海岸线、经纬网、斑马图框、比例尺、指北针、位置图、GeoJSON
terrain     DEM 读取 / Terrarium 在线瓦片 / 山体阴影 / 分层设色 / 等高线
seismic     震源目录、USGS ComCat、震中图、剖面、Mc / b 值、震源机制球
beachball3d 纯 numpy 的三维震源机制球（不依赖 ObsPy）
exporter    可编辑矢量导出：<text> / FontFile2 体检、字体子集内嵌、CI 守门
textnorm    公式 Unicode 化、缺字回退
journal     期刊版式预设与投稿前体检
mlfigs      ML / 评估图：训练曲线、混淆矩阵、ROC / PR、消融表、注意力热图、结构图
adapters    可选依赖适配器：比例尺、标签避让、显著性括号（缺失即降级到内置实现）
ppt         同风格 PPT：封面、章节、图页（SVG 矢量 + PNG 回退）、卡片、表格、KPI、讲稿备注
"""

__version__ = "0.2.0"

from .theme import C, CMAPS, LW, SERIES, SIZES, TYPE, Tokens, darken, lighten, mix, rgba, series, shades  # noqa: F401
from .fonts import FONT, fetch_fonts, setup  # noqa: F401
from .canvas import Canvas  # noqa: F401
from .components import (Card, bullets, card, chip, colorbar, data_spine, flow_arrow,  # noqa: F401
                         footer_notes, formula_box, group_frame, halo, header, info_box,
                         legend_item, loop_arc, param_chips, place_labels, source_line,
                         step_columns, table, tile)
from .charts import bar_labels, callout, highlight_min, note, panel_label, panel_title, style_axes  # noqa: F401
from . import (beachball3d, charts, components, geo, proj3d, seismic, stereonet,
               terrain)  # noqa: F401,E402
from .beachball3d import (BallArt, beachball, beachball3d, focal_axes, moment_tensor,
                          multiview, nodal_normals, plane_normal, polarity, slip_vector,
                          view_basis, view_of)  # noqa: F401
from .seismic import (EventCatalog, aki_b_value, estimate_mc_max_curvature, fetch_usgs_catalog,
                      focal_mechanism, focal_mechanisms, magnitude_legend, magnitude_sizes,
                      plot_cross_section, plot_events, plot_magnitude_frequency,
                      project_cross_section, read_catalog)  # noqa: F401

__all__ = [
    "C", "CMAPS", "LW", "SERIES", "SIZES", "TYPE", "Tokens", "darken", "lighten", "mix", "rgba",
    "series", "shades", "FONT", "fetch_fonts", "setup", "Canvas", "Card", "bullets", "card", "chip",
    "colorbar", "data_spine", "flow_arrow", "footer_notes", "formula_box", "group_frame", "halo",
    "header", "info_box", "legend_item", "loop_arc", "param_chips", "place_labels", "source_line",
    "step_columns", "table", "tile", "bar_labels", "callout", "highlight_min", "note", "panel_label",
    "panel_title", "style_axes", "charts", "components", "geo", "seismic", "proj3d", "stereonet",
    "terrain", "EventCatalog", "aki_b_value", "estimate_mc_max_curvature", "fetch_usgs_catalog",
    "focal_mechanism", "focal_mechanisms", "magnitude_legend", "magnitude_sizes",
    "plot_cross_section", "plot_events", "plot_magnitude_frequency", "project_cross_section",
    "read_catalog", "beachball3d", "BallArt", "beachball", "moment_tensor", "multiview",
    "nodal_normals", "plane_normal", "polarity", "slip_vector", "view_basis", "view_of",
    "focal_axes",
]
