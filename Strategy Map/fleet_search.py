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

import json
import math
import random
import re
import shlex
from dataclasses import dataclass, field, asdict
import formation


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEX_SIDE = 36000.0                  # flat-to-flat (= 1 hex width, = neighbour spacing)
HEX_SIZE = HEX_SIDE / math.sqrt(3)  # centre-to-vertex
APOTHEM = HEX_SIDE / 2.0            # centre-to-edge-midpoint
STEP_YARDS_PER_KNOT = 36000.0 / 108  # = 333.33 -> 18kn covers exactly 1 hex / 6 substeps
DEFAULT_SPACING = 500.0
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


def micro_str(x, y):
    h, edge, dist = micro_position(x, y)
    if edge is None:
        return f"hex{hex_name(*h)} at centre"
    return f"hex{hex_name(*h)}  {dist:.0f} yd from centre → {edge} edge"


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


@dataclass
class Fleet:
    name: str
    side: str
    activated_turn: int
    anchor_xy: tuple          # exact (x, y); NOT snapped to a centre
    anchor_substep: int
    course: str
    speed: int
    ships: list = field(default_factory=list)
    scheduled: bool = False
    schedule_end_substep: float = 0.0
    waypoints: list = field(default_factory=list)   # axial hexes excl. start
    display_history: list = field(default_factory=list)  # [(substep, x, y)]
    formation_kind: str = formation.LINE_AHEAD
    spacing: float = DEFAULT_SPACING
    deploy: str = "right"
    echelon_deg: float = 45.0
    pos_mode: str = formation.REL_MODE
    layout_heading: tuple = None     # 绝对模式布局时航向;None=用当前航向

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

    def ship_positions(self, substep):
        if self.formation_kind == formation.LINE_AHEAD:
            # 单纵:保留 v4 沿航迹鱼贯(turn in succession)
            lead_a = self._arc_at(substep)
            return [(s.name, self._xy_at_arc(lead_a - i * self.spacing))
                    for i, s in enumerate(self.ships)]
        # 其它队形:中心(沿航迹参考点)+ 队形几何
        center = self.lead_xy(substep)
        heading = DIRVEC[self.course]
        offs = formation.ship_offsets(self.formation_kind, len(self.ships),
                                      self.spacing, self.deploy, self.echelon_deg)
        if self.pos_mode == formation.REL_MODE:
            map_offs = formation.to_map_offsets(heading, offs)
        else:
            lh = self.layout_heading if self.layout_heading is not None else heading
            map_offs = formation.to_map_offsets(lh, offs)
        pts = formation.place_map(center, map_offs)
        return [(s.name, p) for s, p in zip(self.ships, pts)]


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
        self.rng = random.Random()

    @property
    def current_turn(self):
        return self.current_substep // 6

    def clock(self, substep):
        return hhmm(self.start_minute + substep * 10)

    # --- fleet ops ---

    def add_fleet(self, name, side, activated, hex_str, course, speed, n):
        if name in self.fleets: raise ValueError(f"fleet {name!r} exists")
        if side not in VALID_SIDES: raise ValueError("side must be GB or GE")
        if course not in NEIGH: raise ValueError(f"course in {DIRECTION_LIST}")
        if speed not in VALID_SPEEDS: raise ValueError(f"speed in {VALID_SPEEDS}")
        if n < 1: raise ValueError("need >= 1 ship")
        h = parse_hex(hex_str)
        f = Fleet(name=name, side=side, activated_turn=activated,
                  anchor_xy=hex_center_xy(*h), anchor_substep=activated * 6,
                  course=course, speed=speed,
                  ships=[Ship(f"{name}-{i+1}") for i in range(n)])
        f.display_history.append((activated * 6, *f.anchor_xy))
        self.fleets[name] = f

    def delete_fleet(self, name):
        if name not in self.fleets: raise KeyError(name)
        del self.fleets[name]

    def relocate(self, name, hex_str, course, speed):
        f = self._get(name)
        if course not in NEIGH: raise ValueError("bad course")
        if speed not in VALID_SPEEDS: raise ValueError("bad speed")
        f.anchor_xy = hex_center_xy(*parse_hex(hex_str))
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
        wps = [parse_hex(h) for h in hex_strs]
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
        self.schedule(name, speed, [hex_name(*h) for h in path])
        return path

    def _get(self, name):
        if name not in self.fleets: raise KeyError(f"no fleet {name!r}")
        return self.fleets[name]

    # --- detection ---

    def _cross_pairs(self, sub):
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
        for offset in range(1, 7):
            sub = self.current_substep + offset
            for f in self.fleets.values():
                if f.is_active(sub):
                    f.display_history.append((sub, *f.lead_xy(sub)))
            pairs = self._cross_pairs(sub)
            hits = [(d, fa, fb) for (d, fa, fb) in pairs if d < self.visibility]
            if hits:
                return self._resolve_encounter(sub)
        self.current_substep += 6
        for f in self.fleets.values():
            if f.scheduled and self.current_substep >= f.schedule_end_substep:
                self._end_schedule(f)
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
        return encounters

    # --- reporting ---

    def status_line(self, f):
        if not f.is_active(self.current_substep):
            return f"  {f.name:<12} [{f.side}] inactive (T{f.activated_turn})"
        lx, ly = f.lead_xy(self.current_substep)
        micro = micro_str(lx, ly)
        if f.scheduled:
            remain = max(0.0, f.schedule_end_substep - self.current_substep)
            end = hex_name(*f.waypoints[-1]) if f.waypoints else "?"
            st = f"sched→{end} ({remain:.0f}st)"
        else:
            st = "free"
        return (f"  {f.name:<12} [{f.side}] {micro}  course={f.course} "
                f"speed={f.speed}kn ships={len(f.ships)} {st}")

    def list_status(self):
        if not self.fleets: return "  (no fleets)"
        return "\n".join(self.status_line(f)
                         for f in sorted(self.fleets.values(), key=lambda x: (x.side, x.name)))

    # --- save / load (JSON: fleet state + clock/substep/visibility; no RNG seed) ---

    @staticmethod
    def _fleet_to_dict(f):
        return {
            'name': f.name, 'side': f.side, 'activated_turn': f.activated_turn,
            'anchor_xy': list(f.anchor_xy), 'anchor_substep': f.anchor_substep,
            'course': f.course, 'speed': f.speed,
            'ships': [s.name for s in f.ships],
            'scheduled': f.scheduled, 'schedule_end_substep': f.schedule_end_substep,
            'waypoints': [list(w) for w in f.waypoints],          # tuples -> lists
            'display_history': [list(h) for h in f.display_history],
        }

    @staticmethod
    def _fleet_from_dict(d):
        # tuples matter: waypoints/anchor feed hex math & == comparisons.
        return Fleet(
            name=d['name'], side=d['side'], activated_turn=d['activated_turn'],
            anchor_xy=tuple(d['anchor_xy']), anchor_substep=d['anchor_substep'],
            course=d['course'], speed=d['speed'],
            ships=[Ship(n) for n in d['ships']],
            scheduled=d['scheduled'], schedule_end_substep=d['schedule_end_substep'],
            waypoints=[tuple(w) for w in d['waypoints']],
            display_history=[tuple(h) for h in d['display_history']],
        )

    def to_dict(self):
        return {
            'version': 4,
            'current_substep': self.current_substep,
            'visibility': self.visibility,
            'start_minute': self.start_minute,
            'fleets': [self._fleet_to_dict(f) for f in self.fleets.values()],
        }

    def load_dict(self, data):
        self.current_substep = data['current_substep']
        self.visibility = data['visibility']
        self.start_minute = data.get('start_minute', 0)
        self.last_report = None
        self.fleets = {f.name: f for f in (self._fleet_from_dict(d) for d in data['fleets'])}

    def save(self, filename):
        with open(filename, 'w', encoding='utf-8') as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)

    def load(self, filename):
        with open(filename, 'r', encoding='utf-8') as fh:
            self.load_dict(json.load(fh))


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
# Demo
# ---------------------------------------------------------------------------

def run_demo(g, seed=None, max_turns=30, frame_prefix='demo'):
    g.fleets.clear(); g.current_substep = 0; g.last_report = None
    g.rng = random.Random(seed); g.visibility = DEFAULT_VISIBILITY
    rng = g.rng
    g.add_fleet("GB1", "GB", 0, f"{rng.randint(-3,1)},{rng.randint(-2,2)}", "E", 18, 4)
    g.add_fleet("GE1", "GE", 0, f"{rng.randint(3,7)},{rng.randint(3,7)}", "W", 18, 3)

    def reroll(n):
        try: g.randwalk(n, rng.choice([12, 18, 24]))
        except Exception: pass
    reroll("GB1"); reroll("GE1")

    files = [f"{frame_prefix}_t00.png"]; plot_state(g, files[0])
    for t in range(1, max_turns + 1):
        encs = g.step_turn()
        fn = f"{frame_prefix}_t{t:02d}.png"; plot_state(g, fn); files.append(fn)
        if encs:
            e = encs[0]
            print(f"  demo: contact {g.clock(round(e['contact_sub']))} after {len(files)-1} frames")
            return files
        for n in list(g.fleets):
            if not g.fleets[n].scheduled: reroll(n)
    print(f"  demo: no contact in {max_turns} turns")
    return files


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

HELP = """\
Commands
--------
  new <name> <GB|GE> <activated_turn> <q,r> <course> <speed> <n_ships>
  delete <name>
  relocate <name> <q,r> <course> <speed>
  course <name> <course> [speed]              (no active schedule)
  schedule <name> <speed> <q,r> <q,r> ...     (2/3/4 waypoints; turns & 180 OK)
  clear <name>                                cancel a schedule, keep position
  randwalk <name> [speed]
  step                                        advance 60 min, detect contact
  list
  vis <yards>                                 0..36000 (cap = 1 hex width)
  time <HHMM>                                 set clock at substep 0 (default 0000)
  plot [file.png]
  demo [seed] [max_turns]
  save <file> / load <file>
  help / quit

Hex names: axial  q,r  (negatives ok), e.g.  0,0   3,-2   -1,5
Courses:   E NE NW W SW SE
Speeds:    12 / 18 / 24 kn  (= 2 / 3 / 4 hex per 3-turn cycle)
"""


def main():
    g = Game()
    print("Jutland Fleet Search & Encounter — MVP v4")
    print("Type 'help' for commands.\n")
    while True:
        try:
            line = input(f"[{g.clock(g.current_substep)} sub{g.current_substep}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); break
        if not line: continue
        try: parts = shlex.split(line)
        except ValueError as e:
            print(f"  parse error: {e}"); continue
        cmd, args = parts[0].lower(), parts[1:]
        try:
            if cmd in ('quit', 'exit', 'q'): break
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
                print(f"  ok: {name!r} randwalk → {' '.join(hex_name(*h) for h in path)}")
            elif cmd == 'list': print(g.list_status())
            elif cmd == 'vis':
                v = float(args[0])
                if v > MAX_VISIBILITY:
                    print(f"  warning: {v:.0f} > 1 hex ({MAX_VISIBILITY:.0f}); clamping"); v = MAX_VISIBILITY
                g.visibility = v; print(f"  ok: visibility = {v:.0f} yd ({v/HEX_SIDE:.2f} hex)")
            elif cmd == 'time':
                t = args[0]; g.start_minute = int(t[:2]) * 60 + int(t[2:])
                print(f"  ok: clock starts {g.clock(0)}")
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
                    print(f"  → {g.clock(g.current_substep)} sub{g.current_substep}, no contact")
                    print(g.list_status())
                else:
                    print(f"\n  ╔══ ENCOUNTER (pre-contact, frozen) ══════════════")
                    print(f"  ║  {g.clock(g.current_substep)}   vis={g.visibility:.0f} yd")
                    print(f"  ╚══════════════════════════════════════════════════")
                    for i, e in enumerate(encs, 1):
                        print(f"\n  contact{i}: {e['gb']} ⟷ {e['ge']}")
                        print(f"    {e['gb']:<6} {micro_str(*e['gb_xy_roll'])}")
                        print(f"    {e['ge']:<6} {micro_str(*e['ge_xy_roll'])}")
                        print(f"    closest pair now: {e['dist_roll']:.0f} yd (>= vis: clean state)")
                        print(f"    [aux] projected contact {g.clock(round(e['contact_sub']))} "
                              f"(+{(e['contact_sub']-g.current_substep)*10:.1f} min), dist = vis:")
                        print(f"          {e['gb']} {micro_str(*e['gb_xy_contact'])}")
                        print(f"          {e['ge']} {micro_str(*e['ge_xy_contact'])}")
                    print("\n  Schedules HALTED.  (post-contact state machine: v5)\n")
            else:
                print(f"  unknown command: {cmd!r}")
        except Exception as e:
            print(f"  error: {e}")


if __name__ == '__main__':
    main()
