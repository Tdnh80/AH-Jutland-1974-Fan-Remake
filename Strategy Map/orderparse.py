"""编组文件解析层(纯文本 → 中间数据模型 → 局部坐标换算)。

与引擎解耦:本模块不 import fleet_search、不 import matplotlib。
中间 dataclass(OrderShip/OrderFormation/OrderFleet/Battle)只承载解析结果,
由 fleet_search.load_order_file 再实例化到运行期 Fleet/Formation/Ship。

坐标约定(spec §6.3):
  forward_hat = DIRVEC[initial_course]
  left_hat    = (forward_hat.y, -forward_hat.x)     # +y 朝南下的左舷法向
  offset_xy   = offset_fwd*forward_hat + offset_left*left_hat
Relative Position 分量:F→+fwd  B→−fwd  L→+left  R→−left  "0"→(0,0)。
"""

import math
import re
from dataclasses import dataclass, field

# pixel direction unit vectors (与 fleet_search.DIRVEC 一致;此处复制以保持本模块零引擎依赖)
_S3 = math.sqrt(3) / 2
DIRVEC = {
    'E':  (1.0, 0.0),
    'W':  (-1.0, 0.0),
    'NE': (0.5, -_S3),
    'NW': (-0.5, -_S3),
    'SE': (0.5, _S3),
    'SW': (-0.5, _S3),
}

DEFAULT_SPACING = 500.0
DEFAULT_ECHELON_DEG = 45.0
DEFAULT_DEPLOY = "right"

# 旋钮取值(与 fleet_search 常量字面值一致;本模块输出字符串,实例化时直接填运行期字段)
TURN_FOLLOW = "follow"
TURN_TOGETHER = "together"
REL_ABSOLUTE = "absolute"
REL_RELATIVE = "relative"
KIND_AHEAD = "ahead"
KIND_ABREAST = "abreast"
KIND_ECHELON = "echelon"
KIND_SINGLE = "single"


@dataclass
class OrderShip:
    name: str
    index: int


@dataclass
class OrderFormation:
    name: str
    n_ships: int
    kind: str
    offset_fwd: float = 0.0
    offset_left: float = 0.0
    spacing: float = DEFAULT_SPACING
    deploy: str = DEFAULT_DEPLOY
    echelon_deg: float = DEFAULT_ECHELON_DEG
    turning: str = TURN_FOLLOW
    relative: str = REL_ABSOLUTE
    note: str = ""
    frozen_offset_xy: tuple = None
    ships: list = field(default_factory=list)


@dataclass
class OrderFleet:
    name: str
    side: str
    initial_course: str
    formations: list = field(default_factory=list)


@dataclass
class Battle:
    side: str
    fleets: list = field(default_factory=list)


_RELPOS_RE = re.compile(r"^(\d+(?:\.\d+)?)([FBLR])$", re.IGNORECASE)


def parse_relative_position(text):
    """'8000F 10000L' -> (offset_fwd, offset_left).  '0' -> (0,0)。

    F→+fwd  B→−fwd  L→+left  R→−left;多分量矢量相加。
    容错全角空格(\\u3000)、多空格、首尾空白、大小写。
    """
    # 归一全角空格为半角,折叠空白
    norm = text.replace("　", " ").strip()
    if norm == "0":
        return (0.0, 0.0)
    fwd = 0.0
    left = 0.0
    for tok in norm.split():
        m = _RELPOS_RE.match(tok)
        if not m:
            raise ValueError(f"bad relative-position token {tok!r} in {text!r}")
        val = float(m.group(1))
        d = m.group(2).upper()
        if d == "F":
            fwd += val
        elif d == "B":
            fwd -= val
        elif d == "L":
            left += val
        else:  # "R"
            left -= val
    return (fwd, left)
