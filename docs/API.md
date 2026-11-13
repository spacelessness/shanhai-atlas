# 核心 API 速查

> 完整签名以源码为准；本页覆盖 90% 的日常用法。
> 约定：`import shanhai_atlas as sha`，`cv = sha.Canvas(w, h)`（英寸，左上原点）。

## 1. 初始化与导出

```python
sha.setup(font_dirs=(), fetch=False, hashsalt="shanhai-atlas",
          text_mode="editable", preset=None)     # → FONT(cjk/serif/mono/math)
sha.font_preset("noto")                          # 字体预设查询
sha.check_fonts()                                # 字体体检：装没装 / 是不是 glyf / 授权来源

cv = sha.Canvas(w, h)                            # 英寸版面
ax = cv.inset(x, y, w, h, z=3)                   # 在版面里放一个 matplotlib Axes
cv.text(x, y, s, size=8, weight=400, color=C.ink, ha="left", va="baseline")
cv.para(x, y, width, runs, size=7.5, leading=1.52)   # 实测断行 + 避头尾
cv.audit(overlap=True, tol=0.012, verbose=True, full=False)   # → 问题数（int）
cv.save(path, formats=None, dpi=None, check=True, strict=False,
        raster_dpi=160, text_mode=None, font_embed="subset", strict_text=False)
cv.close()
```

- `formats=None` → `("pdf", "svg", "png")`；还可选 `pdf-outline` / `tif` / `eps`。
- `text_mode`：`editable`（默认，保留 `<text>`）、`outline`（转曲）、`both`（另存 `.outline.*`）。
- `strict_text=True` 导出后跑 `assert_editable()`，不是真文字就抛 `RuntimeError`。
- `audit(full=True)` 审图内**所有** `Text`（默认只审登记文本），更严也可能报出真实裁切。

## 2. 版面构件

```python
sha.header(cv, kicker, title, subtitle=None, x0=0.34, y=0.36, sizes=None)
sha.card(cv, x, y, w, h, title, subtitle=None, badge=None)      # → Card(.box)
sha.formula_box(cv, x, y, w, formulas, container=card.box)
sha.bullets(cv, x, y, w, items, container=None)
sha.param_chips(cv, x, y, w, labels)
sha.flow_arrow(cv, (x0, y0), (x1, y1), strong=False)
sha.data_spine(cv, ...) / sha.loop_arc(cv, ...) / sha.group_frame(cv, ...)
sha.table(cv, ...) / sha.legend_item(...) / sha.colorbar(...)
sha.source_line(cv, x, y, w, runs, size=6.6)      # 自动加粗"数据："
sha.footer_notes(cv, y, columns, x0=0.34, gap=0.25)
sha.place_labels(cv, ...)                          # 标注避让
```

设计令牌：`sha.theme.C`（配色）、`SERIES`（分类色）、`CMAPS`（`sha.depth` / `sha.terrain` / `sha.sea` / `sha.div` …）、
`TYPE`（字号）、`SIZES`、`LW`；工具函数 `sha.darken/lighten/mix/rgba/series/shades`。

## 3. 图表与坐标轴

```python
sha.style_axes(ax, grid="y", spines=("left", "bottom"), tick_size=6.0, label_size=6.6)
sha.panel_label(ax, "a", x=-0.02, y=1.02, size=8.0)
sha.panel_title(ax, "面板标题", "副题", size=6.1, x=0.0, y=1.02)
sha.note(ax, ...) / sha.callout(ax, ...) / sha.highlight_min(ax, ...) / sha.bar_labels(ax, ...)
```

## 4. 地理 / 地质

```python
from shanhai_atlas.geo import GeoMap, locator, gshhs_available, read_gshhs

m = GeoMap(ax, (W, E, S, N), phi0=None)         # 区域等距圆柱近似
m.coast(res="h", land=C.land, edge=C.coast, lw=0.6, eps_in=0.003)
m.graticule(step=0.25) / m.ticks(step=0.5) / m.zebra(step=0.5, width_in=0.045)
m.scale_bar(25, segments=2, loc=(0.04, 0.05)) / m.north_arrow(loc=(0.94, 0.86))
m.points(lon, lat, s=3.0, c=C.blue) / m.vectors(lon, lat, east_km, north_km, key_km=10)
m.text(lon, lat, s) / m.place(lon, lat, name) / m.label_area(lon, lat, s)
m.box(extent) / m.geojson(data) / m.shapefile(path)      # shapefile 需 [shapefile]
m.to_km(lon, lat) / m.km2deg(dx_km, dy_km) / m.in2deg(inches)
locator(ax, big_extent, highlight_extent, res="h")        # 位置图
```

`sha.proj3d`：正交三维点云 / 面片 / 坐标盒；`sha.stereonet`：下半球等面积极点图、大圆 / 小圆。

## 5. 地形

```python
from shanhai_atlas import terrain

dem = terrain.sample_dem("jacksboro")            # 离线样例
dem = terrain.load_dem("dem.tif")                # GeoTIFF / ASC / NetCDF / NPZ
dem = terrain.fetch_terrarium((W, E, S, N))      # 在线，需署名
dem = dem.coarsen(900)
terrain.draw(ax, dem, sea=True, strength=0.55, cmap="sha.terrain", vert_exag=1.5)
terrain.contours(ax, dem, interval=100.0, index_every=5)
prof = terrain.profile(dem, (lon0, lat0), (lon1, lat1), n=400)
terrain.terrarium_credit(extent)                 # 应写进图注的署名清单
```

## 6. 地震

```python
cat = sha.read_catalog("events.csv", columns=None, source=None, citation="")
cat = sha.fetch_usgs_catalog(extent, start, end, min_magnitude=..., use_cache=True)
cat.to_csv("out.csv")                            # EventCatalog: lon/lat/depth_km/magnitude/time/event_id

sha.plot_events(ax, cat, color_by="depth_km", size_range=(10, 82), levels=8)
sha.magnitude_legend(ax, (2, 3, 4), magnitude_range=(1.0, 6.0))
sec = sha.plot_cross_section(ax, cat, (lon0, lat0), (lon1, lat1),
                             half_width_km=5.0, depth_limits_km=(0, 40))
sec.n_selected
mfd = sha.plot_magnitude_frequency(ax, cat.magnitude, mc=None, bin_width=0.1)
mfd.mc / mfd.b_value / mfd.sigma_b / mfd.n_complete
mc = sha.estimate_mc_max_curvature(cat.magnitude, bin_width=0.1, correction=0.2)
b, sigma_b, n = sha.aki_b_value(cat.magnitude, mc)
sha.focal_mechanism(ax, lon, lat, strike, dip, rake)            # 需 [seismo] ObsPy
sha.beachball3d(ax, strike, dip, rake, az=0, el=0, radius=1.0)  # 纯 NumPy，无需 ObsPy
```

CSV 列名自动识别常见写法（`lon/longitude`、`lat/latitude`、`depth_km/depth`、`magnitude/mag` …），
可用 `columns={"lon": "经度", ...}` 显式指定。

## 7. 可编辑导出与体检

```python
from shanhai_atlas import exporter

exporter.TEXT_MODES                              # ("editable", "outline", "both")
exporter.svg_report("figure.svg")                # text_elements / tspans / font_face / families …
exporter.pdf_report("figure.pdf")                # /FontFile2 / Type3 / ToUnicode / LastResort
exporter.assert_editable("figure.svg")           # 没真文字就抛 RuntimeError
exporter.text_mode_context("editable")           # 上下文管理器
```

## 8. 期刊质量

```python
from shanhai_atlas import journal

p = journal.journal_preset("nature")             # 8 家预设；每条带 verified=False
journal.check_journal(cv, preset="nature", raster_dpi=300)   # → {ok, errors, warnings, metrics, preset}
journal.check_export("figure.svg", preset="nature")
journal.colorblind_report(colors, min_de=10.0)   # 色盲可辨 / 灰度可区分
journal.delta_e(c1, c2)
```

> 预设数字**未联网核对**，请对照出版方官网复核后修改 `journal.PRESETS`。

## 9. ML / 评估图与适配器

```python
from shanhai_atlas import mlfigs, adapters

mlfigs.training_curves(ax, history, val=...) / mlfigs.confusion_matrix(ax, cm)
mlfigs.roc_from_scores(y_true, y_score) / mlfigs.pr_from_scores(...)
mlfigs.roc_curves(ax, curves) / mlfigs.pr_curves(ax, curves)
mlfigs.ablation_table(cv, x, y, w, rows) / mlfigs.attention_map(ax, weights, tokens=...)
mlfigs.arch_diagram(cv, blocks, edges=...) / mlfigs.sparkline(ax, ys)
adapters.backends()                              # 每个适配器走外部包还是内置实现
adapters.scalebar.add_scalebar(...) / adapters.labels.spread_labels(...)
adapters.signif.significance_brackets(...)
```

AUC / AP 由纯 NumPy 手算，不引入 sklearn；外部包（`adjustText` / `matplotlib-scalebar` / `statannotations`）装了就用，没装就降级到内置实现。

## 10. PPT

```python
from shanhai_atlas.ppt import Deck

deck = Deck(footer="…", org="…")
deck.cover(title, subtitle=..., meta=...) / deck.section(n, title)
deck.full_figure("figure.svg", vector=True, notes="…")    # 需同名 .png 作回退
deck.figure(title, "figure.svg", takeaways=[...])
deck.cards(title, items) / deck.bullets(...) / deck.table(...) / deck.kpis(...)
deck.closing("谢谢")
deck.save("deck.pptx")
```

`python -m shanhai_atlas preview deck.pptx` 无需 Office 即可检查几何与文本溢出。

## 11. CLI

```
python -m shanhai_atlas doctor | fonts | preview | gallery | fetch-usgs
```
