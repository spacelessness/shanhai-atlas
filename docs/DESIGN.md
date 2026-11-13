# 设计规范

> 这一套令牌贯穿地图、剖面、统计图、模型结构图与 PPT。目标不是"好看"，是**同一篇论文 / 同一次汇报里不会串风格**。

## 配色

| 角色 | 色值 | 用法 |
|---|---|---|
| 黛蓝 `#1B2A4A` | `C.navy` | 结构、主标题、坐标轴、主要数据 |
| 古铜金 `#B08D57` | `C.gold` | 点睛：题线、强调、最优值 |
| 陶土橙 `#A6583F` | `C.clay` | 风险 / 回路 / 警示，**面积 ≤ 10%** |
| 中性灰阶 | `C.ink` / `C.gray` / `C.muted` | 正文、脚注、辅助线 |
| 分类色 | `SERIES[:5]` | 类别 / 断层 / 序列；色盲安全、灰度可区分 |

- **一张图只设一个强调色**。其余用灰阶和线型区分。
- 色带：`sha.depth`（震源深度）、`sha.terrain`（陆地分层）、`sha.sea`（水深）、`sha.div`（残差 / 正负）、`sha.navy` / `sha.gold`（单色顺序）。
- `journal.colorblind_report()` 可在投稿前检查分类色的 ΔE 与灰度差。

## 字体

- 中文：Noto Sans SC / 思源黑体（SIL OFL）；英文副题：Source Serif 4 斜体；公式：STIX。
- **期刊终稿字号不低于 6 pt**（`TYPE` 里已按 6/6.4/7.2/8 分级）。
- 字体缺失时自动回退到系统字体；排版按**实测字形宽度**断行，换字体不会越界，但行数可能变化 —— 看 `audit()` 输出。
- 导出 SVG 用 `font_embed="subset"` 内嵌实际出现的字形，PDF 用 `pdf.fonttype=42` 嵌入 glyf 字形。

## 版面

- `Canvas` 用**英寸坐标、左上原点**，先定整页尺寸，再用 `inset()` 放真实数据区。
- 常用尺寸：16:9 汇报页 `13.333 × 7.5`；期刊双栏 `7.48 × 5.51`；单栏 `3.54 × …`。
- 每列 / 每个面板一个主题；要点不超过 3 条，每条只讲一件事。
- 参数放标签（`param_chips`），公式放公式框（`formula_box`），来源放页脚（`source_line`）。

## 真实性

- **图中数字全部来自程序输出**，用 `assert` 锁定；不手填、不编造。
- 示意图必须注明"示意"；合成数据必须显式标注 `synthetic`（见 `examples/_synthetic.py`）。
- Mc、b 值、AUC 等统计量由代码计算，工具不替研究者判断目录完整性或模型优劣。

## 质量门槛

| 检查 | 工具 | 合格线 |
|---|---|---|
| 越界 / 压字 | `cv.audit()` | 0 overflow / 0 overlap / 0 issue |
| 全图文字覆盖 | `cv.audit(full=True)` | 交稿前跑一次，报出的是真实裁切 |
| SVG 可编辑 | `exporter.svg_report()` / `assert_editable()` | 有 `<text>`、`tspan` 少、`@font-face` 内嵌 |
| PDF 文字层 | `exporter.pdf_report()` | `/FontFile2 > 0`、`Type3 = 0`、`LastResort = []` |
| 期刊规格 | `journal.check_journal()` / `check_export()` | `ok=True`（预设数值需自行复核） |
| 可复现 | 固定 `hashsalt` | 相同输入 → SVG 逐字节一致 |

## 导出交付建议

1. **可编辑主交付**：`text_mode="editable"` 的 SVG（字体已内嵌）+ PDF 版式核对版。
2. **保底**：`text_mode="both"` 同时给转曲版，避免对方环境不认 `@font-face`。
3. **定稿后再改字**：字体子集只含图中已出现的字，事后新增汉字会掉字。
4. 位图底图 `raster_dpi ≥ 300` 用于投稿。
