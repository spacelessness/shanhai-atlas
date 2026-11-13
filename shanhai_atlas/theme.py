# -*- coding: utf-8 -*-
"""精图 · 设计令牌（单一来源）。

配色、分类色、色带、字号阶梯、线宽与画布尺寸预设。图件（matplotlib）与
幻灯片（python-pptx，见 ``shanhai_atlas.ppt``）共用这一套令牌，保证论文图、模型结构图、
地图与 PPT 页面的视觉完全一致。

设计基调：「黛蓝 × 古铜金」学术风——黛蓝承担结构与标题，古铜金只做点睛
（题线、数据流、强调），陶土橙仅用于风险 / 回路 / 警示语义（面积 ≤ 10%），
其余信息一律用中性灰阶分层。
"""

from __future__ import annotations

import numpy as np
import matplotlib as mpl
from matplotlib.colors import LinearSegmentedColormap, to_hex, to_rgb


class Tokens(dict):
    """dict + 属性访问：``C["navy"]`` 与 ``C.navy`` 等价。"""

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:          # pragma: no cover - 常规属性错误
            raise AttributeError(k) from e

    def __setattr__(self, k, v):
        self[k] = v


# ---------------------------------------------------------------- 配色
C = Tokens(
    # 主色：黛蓝（结构 / 标题）× 古铜金（点睛）
    navy="#1B2A4A", navy_deep="#12203A", navy_lite="#2C4270",
    blue="#3E5C76", blue_soft="#5E7E9E",
    gold="#B08D57", gold_lite="#C9A86A", gold_pale="#E9DDC6",
    gold_wash="#F8F3EA", gold_line="#D8C49F",
    # 语义色：陶土橙 = 风险 / 回路 / 警示；松绿 = 达标 / 通过
    clay="#A6583F", pine="#3F6B54",
    # 文字与中性灰阶
    ink="#2A3342", gray="#66717E", gray_lite="#9AA4B0", muted="#C3CAD3",
    line="#D9DEE5", hair="#E4E8EE", rule="#C9D1DB", axis="#AEB7C2", grid="#EDF0F4",
    # 面
    white="#FFFFFF", paper="#FDFCFA", card="#F5F7FA", frame="#EEF2F7",
    pane="#F3F5F8", pane_edge="#D3DAE3",
    # 地图
    land="#F7F5F0", sea="#E3EAF1", coast="#8492A3", graticule="#CBD3DD",
    sea_label="#7D90A6",
)

#: 分类色（类别 / 断层 / 序列）。前 5 个为默认定性色板，色盲安全且灰度可区分。
SERIES = ["#2E5E8E", "#B08D57", "#A6583F", "#3F6B54", "#6A5B8C",
          "#3B7F86", "#8A6A45", "#5E6B7E"]

#: 线宽阶梯（pt）
LW = Tokens(hair=0.45, thin=0.6, base=0.8, frame=0.7, strong=1.3, rule=2.2)

#: 字号阶梯（pt）。diagram：16×9 英寸整幅图（缩放到幻灯片后约 ×0.83）；
#: paper：期刊最终尺寸（正文 ≥ 6 pt）；slide：python-pptx 原生文本。
TYPE = Tokens(
    diagram=Tokens(kicker=7.2, title=17.5, subtitle=8.5, group=7.3, h1=10.6, h2=7.0,
                   body=7.2, formula=7.4, chip=6.4, label=6.0, caption=5.6, micro=5.2),
    paper=Tokens(title=8.5, h1=7.5, body=7.0, label=6.5, tick=6.0, caption=6.0, micro=5.5),
    slide=Tokens(kicker=10.5, title=25.0, h1=13.5, body=12.5, caption=9.5, micro=8.5),
)

#: 画布尺寸预设（英寸，宽 × 高；高为 None 表示按内容自定）
SIZES = Tokens(
    diagram=(16.0, 9.0),          # 整幅模型结构图 / 海报式长图（16:9）
    slide=(13.333, 7.5),          # PPT 全页 1:1（16:9）
    slide_half=(6.0, 5.2),        # PPT 半页配图
    paper_single=(3.54, None),    # 期刊单栏 90 mm
    paper_onehalf=(5.51, None),   # 1.5 栏 140 mm
    paper_double=(7.48, None),    # 双栏 190 mm
)


# ---------------------------------------------------------------- 颜色工具
def mix(c1, c2, t):
    """线性混色：t=0 → c1，t=1 → c2；返回 RGB 元组。"""
    a, b = np.array(to_rgb(c1)), np.array(to_rgb(c2))
    return tuple(a + (b - a) * float(t))


def lighten(c, t):
    return mix(c, "#FFFFFF", t)


def darken(c, t):
    return mix(c, "#000000", t)


def rgba(c, alpha):
    return (*to_rgb(c), float(alpha))


def shades(base, n, lo=-0.40, hi=0.45):
    """同色系深浅 n 级（从深到浅），用于“同一类的子组分”。"""
    if n == 1:
        return [to_rgb(base)]
    return [darken(base, -t) if t < 0 else lighten(base, t) for t in np.linspace(lo, hi, n)]


def series(n):
    """取 n 个分类色；超过 8 个时在色板内插值（不建议超过 8 类）。"""
    if n <= len(SERIES):
        return SERIES[:n]
    cm = LinearSegmentedColormap.from_list("_s", SERIES)
    return [to_hex(cm(t)) for t in np.linspace(0, 1, n)]


# ---------------------------------------------------------------- 色带
#: 本包色带前缀。历史版本曾用 ``jt.``；同进程并存时若两边都以 force=True
#: 注册同名色带会静默串色，故 0.2 起统一为 ``sha.``，``jt.`` 仍被兼容识别（见 resolve_cmap）。
CMAP_PREFIX = "sha."
LEGACY_CMAP_PREFIX = "jt."


def _cmap(name, stops):
    if isinstance(stops[0], (tuple, list)):
        return LinearSegmentedColormap.from_list(name, stops)
    return LinearSegmentedColormap.from_list(name, list(stops))


CMAPS = Tokens(
    # 深度（浅 → 深：沙金 → 灰蓝 → 黛蓝），震源深度 / 埋深
    depth=_cmap(CMAP_PREFIX + "depth", ["#E4D3AE", "#C29C62", "#7D8A95", "#34507A", "#14223D"]),
    # 单色顺序：白 → 黛蓝
    navy=_cmap(CMAP_PREFIX + "navy", ["#F7F9FB", "#C9D4E0", "#7E95AE", "#3E5C76", "#1B2A4A"]),
    # 单色顺序：白 → 古铜金
    gold=_cmap(CMAP_PREFIX + "gold", ["#FBF8F2", "#EADCC0", "#D2B47F", "#B08D57", "#7D5F33"]),
    # 发散：陶土橙 ← 白 → 黛蓝（异常 / 残差 / 正负变化）
    div=_cmap(CMAP_PREFIX + "div", ["#7E3B27", "#A6583F", "#D9A68F", "#F6F4F1", "#9FB3C8",
                                    "#3E5C76", "#1B2A4A"]),
    # 陆地分层设色（低 → 高：灰绿 → 浅沙 → 驼 → 褐灰 → 岩灰），柔和、不抢数据
    terrain=_cmap(CMAP_PREFIX + "terrain", [(0.00, "#DCE3D2"), (0.18, "#E6E6CC"), (0.40, "#E3D6B4"),
                                            (0.62, "#CDB592"), (0.82, "#AD9682"), (1.00, "#9A938E")]),
    # 海洋水深（深 → 浅）
    sea=_cmap(CMAP_PREFIX + "sea", [(0.00, "#2F4C6E"), (0.35, "#5F7F9F"), (0.70, "#A9BED2"),
                                    (1.00, "#E1E9F1")]),
)


def resolve_cmap(name):
    """色带名 → 色带对象 / 原名。

    ``sha.*`` 与旧前缀 ``jt.*`` 都解析到**本包** CMAPS（不依赖 matplotlib 注册表），
    其余字符串原样返回，由 matplotlib 自己解析。
    """
    if isinstance(name, str):
        for pre in (CMAP_PREFIX, LEGACY_CMAP_PREFIX):
            if name.startswith(pre) and name[len(pre):] in CMAPS:
                return CMAPS[name[len(pre):]]
    return name


def register_cmaps():
    """把 sha.* 色带注册到 matplotlib（之后可直接 cmap="sha.depth"）。

    只注册 ``sha.``，不注册旧前缀 ``jt.``——避免与历史版本同进程导入时互相 force 覆盖。
    """
    reg = getattr(mpl, "colormaps", None)
    for cm in CMAPS.values():
        try:
            if reg is not None:
                reg.register(cm, name=cm.name, force=True)
            else:                                   # matplotlib < 3.5
                mpl.cm.register_cmap(cm.name, cm)
        except Exception:
            pass


register_cmaps()
