# v6 Phase A — Three-Layer Skeleton (Fleet / Formation / Ship) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lift the single-layer `Fleet` into a three-layer `Fleet → Formation → Ship` model with a unified two-stage geometry pipeline and version=6 serialization (upgrading old saves to a single zero-offset Formation), while every existing regression test passes unchanged (zero regression).

**Architecture:** Add `Ship` (leaf with `name`/`index`) and `Formation` (offset + kind + two knobs `turning`/`relative` + lazy `frozen_offset_xy`) classes in `fleet_search.py` next to `Fleet`, reusing the pure geometry helpers already in `formation.py`. `Fleet` gains `initial_course` and a `formations` list and is forced to hold ≥1 Formation; the old per-fleet formation fields (`formation_kind`, `pos_mode`, `layout_heading`, `spacing`, `deploy`, `echelon_deg`) become **backward-compat properties that delegate to the primary Formation (index 0)** so existing tests and the `formation`/`new` CLI keep working byte-for-byte. `ship_positions(sub)` is rewritten as one two-stage pipeline (Fleet center → per-Formation rotated offset → per-Ship follow-arc-rollback / together-rigid) but keeps its `[(name, xy), ...]` return shape so `_cross_pairs`, plotting, and double-blind are untouched. `to_dict` bumps `version:6` with nested `formations`; `_fleet_from_dict` branches on presence of `formations` and runs `upgrade_v5_fleet` for old saves.

**Tech Stack:** Python 3.10+ stdlib only; `unittest` (no pytest); `matplotlib` is NOT imported by any test in this phase. Geometry helpers reused from `formation.py` (`ship_offsets`, `to_map_offsets`, `place_map`).

---

## Locked conventions honored in this phase (spec §9)

- Visibility cap stays 36000, default 20000 — **untouched** (encounter path not modified, only traversal depth).
- Encounter detection still rolls back to the `>vis` substep S−1 and is cross-side only — **untouched**.
- Axial neighbour increments / pixel mapping via `DIRVEC` + `hex_center_xy` — reused, never redefined.
- 18 kn = 6 substeps/hex via `STEP_YARDS_PER_KNOT = 36000/108` — reused in `lead_xy`.
- Positions stored as exact `(x, y)`, never snapped to a hex center.
- `anchor_substep` may be `float` — preserved (no change to its type or arithmetic).
- Cross-side only encounter granularity stays at the Ship level.

## Key module facts the implementer must know (verified against current source)

- `fleet_search.py` constants: `HEX_SIDE = 36000.0`, `_S3 = math.sqrt(3)/2`, `STEP_YARDS_PER_KNOT = 36000/108`, `DEFAULT_SPACING = 500.0`.
- `DIRVEC` is a dict of **unit** vectors, +x East, +y South: `E=(1,0)`, `W=(-1,0)`, `NE=(0.5,-_S3)`, `NW=(-0.5,-_S3)`, `SE=(0.5,_S3)`, `SW=(-0.5,_S3)`. (`NE`: 0.5²+_S3² = 0.25+0.75 = 1.0, unit length.)
- `formation.py` left-vs-right: `to_map_offsets(heading, offsets)` uses **starboard** normal `(-uy, ux)`; `ship_offsets` cross axis is `+ = starboard` with `deploy="right"` → `sign=+1`. The spec's `left_hat=(uy,-ux)` is the negative of this; keep all internal offset math going through `formation.py` so signs stay self-consistent.
- Current `Fleet.ship_positions` (lines 302–319) has two branches: LINE_AHEAD → arc-rollback rigid-along-track (4a); else → `lead_xy` center + `ship_offsets`/`to_map_offsets`/`place_map` with `pos_mode` choosing `course` (REL) vs `layout_heading` (ABS) (4b).
- `Game.add_fleet` (lines 351–363) builds `Fleet(...)` with `ships=[Ship(f"{name}-{i+1}") ...]` and appends a `display_history` entry.
- `_fleet_to_dict` (620–634) / `_fleet_from_dict` (636–654) carry the six legacy formation fields; `to_dict` (656–665) writes `version: 5`.
- Existing tests that MUST keep passing unchanged read/mutate legacy fields directly: `tests/test_formation_integration.py` (sets `f.formation_kind`, `f.pos_mode`), `tests/test_serialization.py` (sets/asserts all six fields + roundtrip), `tests/test_fleet_search.py` (reads `len(f.ships)`).
- The `formation` CLI command (lines 1047–1057) and `add_fleet` write legacy fields — they must continue to work via the delegating properties (no CLI edits in Phase A).

## File structure for this phase

- **Modify** `fleet_search.py`:
  - Replace `Ship` dataclass (238–241) with a richer `Ship` (`name`, `index`).
  - Add a `Formation` class after `Ship`.
  - Rework `Fleet` (243–319): add `initial_course` + `formations`; convert six legacy formation fields to delegating properties; move nothing out of `Fleet` for the kinematics (lead_xy stays on Fleet); rewrite `ship_positions` as the two-stage pipeline.
  - Update `add_fleet` (351–363) to build a default zero-offset single Formation.
  - Update serialization: `_fleet_to_dict` (620–634), `_fleet_from_dict` (636–654), `to_dict` version (658), add `upgrade_v5_fleet`.
- **Create** `tests/test_formation_layers.py`.
- **Do NOT touch** `formation.py` (reused as-is), `journal.py`, `orderparse.py` (Phase B), `course_change`, `step_turn`, `_resolve_encounter` (those are Phases B/C/D).

---

## Task 1: Richer `Ship` (name + index) with backward-compatible construction

**Files:**
- Modify: `fleet_search.py:238-241` (the `Ship` dataclass)
- Test: `tests/test_formation_layers.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_formation_layers.py` with:

```python
import math
import unittest
import fleet_search as fs
import formation as fm


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class TestShipLeaf(unittest.TestCase):
    def test_ship_has_name_and_index(self):
        s = fs.Ship("GB1-1", 0)
        self.assertEqual(s.name, "GB1-1")
        self.assertEqual(s.index, 0)

    def test_ship_index_defaults_to_zero(self):
        s = fs.Ship("solo")
        self.assertEqual(s.index, 0)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_formation_layers -v`
Expected: FAIL — `TypeError: __init__() takes 2 positional arguments but 3 were given` on `test_ship_has_name_and_index` (current `Ship` only has `name`).

- [ ] **Step 3: Write minimal implementation**

Replace lines 238–241 in `fleet_search.py`:

```python
@dataclass
class Ship:
    name: str
    index: int = 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_formation_layers -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add tests/test_formation_layers.py fleet_search.py
git commit -m "feat(v6-A): Ship leaf gains index field (default 0)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `Formation` class + constants (offset, kind, knobs, lazy frozen offset)

**Files:**
- Modify: `fleet_search.py` — add `Formation` class immediately after the `Ship` dataclass (after line 241), and add knob constants near the existing formation constant usage (top of file, after the `import formation` line / near `DEFAULT_SPACING`).
- Test: `tests/test_formation_layers.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_formation_layers.py` (inside the module, before `if __name__`):

```python
class TestFormationClass(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(fs.TURN_FOLLOW, "follow")
        self.assertEqual(fs.TURN_TOGETHER, "together")
        self.assertEqual(fs.REL_ABSOLUTE, "absolute")
        self.assertEqual(fs.REL_RELATIVE, "relative")

    def test_default_formation(self):
        fo = fs.Formation(name="d0", ships=[fs.Ship("a", 0), fs.Ship("b", 1)])
        self.assertEqual(fo.offset_fwd, 0.0)
        self.assertEqual(fo.offset_left, 0.0)
        self.assertEqual(fo.kind, fm.LINE_AHEAD)
        self.assertEqual(fo.spacing, 500.0)
        self.assertEqual(fo.deploy, "right")
        self.assertEqual(fo.echelon_deg, 45.0)
        self.assertEqual(fo.turning, fs.TURN_FOLLOW)
        self.assertEqual(fo.relative, fs.REL_RELATIVE)
        self.assertIsNone(fo.frozen_offset_xy)
        self.assertFalse(fo.is_single)

    def test_single_when_one_ship(self):
        fo = fs.Formation(name="solo", ships=[fs.Ship("only", 0)])
        self.assertTrue(fo.is_single)

    def test_single_when_kind_single(self):
        fo = fs.Formation(name="d", ships=[fs.Ship("a", 0), fs.Ship("b", 1)],
                          kind=fs.KIND_SINGLE)
        self.assertTrue(fo.is_single)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_formation_layers.TestFormationClass -v`
Expected: FAIL — `AttributeError: module 'fleet_search' has no attribute 'TURN_FOLLOW'`.

- [ ] **Step 3: Write minimal implementation**

Add the knob constants near the top of `fleet_search.py`, immediately after the line `DEFAULT_SPACING = 500.0` (line 51):

```python
# v6 three-layer formation knobs
TURN_FOLLOW = "follow"
TURN_TOGETHER = "together"
REL_ABSOLUTE = "absolute"
REL_RELATIVE = "relative"
KIND_AHEAD = formation.LINE_AHEAD       # "ahead"
KIND_ABREAST = formation.LINE_ABREAST   # "abreast"
KIND_ECHELON = formation.ECHELON        # "echelon"
KIND_SINGLE = "single"
```

Add the `Formation` class immediately after the `Ship` dataclass (after `index: int = 0`):

```python
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

    @property
    def is_single(self):
        return len(self.ships) == 1 or self.kind == KIND_SINGLE
```

(`field` and `dataclass` are already imported at the top of the module; confirm the existing `from dataclasses import dataclass, field` import is present — it is, used by `Fleet`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_formation_layers.TestFormationClass -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add tests/test_formation_layers.py fleet_search.py
git commit -m "feat(v6-A): add Formation class and turning/relative/kind constants

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `Fleet` gains `initial_course` + `formations`; legacy fields become delegating properties

This is the zero-regression keystone: existing tests mutate/read `f.formation_kind`, `f.pos_mode`, `f.layout_heading`, `f.spacing`, `f.deploy`, `f.echelon_deg`, and `f.ships`. We make these read/write through the primary Formation (index 0) so no test or CLI line changes.

**Files:**
- Modify: `fleet_search.py:243-300` (the `Fleet` dataclass header + helpers; replace the six legacy field declarations 257–262 and add `initial_course` + `formations`; add `primary` + delegating properties; keep `_polyline`/`_arc_at`/`_xy_at_arc`/`lead_xy` unchanged in behavior).
- Modify: `fleet_search.py:351-363` (`add_fleet` builds the default single Formation).
- Test: `tests/test_formation_layers.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_formation_layers.py`:

```python
class TestFleetHoldsFormation(unittest.TestCase):
    def test_add_fleet_creates_single_zero_offset_formation(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 3)
        f = g.fleets["F"]
        self.assertEqual(len(f.formations), 1)
        prim = f.formations[0]
        self.assertEqual(prim.offset_fwd, 0.0)
        self.assertEqual(prim.offset_left, 0.0)
        self.assertEqual(len(prim.ships), 3)
        self.assertEqual([s.index for s in prim.ships], [0, 1, 2])
        self.assertEqual([s.name for s in prim.ships], ["F-1", "F-2", "F-3"])

    def test_initial_course_set_from_course(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "NE", 18, 2)
        self.assertEqual(g.fleets["F"].initial_course, "NE")
        self.assertEqual(g.fleets["F"].course, "NE")

    def test_legacy_ships_property_reads_primary(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 2)
        f = g.fleets["F"]
        self.assertEqual(len(f.ships), 2)
        self.assertEqual([s.name for s in f.ships], ["F-1", "F-2"])

    def test_legacy_formation_kind_delegates(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 2)
        f = g.fleets["F"]
        self.assertEqual(f.formation_kind, fm.LINE_AHEAD)
        f.formation_kind = fm.LINE_ABREAST
        self.assertEqual(f.formations[0].kind, fm.LINE_ABREAST)
        self.assertEqual(f.formation_kind, fm.LINE_ABREAST)

    def test_legacy_pos_mode_maps_to_relative_knob(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 2)
        f = g.fleets["F"]
        # default is line-ahead/relative -> pos_mode relative
        self.assertEqual(f.pos_mode, fm.REL_MODE)
        f.pos_mode = fm.ABS_MODE
        self.assertEqual(f.formations[0].relative, fs.REL_ABSOLUTE)
        self.assertEqual(f.pos_mode, fm.ABS_MODE)

    def test_legacy_spacing_deploy_echelon_layout_heading_delegate(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 2)
        f = g.fleets["F"]
        f.spacing = 700.0
        f.deploy = "left"
        f.echelon_deg = 30.0
        f.layout_heading = (1.0, 0.0)
        prim = f.formations[0]
        self.assertEqual(prim.spacing, 700.0)
        self.assertEqual(prim.deploy, "left")
        self.assertEqual(prim.echelon_deg, 30.0)
        self.assertEqual(f.layout_heading, (1.0, 0.0))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_formation_layers.TestFleetHoldsFormation -v`
Expected: FAIL — `AttributeError: 'Fleet' object has no attribute 'formations'` (and `add_fleet` does not yet build one).

- [ ] **Step 3: Write minimal implementation**

(a) In the `Fleet` dataclass (lines 243–262), **remove** the six legacy field declarations (lines 257–262: `formation_kind`, `spacing`, `deploy`, `echelon_deg`, `pos_mode`, `layout_heading`) and **add** two new fields in their place, plus keep `ships` for construction compatibility. Replace the field block so the dataclass reads:

```python
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
```

(b) Add the `primary` property and the six delegating properties to `Fleet`, placed right after `__post_init__` and before `is_active`:

```python
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
```

Note on `pos_mode`: `formation.ABS_MODE == "absolute" == REL_ABSOLUTE` and `formation.REL_MODE == "relative" == REL_RELATIVE`, so the string values are identical and the delegation is lossless.

Note on `layout_heading`: the legacy field stored the **absolute-mode layout heading vector** (a `(ux,uy)` tuple), NOT a frozen offset. To preserve the exact legacy roundtrip in `test_serialization`, add a plain attribute on `Formation` to carry it. Add to the `Formation` class body (after `frozen_offset_xy`):

```python
    frozen_offset_xy_legacy: tuple = None   # v5 layout_heading carrier (compat only)
```

(c) Update `add_fleet` (lines 351–363) to build ships with indices and a single Formation. Replace the `Fleet(...)` construction:

```python
        ships = [Ship(f"{name}-{i+1}", i) for i in range(n)]
        f = Fleet(name=name, side=side, activated_turn=activated,
                  anchor_xy=hex_center_xy(*h), anchor_substep=activated * 6,
                  course=course, speed=speed, initial_course=course,
                  ships=ships)
        f.display_history.append((activated * 6, *f.anchor_xy))
        self.fleets[name] = f
```

(`__post_init__` consumes the supplied `ships`, sets indices, builds `formations=[Formation(...)]`, and repoints `f.ships` at the primary list — so `len(f.ships)` and `f.ships[i].name` keep working.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_formation_layers.TestFleetHoldsFormation -v`
Expected: PASS (6 tests).

Then run the legacy formation/serialization regressions to confirm delegation works:

Run: `python -m unittest tests.test_formation_integration tests.test_serialization tests.test_fleet_search -v`
Expected: PASS (all existing tests in those modules green; no edits to those files).

- [ ] **Step 5: Commit**

```bash
git add tests/test_formation_layers.py fleet_search.py
git commit -m "feat(v6-A): Fleet holds >=1 Formation; legacy fields delegate to primary

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Rewrite `ship_positions` as the unified two-stage pipeline (interface unchanged)

Replace the two hard-coded branches with: (1) Fleet center via `lead_xy`; (2) per-Formation center = Fleet center + rotated offset (`relative` knob, absolute lazily frozen); (3) per-Formation internal ship positions (`turning` knob: follow=arc-rollback, together=rigid). Returns the SAME flat `[(name, xy), ...]` across all formations so `_cross_pairs`/plot/double-blind are untouched.

**Files:**
- Modify: `fleet_search.py:302-319` (replace `ship_positions`; add private helpers `_formation_center_xy`, `_formation_ship_positions` on `Fleet`).
- Test: `tests/test_formation_layers.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_formation_layers.py`:

```python
class TestTwoStagePipeline(unittest.TestCase):
    def _fleet(self, course="E", n=3, kind=fm.LINE_AHEAD, relative=fs.REL_RELATIVE,
               turning=fs.TURN_FOLLOW, deploy="right"):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", course, 18, n)
        f = g.fleets["F"]
        prim = f.formations[0]
        prim.kind = kind
        prim.relative = relative
        prim.turning = turning
        prim.deploy = deploy
        return f

    def test_in_succession_concrete_coords(self):
        # absolute+follow, course E, sub=6, 18kn -> lead at (36000,0); trailers rollback 500
        f = self._fleet(course="E", n=3, kind=fm.LINE_AHEAD,
                        relative=fs.REL_ABSOLUTE, turning=fs.TURN_FOLLOW)
        ships = dict(f.ship_positions(6))
        self.assertAlmostEqual(ships["F-1"][0], 36000.0, places=3)
        self.assertAlmostEqual(ships["F-1"][1], 0.0, places=3)
        self.assertAlmostEqual(ships["F-2"][0], 35500.0, places=3)
        self.assertAlmostEqual(ships["F-3"][0], 35000.0, places=3)

    def test_zero_offset_single_formation_equals_v4_line_ahead(self):
        # 4a equivalence: relative+follow line-ahead == old LINE_AHEAD arc-rollback
        f = self._fleet(course="E", n=3, kind=fm.LINE_AHEAD,
                        relative=fs.REL_RELATIVE, turning=fs.TURN_FOLLOW)
        got = f.ship_positions(6)
        # reference: arc rollback directly off the fleet polyline
        lead_a = f._arc_at(6)
        for i, (name, xy) in enumerate(got):
            ref = f._xy_at_arc(lead_a - i * 500.0)
            self.assertAlmostEqual(xy[0], ref[0], places=6)
            self.assertAlmostEqual(xy[1], ref[1], places=6)

    def test_zero_offset_single_formation_equals_v4_abreast_relative(self):
        # 4b equivalence: abreast/relative -> together rigid via formation helpers
        f = self._fleet(course="E", n=3, kind=fm.LINE_ABREAST,
                        relative=fs.REL_RELATIVE, turning=fs.TURN_TOGETHER,
                        deploy="right")
        got = f.ship_positions(6)
        center = f.lead_xy(6)
        offs = fm.ship_offsets(fm.LINE_ABREAST, 3, 500.0, "right", 45.0)
        ref = fm.place_map(center, fm.to_map_offsets(fs.DIRVEC["E"], offs))
        for (name, xy), rp in zip(got, ref):
            self.assertAlmostEqual(xy[0], rp[0], places=6)
            self.assertAlmostEqual(xy[1], rp[1], places=6)

    def test_in_succession_turn_point_does_not_move(self):
        # schedule a turn so the polyline bends, trailers turn at the lead's turn point
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 2)
        f = g.fleets["F"]
        f.formations[0].relative = fs.REL_ABSOLUTE
        # waypoints: go E one hex then SE one hex (line ahead, scheduled)
        f.scheduled = True
        f.waypoints = [(1, 0), (1, 1)]
        f.schedule_end_substep = 12.0
        # at sub=6 lead reaches first waypoint center; trailer still behind on first leg (due E)
        ships6 = dict(f.ship_positions(6))
        # trailer F-2 is 500 yd behind along arc -> still on first (E) leg, y==0
        self.assertAlmostEqual(ships6["F-2"][1], 0.0, places=3)

    def test_turn_together_absolute_freezes_spread(self):
        # abreast + together + absolute: after a course change, map spread stays E-W frozen
        f = self._fleet(course="E", n=3, kind=fm.LINE_ABREAST,
                        relative=fs.REL_ABSOLUTE, turning=fs.TURN_TOGETHER,
                        deploy="right")
        before = dict(f.ship_positions(0))
        # spread vector ship2-ship1 in absolute(E) frame -> due south (+y)
        v0 = (before["F-2"][0] - before["F-1"][0], before["F-2"][1] - before["F-1"][1])
        f.course = "SE"          # fleet turns; absolute freezes initial_course=E
        after = dict(f.ship_positions(0))
        v1 = (after["F-2"][0] - after["F-1"][0], after["F-2"][1] - after["F-1"][1])
        self.assertAlmostEqual(v0[0], v1[0], places=6)
        self.assertAlmostEqual(v0[1], v1[1], places=6)

    def test_compass_relative_follows_turn(self):
        # abreast + together + relative: spread rotates with course (mirror of absolute)
        f = self._fleet(course="E", n=3, kind=fm.LINE_ABREAST,
                        relative=fs.REL_RELATIVE, turning=fs.TURN_TOGETHER,
                        deploy="right")
        before = dict(f.ship_positions(0))
        v0 = (before["F-2"][0] - before["F-1"][0], before["F-2"][1] - before["F-1"][1])
        f.course = "SE"
        after = dict(f.ship_positions(0))
        v1 = (after["F-2"][0] - after["F-1"][0], after["F-2"][1] - after["F-1"][1])
        # relative -> spread direction changed (no longer identical)
        self.assertFalse(abs(v0[0] - v1[0]) < 1e-6 and abs(v0[1] - v1[1]) < 1e-6)

    def test_compass_zero_offset_follow_equals_in_succession(self):
        # relative+follow with zero offset == absolute+follow (both pure fleet-polyline rollback)
        fa = self._fleet(course="E", n=3, kind=fm.LINE_AHEAD,
                         relative=fs.REL_RELATIVE, turning=fs.TURN_FOLLOW)
        fb = self._fleet(course="E", n=3, kind=fm.LINE_AHEAD,
                         relative=fs.REL_ABSOLUTE, turning=fs.TURN_FOLLOW)
        for (na, xa), (nb, xb) in zip(fa.ship_positions(6), fb.ship_positions(6)):
            self.assertAlmostEqual(xa[0], xb[0], places=6)
            self.assertAlmostEqual(xa[1], xb[1], places=6)

    def test_offset_compose_then_absolute_freeze(self):
        # GB 4LCS style: offset (fwd=8000, left=10000), initial_course SE, absolute freeze
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "SE", 18, 2)
        f = g.fleets["F"]
        prim = f.formations[0]
        prim.offset_fwd = 8000.0
        prim.offset_left = 10000.0
        prim.relative = fs.REL_ABSOLUTE
        prim.turning = fs.TURN_TOGETHER
        center_before = f._formation_center_xy(prim, 0)
        f.course = "E"           # fleet turns; absolute offset frozen on SE
        center_after = f._formation_center_xy(prim, 0)
        # frozen: formation-center-minus-fleet-center stays constant after the turn
        fc_b = (center_before[0] - f.lead_xy(0)[0], center_before[1] - f.lead_xy(0)[1])
        fc_a = (center_after[0] - f.lead_xy(0)[0], center_after[1] - f.lead_xy(0)[1])
        self.assertAlmostEqual(fc_b[0], fc_a[0], places=6)
        self.assertAlmostEqual(fc_b[1], fc_a[1], places=6)
        self.assertIsNotNone(prim.frozen_offset_xy)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_formation_layers.TestTwoStagePipeline -v`
Expected: FAIL — `AttributeError: 'Fleet' object has no attribute '_formation_center_xy'` and the concrete-coord assertions error because `ship_positions` still uses the old branches (which now read delegated fields but don't honor `offset_fwd/offset_left` or the `turning` knob semantics).

- [ ] **Step 3: Write minimal implementation**

Replace `ship_positions` (current lines 302–319) with the two-stage pipeline and two helpers:

```python
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

    def _offset_to_map(self, fo, course_key):
        """offset_fwd along course + offset_left to port -> map (dx, dy)."""
        fx, fy = DIRVEC[course_key]
        # port normal for +y-south frame: rotate forward +90deg CW visually -> (fy, -fx)
        lx, ly = fy, -fx
        return (fo.offset_fwd * fx + fo.offset_left * lx,
                fo.offset_fwd * fy + fo.offset_left * ly)

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

    @staticmethod
    def _kind_for_offsets(fo):
        # KIND_SINGLE has no formation.ship_offsets entry; treat as a 1-row line-ahead
        return KIND_AHEAD if fo.kind == KIND_SINGLE else fo.kind

    def ship_positions(self, substep):
        out = []
        for fo in self.formations:
            out.extend(self._formation_ship_positions(fo, substep))
        return out
```

Rationale for the `_offset_to_map` sign: spec §3.2 defines `left_hat=(forward.y, -forward.x)`. For `course E` `forward=(1,0)` → `left_hat=(0,-1)` = due north (toward smaller y, the +y-south frame's left/port when heading east). `offset_left>0` therefore places a Formation to port. This is internally consistent and only affects offset Formations (Phase B data); all Phase A zero-offset tests are unaffected.

Note: for zero-offset single Formation, `TURN_FOLLOW + KIND_AHEAD` reproduces the old 4a branch exactly (`base=(0,0)`, arc rollback by `index*spacing` with indices 0..n-1), and `TURN_TOGETHER` (used by the abreast/echelon equivalence test) reproduces 4b exactly (center via `lead_xy`, `ship_offsets`/`to_map_offsets`/`place_map`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_formation_layers.TestTwoStagePipeline -v`
Expected: PASS (8 tests).

Then the full formation/integration regression:

Run: `python -m unittest tests.test_formation tests.test_formation_integration -v`
Expected: PASS. (Note `test_formation_integration.test_default_is_line_ahead_v4_behavior` and `test_line_abreast_via_formation` exercise the same delegated path; they must still pass because zero-offset follow/together reproduce 4a/4b.)

- [ ] **Step 5: Commit**

```bash
git add tests/test_formation_layers.py fleet_search.py
git commit -m "feat(v6-A): unified two-stage ship_positions pipeline (interface unchanged)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Serialization bump to version=6 (nested formations) + read-old-save upgrade

`to_dict` writes `version: 6` with nested `formations`/`ships`. `_fleet_from_dict` branches: has `formations` → read nested; else → `upgrade_v5_fleet` builds a single zero-offset Formation from the old flat fields. Old test_serialization assertions (which read `f.formation_kind` etc.) keep passing via the delegating properties.

**Files:**
- Modify: `fleet_search.py:620-634` (`_fleet_to_dict`), `636-654` (`_fleet_from_dict`), `658` (`to_dict` version), add `upgrade_v5_fleet` near `_fleet_from_dict`.
- Test: `tests/test_formation_layers.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_formation_layers.py`:

```python
class TestSerializationV6(unittest.TestCase):
    def test_to_dict_version_is_6_and_nested(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "1,2", "E", 18, 3)
        d = g.to_dict()
        self.assertEqual(d["version"], 6)
        fd = d["fleets"][0]
        self.assertIn("initial_course", fd)
        self.assertIn("formations", fd)
        self.assertEqual(len(fd["formations"]), 1)
        fo = fd["formations"][0]
        self.assertIn("offset_fwd", fo)
        self.assertIn("turning", fo)
        self.assertIn("relative", fo)
        self.assertEqual([s["index"] for s in fo["ships"]], [0, 1, 2])

    def test_v6_roundtrip_preserves_formation(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "1,2", "SE", 18, 3)
        prim = g.fleets["F"].formations[0]
        prim.kind = fm.LINE_ABREAST
        prim.offset_fwd = 8000.0
        prim.offset_left = 10000.0
        prim.relative = fs.REL_ABSOLUTE
        prim.turning = fs.TURN_TOGETHER
        prim.deploy = "left"
        prim.echelon_deg = 30.0
        g2 = fs.Game()
        g2.load_dict(g.to_dict())
        p2 = g2.fleets["F"].formations[0]
        self.assertEqual(p2.kind, fm.LINE_ABREAST)
        self.assertEqual(p2.offset_fwd, 8000.0)
        self.assertEqual(p2.offset_left, 10000.0)
        self.assertEqual(p2.relative, fs.REL_ABSOLUTE)
        self.assertEqual(p2.turning, fs.TURN_TOGETHER)
        self.assertEqual(p2.deploy, "left")
        self.assertEqual(p2.echelon_deg, 30.0)
        self.assertEqual(g2.fleets["F"].initial_course, "SE")

    def test_load_v5_save_upgrades_to_single_formation(self):
        # craft a legacy v5 fleet dict (no 'formations' key, flat fields)
        v5 = {
            "version": 5,
            "current_substep": 0,
            "visibility": 20000.0,
            "start_minute": 0,
            "state": "SEARCH",
            "contact_hexes": [],
            "fleets": [{
                "name": "F", "side": "GB", "activated_turn": 0,
                "anchor_xy": [0.0, 0.0], "anchor_substep": 0,
                "course": "E", "speed": 18,
                "ships": ["F-1", "F-2", "F-3"],
                "scheduled": False, "schedule_end_substep": 0.0,
                "waypoints": [], "display_history": [[0, 0.0, 0.0]],
                "formation_kind": "abreast", "spacing": 500.0,
                "deploy": "left", "echelon_deg": 30.0,
                "pos_mode": "absolute", "layout_heading": [1.0, 0.0],
            }],
        }
        g = fs.Game()
        g.load_dict(v5)
        f = g.fleets["F"]
        self.assertEqual(len(f.formations), 1)
        prim = f.formations[0]
        self.assertEqual(prim.offset_fwd, 0.0)
        self.assertEqual(prim.offset_left, 0.0)
        self.assertEqual(prim.kind, "abreast")
        self.assertEqual(prim.relative, fs.REL_ABSOLUTE)   # pos_mode absolute
        self.assertEqual(prim.turning, fs.TURN_TOGETHER)   # non-ahead -> together
        self.assertEqual(prim.frozen_offset_xy, (0.0, 0.0))  # absolute -> frozen zero
        self.assertEqual(f.initial_course, "E")            # old save: initial = course
        self.assertEqual(len(f.ships), 3)
        self.assertEqual([s.index for s in f.ships], [0, 1, 2])

    def test_load_v5_line_ahead_upgrades_to_follow(self):
        v5 = {
            "version": 5, "current_substep": 0, "visibility": 20000.0,
            "start_minute": 0, "state": "SEARCH", "contact_hexes": [],
            "fleets": [{
                "name": "F", "side": "GE", "activated_turn": 0,
                "anchor_xy": [0.0, 0.0], "anchor_substep": 0,
                "course": "E", "speed": 18, "ships": ["F-1", "F-2"],
                "scheduled": False, "schedule_end_substep": 0.0,
                "waypoints": [], "display_history": [[0, 0.0, 0.0]],
                "formation_kind": "ahead", "spacing": 500.0,
                "deploy": "right", "echelon_deg": 45.0,
                "pos_mode": "relative", "layout_heading": None,
            }],
        }
        g = fs.Game()
        g.load_dict(v5)
        prim = g.fleets["F"].formations[0]
        self.assertEqual(prim.turning, fs.TURN_FOLLOW)     # ahead -> follow
        self.assertEqual(prim.relative, fs.REL_RELATIVE)
        self.assertIsNone(prim.frozen_offset_xy)           # relative -> not frozen
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_formation_layers.TestSerializationV6 -v`
Expected: FAIL — `test_to_dict_version_is_6_and_nested` fails on `d["version"] == 6` (still 5) and missing `formations` key; the v5-load tests fail because `_fleet_from_dict` has no upgrade branch.

- [ ] **Step 3: Write minimal implementation**

(a) Replace `to_dict` version literal at line 658:

```python
            'version': 6,
```

(b) Replace `_fleet_to_dict` (620–634) to emit nested formations:

```python
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
```

(c) Replace `_fleet_from_dict` (636–654) with a branch + `upgrade_v5_fleet`:

```python
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
```

Note: `Fleet` is constructed with `formations=...` and no `ships=`; `__post_init__` sees a non-empty `formations`, skips the default build, and repoints `f.ships = f.formations[0].ships`. Since `formations[0]` here is the upgraded/primary Formation, `len(f.ships)` and the delegating `formation_kind`/`pos_mode`/`layout_heading` properties read the right values — so `test_serialization.py` (which asserts `f2.formation_kind == LINE_ABREAST`, `f2.layout_heading == (1.0,0.0)`, etc.) passes unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_formation_layers.TestSerializationV6 -v`
Expected: PASS (4 tests).

Then the legacy serialization regression (must pass unchanged):

Run: `python -m unittest tests.test_serialization -v`
Expected: PASS (3 tests). (`test_fleet_formation_fields_roundtrip` relies on `pos_mode`/`layout_heading`/`formation_kind` delegation surviving the v6 nested roundtrip.)

- [ ] **Step 5: Commit**

```bash
git add tests/test_formation_layers.py fleet_search.py
git commit -m "feat(v6-A): serialize version=6 nested formations; upgrade v5 saves on load

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Full regression sweep + encounter zero-regression assertion

Confirm the entire suite is green (zero regression) and add one explicit test that the deeper `_cross_pairs` traversal still detects a cross-side encounter and rolls back to S−1, exercised through two zero-offset single-Formation fleets.

**Files:**
- Test: `tests/test_formation_layers.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_formation_layers.py`:

```python
class TestEncounterZeroRegression(unittest.TestCase):
    def test_cross_pairs_still_detects_and_rolls_back(self):
        g = fs.Game()
        g.visibility = 20000.0
        # GB heading E from (0,0); GE sitting still ~1 hex east so they close to <vis
        g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 2)
        g.add_fleet("GE1", "GE", 0, "1,0", "W", 18, 2)
        # step several turns; they approach head-on and must trigger CONTACT
        triggered = False
        for _ in range(6):
            g.step_turn()
            if g.state == fs.STATE_CONTACT:
                triggered = True
                break
        self.assertTrue(triggered, "expected an encounter between approaching fleets")
        # rollback invariant: at the frozen substep all GBxGE ship pairs are >= vis
        pairs = g._cross_pairs(g.current_substep)
        self.assertTrue(pairs, "expected cross-side pairs")
        self.assertTrue(all(d >= g.visibility - 1e-6 for d, _, _ in pairs),
                        "frozen state must be the pre-contact >vis substep")

    def test_cross_pairs_only_crosses_sides(self):
        g = fs.Game()
        g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 2)
        g.add_fleet("GB2", "GB", 0, "0,1", "E", 18, 2)
        # two same-side fleets -> no cross pairs at all
        self.assertEqual(g._cross_pairs(0), [])
```

- [ ] **Step 2: Run test to verify it fails OR passes**

Run: `python -m unittest tests.test_formation_layers.TestEncounterZeroRegression -v`
Expected: PASS if the geometry already closes to <vis (it should: head-on E vs W from adjacent hexes). If `test_cross_pairs_still_detects_and_rolls_back` does NOT trigger CONTACT within 6 turns, adjust the GE start to `"2,0"` and re-run; the assertion logic stays the same. (This task asserts existing behavior is intact, so passing on first run is the success condition; the test is still written first per TDD discipline.)

- [ ] **Step 3: (No new implementation)**

No source change — this task verifies the rewrite from Tasks 4–5 did not regress encounter detection. If it fails, that is a real regression in `_formation_ship_positions`/`ship_positions`; debug there using superpowers:systematic-debugging, do NOT weaken the test.

- [ ] **Step 4: Run the FULL suite to confirm zero regression**

Run: `python -m unittest discover -s tests -t .`
Expected: OK — all tests pass, including `test_fleet_search`, `test_formation`, `test_formation_integration`, `test_serialization`, `test_post_encounter`, `test_state_machine_loop`, `test_journal`, `test_journal_header`, `test_journal_integration`, `test_view_filter`, `test_cli_*`, `test_coords`, `test_closeup_smoke`, `test_execute_command`, `test_demo_convergence`, `test_server_*`, `test_timekeep`, and the new `test_formation_layers`. Report the final `OK` line and test count.

- [ ] **Step 5: Commit**

```bash
git add tests/test_formation_layers.py
git commit -m "test(v6-A): encounter zero-regression through deeper formation traversal

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review (run by implementer before declaring Phase A done)

**Spec coverage check:**
- §2 three-layer model / fields / constants → Tasks 1 (Ship), 2 (Formation + constants), 3 (Fleet `initial_course`/`formations`). ✅
- §3.1 `lead_xy` stays on Fleet → unchanged (Task 4 reuses it). ✅
- §3.2 Formation center = fleet center + rotated offset; absolute lazy-frozen → `_formation_center_xy`/`_offset_to_map` (Task 4). ✅
- §3.3 follow=arc-rollback, together=rigid → `_formation_ship_positions` (Task 4). ✅
- §3.4 `ship_positions` returns `[(name, xy)]` unchanged → Task 4 + Task 6 regression. ✅
- §8.1 version=6 nested → Task 5. ✅
- §8.2 `upgrade_v5_fleet` single zero-offset Formation (relative/turning/frozen rules, `initial_course=course`) → Task 5. ✅
- Locked conventions (§9): visibility 36000 cap untouched; rollback to >vis untouched (Task 6 asserts); axial increments via DIRVEC; 18kn=6/hex via STEP_YARDS_PER_KNOT; cross-side only (Task 6); exact xy no snap; `anchor_substep` typed float. ✅

**Out of scope for Phase A (do NOT implement here):** `course` queued turning, `next_cell_center_along`, pending fields, `_cross_pairs` report-center change to fleet geometric center, `orderparse.py`, `loadorder`/`add formation` CLI, journal turn-key, demo scripting. Those are Phases B/C/D.

**Type/name consistency:** `Ship(name, index)`, `Formation(name, ships, offset_fwd, offset_left, relative, kind, spacing, deploy, echelon_deg, turning, frozen_offset_xy, frozen_offset_xy_legacy)`, `Fleet(... initial_course, formations ...)`, `Fleet._formation_center_xy`, `Fleet._offset_to_map`, `Fleet._formation_ship_positions`, `Fleet._kind_for_offsets`, `Game._formation_to_dict`, `Game._formation_from_dict`, `Game.upgrade_v5_fleet` — used identically across Tasks 2–6. ✅

**Risk notes for the implementer:**
1. **Delegating properties vs dataclass fields:** `Fleet` is a `@dataclass`; you are REMOVING the six legacy fields and ADDING same-named `@property`/setter. A dataclass field and a property of the same name conflict — make sure the six names (`formation_kind`, `spacing`, `deploy`, `echelon_deg`, `pos_mode`, `layout_heading`) appear ONLY as properties, not as dataclass fields. The remaining dataclass fields are exactly: name, side, activated_turn, anchor_xy, anchor_substep, course, speed, ships, scheduled, schedule_end_substep, waypoints, display_history, initial_course, formations.
2. **`__post_init__` repoints `self.ships`:** after construction `f.ships is f.formations[0].ships` (same object). Do not later reassign `f.ships` to a new list elsewhere or the alias breaks; in Phase A nothing does.
3. **`pos_mode` string equivalence:** `formation.ABS_MODE=="absolute"==REL_ABSOLUTE` and `formation.REL_MODE=="relative"==REL_RELATIVE`; the delegation is lossless precisely because the constant values coincide. If anyone changes those strings, the delegation breaks.
4. **`layout_heading` is NOT `frozen_offset_xy`:** they carry different things (heading vector vs map offset). Keep them as two separate Formation attributes (`frozen_offset_xy_legacy` for the v5 heading, `frozen_offset_xy` for the v6 lazy-frozen offset) or `test_serialization.test_fleet_formation_fields_roundtrip` will fail.
