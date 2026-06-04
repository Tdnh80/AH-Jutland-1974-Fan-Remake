"""队形几何:中心点 + 航向 + 各船偏移 -> 各船精确 (x, y)。

坐标系同 fleet_search:+x 东、+y 南。航向用单位向量 (ux, uy)。
偏移在「航向坐标系」下表示:along 沿航向(+ 前 / - 后),cross 垂直航向(+ 右舷 / - 左舷)。
右舷法向 = (-uy, ux)(航向东 (1,0) 的右舷为 (0,1) 即南)。
"""

import math

LINE_AHEAD = "ahead"
LINE_ABREAST = "abreast"
ECHELON = "echelon"

ABS_MODE = "absolute"   # 参考地图(地理北),转向不跟转
REL_MODE = "relative"   # 参考航向,转向跟转


def ship_offsets(kind, n, spacing, deploy="right", echelon_deg=45.0):
    """各船在航向系下的 (along, cross) 偏移;第 0 船为基准 (0,0)。"""
    sign = 1.0 if deploy == "right" else -1.0
    out = []
    for i in range(n):
        if kind == LINE_AHEAD:
            out.append((-i * spacing, 0.0))
        elif kind == LINE_ABREAST:
            out.append((0.0, sign * i * spacing))
        elif kind == ECHELON:
            rad = math.radians(echelon_deg)
            out.append((-i * spacing * math.cos(rad),
                        sign * i * spacing * math.sin(rad)))
        else:
            raise ValueError(f"unknown formation {kind!r}")
    return out


def to_map_offsets(heading, offsets):
    """把航向系偏移转成地图系偏移(用给定航向)。"""
    ux, uy = heading
    px, py = -uy, ux                       # 右舷法向
    return [(a * ux + c * px, a * uy + c * py) for a, c in offsets]


def place_map(center, map_offsets):
    """中心 + 地图系偏移 -> 各船 (x, y)。"""
    cx, cy = center
    return [(cx + dx, cy + dy) for dx, dy in map_offsets]


def place_relative(center, heading, offsets):
    """相对模式:偏移随当前航向旋转。"""
    return place_map(center, to_map_offsets(heading, offsets))
