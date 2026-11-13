# 示例

全部示例**离线可跑、自包含**，产物写到 `output/`（不入库）。

```bash
python -m shanhai_atlas gallery --out output        # 一次跑完
python examples/ex06_seismology.py --out output     # 单个运行
```

| 脚本 | 覆盖能力 | 数据 | 可选依赖 |
|---|---|---|---|
| `ex01_structure_figure.py` | 16:9 模型结构 / 技术路线：卡片、公式框、数据流、真实中间结果小图 | matplotlib 自带 3″ DEM 样例 | — |
| `ex02_geo_map.py` | 地理底图：海岸线、断层迹线、震中、台站、色条、比例尺、指北针、位置图 | 合成 + GSHHG | `[geo]`（缺则跳过海岸线 / 位置图） |
| `ex03_terrain_map.py` | 地形：晕渲、等高线、A–A′ 剖面、坡度统计；`--dem` / `--terrarium` 换自己的 DEM | matplotlib 自带 DEM 样例 | `[tiff]` / `[netcdf]`（自定义 DEM 时） |
| `ex04_data_panels.py` | 期刊双栏四面板：MFD、深度分布、累积事件、深度–震级 | 合成 | — |
| `ex05_deck.py` | 同风格 PPT：封面、整页矢量图、卡片、结束页 + 讲稿备注 | 合成 | `[ppt]`（缺则优雅跳过） |
| `ex06_seismology.py` | 震中图 + 震源剖面 + 震级–频度，三格式导出 | 合成，或 `--catalog your.csv` | `[geo]`（海岸线） |

## 数据声明

`_synthetic.py` 生成的经纬度、深度、震级、断层迹线、台站位置**全部是固定随机种子的合成示意数据**：

- 不是任何机构发布的地震目录，不是观测结果，不含真实台站坐标；
- 不能用于任何科学结论，图中 Mc / b 值只演示计算流程；
- 示例区域为海外公开研究区，不加载行政边界或国界数据。

真实研究请用自己的授权数据：

```bash
python examples/ex06_seismology.py --catalog your_authorized_catalog.csv
```

CSV 至少含 `lon,lat` 两列；`depth_km`、`magnitude`、`time`、`event_id` 可选，常见列名自动识别。
也可以直接构造 `EventCatalog`：

```python
import numpy as np
from shanhai_atlas.seismic import EventCatalog
cat = EventCatalog(lon=np.array([...]), lat=np.array([...]),
                   depth_km=np.array([...]), magnitude=np.array([...]))
```

## 字体

示例调用 `sha.setup(..., fetch=True)`：找不到中文字体时会自动下载 Noto Sans SC（约 35 MB，SIL OFL）。
离线环境请先手动准备，或指定本地字体目录：

```bash
python -m shanhai_atlas fonts
# 或
SHANHAI_FONT_DIR=/path/to/fonts python examples/ex02_geo_map.py
```
