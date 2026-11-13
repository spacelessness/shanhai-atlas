# 第三方资源、数据与许可

本项目代码为 **MIT**（见 `LICENSE`）。第三方依赖、数据、字体与算法仍按各自许可使用，不受本项目许可影响。
完整的合规说明见 [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md)。

## 1. 总结

- **代码**：全部为本项目编写，没有复制第三方项目的源代码。
- **运行依赖**：只调用 matplotlib、NumPy、python-pptx 等库的公开接口。
- **仓库不含第三方数据或字体文件**：GSHHG 海岸线、字体、在线地形瓦片、USGS 目录都在安装或运行时从官方渠道获取。
- **仓库不含任何真实地震编目 / 台站坐标**：示例数据为合成示意数据。
- 首页预览图 `docs/images/overview.png` 是本项目用合成数据渲染的示例图，图中的海岸线署名已写在页脚。

## 2. Python 依赖

| 库 | 用途 | 许可 | 是否必需 |
|---|---|---|---|
| NumPy | 数值计算 | BSD-3-Clause | 必需 |
| matplotlib | 绘图、mathtext、SVG / PNG / PDF 输出 | Matplotlib License（基于 PSF） | 必需 |
| fontTools | 字体子集、glyf/CFF 判定、字形覆盖检查 | MIT | 必需 |
| contourpy、Pillow | 等高线追踪、PNG 读写（随 matplotlib 安装） | BSD-3-Clause、MIT-CMU | 必需（间接） |
| python-pptx、lxml | 生成 PPT、编辑 XML | MIT、BSD-3-Clause | 可选 `[ppt]` |
| tifffile | 读取 GeoTIFF | BSD-3-Clause | 可选 `[tiff]` |
| xarray、netCDF4 | 读取 NetCDF / GMT grd | Apache-2.0、MIT | 可选 `[netcdf]` |
| pyshp | 读取 Shapefile | MIT | 可选 `[shapefile]` |
| ObsPy | 经典 SDR 震源机制球接口 | LGPL-3.0 | 可选 `[seismo]`，只在调用时导入 |
| basemap-data / basemap-data-hires | 打包 GSHHG 海岸线数据 | LGPL-3.0 | 可选 `[geo]` |
| rasterio | 读取带 CRS / NoData 的 GeoTIFF | BSD-3-Clause | **不在 extras 中**，用户自行按需安装 |

> `rasterio` 会把 NumPy 顶到 2.x，与 `tifffile` 及本工具的 1.x 验证环境冲突，故不列为推荐依赖。
> 内置 `beachball3d` 是纯 NumPy 实现，不依赖 ObsPy。

## 3. 数据

| 资源 | 怎么用 | 许可与义务 |
|---|---|---|
| **GSHHG 海岸线**（Wessel & Smith, 1996, *JGR* 101(B4)） | 由 PyPI 包 `basemap-data-hires`（f / h）或 `basemap-data`（i / l / c）提供；本工具自行解析数据格式，不调用 basemap 代码 | LGPL-3.0。图中须注明来源。若再分发数据文件本身，须附 LGPL 文本；**本仓库不分发**。 |
| **AWS Open Data「Terrain Tiles」**（Terrarium 编码） | `terrain.fetch_terrarium()` 联网下载；瓦片由 Mapzen / Tilezen Joerd 汇编，来源含 SRTM、GMTED2010、3DEP、ETOPO1 及各国 DEM | **必须按数据源署名**，见 [tilezen/joerd attribution](https://github.com/tilezen/joerd/blob/master/docs/attribution.md)。`terrain.terrarium_credit(extent)` 会按图幅列出所需署名。这是公开高程数据，不是在线地图底图服务。 |
| **matplotlib 样例 DEM** `jacksboro_fault_dem.npz` | `terrain.sample_dem()`，仅用于示例 01 / 03 | 随 matplotlib 分发；文档未注明原始来源，图中只写"matplotlib 自带 3″ DEM 样例"。 |
| **USGS ComCat** | `seismic.fetch_usgs_catalog()` / `python -m shanhai_atlas fetch-usgs`，用户显式指定区域与时段后查询 FDSN Event Web Service | USGS 公开服务。每次查询保留 URL、参数、访问时间并导出 `.meta.json`；引用 U.S. Geological Survey, ComCat。外部贡献数据应按服务元数据再核对引用要求。 |
| **合成示例数据** | `examples/_synthetic.py` | 本项目生成，随机示意，不是观测数据。 |

## 4. 字体

| 字体 | 用途 | 许可 |
|---|---|---|
| Noto Sans SC（思源黑体，Google / Adobe） | 中文与正文 | SIL OFL 1.1 |
| Source Serif 4（Adobe） | 英文斜体副题 | SIL OFL 1.1 |
| STIX（公式）、DejaVu Sans Mono（等宽） | 公式、数据表 | SIL OFL 1.1 / Bitstream Vera 衍生许可 |

字体由 `python -m shanhai_atlas fonts` 下载到用户缓存目录（`~/.cache/shanhai_atlas/fonts`），**不进仓库**。
输出的 SVG 可内嵌按需子集化的字体（base64），PDF 嵌入字形；OFL 允许在文档中嵌入字体，字体文件本身不随项目分发。

## 5. 自行实现的公开方法与规范

- **山体阴影**：Lambert 余弦光照；Mark, R. K. (1992) 多方向斜向加权（与 GDAL `gdaldem hillshade -multidirectional` 同权重）。
- **几何**：Ramer–Douglas–Peucker 折线化简；Sutherland–Hodgman 多边形裁剪。
- **地形瓦片**：Web Mercator / XYZ 编号（OSM "slippy map" 约定）；Terrarium 高程编码（Mapzen）。
- **极射投影**：下半球等面积（Schmidt）投影。
- **统计**：Aki (1965) b 值极大似然估计；最大曲率法 + 0.2 确定 Mc（Woessner & Wiemer, 2005，仅为探索性基线）；核密度带宽用 Silverman 经验公式；ROC-AUC / PR-AP 由纯 NumPy 实现。
- **地震学几何**：局部等距圆柱下的沿剖面距离 / 垂向偏移，仅适用于区域小范围。
- **震源机制**：Aki–Richards SDR beachball 可选调用 ObsPy 的 LGPL 实现；内置 `beachball3d` 为本项目的独立实现，未复制其代码。
- **PPT 中嵌入 SVG**：Office 2016 起支持的 svgBlip 扩展（[MS-ODRAWXML]，扩展 URI `{96DAC541-7B7A-43D3-8B79-37D633B846F1}`），附 PNG 回退图。

## 6. 设计 / 工具参考（未复制其代码）

GMT / PyGMT、cartopy、SciencePlots、seaborn、adjustText、matplotlib-scalebar、statannotations 等项目的公开文档，
用于界定本工具的能力边界与适配器设计；不包含它们的源文件、模板或内容复制。

## 7. 本项目自身的许可

**MIT**。你可以自由使用、修改、再分发，包括商业用途，条件见 `LICENSE`。
第三方数据、字体与依赖仍按各自许可；特别是 GSHHG 与 Terrarium 的署名义务，不会因本项目采用 MIT 而免除。
