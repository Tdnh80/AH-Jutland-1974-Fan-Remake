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


def local_to_map(fleet_center_xy, course, offset_fwd, offset_left):
    """局部 (fwd,left) → 地图绝对 (x,y)(spec §6.3)。

    forward_hat = DIRVEC[course]
    left_hat    = (forward_hat.y, -forward_hat.x)       # +y 朝南下的左舷法向
    offset_xy   = offset_fwd*forward_hat + offset_left*left_hat
    return fleet_center_xy + offset_xy

    course 既可是 initial_course(absolute 冻结)也可是当前 course(relative 每拍重算);
    本函数不区分,调用方决定传哪个。
    """
    fx, fy = DIRVEC[course]
    lx, ly = (fy, -fx)
    cx, cy = fleet_center_xy
    ox = offset_fwd * fx + offset_left * lx
    oy = offset_fwd * fy + offset_left * ly
    return (cx + ox, cy + oy)


# 全角破折号(数据行分隔符)。文件实测用 EM DASH —。
_DASH = "—"
# Fleet 行:'BS：Initial Course SE（45°）' / 'SG：Initial Course NW'
_FLEET_RE = re.compile(r"^([A-Za-z0-9]+)\s*[:：]\s*Initial\s+Course\s+([A-Za-z]+)",
                       re.IGNORECASE)

# 既定决策注记(spec §6.4)
_NOTE_6TH = "推断修正:原文5625L,按左右对称应为5625R"
_NOTE_MUNCHEN = "同名舰两次,按字面各导,请核对笔误"
_NOTE_2CS = "原注'是否坐标变化至下一格/作为独立Fleet';本导入按同Fleet两Formation,未移格"


def _norm_course(token):
    """'SE（45°）' / 'NW' -> 'SE'/'NW'(取前缀字母方向键)。"""
    t = token.strip().upper()
    m = re.match(r"^(NE|NW|SE|SW|E|W|N|S)", t)
    if not m:
        raise ValueError(f"bad initial course {token!r}")
    return m.group(1)


def _split_cols(line):
    """按全角破折号切列并 strip(去掉首尾空白与全角空格)。"""
    return [c.replace("　", " ").strip() for c in line.split(_DASH)]


def _parse_kind(text):
    t = text.lower()
    if "abreast" in t:
        return KIND_ABREAST
    if "echelon" in t:
        return KIND_ECHELON
    return KIND_AHEAD   # 'line ahead' 及缺省


def _parse_turning(text):
    t = text.strip().lower()
    if "together" in t:
        return TURN_TOGETHER
    if "follow" in t:
        return TURN_FOLLOW
    return TURN_FOLLOW


def _parse_relative(text):
    return REL_RELATIVE if text.strip().lower().startswith("relative") else REL_ABSOLUTE


_SPACING_RE = re.compile(r"space\s*[:：]?\s*(\d+(?:\.\d+)?)\s*yds?", re.IGNORECASE)
_DEPLOY_RE = re.compile(r"Deployment\s+direction\s*[:：]?\s*([LR])", re.IGNORECASE)


def _parse_formation_row(cols):
    """单条数据行的列 -> OrderFormation(不含同名消歧/既定决策注记,那些在 parse_battle 里加)。

    列布局(实测,列数 4~8 不等;single 行只有 名/Ships/RelPos/Relative 4 列):
      name | Ships(n) | Formation类型 | [info: space/deploy] ... | Turning | RelPos | Relative
    策略:第 0 列=name,第 1 列=Ships;末列=Relative(absolute/relative);
    RelPos=倒数第二列;在中段(cols[2:-2])按关键字提取 kind/spacing/deploy/turning。
    """
    name = cols[0]
    n_ships = int(re.search(r"\d+", cols[1]).group(0))
    relative = _parse_relative(cols[-1])
    relpos_text = cols[-2]
    joined = " ".join(cols[2:-2])     # 中段合并,便于关键字扫描

    if n_ships == 1:
        kind = KIND_SINGLE
        turning = "na"
        spacing = DEFAULT_SPACING
        deploy = DEFAULT_DEPLOY
        echelon_deg = DEFAULT_ECHELON_DEG
    else:
        kind = _parse_kind(joined)
        turning = _parse_turning(joined)
        sm = _SPACING_RE.search(joined)
        spacing = float(sm.group(1)) if sm else DEFAULT_SPACING
        dm = _DEPLOY_RE.search(joined)
        deploy = ("right" if dm.group(1).upper() == "R" else "left") if dm else DEFAULT_DEPLOY
        echelon_deg = DEFAULT_ECHELON_DEG

    fwd, left = parse_relative_position(relpos_text)
    return OrderFormation(
        name=name, n_ships=n_ships, kind=kind,
        offset_fwd=fwd, offset_left=left, spacing=spacing,
        deploy=deploy, echelon_deg=echelon_deg,
        turning=turning, relative=relative,
    )


def _make_ships(formation):
    formation.ships = [OrderShip(name=f"{formation.name}-{i + 1}", index=i)
                       for i in range(formation.n_ships)]


def parse_battle(text, side):
    """整文件文本 -> Battle(side 的若干 OrderFleet,各挂 OrderFormation)。

    既定决策(spec §6.4)在此层落地:6th Div. 改判 5625R + note;
    两个同名 München -> #1/#2 + note;2CS 两行 -> 2CS#1/#2 + note;
    其余同名行也按出现顺序加 #k 后缀消歧。
    """
    fleets = []
    cur = None
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        fm_fleet = _FLEET_RE.match(line.strip())
        if fm_fleet:
            cur = OrderFleet(name=fm_fleet.group(1),
                             side=side,
                             initial_course=_norm_course(fm_fleet.group(2)),
                             formations=[])
            fleets.append(cur)
            continue
        if cur is None or _DASH not in line:
            continue
        cols = _split_cols(line)
        if len(cols) < 4 or not cols[0]:
            continue
        fm = _parse_formation_row(cols)
        cur.formations.append(fm)

    for fl in fleets:
        _apply_decisions_and_dedup(fl)
        for fm in fl.formations:
            _make_ships(fm)
    return Battle(side=side, fleets=fleets)


def _apply_decisions_and_dedup(fleet):
    """落地 §6.4 既定决策 + 同名 Formation 加 #k 后缀。"""
    # 1) 6th Div. 修正(仅 GB BS):若 offset_left>0(误判 L)则翻成 R 并加 note
    for fm in fleet.formations:
        if fm.name == "6th Div." and fm.offset_left > 0:
            fm.offset_left = -fm.offset_left
            fm.note = _NOTE_6TH

    # 2) 同名去重:统计名字出现次数,>1 的按出现顺序加 #1/#2...
    from collections import Counter
    counts = Counter(fm.name for fm in fleet.formations)
    seen = {}
    for fm in fleet.formations:
        if counts[fm.name] > 1:
            base = fm.name
            seen[base] = seen.get(base, 0) + 1
            fm.name = f"{base}#{seen[base]}"
            if base == "München":
                fm.note = _NOTE_MUNCHEN
            elif base == "2CS":
                fm.note = _NOTE_2CS
            else:
                fm.note = fm.note or f"同名{base}第{seen[base]}个,请核对"


def parse_battle_file(path, side):
    with open(path, encoding="utf-8") as fh:
        return parse_battle(fh.read(), side)
