# Changelog

本文件记录面向开源发布的版本变更。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [0.2.0] - 2026-11-13

首次公开发布。以本地 `D:/AGENT/tools/Shanhai_Atlas` 为源，做工程收敛，**核心算法零改动**。

### 新增

- MIT 许可证、完整 README、API / 设计规范 / 数据合规三份文档、贡献指引、`.gitignore`。
- `examples/_synthetic.py`：固定随机种子的合成示意数据发生器，替代原先对私有项目
  `04_BayesFault/`（Kaikōura 精定位目录与 `bayesfault` 包）的依赖。
- 重写 `ex02` / `ex04` / `ex05` / `ex06` 四个示例为自包含可运行；`ex01` / `ex03` 改为独立输出目录。
- 6 个示例全部离线可跑；缺少 GSHHG 海岸线或 python-pptx 时自动降级 / 优雅跳过。

### 收敛

- 移除 `gallery/`（约 12 MB 旧版转曲 SVG 与 PNG）、`skill/`（本地 Agent Skill 副本）、
  `*.egg-info/`、`.pytest_cache/` 与 `__pycache__`；发布仓库只保留纯文本源码与一张 198 KB 预览图。
- 统一命名：包名 / CLI / 缓存 / 文档全部为 `shanhai_atlas`，示例别名 `jt` → `sha`；
  历史兼容前缀 `jt.*` 与旧字体缓存目录保留但注明来源。
- 版本统一为 `0.2.0`（此前 `__version__=0.1.0` 与 Skill 声明的 0.2.0 不一致）。
- `pyproject.toml` 补 license / authors / keywords / classifiers / project.urls；
  **移除 `rasterio` extra**（会把 NumPy 顶到 2.x，与 `tifffile` 及本地 1.x 环境冲突）。
- `THIRD_PARTY.md` 去掉对内部项目的引用，明确本项目 MIT 与第三方数据各自许可。

### 保留（自 0.1.x 已具备，本版不动）

- 可编辑矢量导出：`exporter` / `textnorm`，`save()` 默认 PDF + SVG + PNG，
  `text_mode` 三模式、`font_embed` 子集内嵌、`strict_text` CI 守门。
- 期刊质量：`journal` 8 家预设 + `check_journal()` / `check_export()`（数值均带 `verified=False`）。
- ML / 评估图：`mlfigs` 纯 NumPy 实现，不引入 sklearn。
- 适配器：`adapters` 比例尺 / 标签避让 / 显著性括号，可选依赖缺失即降级到内置实现。
- 三维震源机制球 `beachball3d`、等面积极点图 `stereonet`、正交三维 `proj3d`。

### 验证

- `pytest -q` → **114 passed, 1 skipped**（与本地源版本一致，零退化）。
- 6 个示例全部端到端跑通，版面自检 0 越界 / 0 压字。
- `ex06_seismology.svg` 体检：62 个 `<text>`、59 个纯文本元素、9 个 `tspan`、
  3 个 `@font-face` 内嵌字体子集，`assert_editable()` 通过。

### 已知边界

- 期刊预设数字未联网核对（`verified=False`），请对照官网复核。
- Illustrator 中"改字"时可能提示字体缺失（AI 行为，非导出缺陷）；稳妥交付可用 `text_mode="both"`。
- 字体子集只含图中已出现的字，事后新增汉字可能掉字。

## [0.1.0]

内部工作版本，未公开发布。
