# 贡献指引

欢迎 issue 与 PR。这个项目的定位很窄：**把地理 / 地质 / 地形 / 地震的科研出图，收敛成一套可复现、可自检的 Python 版面工具**。它不打算重写 GMT、cartopy 或 GIS。

## 提交前

```bash
pip install -e ".[dev,all]"
python -m pytest -q                     # 当前基线：114 passed, 1 skipped
python -m shanhai_atlas gallery        # 6 个示例必须全部跑通
```

- 新增图型请同时给出**可运行示例**和**至少一项测试**。
- 图中数值必须来自程序输出，不写死、不编造；示意数据必须显式标注 `synthetic`。
- 版面改动请附 `cv.audit()` 结果（0 越界 / 0 压字）。
- 导出层改动请附 `svg_report()` / `pdf_report()` 的读数，不靠肉眼看缩略图判断"可编辑"。

## 边界

- **核心依赖只有** `numpy` / `matplotlib` / `fonttools`。新增依赖必须放进 optional extras，且缺失时降级，不能让 `import shanhai_atlas` 失败。
- 不引入 `rasterio` 作为默认或推荐依赖（NumPy 2.x 冲突）；不引入 sklearn / torch / tensorflow。
- 不把任何真实地震编目、台站坐标、行政边界、字体文件或大二进制提交进仓库。示例数据一律走 `examples/_synthetic.py`。
- 不更换绘图引擎（matplotlib + python-pptx 保持不变）。

## 数据与许可

- 本仓库代码为 MIT；第三方数据 / 字体按各自许可，见 `THIRD_PARTY.md`。
- 提交 PR 即表示同意你的贡献按 MIT 许可发布。
- 涉及 USGS ComCat、GSHHG、Terrarium 等外部数据时，请保留来源记录与署名调用。

## 报告问题

请附：Python / NumPy / matplotlib 版本、最小复现脚本、`python -m shanhai_atlas doctor` 输出。
