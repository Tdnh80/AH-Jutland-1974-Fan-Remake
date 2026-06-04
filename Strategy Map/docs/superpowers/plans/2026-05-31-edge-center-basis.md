# Edge-Center Coordinate Basis — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move a fleet's resting/anchor point from the hex **centre** to the hex **edge-centre** (entry edge = behind heading), and report micro-position relative to edge-centres — so `course` turns apply at the hex centre half a turn later (18kn: sub3), matching the wargame's edge-based movement.

**Architecture:** The engine is anchor-agnostic (exact xy + arc-length parameterisation), so the change is: (1) two new geometry helpers; (2) re-point the 4 placement sites (`add_fleet`/`relocate`/`load_order_file`/`schedule`) from hex-centre to entry-edge-centre; (3) rewrite `micro_position`/`micro_str` to report relative to edge-centres. Turn logic (`next_cell_center_along`, course-queue), detection, formations, state machine, serialization all stay unchanged. Positions shift back by `APOTHEM=18000` uniformly, so a test sweep updates hardcoded coordinates.

**Tech Stack:** Python 3.10+, stdlib `unittest` (no pytest). Windows/PowerShell: use `python` (not `python3`). Run tests with `python -m unittest ...`.

**Spec:** `docs/superpowers/specs/2026-05-31-edge-center-basis-design.md`

**Locked conventions (do not break):** visibility cap 36000 / default 20000; encounter = cross-side Euclidean < vis, roll back to last >=vis substep; axial neighbour deltas; 18kn = 6 substeps/hex; STEP_YARDS_PER_KNOT = 36000/108; positions stored exact (edge-centres are real points, not snapping); `anchor_substep` may be float. Turn point stays the hex CENTRE.

**Key geometry:** `edge_center(q,r,d) = hex_center_xy(q,r) + APOTHEM·DIRVEC[d]`; `APOTHEM = 18000`. Entry edge = `OPPOSITE[course]` edge. `DIRVEC` has the 6 hex dirs + N/S (N/S are vertices → no edge → fall back to centre).

---

### Task 1: `edge_center` + `entry_edge_center` helpers

**Files:**
- Modify: `fleet_search.py` — add two module-level functions right after `_axial_dist` (search for `def _axial_dist`).
- Test: `tests/test_cli_coords.py` (append a class).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_coords.py`:

```python
class TestEdgeCenter(unittest.TestCase):
    def test_edge_center_each_dir_is_apothem_from_centre(self):
        c = fs.hex_center_xy(3, 1)
        for d in ('E', 'W', 'NE', 'NW', 'SE', 'SW'):
            ec = fs.edge_center(3, 1, d)
            ux, uy = fs.DIRVEC[d]
            self.assertAlmostEqual(ec[0], c[0] + fs.APOTHEM * ux, places=3)
            self.assertAlmostEqual(ec[1], c[1] + fs.APOTHEM * uy, places=3)

    def test_entry_edge_is_behind_heading(self):
        # heading E -> entry edge is the W edge (= centre - APOTHEM along E)
        c = fs.hex_center_xy(0, 0)
        ee = fs.entry_edge_center(0, 0, 'E')
        self.assertAlmostEqual(ee[0], c[0] - fs.APOTHEM, places=3)
        self.assertAlmostEqual(ee[1], c[1], places=3)

    def test_entry_edge_ns_falls_back_to_centre(self):
        # N/S are vertex directions (no edge) -> fall back to hex centre
        c = fs.hex_center_xy(2, 2)
        self.assertEqual(fs.entry_edge_center(2, 2, 'N'), c)
        self.assertEqual(fs.entry_edge_center(2, 2, 'S'), c)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_cli_coords.TestEdgeCenter -v`
Expected: FAIL — `AttributeError: module 'fleet_search' has no attribute 'edge_center'`.

- [ ] **Step 3: Write minimal implementation**

In `fleet_search.py`, immediately after the `_axial_dist` function, add:

```python
def edge_center(q, r, d):
    """该格在方向 d 的边中心 = 格心 + APOTHEM·DIRVEC[d](d 须为 6 个边方向之一)。"""
    cx, cy = hex_center_xy(q, r)
    ux, uy = DIRVEC[d]
    return (cx + APOTHEM * ux, cy + APOTHEM * uy)


def entry_edge_center(q, r, course):
    """舰队"进入边"中心 = 航向后方那条边(OPPOSITE[course])的中心。
    course 为 N/S(顶点方向,无边)时退化为格心。"""
    opp = OPPOSITE.get(course)
    if opp is None:
        return hex_center_xy(q, r)
    return edge_center(q, r, opp)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_cli_coords.TestEdgeCenter -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py tests/test_cli_coords.py
git commit -m "feat(edge-basis): add edge_center / entry_edge_center helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `micro_position` / `micro_str` report relative to edge-centres

**Files:**
- Modify: `fleet_search.py` — `micro_position` (search `def micro_position`) and `micro_str` (search `def micro_str`).
- Test: `tests/test_cli_coords.py`.

Current `micro_position(x,y)` returns centre-relative info and `micro_str` renders "Xyd from centre → DIR edge". Replace with edge-centre-relative.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_coords.py`:

```python
class TestMicroEdge(unittest.TestCase):
    def test_at_w_edge_centre_reports_zero(self):
        x, y = fs.edge_center(0, 0, 'W')
        s = fs.micro_str(x, y)
        self.assertIn("W", s)                 # names the W edge
        self.assertNotIn("+", s)              # at the edge centre -> no offset

    def test_at_hex_centre_reports_centre(self):
        x, y = fs.hex_center_xy(0, 0)
        self.assertIn("centre", fs.micro_str(x, y).lower())

    def test_offset_from_edge_centre_shows_distance(self):
        ex, ey = fs.edge_center(0, 0, 'E')
        s = fs.micro_str(ex - 1000.0, ey)     # 1000 yd off the E edge centre
        self.assertIn("E", s)
        self.assertIn("1000", s)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_cli_coords.TestMicroEdge -v`
Expected: FAIL (current `micro_str` says "from centre", no edge-centre wording / offset format).

- [ ] **Step 3: Write minimal implementation**

Replace `micro_position` and `micro_str` in `fleet_search.py` with:

```python
def micro_position(x, y):
    """返回 (hex, edge_dir, dist):点所在格 + 最近的边中心方向 + 距该边中心码数。
    点恰在格心(到各边等距 ~ APOTHEM)时 edge_dir 为 None。"""
    h = xy_to_hex(x, y)
    cx, cy = hex_center_xy(*h)
    # 恰在格心:到任意边中心都约 = APOTHEM,无明确"最近边"
    if math.hypot(x - cx, y - cy) < 1e-6:
        return (h, None, 0.0)
    best_dir, best_d = None, None
    for d in DIRECTION_LIST:                       # 6 个边方向
        ex, ey = edge_center(*h, d)
        dist = math.hypot(x - ex, y - ey)
        if best_d is None or dist < best_d:
            best_dir, best_d = d, dist
    return (h, best_dir, best_d)


def micro_str(x, y):
    h, edge_dir, dist = micro_position(x, y)
    q, r = h
    cell = display_cell(q, r)
    if edge_dir is None:
        return f"{cell} centre"
    if dist < 1e-3:
        return f"{cell} {edge_dir} edge-centre"
    return f"{cell} {edge_dir} edge-centre +{dist:.0f}yd"
```

(Confirm `math`, `xy_to_hex`, `hex_center_xy`, `display_cell`, `DIRECTION_LIST`, `edge_center` are all available at module level — they are.)

- [ ] **Step 4: Run the new test + grep for other consumers**

Run: `python -m unittest tests.test_cli_coords.TestMicroEdge -v`
Expected: PASS (3 tests).

Then find any other test asserting the old report wording:
Run: `python -m unittest tests.test_cli_coords -v`
If any existing `test_cli_coords` test asserts "from centre" / old format, update its expectation to the new `micro_str` wording (recompute by hand using the formulas above). Do NOT change behaviour to satisfy a stale assertion — fix the assertion.

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py tests/test_cli_coords.py
git commit -m "feat(edge-basis): micro report relative to edge-centres

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Flip the 4 placement sites to entry-edge-centre (atomic) + new behaviour tests + repair shifted tests

This is the disruptive change: every position shifts back by APOTHEM along the heading. Do production edits + add new-behaviour tests + repair all shifted assertions in ONE commit so the suite ends green.

**Files:**
- Modify: `fleet_search.py` — `add_fleet` (search `def add_fleet`), `relocate` (search `def relocate`), `load_order_file` (search `anchor_xy=center` / the Fleet construction), `schedule` (search `f.anchor_xy = hex_center_xy(*cur_hex)`).
- Test: `tests/test_course_queue.py`, `tests/test_orderparse.py`, `tests/test_replay.py`, `tests/test_formation_layers.py`, `tests/test_closeup_smoke.py`, plus a new `tests/test_edge_basis.py`.

- [ ] **Step 1: Write the failing new-behaviour tests**

Create `tests/test_edge_basis.py`:

```python
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fleet_search as fs

AP = fs.APOTHEM   # 18000


class TestPlacementAtEntryEdge(unittest.TestCase):
    def test_new_fleet_anchors_at_entry_edge(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 2)
        f = g.fleets["F"]
        # heading E -> W edge of (0,0) = (-18000, 0)
        self.assertAlmostEqual(f.anchor_xy[0], -AP, places=3)
        self.assertAlmostEqual(f.anchor_xy[1], 0.0, places=3)
        # crosses centre at sub3, exit (E) edge at sub6
        self.assertAlmostEqual(f.lead_xy(3)[0], 0.0, places=3)
        self.assertAlmostEqual(f.lead_xy(6)[0], AP, places=3)

    def test_relocate_anchors_at_entry_edge(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 1)
        g.relocate("F", "5,0", "W", 18)             # heading W -> E edge of (5,0)
        c = fs.hex_center_xy(5, 0)
        f = g.fleets["F"]
        self.assertAlmostEqual(f.anchor_xy[0], c[0] + AP, places=3)
        self.assertAlmostEqual(f.anchor_xy[1], c[1], places=3)


class TestCourseTurnsAtCentreHalfTurn(unittest.TestCase):
    def test_18kn_turns_at_sub3(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 1)
        g.course_change("F", "SE")
        g.step_turn()                                # within first turn: centre at sub3
        f = g.fleets["F"]
        self.assertEqual(f.course, "SE")
        self.assertAlmostEqual(f.anchor_substep, 3.0, delta=1e-6)
        self.assertAlmostEqual(f.anchor_xy[0], 0.0, places=3)   # hex (0,0) centre
        self.assertAlmostEqual(f.anchor_xy[1], 0.0, places=3)


class TestScheduleRestsOnEdges(unittest.TestCase):
    def test_schedule_start_snaps_to_entry_edge_and_boundaries_on_edges(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 1)
        g.schedule("F", 18, ["1,0", "2,0", "3,0"])  # straight E, 3 hexes
        f = g.fleets["F"]
        # start snapped to W edge of (0,0)
        self.assertAlmostEqual(f.anchor_xy[0], -AP, places=3)
        # turn boundaries (sub6/12/18 from sub0) land on shared edge-centres:
        # sub6 -> E edge of (0,0) = (+18000,0); sub18 -> E edge of (2,0) = (90000,0)
        self.assertAlmostEqual(f.lead_xy(6)[0], AP, places=3)
        self.assertAlmostEqual(f.lead_xy(18)[0], 5 * AP, places=3)   # 90000


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `python -m unittest tests.test_edge_basis -v`
Expected: FAIL — placements still at hex centres (anchor 0.0 not -18000), 18kn turn at sub6 not sub3.

- [ ] **Step 3: Make the production change (4 sites)**

(a) `add_fleet` — change the anchor:
```python
# OLD:  anchor_xy=hex_center_xy(*h), anchor_substep=activated * 6,
anchor_xy=entry_edge_center(*h, course), anchor_substep=activated * 6,
```
And the display_history seed line in add_fleet (search `f.display_history.append((activated * 6, *f.anchor_xy))`) stays — it already uses `f.anchor_xy`, now the edge-centre.

(b) `relocate`:
```python
# OLD:  f.anchor_xy = hex_center_xy(*parse_cell_or_hex(hex_str))
f.anchor_xy = entry_edge_center(*parse_cell_or_hex(hex_str), course)
```
(`relocate(self, name, hex_str, course, speed)` — `course` is a param; if relocate sets `f.course = course` after, keep that order so `course` is valid.)

(c) `load_order_file` — the Fleet geometric centre. Find `center = hex_center_xy(*h)` and the `Fleet(... anchor_xy=center ...)`/`display_history.append((activated*6, *center))`. Replace the per-fleet anchor: inside the `for ofleet` loop, after `crs = ofleet.initial_course`, compute the entry edge for THIS fleet's course:
```python
fleet_anchor = entry_edge_center(*h, crs)   # crs may be N/S -> falls back to centre
...
f = Fleet(..., anchor_xy=fleet_anchor, ...)
f.display_history.append((activated * 6, *fleet_anchor))
```
(Keep `center` if still used elsewhere; otherwise replace its uses with `fleet_anchor`.)

(d) `schedule` — change the snap target:
```python
# OLD:  f.anchor_xy = hex_center_xy(*cur_hex)
# course is set on the next line as direction_between(chain[0], chain[1]); compute it first:
_crs = direction_between(chain[0], chain[1])
f.anchor_xy = entry_edge_center(*cur_hex, _crs)
f.anchor_substep = self.current_substep
f.course = _crs
```
(Reuse `_crs` for `f.course` so it's computed once.)

- [ ] **Step 4: Run the full suite; repair shifted assertions**

Run: `python -m unittest discover -s tests -t .`

The new `test_edge_basis` should pass. Many existing tests now fail on hardcoded positions — these are EXPECTED shifts, not regressions. Repair each failing assertion to the recomputed value (positions shift back by APOTHEM along the entry-edge direction; 18kn `course` turns now land at sub3, 24kn sub2.25, 12kn sub4.5 — all within the first `step_turn`). Known hotspots and their fixes:

- `tests/test_course_queue.py` (TestStepTurnArrival): fleet `add_fleet "0,0" E 18` now anchors at (-18000,0). `course SE` turns at **sub3** at hex centre **(0,0)** (was sub6 at (36000,0)).
  - `test_turn_applied_at_next_centre_18kn`: `anchor_substep == 3.0`; `anchor_xy ≈ (0,0)`.
  - `test_turn_point_is_a_hex_centre`: `anchor_xy == hex_center_xy(0,0)` = (0,0).
  - `test_turn_timing_12kn_*`: 12kn reaches the centre at sub **4.5** within the FIRST step (centre is only 18000 ahead). Rename/rewrite: after one `step_turn`, `course == "SE"`, `anchor_substep == 4.5`. (No longer "needs two turns".)
  - `test_turn_timing_24kn_*`: `anchor_substep == 2.25`.
  - `test_succession_trailing_ship_stays_on_old_leg`: the turn now happens at sub3; inspect at the turn moment. After `step_turn` (current_substep=6, anchor (0,0)/SE/sub3): lead `lead_xy(6) = (0,0)+18000·DIRVEC[SE]`; trailing ship's negative-arc rollback still uses `incoming_dir=E`. Recompute the asserted coords, or assert the invariant "trailing ship is behind along the path" rather than exact y. Keep the test meaningful (don't delete).
  - `test_180_reversal_*`: `pending_turn_xy == hex_center_xy(0,0)` (the next centre from the W edge), anchor after turn = (0,0).
  - `TestCourseChangeQueues.test_course_not_applied_immediately`: `pending_turn_xy ≈ (0,0)` (was (36000,0)).
  - `TestNextCellCenter`: unchanged (tests the helper directly).
- `tests/test_replay.py` (`test_replay_restores_substep_and_position`): GB1 `add_fleet "0,0" E 18` anchors at (-18000,0); `lead_xy(6k) = (-18000 + 6k·6000, 0)`. Update the expected x from `6k·6000` to `-18000 + 6k·6000`. The encounter test (`GE1` near) — recompute the 19000-gap setup if it asserts positions; the encounter still fires.
- `tests/test_orderparse.py`: `test_fleet_center_at_start_hex_formation_keeps_offset` and `test_zero_offset_formation_at_fleet_center` and `test_save_load_roundtrip_preserves_offsets`: the Fleet geometric centre (anchor) is now the entry edge of start hex for that fleet's course (GB-BS course SE → NW edge; GE-SG course NW → SE edge; GE-BS course N → falls back to hex centre). Recompute the asserted anchor: `entry_edge_center(0,0, fleet.course)`. Formation-centre / offset assertions are relative to the Fleet centre, so add the entry-edge shift to the expected absolute coords.
- `tests/test_formation_layers.py`: any test asserting absolute ship coords after `add_fleet` shifts by the entry-edge offset; the equivalence tests that compare to `_xy_at_arc`/`place_map` formulas are relative and should still pass.
- `tests/test_closeup_smoke.py`: schedules to contact; only asserts `state == CONTACT` + file written — should still pass (recompute only if it asserts coords).

For each failing test: recompute the correct value from the new geometry and update the assertion (never weaken behaviour to fit a stale number). Re-run until green.

- [ ] **Step 5: Confirm full green + commit**

Run: `python -m unittest discover -s tests -t .`
Expected: `OK` (all tests).

```bash
git add fleet_search.py tests/test_edge_basis.py tests/test_course_queue.py tests/test_replay.py tests/test_orderparse.py tests/test_formation_layers.py tests/test_closeup_smoke.py
git commit -m "feat(edge-basis): anchor at entry edge-centre (new/relocate/loadorder/schedule)

Fleets now rest at the hex edge-centre behind the heading; course turns apply at
the hex centre, i.e. sub3 at 18kn (half a turn) instead of a full turn later.
Schedule snaps its start to the entry edge so turn boundaries land on shared
edge-centres and waypoint centres become mid-turn pivots. Positions shift back
by APOTHEM; tests repaired to the recomputed coordinates.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Update docs to the edge-centre convention

**Files:**
- Modify: `CLAUDE.md` (locked conventions / 队形 / course sections), `DEVELOPER.md` (coordinate + course sections), `README.md` (§3 concepts, §5 report reading).

- [ ] **Step 1: Update CLAUDE.md**

In the 坐标 / 运动学 locked-convention area, replace "常态静止点 = 格心 ... 报告不吸附格心" wording with:
> 常态静止/锚点 = **六角格边中心**(进入边 = 航向后方那条边,`格心 + APOTHEM·DIRVEC[OPPOSITE[course]]`);运动中仍存精确 (x,y) 不吸附;**报告基准 = 格边中心**(`micro_str` 输出 `(q,r) <dir> edge-centre [+Xyd]`,恰在格心报 `centre`)。转向点仍是格心 ⇒ 18 节在 sub3 转向。新增 helper `entry_edge_center`/`edge_center`。`new`/`relocate`/`loadorder`/`schedule` 一律锚到进入边中心。

- [ ] **Step 2: Update DEVELOPER.md**

In the coordinate section add a bullet: edge-centre = `格心 + APOTHEM·DIRVEC[d]`; `entry_edge_center(q,r,course)`; placement at entry edge; micro report edge-relative. In the course-queue section note: because rest is now an edge-centre, the next hex centre is half a hex ahead, so 18kn turns at sub3 (`next_cell_center_along` unchanged).

- [ ] **Step 3: Update README.md**

§3 "海图与坐标": add that a fleet sits at the **edge of a hex** (the edge it entered through), not the centre; `course K10 E` rests at K10's west edge-centre. §5 report reading: update the `micro_str` example to the new "edge-centre" wording.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md DEVELOPER.md README.md
git commit -m "docs: edge-centre basis (rest/anchor at edge-centre, micro report)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review notes
- **Spec coverage**: §3.1 helpers→Task1; §3.4 report→Task2; §3.2 placement (4 sites incl. schedule §3.5)→Task3; §3.6 locked-convention + §3.3 turn-at-centre (verified sub3)→Task3 tests; docs→Task4; §5 test sweep→Task3 Step4. §3.3 `next_cell_center_along` explicitly unchanged. §4 N/S fallback→Task1 test. ✓
- **Risk**: Task3 is large (atomic basis flip). The new-behaviour tests pin the intended geometry; the repair step recomputes shifted assertions. If a test's correct new value is unclear, recompute from `entry_edge_center` + arc formulas; do not weaken assertions.
- **Boundary rounding**: a fleet exactly on an edge → `xy_to_hex` may round either side; verified turn point still resolves to the intended centre (spec §3.3/§4). Not separately tested (covered by sub3 turn test).
