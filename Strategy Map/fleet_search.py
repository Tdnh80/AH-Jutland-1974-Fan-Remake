#!/usr/bin/env python3
"""
Jutland Fleet Search & Encounter — MVP CLI prototype (v4)
=========================================================

v4 changes (per 修正.txt):
* Coordinates switched to axial (q, r).  Uniform neighbour deltas, negatives OK.
  Origin (0,0) is an arbitrary reference; remap later via a single constant.
* Visibility cap restored to one hex width (HEX_SIDE = 36000 yd); default 20000.
  (The visibility circle is a detection RADIUS and may legitimately span >1 hex.)
* Encounter resolution rolls BACK to the last 10-min step where the closing pair
  was still >= vis (clean pre-contact state).  The exact =vis crossing is given
  as auxiliary projected-contact info only.
* Encounter report: HHMM clock time, NO per-ship pairing.  Each involved fleet's
  reference centre is reported as <hex> <edge> <distance-to-centre>.
* `clear <name>` cancels a schedule (keeps position/heading).
* Colours swapped: GB red, GE blue.
* Visibility circles drawn for ALL ships (all-or-nothing).
* 180-degree reversal in a schedule is now allowed.
* Random walk biased toward going straight (fewer zig-zags).
* Position is kept as exact (x, y); reported micro-position is never snapped
  to a hex centre.

Deferred to v5 (need 修正.txt material): formation states (column / line-abreast
/ echelon) + relative-position modes; post-encounter state machine
(maintain / break contact); networking.
"""

import io
import json
import math
import random
import re
import shlex
from contextlib import redirect_stdout
from dataclasses import dataclass, field, asdict
import formation
import journal as journal_mod
import coords
import timekeep
import orderparse


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEX_SIDE = 36000.0                  # flat-to-flat (= 1 hex width, = neighbour spacing)
HEX_SIZE = HEX_SIDE / math.sqrt(3)  # centre-to-vertex
APOTHEM = HEX_SIDE / 2.0            # centre-to-edge-midpoint
STEP_YARDS_PER_KNOT = 36000.0 / 108  # = 333.33 -> 18kn covers exactly 1 hex / 6 substeps
DEFAULT_SPACING = 500.0
# v6 three-layer formation knobs
TURN_FOLLOW = "follow"
TURN_TOGETHER = "together"
REL_ABSOLUTE = "absolute"
REL_RELATIVE = "relative"
KIND_AHEAD = formation.LINE_AHEAD       # "ahead"
KIND_ABREAST = formation.LINE_ABREAST   # "abreast"
KIND_ECHELON = formation.ECHELON        # "echelon"
KIND_SINGLE = "single"
DEFAULT_VISIBILITY = 20000.0        # base figure from requirement.docx
MAX_VISIBILITY = HEX_SIDE           # 36000; "能见度最高 36k yards"

# axial neighbour deltas (pointy-top), uniform for every hex
NEIGH = {
    'E':  (1, 0),
    'W':  (-1, 0),
    'NE': (1, -1),
    'NW': (0, -1),
    'SE': (0, 1),
    'SW': (-1, 1),
}
DIRECTION_LIST = ['E', 'NE', 'NW', 'W', 'SW', 'SE']
OPPOSITE = {'E': 'W', 'W': 'E', 'NE': 'SW', 'SW': 'NE', 'NW': 'SE', 'SE': 'NW'}
VALID_SPEEDS = (12, 18, 24)
VALID_SIDES = ('GB', 'GE')
STATE_SEARCH = "SEARCH"
STATE_CONTACT = "CONTACT"
HEX_PER_CYCLE = {12: 2, 18: 3, 24: 4}

# pixel direction unit vectors (+y = "south"/down on the plot)
_S3 = math.sqrt(3) / 2
DIRVEC = {
    'E':  (1.0, 0.0),
    'W':  (-1.0, 0.0),
    'NE': (0.5, -_S3),
    'NW': (-0.5, -_S3),
    'SE': (0.5, _S3),
    'SW': (-0.5, _S3),
}


# ---------------------------------------------------------------------------
# Axial hex helpers
# ---------------------------------------------------------------------------

def parse_hex(s):
    """'q,r' or '(q,r)' -> (q, r) ints, negatives allowed."""
    m = re.match(r"^\(?\s*(-?\d+)\s*,\s*(-?\d+)\s*\)?$", s.strip())
    if not m:
        raise ValueError(f"bad hex {s!r}; use q,r e.g. 3,-2")
    return (int(m.group(1)), int(m.group(2)))


def hex_name(q, r):
    return f"({q},{r})"


def hex_center_xy(q, r):
    x = HEX_SIDE * (q + r / 2.0)
    y = HEX_SIDE * _S3 * r
    return (x, y)


def _cube_round(x, y, z):
    rx, ry, rz = round(x), round(y), round(z)
    dx, dy, dz = abs(rx - x), abs(ry - y), abs(rz - z)
    if dx > dy and dx > dz:
        rx = -ry - rz
    elif dy > dz:
        ry = -rx - rz
    else:
        rz = -rx - ry
    return rx, ry, rz


def xy_to_hex(x, y):
    """pixel -> nearest axial hex (the containing hex)."""
    r = y / (HEX_SIDE * _S3)
    q = x / HEX_SIDE - r / 2.0
    rx, ry, rz = _cube_round(q, -q - r, r)
    return (rx, rz)


def hex_neighbour(h, d):
    dq, dr = NEIGH[d]
    return (h[0] + dq, h[1] + dr)


def direction_between(a, b):
    for d in NEIGH:
        if hex_neighbour(a, d) == b:
            return d
    return None


def micro_position(x, y):
    """Return (hex, edge_dir, dist_to_centre).  edge_dir = the edge midpoint the
    point lies toward (one of 6 dirs), dist = yards from hex centre."""
    h = xy_to_hex(x, y)
    cx, cy = hex_center_xy(*h)
    dx, dy = x - cx, y - cy
    dist = math.hypot(dx, dy)
    if dist < 1.0:
        return h, None, 0.0
    best, best_dot = None, -2.0
    for d, (vx, vy) in DIRVEC.items():
        dot = (dx * vx + dy * vy) / dist
        if dot > best_dot:
            best, best_dot = d, dot
    return h, best, dist


def parse_cell_or_hex(s):
    """玩家用字母数字 'A13';开发者仍可用 'q,r'。-> (q, r)。"""
    try:
        return coords.parse_cell(s)
    except ValueError:
        return parse_hex(s)


def display_cell(q, r):
    """显示用字母数字;地图外行号回退到 (q,r)。"""
    try:
        return coords.cell_name(q, r)
    except ValueError:
        return hex_name(q, r)


def micro_str(x, y):
    h, edge, dist = micro_position(x, y)
    name = display_cell(*h)
    if edge is None:
        return f"{name} at centre"
    return f"{name}  {dist:.0f} yd from centre → {edge} edge"


def random_walk_path(start, speed, rng, prev_dir=None, straight_bias=0.65,
                     bound=40):
    n = HEX_PER_CYCLE[speed]
    cur, cd, out = start, prev_dir, []
    for _ in range(n):
        if cd is not None and rng.random() < straight_bias:
            order = [cd] + [d for d in DIRECTION_LIST if d not in (cd, OPPOSITE[cd])]
        else:
            order = [d for d in DIRECTION_LIST if cd is None or d != OPPOSITE[cd]]
            rng.shuffle(order)
        for d in order:
            nb = hex_neighbour(cur, d)
            if abs(nb[0]) <= bound and abs(nb[1]) <= bound:
                cur, cd = nb, d
                out.append(cur)
                break
    return out


def attracted_walk_path(start, target, speed, rng, prev_dir=None, pull=0.0, bound=40):
    """像 random_walk_path,但以概率 pull 选朝 target 方向推进的相邻格。"""
    n = HEX_PER_CYCLE[speed]
    cur, cd, out = start, prev_dir, []
    for _ in range(n):
        if rng.random() < pull:
            # 选使到 target 的轴向距离最小的相邻方向
            best, bestd = None, None
            for d in DIRECTION_LIST:
                nb = hex_neighbour(cur, d)
                if abs(nb[0]) > bound or abs(nb[1]) > bound:
                    continue
                dd = abs(nb[0] - target[0]) + abs(nb[1] - target[1])
                if bestd is None or dd < bestd:
                    best, bestd = d, dd
            if best is not None:
                nb = hex_neighbour(cur, best)
                out.append(nb)
                cur, cd = nb, best
                continue
        # 否则普通直行偏置随机走一步
        step = random_walk_path(cur, 12, rng, prev_dir=cd)  # 12kn -> 1 步
        if step:
            new_pos = step[0]
            new_dir = direction_between(cur, new_pos) or cd
            cur, cd = new_pos, new_dir
            out.append(cur)
    return out[:n]


def hhmm(total_minutes):
    h = (total_minutes // 60) % 24
    m = total_minutes % 60
    return f"{h:02d}{m:02d}"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Ship:
    name: str
    index: int = 0


@dataclass
class Formation:
    name: str
    ships: list = field(default_factory=list)
    offset_fwd: float = 0.0          # +forward / -back, yards (along initial/current course)
    offset_left: float = 0.0         # +port / -starboard, yards
    relative: str = REL_RELATIVE     # absolute = freeze offset on initial_course; relative = follow course
    kind: str = KIND_AHEAD
    spacing: float = DEFAULT_SPACING
    deploy: str = "right"
    echelon_deg: float = 45.0
    turning: str = TURN_FOLLOW       # follow = arc-rollback; together = rigid
    frozen_offset_xy: tuple = None   # lazily frozen map offset in absolute mode (None = not yet)
    frozen_offset_xy_legacy: tuple = None   # v5 layout_heading carrier (compat only)
    note: str = ""                   # provenance note (e.g. inferred order-file decision)

    @property
    def is_single(self):
        return len(self.ships) == 1 or self.kind == KIND_SINGLE


@dataclass
class Fleet:
    name: str
    side: str
    activated_turn: int
    anchor_xy: tuple          # exact (x, y); NOT snapped to a centre
    anchor_substep: float     # may be float (locked invariant)
    course: str
    speed: int
    ships: list = field(default_factory=list)   # transitional; mirrored into primary Formation
    scheduled: bool = False
    schedule_end_substep: float = 0.0
    waypoints: list = field(default_factory=list)   # axial hexes excl. start
    display_history: list = field(default_factory=list)  # [(substep, x, y)]
    initial_course: str = None       # course anchored at layout time (0deg axis for L/R/F/B)
    formations: list = field(default_factory=list)   # >=1 Formation (lower layer)

    def __post_init__(self):
        if self.initial_course is None:
            self.initial_course = self.course
        if not self.formations:
            # wrap any constructor-supplied ships into a default zero-offset single Formation
            ships = self.ships if self.ships else []
            for i, s in enumerate(ships):
                s.index = i
            self.formations = [Formation(name=self.name, ships=list(ships))]
        # keep self.ships pointing at the primary Formation's ship list (single source)
        self.ships = self.formations[0].ships

    @property
    def primary(self):
        return self.formations[0]

    # --- backward-compat legacy formation fields (delegate to primary Formation) ---
    @property
    def formation_kind(self):
        return self.primary.kind

    @formation_kind.setter
    def formation_kind(self, v):
        self.primary.kind = v

    @property
    def spacing(self):
        return self.primary.spacing

    @spacing.setter
    def spacing(self, v):
        self.primary.spacing = v

    @property
    def deploy(self):
        return self.primary.deploy

    @deploy.setter
    def deploy(self, v):
        self.primary.deploy = v

    @property
    def echelon_deg(self):
        return self.primary.echelon_deg

    @echelon_deg.setter
    def echelon_deg(self, v):
        self.primary.echelon_deg = v

    @property
    def pos_mode(self):
        # legacy formation.ABS_MODE/REL_MODE == REL_ABSOLUTE/REL_RELATIVE (same string values)
        return self.primary.relative

    @pos_mode.setter
    def pos_mode(self, v):
        self.primary.relative = v

    @property
    def layout_heading(self):
        return self.primary.frozen_offset_xy_legacy

    @layout_heading.setter
    def layout_heading(self, v):
        self.primary.frozen_offset_xy_legacy = (tuple(v) if v is not None else None)

    def is_active(self, substep):
        return substep >= self.activated_turn * 6

    def _polyline(self):
        if self.scheduled and self.waypoints:
            return [self.anchor_xy] + [hex_center_xy(*w) for w in self.waypoints]
        ux, uy = DIRVEC[self.course]
        ax, ay = self.anchor_xy
        far = HEX_SIDE * 400
        return [(ax, ay), (ax + far * ux, ay + far * uy)]

    def _arc_at(self, substep):
        return (substep - self.anchor_substep) * self.speed * STEP_YARDS_PER_KNOT

    def _xy_at_arc(self, arc):
        poly = self._polyline()
        if arc <= 0:
            (x0, y0), (x1, y1) = poly[0], poly[1]
            dx, dy = x1 - x0, y1 - y0
            d = math.hypot(dx, dy) or 1.0
            return (x0 + arc * dx / d, y0 + arc * dy / d)
        rem = arc
        for i in range(len(poly) - 1):
            (x0, y0), (x1, y1) = poly[i], poly[i + 1]
            dx, dy = x1 - x0, y1 - y0
            seg = math.hypot(dx, dy)
            if rem <= seg:
                t = rem / seg if seg else 0.0
                return (x0 + t * dx, y0 + t * dy)
            rem -= seg
        (x0, y0), (x1, y1) = poly[-2], poly[-1]
        dx, dy = x1 - x0, y1 - y0
        d = math.hypot(dx, dy) or 1.0
        return (x1 + rem * dx / d, y1 + rem * dy / d)

    def lead_xy(self, substep):
        return self._xy_at_arc(self._arc_at(substep))

    def _offset_to_map(self, fo, course_key):
        """offset_fwd along course + offset_left to port -> map (dx, dy)."""
        fx, fy = DIRVEC[course_key]
        # port normal for +y-south frame: left_hat = (fy, -fx).  Note this is the
        # NEGATIVE of formation.py's starboard normal (-uy, ux); the two modules
        # use opposite sign conventions (here: +left = port; formation: +right).
        lx, ly = fy, -fx
        return (fo.offset_fwd * fx + fo.offset_left * lx,
                fo.offset_fwd * fy + fo.offset_left * ly)

    def _formation_center_xy(self, fo, substep):
        """Stage 2: fleet center + rotated offset (relative knob)."""
        cx, cy = self.lead_xy(substep)
        if fo.offset_fwd == 0.0 and fo.offset_left == 0.0:
            return (cx, cy)
        if fo.relative == REL_ABSOLUTE:
            if fo.frozen_offset_xy is None:
                fo.frozen_offset_xy = self._offset_to_map(fo, self.initial_course)
            ox, oy = fo.frozen_offset_xy
        else:
            ox, oy = self._offset_to_map(fo, self.course)
        return (cx + ox, cy + oy)

    @staticmethod
    def _kind_for_offsets(fo):
        # KIND_SINGLE has no formation.ship_offsets entry; treat as a 1-row line-ahead
        return KIND_AHEAD if fo.kind == KIND_SINGLE else fo.kind

    def _formation_ship_positions(self, fo, substep):
        """Stage 3: internal ship positions for one Formation (turning knob)."""
        n = len(fo.ships)
        if fo.turning == TURN_FOLLOW and fo.kind == KIND_AHEAD:
            # follow / in-succession: arc-rollback along the fleet polyline (+ frozen translate)
            lead_a = self._arc_at(substep)
            if fo.offset_fwd == 0.0 and fo.offset_left == 0.0:
                base = (0.0, 0.0)
            elif fo.relative == REL_ABSOLUTE:
                if fo.frozen_offset_xy is None:
                    fo.frozen_offset_xy = self._offset_to_map(fo, self.initial_course)
                base = fo.frozen_offset_xy
            else:
                base = self._offset_to_map(fo, self.course)
            out = []
            for s in fo.ships:
                x, y = self._xy_at_arc(lead_a - s.index * fo.spacing)
                out.append((s.name, (x + base[0], y + base[1])))
            return out
        # together (or non-ahead follow falls back to rigid): rigid spread about formation center
        center = self._formation_center_xy(fo, substep)
        hat = DIRVEC[self.initial_course] if fo.relative == REL_ABSOLUTE else DIRVEC[self.course]
        offs = formation.ship_offsets(self._kind_for_offsets(fo), n,
                                      fo.spacing, fo.deploy, fo.echelon_deg)
        map_offs = formation.to_map_offsets(hat, offs)
        pts = formation.place_map(center, map_offs)
        return [(s.name, p) for s, p in zip(fo.ships, pts)]

    def ship_positions(self, substep):
        out = []
        for fo in self.formations:
            out.extend(self._formation_ship_positions(fo, substep))
        return out


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------

class Game:
    def __init__(self):
        self.fleets = {}
        self.current_substep = 0
        self.visibility = DEFAULT_VISIBILITY
        self.start_minute = 0          # clock time at substep 0
        self.last_report = None        # dict for plotting the encounter marker
        self.state = STATE_SEARCH
        self.contact_hexes = set()
        self.rng = random.Random()
        self.journal = journal_mod.Journal(self.start_minute, self.visibility)

    @property
    def current_turn(self):
        return self.current_substep // 6

    def clock(self, substep):
        return hhmm(self.start_minute + substep * 10)

    def datestr(self, substep):
        """绝对日期时刻 DD/MM/YY HHMM。"""
        return timekeep.fmt_date(self.start_minute + substep * 10)

    # --- fleet ops ---

    def add_fleet(self, name, side, activated, hex_str, course, speed, n):
        if name in self.fleets: raise ValueError(f"fleet {name!r} exists")
        if side not in VALID_SIDES: raise ValueError("side must be GB or GE")
        if course not in NEIGH: raise ValueError(f"course in {DIRECTION_LIST}")
        if speed not in VALID_SPEEDS: raise ValueError(f"speed in {VALID_SPEEDS}")
        if n < 1: raise ValueError("need >= 1 ship")
        h = parse_cell_or_hex(hex_str)
        ships = [Ship(f"{name}-{i+1}", i) for i in range(n)]
        f = Fleet(name=name, side=side, activated_turn=activated,
                  anchor_xy=hex_center_xy(*h), anchor_substep=activated * 6,
                  course=course, speed=speed, initial_course=course,
                  ships=ships)
        f.display_history.append((activated * 6, *f.anchor_xy))
        self.fleets[name] = f

    def load_order_file(self, path, side, start_hex="0,0", speed=18, activated=0):
        """读编组文件 -> 每个 OrderFormation 实例化为一个运行期 Fleet。

        返回创建的运行期 Fleet 名列表。Fleet 名 = '<OrderFleet>/<Formation>'。
        absolute 模式懒冻结 frozen_offset_xy(本处 offset 已并入 anchor_xy,
        运行期 Formation 自身 offset=0,故 frozen_offset_xy=(0,0));relative 留 None。
        """
        if side not in VALID_SIDES:
            raise ValueError("side must be GB or GE")
        if speed not in VALID_SPEEDS:
            raise ValueError(f"speed in {VALID_SPEEDS}")
        battle = orderparse.parse_battle_file(path, side)
        h = parse_cell_or_hex(start_hex)
        center = hex_center_xy(*h)
        created = []
        for ofleet in battle.fleets:
            crs = ofleet.initial_course
            if crs not in NEIGH:
                raise ValueError(f"unsupported initial course {crs!r} in {ofleet.name}")
            for ofm in ofleet.formations:
                # side prefix keeps names globally unique when both GB & GE are
                # loaded into one Game (both sides have a Fleet named "BS" with
                # overlapping Division names, e.g. "1st Div."/"3rd Div.").
                fleet_name = f"{side} {ofleet.name}/{ofm.name}"
                if fleet_name in self.fleets:
                    raise ValueError(f"fleet {fleet_name!r} already exists")
                anchor = orderparse.local_to_map(center, crs,
                                                 ofm.offset_fwd, ofm.offset_left)
                ships = [Ship(name=f"{fleet_name}-{i+1}", index=i)
                         for i in range(ofm.n_ships)]
                relative = ofm.relative
                turning = ofm.turning if ofm.turning != "na" else TURN_FOLLOW
                run_fm = Formation(
                    name=ofm.name, ships=ships,
                    offset_fwd=0.0, offset_left=0.0,
                    relative=relative, kind=ofm.kind,
                    spacing=ofm.spacing, deploy=ofm.deploy,
                    echelon_deg=ofm.echelon_deg, turning=turning,
                    frozen_offset_xy=((0.0, 0.0) if relative == REL_ABSOLUTE else None),
                    note=ofm.note,
                )
                f = Fleet(
                    name=fleet_name, side=side, activated_turn=activated,
                    anchor_xy=anchor, anchor_substep=activated * 6,
                    course=crs, speed=speed, initial_course=crs,
                    formations=[run_fm],
                )
                f.display_history.append((activated * 6, *anchor))
                self.fleets[fleet_name] = f
                created.append(fleet_name)
        return created

    def delete_fleet(self, name):
        if name not in self.fleets: raise KeyError(name)
        del self.fleets[name]

    def relocate(self, name, hex_str, course, speed):
        f = self._get(name)
        if course not in NEIGH: raise ValueError("bad course")
        if speed not in VALID_SPEEDS: raise ValueError("bad speed")
        f.anchor_xy = hex_center_xy(*parse_cell_or_hex(hex_str))
        f.anchor_substep = self.current_substep
        f.course = course; f.speed = speed
        f.scheduled = False; f.schedule_end_substep = 0.0; f.waypoints = []
        f.display_history = [(self.current_substep, *f.anchor_xy)]

    def course_change(self, name, course, speed=None):
        f = self._get(name)
        if course not in NEIGH: raise ValueError("bad course")
        if speed is not None and speed not in VALID_SPEEDS: raise ValueError("bad speed")
        if f.scheduled: raise ValueError(f"{name!r} has an active schedule; clear it first")
        f.anchor_xy = f.lead_xy(self.current_substep)   # exact, no snap
        f.anchor_substep = self.current_substep
        f.course = course
        if speed is not None: f.speed = speed

    def clear_schedule(self, name):
        f = self._get(name)
        if not f.scheduled:
            return False
        f.anchor_xy = f.lead_xy(self.current_substep)
        f.anchor_substep = self.current_substep
        f.scheduled = False; f.schedule_end_substep = 0.0; f.waypoints = []
        return True

    def schedule(self, name, speed, hex_strs):
        f = self._get(name)
        if speed not in VALID_SPEEDS: raise ValueError("speed 12/18/24")
        need = HEX_PER_CYCLE[speed]
        if len(hex_strs) != need:
            raise ValueError(f"{speed}kn needs {need} waypoints, got {len(hex_strs)}")
        cur_hex = xy_to_hex(*f.lead_xy(self.current_substep))
        wps = [parse_cell_or_hex(h) for h in hex_strs]
        chain = [cur_hex] + wps
        for a, b in zip(chain, chain[1:]):
            if direction_between(a, b) is None:
                raise ValueError(f"{hex_name(*a)} -> {hex_name(*b)} not adjacent")
            # 180-degree reversal now allowed (v4); no reversal check
        f.anchor_xy = hex_center_xy(*cur_hex)
        f.anchor_substep = self.current_substep
        f.course = direction_between(chain[0], chain[1])
        f.speed = speed
        f.waypoints = wps
        f.scheduled = True
        total = need * HEX_SIDE
        f.schedule_end_substep = self.current_substep + total / (speed * STEP_YARDS_PER_KNOT)

    def randwalk(self, name, speed=None):
        f = self._get(name)
        if speed is None: speed = f.speed
        if speed not in VALID_SPEEDS: raise ValueError("bad speed")
        cur = xy_to_hex(*f.lead_xy(self.current_substep))
        path = random_walk_path(cur, speed, self.rng, prev_dir=f.course)
        if len(path) != HEX_PER_CYCLE[speed]:
            raise RuntimeError("random walk hit bound; relocate fleet")
        self.schedule(name, speed, [display_cell(*h) for h in path])
        return path

    def _get(self, name):
        if name not in self.fleets: raise KeyError(f"no fleet {name!r}")
        return self.fleets[name]

    # --- detection ---

    def _cross_pairs(self, sub):
        # Traverse fleet -> formation -> ship: ship_positions(sub) already aggregates
        # the exact xy of every Ship across ALL of this Fleet's Formations.  Encounter
        # granularity stays at the Ship level (the vertex-to-vertex case needs true
        # per-ship Euclidean distance); only cross-side GB x GE pairs are produced.
        gb = [f for f in self.fleets.values() if f.side == 'GB' and f.is_active(sub)]
        ge = [f for f in self.fleets.values() if f.side == 'GE' and f.is_active(sub)]
        pairs = []
        for fa in gb:
            pa = fa.ship_positions(sub)
            for fb in ge:
                pb = fb.ship_positions(sub)
                for _, (ax, ay) in pa:
                    for _, (bx, by) in pb:
                        pairs.append((math.hypot(ax - bx, ay - by), fa, fb))
        return pairs

    def _min_dist_between(self, fa, fb, sub_float):
        pa = fa.ship_positions(sub_float)
        pb = fb.ship_positions(sub_float)
        best = math.inf
        for _, (ax, ay) in pa:
            for _, (bx, by) in pb:
                d = math.hypot(ax - bx, ay - by)
                if d < best: best = d
        return best

    def step_turn(self):
        if self.state == STATE_CONTACT:
            if not self.resume_search_if_clear():
                # 仍保持接触:推进时间,记录相邻格进入者,不重复回退(否则死锁)
                self.current_substep += 6
                for f in self.fleets.values():
                    if f.is_active(self.current_substep):
                        f.display_history.append((self.current_substep, *f.lead_xy(self.current_substep)))
                if self.last_report is not None:
                    self.last_report['entrants'] = self.adjacent_entrants()
                self.journal.record_turn(self.to_dict())
                return None
            # 已脱离接触 -> 落入下面常规搜索推进
        for offset in range(1, 7):
            sub = self.current_substep + offset
            for f in self.fleets.values():
                if f.is_active(sub):
                    f.display_history.append((sub, *f.lead_xy(sub)))
            pairs = self._cross_pairs(sub)
            hits = [(d, fa, fb) for (d, fa, fb) in pairs if d < self.visibility]
            if hits:
                result = self._resolve_encounter(sub)
                self.journal.record_turn(self.to_dict())
                return result
        self.current_substep += 6
        for f in self.fleets.values():
            if f.scheduled and self.current_substep >= f.schedule_end_substep:
                self._end_schedule(f)
        self.journal.record_turn(self.to_dict())
        return None

    def _end_schedule(self, f):
        end = f.schedule_end_substep
        f.anchor_xy = f.lead_xy(end)
        f.anchor_substep = end
        if f.waypoints and len(f.waypoints) >= 1:
            prev = xy_to_hex(*f.lead_xy(end - 1)) if end >= 1 else None
            last = f.waypoints[-1]
            d = direction_between(f.waypoints[-2] if len(f.waypoints) >= 2 else xy_to_hex(*f.anchor_xy), last)
            if d: f.course = d
        f.scheduled = False; f.schedule_end_substep = 0.0; f.waypoints = []

    def _resolve_encounter(self, S):
        """S = first substep with any cross pair < vis.  Roll back to S-1."""
        roll = S - 1
        # involved fleet pairs at S
        involved = {}
        for d, fa, fb in self._cross_pairs(S):
            if d < self.visibility:
                key = (fa.name, fb.name)
                if key not in involved or d < involved[key][0]:
                    involved[key] = (d, fa, fb)

        encounters = []
        for (gbn, gen), (_, fa, fb) in involved.items():
            d_roll = self._min_dist_between(fa, fb, roll)
            d_S = self._min_dist_between(fa, fb, S)
            # projected =vis crossing between roll and S
            if d_roll > self.visibility >= d_S and d_roll > d_S:
                t = (d_roll - self.visibility) / (d_roll - d_S)   # 0..1
            else:
                t = 0.0
            contact_sub = roll + t
            entry = dict(
                gb=fa.name, ge=fb.name,
                gb_xy_roll=fa.lead_xy(roll), ge_xy_roll=fb.lead_xy(roll),
                dist_roll=d_roll,
                contact_sub=contact_sub,
                gb_xy_contact=fa.lead_xy(contact_sub), ge_xy_contact=fb.lead_xy(contact_sub),
            )
            encounters.append(entry)

        # freeze at roll
        self.current_substep = max(roll, 0)
        for f in self.fleets.values():
            if f.scheduled:
                self.clear_schedule(f.name)
        self.last_report = dict(substep=self.current_substep, encounters=encounters)
        hexes = set()
        for e in encounters:
            hexes.add(xy_to_hex(*e['gb_xy_roll']))
            hexes.add(xy_to_hex(*e['ge_xy_roll']))
        self.contact_hexes = hexes
        self.state = STATE_CONTACT
        return encounters

    def adjacent_entrants(self, lookahead=18):
        """接敌(CONTACT)态下,未参与的舰队若位于某接敌格的相邻格、且在
        lookahead 拍内驶入某接敌格,则纳入;返回 [(name, entry_substep, hex)]。
        始终未驶入(驶离)的不纳入。"""
        if self.state != STATE_CONTACT or not self.last_report:
            return []
        involved = set()
        for e in self.last_report['encounters']:
            involved.add(e['gb'])
            involved.add(e['ge'])
        adj = set()
        for ch in self.contact_hexes:
            for d in NEIGH:
                adj.add(hex_neighbour(ch, d))
        sub = self.current_substep
        out = []
        for f in self.fleets.values():
            if f.name in involved or not f.is_active(sub):
                continue
            if xy_to_hex(*f.lead_xy(sub)) not in adj:
                continue
            entry = None
            for k in range(1, lookahead + 1):
                h = xy_to_hex(*f.lead_xy(sub + k))
                if h in self.contact_hexes:
                    entry = sub + k
                    break
            if entry is not None:
                out.append((f.name, entry, xy_to_hex(*f.lead_xy(entry))))
        return out

    def resume_search_if_clear(self):
        """CONTACT 态下,若所有原涉及舰队的中心都已驶出接敌格,则脱离接触、回 SEARCH。
        注意:接敌定格拍本身所有对就 >= vis(干净的接触前状态),所以脱离判据不能用
        vis 距离(那会在刚接敌时就误判脱离),而要看「中心是否仍在接敌格」。"""
        if self.state != STATE_CONTACT or not self.last_report:
            return False
        involved = set()
        for e in self.last_report['encounters']:
            involved.add(e['gb'])
            involved.add(e['ge'])
        sub = self.current_substep
        for name in involved:
            f = self.fleets.get(name)
            if f is not None and xy_to_hex(*f.lead_xy(sub)) in self.contact_hexes:
                return False
        self.state = STATE_SEARCH
        self.contact_hexes = set()
        return True

    # --- reporting ---

    def status_line(self, f):
        if not f.is_active(self.current_substep):
            return f"  {f.name:<12} [{f.side}] inactive (T{f.activated_turn})"
        # center = formation reference point (lead_xy); spec §3.3
        cx, cy = f.lead_xy(self.current_substep)
        micro = micro_str(cx, cy)
        if f.scheduled:
            remain = max(0.0, f.schedule_end_substep - self.current_substep)
            end = display_cell(*f.waypoints[-1]) if f.waypoints else "?"
            st = f"sched→{end} ({remain:.0f}st)"
        else:
            st = "free"
        return (f"  {f.name:<12} [{f.side}] center={micro}  course={f.course} "
                f"speed={f.speed}kn ships={len(f.ships)} {st}")

    def list_status(self):
        if not self.fleets: return "  (no fleets)"
        return "\n".join(self.status_line(f)
                         for f in sorted(self.fleets.values(), key=lambda x: (x.side, x.name)))

    # --- save / load (JSON: fleet state + clock/substep/visibility; no RNG seed) ---

    @staticmethod
    def _formation_to_dict(fo):
        return {
            'name': fo.name,
            'ships': [{'name': s.name, 'index': s.index} for s in fo.ships],
            'offset_fwd': fo.offset_fwd, 'offset_left': fo.offset_left,
            'relative': fo.relative, 'kind': fo.kind, 'spacing': fo.spacing,
            'deploy': fo.deploy, 'echelon_deg': fo.echelon_deg,
            'turning': fo.turning,
            'frozen_offset_xy': (list(fo.frozen_offset_xy)
                                 if fo.frozen_offset_xy is not None else None),
            'frozen_offset_xy_legacy': (list(fo.frozen_offset_xy_legacy)
                                        if fo.frozen_offset_xy_legacy is not None else None),
            'note': fo.note,
        }

    @staticmethod
    def _fleet_to_dict(f):
        return {
            'name': f.name, 'side': f.side, 'activated_turn': f.activated_turn,
            'anchor_xy': list(f.anchor_xy), 'anchor_substep': f.anchor_substep,
            'course': f.course, 'speed': f.speed,
            'initial_course': f.initial_course,
            'ships': [s.name for s in f.ships],   # kept for human readability / v5 tools
            'scheduled': f.scheduled, 'schedule_end_substep': f.schedule_end_substep,
            'waypoints': [list(w) for w in f.waypoints],
            'display_history': [list(h) for h in f.display_history],
            'formations': [Game._formation_to_dict(fo) for fo in f.formations],
        }

    @staticmethod
    def _formation_from_dict(fd):
        fol = fd.get('frozen_offset_xy_legacy')
        fo = Formation(
            name=fd['name'],
            ships=[Ship(s['name'], s.get('index', i)) for i, s in enumerate(fd['ships'])],
            offset_fwd=fd.get('offset_fwd', 0.0), offset_left=fd.get('offset_left', 0.0),
            relative=fd.get('relative', REL_RELATIVE), kind=fd.get('kind', KIND_AHEAD),
            spacing=fd.get('spacing', DEFAULT_SPACING), deploy=fd.get('deploy', 'right'),
            echelon_deg=fd.get('echelon_deg', 45.0), turning=fd.get('turning', TURN_FOLLOW),
            note=fd.get('note', ''),
        )
        foz = fd.get('frozen_offset_xy')
        fo.frozen_offset_xy = tuple(foz) if foz is not None else None
        fo.frozen_offset_xy_legacy = tuple(fol) if fol is not None else None
        return fo

    @staticmethod
    def upgrade_v5_fleet(d):
        """v5 (flat formation fields, no 'formations') -> single zero-offset Formation."""
        kind = d.get('formation_kind', KIND_AHEAD)
        pos_mode = d.get('pos_mode', REL_RELATIVE)
        relative = REL_ABSOLUTE if pos_mode == REL_ABSOLUTE else REL_RELATIVE
        turning = TURN_FOLLOW if kind == KIND_AHEAD else TURN_TOGETHER
        lh = d.get('layout_heading')
        fo = Formation(
            name=d['name'],
            ships=[Ship(n, i) for i, n in enumerate(d['ships'])],
            offset_fwd=0.0, offset_left=0.0, relative=relative, kind=kind,
            spacing=d.get('spacing', DEFAULT_SPACING), deploy=d.get('deploy', 'right'),
            echelon_deg=d.get('echelon_deg', 45.0), turning=turning,
        )
        fo.frozen_offset_xy = (0.0, 0.0) if relative == REL_ABSOLUTE else None
        fo.frozen_offset_xy_legacy = tuple(lh) if lh is not None else None
        return fo

    @staticmethod
    def _fleet_from_dict(d):
        if 'formations' in d:
            formations = [Game._formation_from_dict(fd) for fd in d['formations']]
        else:
            formations = [Game.upgrade_v5_fleet(d)]
        f = Fleet(
            name=d['name'], side=d['side'], activated_turn=d['activated_turn'],
            anchor_xy=tuple(d['anchor_xy']), anchor_substep=d['anchor_substep'],
            course=d['course'], speed=d['speed'],
            initial_course=d.get('initial_course', d['course']),
            scheduled=d['scheduled'], schedule_end_substep=d['schedule_end_substep'],
            waypoints=[tuple(w) for w in d['waypoints']],
            display_history=[tuple(h) for h in d['display_history']],
            formations=formations,
        )
        return f

    def to_dict(self):
        return {
            'version': 6,
            'current_substep': self.current_substep,
            'visibility': self.visibility,
            'start_minute': self.start_minute,
            'state': self.state,
            'contact_hexes': sorted(list(h) for h in self.contact_hexes),
            'fleets': [self._fleet_to_dict(f) for f in self.fleets.values()],
        }

    def load_dict(self, data):
        self.current_substep = data['current_substep']
        self.visibility = data['visibility']
        self.start_minute = data.get('start_minute', 0)
        self.last_report = None
        self.state = data.get('state', STATE_SEARCH)
        self.contact_hexes = {tuple(h) for h in data.get('contact_hexes', [])}
        self.fleets = {f.name: f for f in (self._fleet_from_dict(d) for d in data['fleets'])}

    def save(self, filename):
        import json as _json
        self.journal.epoch_minute = self.start_minute
        self.journal.visibility = self.visibility
        payload = {"current": self.to_dict(), "journal": _json.loads(self.journal.to_json())}
        with open(filename, 'w', encoding='utf-8') as fh:
            _json.dump(payload, fh, ensure_ascii=False, indent=2)

    def load(self, filename):
        import json as _json
        with open(filename, 'r', encoding='utf-8') as fh:
            payload = _json.load(fh)
        self.load_dict(payload["current"])
        self.journal = journal_mod.Journal.from_json(_json.dumps(payload["journal"]))

    def replay_to(self, turn):
        """把盘面恢复到日志里第 turn 个回合快照(0 起)。不改动日志本身。"""
        snap = self.journal.snapshot_at_turn(turn)
        if snap is None:
            raise IndexError(f"no snapshot for turn {turn}")
        self.load_dict(snap)


# ---------------------------------------------------------------------------
# Double-blind view filter
# ---------------------------------------------------------------------------

def view_for_side(game, side):
    """裁判机对某一方的双盲视图:己方舰队全可见;接敌后才见对方涉及接敌的中心。"""
    own = [Game._fleet_to_dict(f) for f in game.fleets.values() if f.side == side]
    enemy_contacts = []
    if game.state == STATE_CONTACT and game.last_report:
        seen = set()
        for e in game.last_report['encounters']:
            if side == 'GB':
                name, xy = e['ge'], e['ge_xy_roll']
            else:
                name, xy = e['gb'], e['gb_xy_roll']
            if name in seen:
                continue
            seen.add(name)
            enemy_contacts.append({'name': name, 'center': list(xy),
                                   'cell': display_cell(*xy_to_hex(*xy))})
    return {
        'side': side,
        'state': game.state,
        'turn': game.current_turn,
        'substep': game.current_substep,
        'own': own,
        'enemy_contacts': enemy_contacts,
    }


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def _hex_corners(cx, cy):
    return [(cx + HEX_SIZE * math.cos(math.radians(-90 + 60 * i)),
             cy + HEX_SIZE * math.sin(math.radians(-90 + 60 * i))) for i in range(6)]


def plot_state(game, filename):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon, Circle
    except ImportError:
        raise RuntimeError("matplotlib not installed; pip install matplotlib")

    active = [f for f in game.fleets.values() if f.is_active(game.current_substep)]
    pts = []
    for f in active:
        for _, x, y in f.display_history:
            pts.append((x, y))
        if f.scheduled:
            for s in range(game.current_substep, int(f.schedule_end_substep) + 1):
                pts.append(f.lead_xy(s))
        for _, p in f.ship_positions(game.current_substep):
            pts.append(p)
    rep = game.last_report
    show_enc = rep and rep['substep'] == game.current_substep
    if show_enc:
        for e in rep['encounters']:
            pts += [e['gb_xy_roll'], e['ge_xy_roll'], e['gb_xy_contact'], e['ge_xy_contact']]
    if not pts:
        pts = [hex_center_xy(0, 0)]

    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    m = HEX_SIDE * 1.5
    x_min, x_max = min(xs) - m, max(xs) + m
    y_min, y_max = min(ys) - m, max(ys) + m
    ext = HEX_SIDE * 4
    if x_max - x_min < ext:
        c = (x_min + x_max) / 2; x_min, x_max = c - ext / 2, c + ext / 2
    if y_max - y_min < ext:
        c = (y_min + y_max) / 2; y_min, y_max = c - ext / 2, c + ext / 2

    # grid: enumerate hexes whose centre is in view
    r_lo = int(math.floor(y_min / (HEX_SIDE * _S3))) - 1
    r_hi = int(math.ceil(y_max / (HEX_SIDE * _S3))) + 1
    fig, ax = plt.subplots(figsize=(11, 10))
    for r in range(r_lo, r_hi + 1):
        q_lo = int(math.floor(x_min / HEX_SIDE - r / 2.0)) - 1
        q_hi = int(math.ceil(x_max / HEX_SIDE - r / 2.0)) + 1
        for q in range(q_lo, q_hi + 1):
            cx, cy = hex_center_xy(q, r)
            if not (x_min <= cx <= x_max and y_min <= cy <= y_max): continue
            ax.add_patch(Polygon(_hex_corners(cx, cy), closed=True, fill=False,
                                 edgecolor='#d3d3d3', linewidth=0.5))
            ax.text(cx, cy, f"{q},{r}", ha='center', va='center',
                    fontsize=6, color='#c0c0c0')

    colors = {'GB': '#a32020', 'GE': '#1f4e8a'}   # swapped: GB red, GE blue
    for f in active:
        col = colors[f.side]
        px = [p[1] for p in f.display_history]; py = [p[2] for p in f.display_history]
        if len(px) >= 2:
            ax.plot(px, py, '-', color=col, alpha=0.55, linewidth=1.5)
        if f.scheduled:
            fx, fy = [], []
            for s in range(game.current_substep, int(f.schedule_end_substep) + 1):
                x, y = f.lead_xy(s); fx.append(x); fy.append(y)
            ax.plot(fx, fy, '--', color=col, alpha=0.6, linewidth=1.5)
            if fx: ax.plot(fx[-1], fy[-1], '*', color=col, markersize=12,
                           markeredgecolor='black', markeredgewidth=0.4)
        for _, (sx, sy) in f.ship_positions(game.current_substep):
            ax.plot(sx, sy, 'o', color=col, markersize=5,
                    markeredgecolor='black', markeredgewidth=0.4)
            ax.add_patch(Circle((sx, sy), game.visibility, fill=False,
                                edgecolor=col, alpha=0.18, linewidth=0.8, linestyle=':'))
        lx, ly = f.lead_xy(game.current_substep)
        ax.annotate(f"{f.name}\n{f.speed}kn", (lx, ly),
                    textcoords='offset points', xytext=(10, -4),
                    fontsize=9, color=col, weight='bold')

    if show_enc and rep['encounters']:
        e = rep['encounters'][0]
        mx = (e['gb_xy_contact'][0] + e['ge_xy_contact'][0]) / 2
        my = (e['gb_xy_contact'][1] + e['ge_xy_contact'][1]) / 2
        ax.plot(mx, my, 'X', color='gold', markersize=20,
                markeredgecolor='black', markeredgewidth=1.2, zorder=5)
        ax.annotate(f"CONTACT\n{game.clock(round(e['contact_sub']))}", (mx, my),
                    textcoords='offset points', xytext=(14, 14), fontsize=10,
                    weight='bold', bbox=dict(boxstyle='round,pad=0.3', fc='gold', alpha=0.85))

    ax.set_xlim(x_min, x_max); ax.set_ylim(y_min, y_max)
    ax.set_aspect('equal'); ax.invert_yaxis()
    ax.set_title(f"Jutland Search — {game.clock(game.current_substep)} "
                 f"(sub{game.current_substep})   vis={game.visibility:.0f} yd "
                 f"({game.visibility/HEX_SIDE:.2f} hex)   GB=red GE=blue")
    ax.set_xticks([]); ax.set_yticks([])
    plt.tight_layout(); plt.savefig(filename, dpi=110, bbox_inches='tight'); plt.close(fig)


# ---------------------------------------------------------------------------
# Close-up encounter plot
# ---------------------------------------------------------------------------

def plot_encounter_closeup(game, filename):
    """画只包含接敌格及其邻格的特写图。若 contact_hexes 为空则退化为 plot_state。"""
    if not game.contact_hexes:
        plot_state(game, filename)
        return

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon, Circle
    except ImportError:
        raise RuntimeError("matplotlib not installed; pip install matplotlib")

    # 计算包围盒:所有接敌格中心 + 邻格 的像素范围
    all_hexes = set(game.contact_hexes)
    for ch in game.contact_hexes:
        for d in NEIGH:
            all_hexes.add(hex_neighbour(ch, d))

    pts = [hex_center_xy(*h) for h in all_hexes]
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    margin = HEX_SIDE * 1.5
    x_min, x_max = min(xs) - margin, max(xs) + margin
    y_min, y_max = min(ys) - margin, max(ys) + margin

    active = [f for f in game.fleets.values() if f.is_active(game.current_substep)]

    # grid
    r_lo = int(math.floor(y_min / (HEX_SIDE * _S3))) - 1
    r_hi = int(math.ceil(y_max / (HEX_SIDE * _S3))) + 1
    fig, ax = plt.subplots(figsize=(8, 7))
    for r in range(r_lo, r_hi + 1):
        q_lo = int(math.floor(x_min / HEX_SIDE - r / 2.0)) - 1
        q_hi = int(math.ceil(x_max / HEX_SIDE - r / 2.0)) + 1
        for q in range(q_lo, q_hi + 1):
            cx, cy = hex_center_xy(q, r)
            if not (x_min <= cx <= x_max and y_min <= cy <= y_max): continue
            in_contact = (q, r) in game.contact_hexes
            ec = '#a0a0a0' if in_contact else '#d3d3d3'
            lw = 1.0 if in_contact else 0.5
            fc = '#ffffcc' if in_contact else 'none'
            ax.add_patch(Polygon(_hex_corners(cx, cy), closed=True,
                                 facecolor=fc, edgecolor=ec, linewidth=lw))
            ax.text(cx, cy, display_cell(q, r), ha='center', va='center',
                    fontsize=7, color='#808080')

    colors = {'GB': '#a32020', 'GE': '#1f4e8a'}
    for f in active:
        col = colors[f.side]
        for _, (sx, sy) in f.ship_positions(game.current_substep):
            ax.plot(sx, sy, 'o', color=col, markersize=6,
                    markeredgecolor='black', markeredgewidth=0.5)
            ax.add_patch(Circle((sx, sy), game.visibility, fill=False,
                                edgecolor=col, alpha=0.18, linewidth=0.8, linestyle=':'))
        lx, ly = f.lead_xy(game.current_substep)
        ax.annotate(f"{f.name}\n{f.speed}kn", (lx, ly),
                    textcoords='offset points', xytext=(10, -4),
                    fontsize=9, color=col, weight='bold')

    rep = game.last_report
    show_enc = rep and rep['substep'] == game.current_substep
    if show_enc and rep['encounters']:
        e = rep['encounters'][0]
        mx = (e['gb_xy_contact'][0] + e['ge_xy_contact'][0]) / 2
        my = (e['gb_xy_contact'][1] + e['ge_xy_contact'][1]) / 2
        ax.plot(mx, my, 'X', color='gold', markersize=20,
                markeredgecolor='black', markeredgewidth=1.2, zorder=5)
        ax.annotate(f"CONTACT\n{game.clock(round(e['contact_sub']))}", (mx, my),
                    textcoords='offset points', xytext=(14, 14), fontsize=10,
                    weight='bold', bbox=dict(boxstyle='round,pad=0.3', fc='gold', alpha=0.85))

    ax.set_xlim(x_min, x_max); ax.set_ylim(y_min, y_max)
    ax.set_aspect('equal'); ax.invert_yaxis()
    ax.set_title(f"Encounter Close-up — {game.clock(game.current_substep)} "
                 f"(sub{game.current_substep})   vis={game.visibility:.0f} yd   GB=red GE=blue")
    ax.set_xticks([]); ax.set_yticks([])
    plt.tight_layout(); plt.savefig(filename, dpi=110, bbox_inches='tight'); plt.close(fig)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def run_demo(g, seed=None, max_turns=30, frame_prefix='demo'):
    g.fleets.clear(); g.current_substep = 0; g.last_report = None
    g.rng = random.Random(seed); g.visibility = DEFAULT_VISIBILITY
    rng = g.rng
    g.add_fleet("GB1", "GB", 0, f"{rng.randint(-3,1)},{rng.randint(-2,2)}", "E", 18, 4)
    g.add_fleet("GE1", "GE", 0, f"{rng.randint(3,7)},{rng.randint(3,7)}", "W", 18, 3)

    def attracted_schedule(name, target_name, turn):
        """给 name 队设定朝 target_name 偏置的随机走路径;pull 随回合递增。"""
        f = g._get(name)
        target_f = g._get(target_name)
        speed = rng.choice([12, 18, 24])
        pull = min(0.85, 0.1 + 0.06 * turn)
        cur = xy_to_hex(*f.lead_xy(g.current_substep))
        target_hex = xy_to_hex(*target_f.lead_xy(g.current_substep))
        path = attracted_walk_path(cur, target_hex, speed, rng, prev_dir=f.course, pull=pull)
        if len(path) == HEX_PER_CYCLE[speed]:
            try:
                g.schedule(name, speed, [display_cell(*h) for h in path])
            except Exception:
                pass
        else:
            try:
                g.randwalk(name, speed)
            except Exception:
                pass

    # Initial schedules
    try: attracted_schedule("GB1", "GE1", 0)
    except Exception: pass
    try: attracted_schedule("GE1", "GB1", 0)
    except Exception: pass

    files = [f"{frame_prefix}_t00.png"]; plot_state(g, files[0])
    for t in range(1, max_turns + 1):
        encs = g.step_turn()
        fn = f"{frame_prefix}_t{t:02d}.png"; plot_state(g, fn); files.append(fn)
        if encs:
            e = encs[0]
            print(f"  demo: contact {g.clock(round(e['contact_sub']))} after {len(files)-1} frames")
            return files
        for n in list(g.fleets):
            if not g.fleets[n].scheduled:
                other = "GE1" if n == "GB1" else "GB1"
                if other in g.fleets:
                    try: attracted_schedule(n, other, t)
                    except Exception: pass
                else:
                    try: g.randwalk(n, rng.choice([12, 18, 24]))
                    except Exception: pass
    print(f"  demo: no contact in {max_turns} turns")
    return files


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

HELP = """\
Commands
--------
  new <name> <GB|GE> <activated_turn> <cell> <course> <speed> <n_ships>
  delete <name>
  relocate <name> <cell> <course> <speed>
  course <name> <course> [speed]              (no active schedule)
  schedule <name> <speed> <cell> <cell> ...   (2/3/4 waypoints; turns & 180 OK)
  clear <name>                                cancel a schedule, keep position
  randwalk <name> [speed]
  formation <name> <ahead|abreast|echelon> [right|left] [absolute|relative] [deg]
  replay <turn>                               restore board to saved turn snapshot
  step                                        advance 60 min, detect contact
  list
  vis <yards>                                 0..36000 (cap = 1 hex width)
  time <HHMM>                                 set clock at substep 0 (default 0000)
  plot [file.png]
  demo [seed] [max_turns]
  save <file> / load <file>
  help / quit

Cell names: letter-number  e.g. A13  Z5  DD-1  (or axial q,r for developers)
Courses:   E NE NW W SW SE
Speeds:    12 / 18 / 24 kn  (= 2 / 3 / 4 hex per 3-turn cycle)
"""


class QuitSignal(Exception):
    pass


def run_command(game, line):
    """执行一条命令文本(print 输出)。退出类命令抛 QuitSignal。"""
    if not line.strip():
        return
    game.journal.record_command(game.start_minute + game.current_substep * 10, line)
    try:
        parts = shlex.split(line)
    except ValueError as e:
        print(f"  parse error: {e}")
        return
    cmd, args = parts[0].lower(), parts[1:]
    g = game  # 现有分支用的是变量名 g;保持一致以便直接移动
    if cmd in ('quit', 'exit', 'q'):
        raise QuitSignal()
    elif cmd in ('help', '?'): print(HELP)
    elif cmd == 'new':
        name, side, act, hx, crs, spd, n = args
        g.add_fleet(name, side.upper(), int(act), hx, crs.upper(), int(spd), int(n))
        print(f"  ok: {name!r} created")
    elif cmd == 'delete':
        g.delete_fleet(args[0]); print(f"  ok: deleted {args[0]!r}")
    elif cmd == 'relocate':
        name, hx, crs, spd = args
        g.relocate(name, hx, crs.upper(), int(spd)); print(f"  ok: relocated {name!r}")
    elif cmd == 'course':
        spd = int(args[2]) if len(args) > 2 else None
        g.course_change(args[0], args[1].upper(), spd); print("  ok: course changed")
    elif cmd == 'clear':
        ok = g.clear_schedule(args[0])
        print(f"  ok: schedule cleared" if ok else "  (no active schedule)")
    elif cmd == 'schedule':
        name = args[0]; spd = int(args[1]); path = args[2:]
        g.schedule(name, spd, path)
        print(f"  ok: {name!r} sched {spd}kn via {' '.join(path)}")
    elif cmd == 'randwalk':
        name = args[0]; spd = int(args[1]) if len(args) > 1 else None
        path = g.randwalk(name, spd)
        print(f"  ok: {name!r} randwalk → {' '.join(display_cell(*h) for h in path)}")
    elif cmd == 'formation':
        # formation <name> <ahead|abreast|echelon> [right|left] [absolute|relative] [echelon_deg]
        name = args[0]
        f = g._get(name)
        f.formation_kind = args[1].lower()
        if len(args) > 2: f.deploy = args[2].lower()
        if len(args) > 3: f.pos_mode = args[3].lower()
        if len(args) > 4: f.echelon_deg = float(args[4])
        if f.pos_mode == formation.ABS_MODE:
            f.layout_heading = DIRVEC[f.course]
        print(f"  ok: {name!r} formation {f.formation_kind}/{f.pos_mode}")
    elif cmd == 'replay':
        g.replay_to(int(args[0])); print(f"  ok: replayed to turn {args[0]}")
        print(g.list_status())
    elif cmd == 'list': print(g.list_status())
    elif cmd == 'vis':
        v = float(args[0])
        if v > MAX_VISIBILITY:
            print(f"  warning: {v:.0f} > 1 hex ({MAX_VISIBILITY:.0f}); clamping"); v = MAX_VISIBILITY
        g.visibility = v; print(f"  ok: visibility = {v:.0f} yd ({v/HEX_SIDE:.2f} hex)")
    elif cmd == 'time':
        g.start_minute = timekeep.parse_time(args[0])
        print(f"  ok: clock starts {g.datestr(0)}")
    elif cmd == 'save':
        g.save(args[0]); print(f"  ok: saved {args[0]!r}")
    elif cmd == 'load':
        g.load(args[0]); print(f"  ok: loaded {args[0]!r}")
        print(g.list_status())
    elif cmd == 'plot':
        fn = args[0] if args else 'board.png'; plot_state(g, fn); print(f"  ok: saved {fn}")
    elif cmd == 'demo':
        seed = int(args[0]) if args else None
        mt = int(args[1]) if len(args) > 1 else 30
        run_demo(g, seed=seed, max_turns=mt)
    elif cmd == 'step':
        encs = g.step_turn()
        if not encs:
            print(f"  → T{g.current_turn} sub{g.current_substep} {g.datestr(g.current_substep)}, no contact")
            print(g.list_status())
        else:
            print(f"\n  ╔══ ENCOUNTER (pre-contact, frozen) ══════════════")
            print(f"  ║  T{g.current_turn} sub{g.current_substep} {g.datestr(g.current_substep)}   vis={g.visibility:.0f} yd")
            print(f"  ╚══════════════════════════════════════════════════")
            for i, e in enumerate(encs, 1):
                print(f"\n  contact{i}: {e['gb']} ⟷ {e['ge']}")
                # center micro-coordinates (formation reference point, spec §3.3)
                print(f"    {e['gb']:<6} center {micro_str(*e['gb_xy_roll'])}")
                print(f"    {e['ge']:<6} center {micro_str(*e['ge_xy_roll'])}")
                print(f"    closest pair now: {e['dist_roll']:.0f} yd (>= vis: clean state)")
                print(f"    [aux] projected contact {g.clock(round(e['contact_sub']))} "
                      f"(+{(e['contact_sub']-g.current_substep)*10:.1f} min), dist = vis:")
                print(f"          {e['gb']} center {micro_str(*e['gb_xy_contact'])}")
                print(f"          {e['ge']} center {micro_str(*e['ge_xy_contact'])}")
            print("\n  Schedules HALTED.  (post-contact state machine: v5)\n")
    else:
        print(f"  unknown command: {cmd!r}")


PLAYER_COMMANDS = {'new', 'relocate', 'course', 'clear', 'schedule', 'randwalk', 'formation'}


def authorize_player_command(game, side, line):
    """裁判机:判断某一方是否有权执行该命令。返回 (ok, reason)。
    只允许作用于己方的玩家命令;查询/全局命令(list/step/demo/save/load/plot/replay/vis/time)
    属裁判,客户端拒绝(也避免 output 泄漏敌方)。"""
    try:
        parts = shlex.split(line)
    except ValueError:
        return False, "parse error"
    if not parts:
        return False, "empty command"
    cmd, args = parts[0].lower(), parts[1:]
    if cmd not in PLAYER_COMMANDS:
        return False, f"'{cmd}' is referee-only for players"
    if cmd == 'new':
        if len(args) >= 2 and args[1].upper() == side:
            return True, ""
        return False, "cannot create a fleet for the other side"
    name = args[0] if args else ""
    f = game.fleets.get(name)
    if f is not None and f.side != side:
        return False, "not your fleet"
    return True, ""


def execute_command(game, line):
    """像 run_command,但捕获输出为字符串返回(供服务器用)。QuitSignal -> 返回 '__QUIT__'。"""
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            run_command(game, line)
    except QuitSignal:
        return "__QUIT__"
    return buf.getvalue()


def main():
    g = Game()
    print("Jutland Fleet Search & Encounter — v5")
    print("Type 'help' for commands.\n")
    while True:
        try:
            line = input(f"[T{g.current_turn} sub{g.current_substep} "
                         f"{g.datestr(g.current_substep)}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); break
        if not line:
            continue
        try:
            run_command(g, line)
        except QuitSignal:
            break
        except Exception as e:
            print(f"  error: {e}")


if __name__ == '__main__':
    main()
