# 数据合规与使用责任

这份文档说明**仓库里有什么、没有什么**，以及使用外部数据时的义务。请在使用工具出图前读一遍。

## 1. 仓库内容

| 类别 | 是否入库 | 说明 |
|---|---|---|
| Python 源码 / 测试 / 文档 | ✅ | 纯文本 |
| 首页预览图 `docs/images/overview.png` | ✅ | 用合成数据渲染的示例图，198 KB |
| 地震编目、台站坐标、观测数据 | ❌ | **一条都没有** |
| DEM / 地形栅格、海岸线数据文件 | ❌ | 运行时从官方渠道获取 |
| 字体文件 | ❌ | 下载到用户缓存，或内嵌子集到导出产物 |
| 行政边界 / 国界数据 | ❌ | 示例只用 GSHHG 海岸线 |
| API key / 令牌 / 凭据 | ❌ | 不提供在线地图服务，无需密钥 |

`examples/_synthetic.py` 生成的经纬度、深度、震级、断层迹线、台站位置全部是**固定随机种子的合成示意数据**：
不是任何机构发布的地震目录，不是观测结果，不含真实台站坐标，不能用于任何科学结论。
示例区域选在海外公开研究区，避免涉及行政区划表达。

## 2. 使用者自备数据的责任

工具不替使用者判断数据授权。真实研究请注意：

- **正式编目 / 内部台网数据**：许多机构发布的地震目录、台站坐标与波形受再分发条款约束。
  使用、引用或再分发前须自行取得授权；不要把这类数据提交到公开仓库或附在公开图件中。
- 用 `read_catalog()` 读入自己的 CSV 时，通过 `source=` / `citation=` 写明来源，并在图注中署名。
- 图件中若含点位数据，请确认不涉及个人信息或未公开敏感坐标。
- 涉及国界、行政区划的表达，须使用符合国家标准的底图数据；本工具不提供此类数据，也不做自动边界绘制。

## 3. 外部数据源与署名

| 数据源 | 获取方式 | 义务 |
|---|---|---|
| **GSHHG 海岸线** | `pip install shanhai-atlas[geo]`（basemap-data / basemap-data-hires） | LGPL-3.0；图中注明 "GSHHG (Wessel & Smith, 1996)"；再分发数据文件须附 LGPL 文本（本仓库不分发） |
| **USGS ComCat** | `fetch_usgs_catalog()` / `python -m shanhai_atlas fetch-usgs` | 公开服务；每次查询保存 URL / 参数 / 访问时间到 `.meta.json`；引用 U.S. Geological Survey, ComCat；按服务元数据核对外部贡献数据的引用要求 |
| **AWS Terrain Tiles（Terrarium）** | `terrain.fetch_terrarium()` | 按 [tilezen/joerd attribution](https://github.com/tilezen/joerd/blob/master/docs/attribution.md) 署名；`terrain.terrarium_credit(extent)` 会按图幅列出。这是公开高程数据，不是在线地图底图服务 |
| **matplotlib 样例 DEM** | `terrain.sample_dem()` | 仅作示例，图中写"matplotlib 自带 3″ DEM 样例"，不标注未注明的原始数据集 |
| **Noto Sans SC / Source Serif 4** | `python -m shanhai_atlas fonts` | SIL OFL 1.1；字体文件不随项目分发 |

## 4. 地图能力边界（重要）

- 本工具是**离线科研出图与排版工具**，不是地图服务，不替代 GMT / PyGMT / cartopy / GIS。
- 内置 `GeoMap` 只做小范围区域经纬度**等距圆柱近似**（建议单幅跨度 ≤ 15°），不做全球图、跨日期变更线、自动 CRS 识别或高精度椭球测地。
- 不提供在线底图瓦片服务，不内嵌任何地图 API 密钥，也不加载行政边界 / 国界数据。
- 需要全球图、严格投影或含行政区划表达的底图时，请用专业制图库 / 合规底图服务产出图件，再放进本工具的版面。

## 5. 引用与许可

- 代码：MIT（见 `LICENSE`）。
- 第三方数据、字体、依赖：各自许可，见 `THIRD_PARTY.md`。采用 MIT **不免除** GSHHG / Terrarium 等数据的署名义务。
- 学术使用请引用相应数据原始文献（如 Wessel & Smith, 1996；Aki, 1965；Woessner & Wiemer, 2005），工具本身不构成数据来源。
