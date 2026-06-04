# v6 Phase C — Course Queue Turning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `course` change queue until the flagship reaches the next hex centre along its current heading, then turn there (single-纵阵 turn-in-succession 回转点 semantics), instead of turning instantly at an arbitrary mid-cell point.

**Architecture:** Add three `pending_*` fields to `Fleet`. Add a pure module-level `next_cell_center_along(P, course)` (project P onto the course axis through its containing hex centre, ceil to the next centre). `course_change` no longer mutates `anchor`/`course`; it records the pending request and pre-computes the turn point. `step_turn` detects flagship arrival at the pending turn point (after recording history, before encounter detection) and applies the turn via `_apply_pending_turn` (a sibling of `_end_schedule`, with a `float` `anchor_substep` = exact fractional substep of arrival). Entering CONTACT clears all fleets' pending turns (symmetric with clearing schedules). Serialization gains the three fields with `d.get(...)` backward-compatibility.

**Tech Stack:** Python 3.10+, stdlib only. Tests use stdlib `unittest` in `tests/`. matplotlib is not touched by this phase.

This phase is independent of Phase B (multi-Formation). It operates on the Fleet centre track layer only and stays compatible with the existing single-`Fleet` model.

**Locked conventions honored (spec §9):** visibility cap 36000, rollback to the `>vis` substep, uniform axial neighbour deltas via `DIRVEC`, 18kn = 6 substeps/hex (`STEP_YARDS_PER_KNOT = 36000/108`), cross-side-only encounter detection, exact xy never snapped to centre (the turn point IS a centre, but that is a kinematic arrival point, not display snapping), `anchor_substep` may be `float`.

**Run all tests:** `python -m unittest discover -s tests -t .`
**Run a single module:** `python -m unittest tests.test_course_queue -v`

---

## Reference: current source (verified against `fleet_search.py`)

- `Fleet` dataclass: `fleet_search.py:243-262` (fields). `_polyline` 267-273 uses `self.course` + `self.anchor_xy` for the non-scheduled straight ray; `_arc_at` 275-276; `_xy_at_arc` 278-297; `lead_xy` 299-300.
- `course_change`: `fleet_search.py:379-387`.
- `clear_schedule`: 389-396. `_end_schedule`: 491-500.
- `step_turn`: 460-489 (history recorded inside the `for offset in range(1,7)` loop at 476-477, then encounter detection at 478-483).
- `_resolve_encounter`: 502-544 (clears schedules at 534-536, sets `state = STATE_CONTACT` at 543).
- `to_dict`: 656-665; `_fleet_to_dict`: 620-634; `_fleet_from_dict`: 636-654; `load_dict`: 667-674.
- Module-level constants: `DIRVEC` 74-81, `HEX_SIDE` 47, `STEP_YARDS_PER_KNOT` 50, `hex_center_xy` 100-103, `xy_to_hex` 118-123.

**Verified facts** (computed against the live module):
- `next_cell_center_along((0,0),'E') == hex_center_xy(1,0) == (36000.0, 0.0)`.
- `next_cell_center_along((0,0),'SE') == hex_center_xy(0,1) == (18000.0, 31176.914...)`.
- `next_cell_center_along((3000.0,0.0),'E') == (36000.0, 0.0)` (mid-cell point projects to next E centre).
- 18kn arc over the 36000 to a neighbour centre = exactly 6 substeps; 12kn = 9.0 substeps; 24kn = 4.5 substeps.

---

## Task 1: `next_cell_center_along` module-level helper

**Files:**
- Modify: `fleet_search.py` (add a new module-level function immediately after `hhmm`, around line 232, before the `Data model` section header at 234)
- Test: `tests/test_course_queue.py` (Create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_course_queue.py` with this content (later tasks append more classes to the same file):

```python
#!/usr/bin/env python3
"""v6 Phase C —— course 排队转向回归测试。

只依赖标准库 unittest。覆盖:
  * next_cell_center_along 六方向 / 格心 / 格内偏移 / ceil 边界
  * course_change 排队(不立即生效) / schedule 互斥 / 覆盖语义
  * step_turn 抵达格心才转 / t_hit 精度(18/12/24kn) / 鱼贯后船滞后转
  * 180° 掉头排队 / _end_schedule 后非格心仍正确求 pending_turn_xy
  * 接敌清 pending / save-load 往返 pending
"""

import math
import unittest

import fleet_search as fs


TOL = 1e-6


class TestNextCellCenterAlong(unittest.TestCase):
    """模块级 next_cell_center_along(P, course):沿 course 轴前方第一格心。"""

    def test_from_centre_all_six_directions(self):
        c0 = fs.hex_center_xy(0, 0)
        for d, (dq, dr) in fs.NEIGH.items():
            got = fs.next_cell_center_along(c0, d)
            want = fs.hex_center_xy(dq, dr)
            self.assertAlmostEqual(got[0], want[0], delta=1e-3, msg=f"{d} x")
            self.assertAlmostEqual(got[1], want[1], delta=1e-3, msg=f"{d} y")

    def test_from_centre_picks_adjacent_not_self(self):
        # P 恰在格心时取沿 course 相邻格心(turn_arc=36000),不取自身。
        c0 = fs.hex_center_xy(2, -1)
        got = fs.next_cell_center_along(c0, 'E')
        self.assertNotAlmostEqual(got[0], c0[0], delta=1.0)
        want = fs.hex_center_xy(3, -1)
        self.assertAlmostEqual(got[0], want[0], delta=1e-3)
        self.assertAlmostEqual(got[1], want[1], delta=1e-3)

    def test_from_midcell_offset_picks_next_centre(self):
        # 格 (0,0) 内沿 E 偏 3000,前方第一格心仍是 (1,0)。
        got = fs.next_cell_center_along((3000.0, 0.0), 'E')
        want = fs.hex_center_xy(1, 0)
        self.assertAlmostEqual(got[0], want[0], delta=1e-3)
        self.assertAlmostEqual(got[1], want[1], delta=1e-3)

    def test_ceil_boundary_just_short_of_centre(self):
        # 距下一格心仅差 1 码(s 接近 36000)仍应取该格心而非再下一个。
        got = fs.next_cell_center_along((36000.0 - 1.0, 0.0), 'E')
        want = fs.hex_center_xy(1, 0)
        self.assertAlmostEqual(got[0], want[0], delta=1e-3)

    def test_result_is_one_hex_arc_from_a_centre(self):
        # 返回点本身是某格心,且沿 course 距出发格心整数倍 36000。
        c0 = fs.hex_center_xy(0, 0)
        got = fs.next_cell_center_along(c0, 'SE')
        h = fs.xy_to_hex(*got)
        cc = fs.hex_center_xy(*h)
        self.assertAlmostEqual(got[0], cc[0], delta=1e-3)
        self.assertAlmostEqual(got[1], cc[1], delta=1e-3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_course_queue.TestNextCellCenterAlong -v`
Expected: FAIL — `AttributeError: module 'fleet_search' has no attribute 'next_cell_center_along'`.

- [ ] **Step 3: Write minimal implementation**

In `fleet_search.py`, add this function right after the `hhmm` function (after line 231, before the `# ---` block at line 234). It uses the module constants `DIRVEC`, `HEX_SIDE`, `xy_to_hex`, `hex_center_xy` (all defined above it):

```python
NEXT_CELL_EPS = 1e-6   # yards; nudge so a point exactly on a centre advances one hex


def next_cell_center_along(P, course):
    """沿 course 正方向,P 前方第一个格心的精确像素坐标。

    把 P 投影到「过其所在格格心、方向 DIRVEC[course]」的轴上,取 ceil 到下一个
    36000 间距的格心。P 恰在格心时(s≈0)取沿 course 相邻格心(EPS 推一把)。
    投影算法不要求 P 落在格心连线上(_end_schedule 后 anchor 可能横向偏移)。
    """
    ux, uy = DIRVEC[course]
    h0 = xy_to_hex(*P)
    cx, cy = hex_center_xy(*h0)
    s = (P[0] - cx) * ux + (P[1] - cy) * uy
    s_next = math.ceil((s + NEXT_CELL_EPS) / HEX_SIDE) * HEX_SIDE
    return (cx + s_next * ux, cy + s_next * uy)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_course_queue.TestNextCellCenterAlong -v`
Expected: PASS (5 tests OK).

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py tests/test_course_queue.py
git commit -m "feat(course-queue): add next_cell_center_along helper

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Add `pending_*` fields to `Fleet` + serialization round-trip

**Files:**
- Modify: `fleet_search.py:243-262` (add three fields to the `Fleet` dataclass after `layout_heading` at line 262)
- Modify: `fleet_search.py:620-634` (`_fleet_to_dict` — emit the three fields)
- Modify: `fleet_search.py:636-654` (`_fleet_from_dict` — read with `d.get(..., None)`)
- Test: `tests/test_course_queue.py` (append `TestPendingSerialization`)

- [ ] **Step 1: Write the failing test**

Append this class to `tests/test_course_queue.py`:

```python
class TestPendingSerialization(unittest.TestCase):
    """pending_course / pending_speed / pending_turn_xy 序列化往返 + 向后兼容。"""

    def test_fleet_has_pending_fields_default_none(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 3)
        f = g.fleets["F"]
        self.assertIsNone(f.pending_course)
        self.assertIsNone(f.pending_speed)
        self.assertIsNone(f.pending_turn_xy)

    def test_roundtrip_preserves_pending(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 3)
        f = g.fleets["F"]
        f.pending_course = "SE"
        f.pending_speed = 24
        f.pending_turn_xy = (36000.0, 0.0)
        g2 = fs.Game()
        g2.load_dict(g.to_dict())
        f2 = g2.fleets["F"]
        self.assertEqual(f2.pending_course, "SE")
        self.assertEqual(f2.pending_speed, 24)
        self.assertEqual(tuple(f2.pending_turn_xy), (36000.0, 0.0))

    def test_load_legacy_dict_without_pending(self):
        # 旧档没有这三个键,应回落 None(d.get 容错)。
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 3)
        d = g.to_dict()
        for fd in d['fleets']:
            fd.pop('pending_course', None)
            fd.pop('pending_speed', None)
            fd.pop('pending_turn_xy', None)
        g2 = fs.Game()
        g2.load_dict(d)
        f2 = g2.fleets["F"]
        self.assertIsNone(f2.pending_course)
        self.assertIsNone(f2.pending_speed)
        self.assertIsNone(f2.pending_turn_xy)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_course_queue.TestPendingSerialization -v`
Expected: FAIL — `test_fleet_has_pending_fields_default_none` raises `AttributeError: 'Fleet' object has no attribute 'pending_course'`.

- [ ] **Step 3: Write minimal implementation**

(3a) In `fleet_search.py`, add the three fields to the `Fleet` dataclass. Find the last field:

```python
    layout_heading: tuple = None     # 绝对模式布局时航向;None=用当前航向
```

Replace it with:

```python
    layout_heading: tuple = None     # 绝对模式布局时航向;None=用当前航向
    # --- course 排队转向(v6 阶段 C);None=无待转向 ---
    pending_course: str = None       # 待生效目标航向
    pending_speed: int = None        # 待生效目标速度;None=不变
    pending_turn_xy: tuple = None    # 预算的下一格心精确像素坐标(缓存)
```

(3b) In `_fleet_to_dict`, find the closing of the returned dict:

```python
            'pos_mode': f.pos_mode,
            'layout_heading': list(f.layout_heading) if f.layout_heading is not None else None,
        }
```

Replace with:

```python
            'pos_mode': f.pos_mode,
            'layout_heading': list(f.layout_heading) if f.layout_heading is not None else None,
            'pending_course': f.pending_course,
            'pending_speed': f.pending_speed,
            'pending_turn_xy': (list(f.pending_turn_xy)
                                if f.pending_turn_xy is not None else None),
        }
```

(3c) In `_fleet_from_dict`, find:

```python
        f.pos_mode = d.get('pos_mode', formation.REL_MODE)
        f.layout_heading = tuple(lh) if lh is not None else None
        return f
```

Replace with:

```python
        f.pos_mode = d.get('pos_mode', formation.REL_MODE)
        f.layout_heading = tuple(lh) if lh is not None else None
        f.pending_course = d.get('pending_course')
        f.pending_speed = d.get('pending_speed')
        pxy = d.get('pending_turn_xy')
        f.pending_turn_xy = tuple(pxy) if pxy is not None else None
        return f
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_course_queue.TestPendingSerialization -v`
Expected: PASS (3 tests OK).

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py tests/test_course_queue.py
git commit -m "feat(course-queue): add pending_* fields with serialization

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `course_change` registers a pending turn instead of turning instantly

**Files:**
- Modify: `fleet_search.py:379-387` (`course_change`)
- Test: `tests/test_course_queue.py` (append `TestCourseChangeQueues`)

- [ ] **Step 1: Write the failing test**

Append this class to `tests/test_course_queue.py`:

```python
class TestCourseChangeQueues(unittest.TestCase):
    """course 不再即时转:登记 pending,位置/航向当拍不变;转向点=下一格心。"""

    def _fleet_midcell(self):
        # 走到 substep 2(18kn -> 12000,0),仍在格 (0,0) 内、非格心。
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 3)
        g.current_substep = 2
        return g

    def test_course_registers_pending_and_does_not_turn_now(self):
        g = self._fleet_midcell()
        f = g.fleets["F"]
        before_xy = f.lead_xy(g.current_substep)
        before_course = f.course
        g.course_change("F", "SE")
        # 当拍航向/位置不变(锚点不动)
        self.assertEqual(f.course, before_course)
        now_xy = f.lead_xy(g.current_substep)
        self.assertAlmostEqual(now_xy[0], before_xy[0], delta=TOL)
        self.assertAlmostEqual(now_xy[1], before_xy[1], delta=TOL)
        # pending 已登记;转向点=沿当前 E 航向的下一格心 (1,0)
        self.assertEqual(f.pending_course, "SE")
        self.assertIsNone(f.pending_speed)
        want = fs.next_cell_center_along(before_xy, "E")
        self.assertAlmostEqual(f.pending_turn_xy[0], want[0], delta=1e-3)
        self.assertAlmostEqual(f.pending_turn_xy[1], want[1], delta=1e-3)

    def test_course_with_speed_queues_speed_too(self):
        g = self._fleet_midcell()
        f = g.fleets["F"]
        g.course_change("F", "SE", 24)
        self.assertEqual(f.pending_speed, 24)
        self.assertEqual(f.speed, 18)   # 速度也排队,当拍不变

    def test_course_blocked_while_scheduled(self):
        g = self._fleet_midcell()
        g.schedule("F", 18, ["1,0", "2,0", "3,0"])
        with self.assertRaises(ValueError):
            g.course_change("F", "SE")

    def test_same_course_no_speed_change_is_noop(self):
        g = self._fleet_midcell()
        f = g.fleets["F"]
        g.course_change("F", "E")        # 与当前航向相同、无速度变化
        self.assertIsNone(f.pending_course)
        self.assertIsNone(f.pending_turn_xy)

    def test_resending_course_updates_target_keeps_turn_point(self):
        g = self._fleet_midcell()
        f = g.fleets["F"]
        g.course_change("F", "SE")
        tp = f.pending_turn_xy
        g.course_change("F", "NE")       # 再发:只更新目标,转向点不重算
        self.assertEqual(f.pending_course, "NE")
        self.assertEqual(f.pending_turn_xy, tp)

    def test_bad_course_and_bad_speed_rejected(self):
        g = self._fleet_midcell()
        with self.assertRaises(ValueError):
            g.course_change("F", "X")
        with self.assertRaises(ValueError):
            g.course_change("F", "SE", 99)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_course_queue.TestCourseChangeQueues -v`
Expected: FAIL — `test_course_registers_pending_and_does_not_turn_now` fails because the current `course_change` immediately sets `f.course = "SE"` and moves `anchor_xy`, so `f.pending_course` is `None` and `f.course != before_course`.

- [ ] **Step 3: Write minimal implementation**

In `fleet_search.py`, replace the whole `course_change` method (lines 379-387):

```python
    def course_change(self, name, course, speed=None):
        f = self._get(name)
        if course not in NEIGH: raise ValueError("bad course")
        if speed is not None and speed not in VALID_SPEEDS: raise ValueError("bad speed")
        if f.scheduled: raise ValueError(f"{name!r} has an active schedule; clear it first")
        f.anchor_xy = f.lead_xy(self.current_substep)   # exact, no snap
        f.anchor_substep = self.current_substep
        f.course = course
        if speed is not None: f.speed = speed
```

with:

```python
    def course_change(self, name, course, speed=None):
        f = self._get(name)
        if course not in NEIGH: raise ValueError("bad course")
        if speed is not None and speed not in VALID_SPEEDS: raise ValueError("bad speed")
        if f.scheduled: raise ValueError(f"{name!r} has an active schedule; clear it first")
        # 与当前航向相同且无速度变化 -> no-op
        if course == f.course and (speed is None or speed == f.speed):
            return
        # 排队到旗舰沿「当前航向」抵达的下一格心再转;速度也排队到同一格心。
        # 未到达前位置仍在原射线上,格心不变,故覆盖时不重算 pending_turn_xy。
        if f.pending_turn_xy is None:
            here = f.lead_xy(self.current_substep)
            f.pending_turn_xy = next_cell_center_along(here, f.course)
        f.pending_course = course
        f.pending_speed = speed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_course_queue.TestCourseChangeQueues -v`
Expected: PASS (6 tests OK).

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py tests/test_course_queue.py
git commit -m "feat(course-queue): course_change registers pending turn

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `_apply_pending_turn` (sibling of `_end_schedule`, float anchor_substep)

**Files:**
- Modify: `fleet_search.py` (add `_apply_pending_turn` method to `Game`, immediately after `_end_schedule` which ends at line 500)
- Test: `tests/test_course_queue.py` (append `TestApplyPendingTurn`)

- [ ] **Step 1: Write the failing test**

Append this class to `tests/test_course_queue.py`:

```python
class TestApplyPendingTurn(unittest.TestCase):
    """_apply_pending_turn(f, t_hit):钉锚到格心、anchor_substep=float、改 course/speed、清 pending。"""

    def _pending_fleet(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 3)
        f = g.fleets["F"]
        f.pending_course = "SE"
        f.pending_speed = 24
        f.pending_turn_xy = fs.hex_center_xy(1, 0)   # (36000,0)
        return g, f

    def test_apply_sets_anchor_course_and_clears_pending(self):
        g, f = self._pending_fleet()
        g._apply_pending_turn(f, 6.0)
        self.assertEqual(f.anchor_xy, fs.hex_center_xy(1, 0))
        self.assertEqual(f.anchor_substep, 6.0)
        self.assertEqual(f.course, "SE")
        self.assertEqual(f.speed, 24)
        self.assertIsNone(f.pending_course)
        self.assertIsNone(f.pending_speed)
        self.assertIsNone(f.pending_turn_xy)

    def test_apply_keeps_speed_when_pending_speed_none(self):
        g, f = self._pending_fleet()
        f.pending_speed = None
        g._apply_pending_turn(f, 6.0)
        self.assertEqual(f.speed, 18)   # 未排速度 -> 不变

    def test_anchor_substep_can_be_float(self):
        g, f = self._pending_fleet()
        g._apply_pending_turn(f, 4.5)   # 24kn 抵达可能是分数拍
        self.assertEqual(f.anchor_substep, 4.5)
        # 新折线沿 SE,从 (36000,0) 起算;t=4.5 时 lead_xy 就是该格心
        x, y = f.lead_xy(4.5)
        self.assertAlmostEqual(x, 36000.0, delta=1e-3)
        self.assertAlmostEqual(y, 0.0, delta=1e-3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_course_queue.TestApplyPendingTurn -v`
Expected: FAIL — `AttributeError: 'Game' object has no attribute '_apply_pending_turn'`.

- [ ] **Step 3: Write minimal implementation**

In `fleet_search.py`, add this method right after `_end_schedule` (after line 500, before `_resolve_encounter` at line 502):

```python
    def _apply_pending_turn(self, f, t_hit):
        """旗舰抵达 pending_turn_xy(格心)那一刻应用排队转向。类比 _end_schedule:
        把锚点钉到该格心、anchor_substep=t_hit(float)、改 course、若有则改 speed、
        清空三个 pending 字段。转向后本拍剩余弧长由 lead_xy 自动按新折线派生。"""
        f.anchor_xy = f.pending_turn_xy
        f.anchor_substep = t_hit
        f.course = f.pending_course
        if f.pending_speed is not None:
            f.speed = f.pending_speed
        f.pending_course = None
        f.pending_speed = None
        f.pending_turn_xy = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_course_queue.TestApplyPendingTurn -v`
Expected: PASS (3 tests OK).

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py tests/test_course_queue.py
git commit -m "feat(course-queue): add _apply_pending_turn (float anchor_substep)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `step_turn` arrival detection (turn before encounter detection)

**Files:**
- Modify: `fleet_search.py:473-489` (`step_turn` — insert arrival check inside the `for offset in range(1, 7)` loop, after recording history at 476-477 and before `pairs = self._cross_pairs(sub)` at 478)
- Test: `tests/test_course_queue.py` (append `TestStepTurnArrival`)

- [ ] **Step 1: Write the failing test**

Append this class to `tests/test_course_queue.py`:

```python
class TestStepTurnArrival(unittest.TestCase):
    """step_turn 在「记 history 后、接敌检测前」检测旗舰抵达 pending_turn_xy 并转向。"""

    def test_turn_applied_at_next_centre_18kn(self):
        # 从格心 (0,0) 出发,course E,18kn。发 course SE。
        # 下一格心 (1,0) 在 substep 6 抵达 -> 一个 step (sub0->6) 内转向。
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 3)
        f = g.fleets["F"]
        g.course_change("F", "SE")
        self.assertEqual(f.pending_course, "SE")
        g.step_turn()
        # 转向已生效:course=SE,anchor 钉在 (1,0) 格心,anchor_substep=6
        self.assertEqual(f.course, "SE")
        self.assertEqual(f.anchor_xy, fs.hex_center_xy(1, 0))
        self.assertAlmostEqual(f.anchor_substep, 6.0, delta=TOL)
        self.assertIsNone(f.pending_course)
        # 到本回合末(sub6)恰在格心 (1,0)(t_hit=6,剩余弧长 0)
        x, y = f.lead_xy(g.current_substep)
        self.assertAlmostEqual(x, 36000.0, delta=1e-3)
        self.assertAlmostEqual(y, 0.0, delta=1e-3)

    def test_t_hit_precision_12kn_fractional(self):
        # 12kn:到下一格心需 9 拍(36000/(12*333.33)=9),一个 step 只走 6 拍,未到。
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 12, 2)
        f = g.fleets["F"]
        g.course_change("F", "SE")
        g.step_turn()                       # sub0 -> sub6,弧长 24000 < 36000,未到
        self.assertEqual(f.course, "E")
        self.assertEqual(f.pending_course, "SE")
        g.step_turn()                       # sub6 -> sub12,跨过 sub9 抵达
        self.assertEqual(f.course, "SE")
        self.assertAlmostEqual(f.anchor_substep, 9.0, delta=TOL)
        self.assertEqual(f.anchor_xy, fs.hex_center_xy(1, 0))

    def test_t_hit_precision_24kn_half_substep(self):
        # 24kn:到下一格心需 4.5 拍(36000/(24*333.33)=4.5),一个 step 内抵达。
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 24, 2)
        f = g.fleets["F"]
        g.course_change("F", "SE")
        g.step_turn()
        self.assertEqual(f.course, "SE")
        self.assertAlmostEqual(f.anchor_substep, 4.5, delta=TOL)
        self.assertEqual(f.anchor_xy, fs.hex_center_xy(1, 0))

    def test_succession_trailing_ship_turns_at_same_centre(self):
        # 鱼贯:旗舰在 (1,0) 格心转 SE,后船在旗舰抵达同一格心后才跟转(滞后弧长)。
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 3)
        g.course_change("F", "SE")
        g.step_turn()                       # 旗舰已在 (1,0) 转向
        f = g.fleets["F"]
        ships = f.ship_positions(g.current_substep)   # sub6
        lead = ships[0][1]
        s2 = ships[1][1]
        # 旗舰在格心 (1,0);后船落后 500 弧长,仍在旧 E 段上(x<36000,y≈0)
        self.assertAlmostEqual(lead[0], 36000.0, delta=1e-3)
        self.assertAlmostEqual(lead[1], 0.0, delta=1e-3)
        self.assertLess(s2[0], 36000.0)
        self.assertAlmostEqual(s2[1], 0.0, delta=1.0)
        # 再走一拍,旗舰进入 SE 段(y>0),后船随后跟弯
        ahead = f.lead_xy(g.current_substep + 1)
        self.assertGreater(ahead[1], 0.0)

    def test_180_reversal_queues_to_forward_centre(self):
        # 180° 掉头(简化):排队到前方格心反向。course E -> W。
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 3)
        f = g.fleets["F"]
        g.course_change("F", "W")
        # 转向点是沿当前 E 航向的前方格心 (1,0),不是后方
        self.assertEqual(f.pending_turn_xy, fs.hex_center_xy(1, 0))
        g.step_turn()
        self.assertEqual(f.course, "W")
        self.assertEqual(f.anchor_xy, fs.hex_center_xy(1, 0))
        # 转向后沿 W 折返,sub7 的 x 应小于格心 x
        self.assertLess(f.lead_xy(g.current_substep + 1)[0], 36000.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_course_queue.TestStepTurnArrival -v`
Expected: FAIL — `test_turn_applied_at_next_centre_18kn` fails: `f.course` is still `"E"` and `f.pending_course` is still `"SE"` because `step_turn` never inspects pending turns.

- [ ] **Step 3: Write minimal implementation**

In `fleet_search.py`, find this block inside `step_turn` (lines 473-483):

```python
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
```

Replace it with:

```python
        for offset in range(1, 7):
            sub = self.current_substep + offset
            for f in self.fleets.values():
                if f.is_active(sub):
                    f.display_history.append((sub, *f.lead_xy(sub)))
            # 待转向到达检测(转向先于接敌判定生效):单拍弧长 <= 24*333.33 ~ 8000
            # < 36000,故一拍内最多触发一次。
            self._check_pending_turns(sub)
            pairs = self._cross_pairs(sub)
            hits = [(d, fa, fb) for (d, fa, fb) in pairs if d < self.visibility]
            if hits:
                result = self._resolve_encounter(sub)
                self.journal.record_turn(self.to_dict())
                return result
```

Then add the `_check_pending_turns` helper to `Game`, immediately after `_apply_pending_turn` (added in Task 4):

```python
    def _check_pending_turns(self, sub):
        """sub 为当前推进到的整数拍。对有 pending_course 的 fleet,若旗舰在
        (sub-1, sub] 之间沿当前航向抵达 pending_turn_xy,求精确分数拍 t_hit 并转向。"""
        EPS = 1e-6
        for f in self.fleets.values():
            if f.pending_course is None or f.pending_turn_xy is None:
                continue
            ux, uy = DIRVEC[f.course]
            turn_arc = ((f.pending_turn_xy[0] - f.anchor_xy[0]) * ux
                        + (f.pending_turn_xy[1] - f.anchor_xy[1]) * uy)
            arc_prev = f._arc_at(sub - 1)
            arc_now = f._arc_at(sub)
            if arc_prev < turn_arc <= arc_now + EPS:
                t_hit = f.anchor_substep + turn_arc / (f.speed * STEP_YARDS_PER_KNOT)
                self._apply_pending_turn(f, t_hit)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_course_queue.TestStepTurnArrival -v`
Expected: PASS (5 tests OK).

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py tests/test_course_queue.py
git commit -m "feat(course-queue): step_turn applies queued turn at next centre

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Entering CONTACT clears all pending turns + `_end_schedule` interop

**Files:**
- Modify: `fleet_search.py:533-536` (`_resolve_encounter` — where schedules are cleared, also clear pending)
- Test: `tests/test_course_queue.py` (append `TestContactClearsPending`)

- [ ] **Step 1: Write the failing test**

Append this class to `tests/test_course_queue.py`:

```python
class TestContactClearsPending(unittest.TestCase):
    """进入 CONTACT 时一并清空所有 fleet 的 pending(与清 schedule 对称)。"""

    def test_resolve_encounter_clears_pending(self):
        # 对冲接敌;给一支舰队挂一个未到达的 pending,接敌后应被清。
        g = fs.Game()
        g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 3)
        g.add_fleet("GE1", "GE", 0, "4,0", "W", 18, 2)
        g.schedule("GB1", 18, ["1,0", "2,0", "3,0"])
        g.schedule("GE1", 18, ["3,0", "2,0", "1,0"])
        # 手动给 GB1 埋一个 pending(模拟尚未到达的排队转向)
        gb = g.fleets["GB1"]
        gb.pending_course = "SE"
        gb.pending_turn_xy = fs.hex_center_xy(2, 0)
        g.step_turn()                       # 第 1 回合无接触
        g.step_turn()                       # 第 2 回合命中 -> CONTACT
        self.assertEqual(g.state, fs.STATE_CONTACT)
        for f in g.fleets.values():
            self.assertIsNone(f.pending_course, msg=f.name)
            self.assertIsNone(f.pending_speed, msg=f.name)
            self.assertIsNone(f.pending_turn_xy, msg=f.name)


class TestPendingAfterEndSchedule(unittest.TestCase):
    """_end_schedule 后 anchor 可能非格心(横向偏移),next_cell_center_along 仍正确。"""

    def test_course_after_schedule_with_lateral_offset(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 3)
        # 拐弯 schedule:E 然后 SE,使结束时 anchor 在格心 (但 course=SE)
        g.schedule("F", 18, ["1,0", "1,1", "2,1"])
        g.step_turn()                       # 第一回合走 3 格
        # schedule 结束后再发 course,应能在当前航向前方格心排队
        f = g.fleets["F"]
        g.clear_schedule("F")               # 若仍 scheduled 则清掉,保留位置/航向
        here = f.lead_xy(g.current_substep)
        g.course_change("F", "E")
        if f.pending_course is not None:    # 若与当前航向不同才会登记
            want = fs.next_cell_center_along(here, f.course)
            self.assertAlmostEqual(f.pending_turn_xy[0], want[0], delta=1e-3)
            self.assertAlmostEqual(f.pending_turn_xy[1], want[1], delta=1e-3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_course_queue.TestContactClearsPending tests.test_course_queue.TestPendingAfterEndSchedule -v`
Expected: FAIL — `test_resolve_encounter_clears_pending` fails: after CONTACT, `GB1.pending_course` is still `"SE"` because `_resolve_encounter` only clears schedules.

- [ ] **Step 3: Write minimal implementation**

In `fleet_search.py`, find this block in `_resolve_encounter` (lines 533-536):

```python
        # freeze at roll
        self.current_substep = max(roll, 0)
        for f in self.fleets.values():
            if f.scheduled:
                self.clear_schedule(f.name)
```

Replace with:

```python
        # freeze at roll
        self.current_substep = max(roll, 0)
        for f in self.fleets.values():
            if f.scheduled:
                self.clear_schedule(f.name)
            # 进 CONTACT 一并清空 pending 转向(与清 schedule 对称,spec §5.6)
            f.pending_course = None
            f.pending_speed = None
            f.pending_turn_xy = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_course_queue.TestContactClearsPending tests.test_course_queue.TestPendingAfterEndSchedule -v`
Expected: PASS (2 tests OK).

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py tests/test_course_queue.py
git commit -m "feat(course-queue): clear pending turns when entering CONTACT

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Save/load round-trip of pending + full regression (zero-regression gate)

**Files:**
- Test: `tests/test_course_queue.py` (append `TestPendingSaveLoadFile`)
- No source changes (this task is the integration + regression gate)

- [ ] **Step 1: Write the failing test**

Append this class to `tests/test_course_queue.py`:

```python
class TestPendingSaveLoadFile(unittest.TestCase):
    """save/load 文件往返恢复 pending(端到端,经 JSON 文件)。"""

    def test_file_roundtrip_preserves_pending(self):
        import os
        import tempfile
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 3)
        g.course_change("F", "SE", 24)      # 登记 pending(含 speed)
        f = g.fleets["F"]
        self.assertEqual(f.pending_course, "SE")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "pend.json")
            g.save(path)
            g2 = fs.Game()
            g2.load(path)
        f2 = g2.fleets["F"]
        self.assertEqual(f2.pending_course, "SE")
        self.assertEqual(f2.pending_speed, 24)
        self.assertAlmostEqual(f2.pending_turn_xy[0], f.pending_turn_xy[0], delta=1e-3)
        self.assertAlmostEqual(f2.pending_turn_xy[1], f.pending_turn_xy[1], delta=1e-3)
        self.assertIsInstance(f2.pending_turn_xy, tuple)
        # load 后继续推进:抵达格心应正常转向
        g2.step_turn()
        self.assertEqual(g2.fleets["F"].course, "SE")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_course_queue.TestPendingSaveLoadFile -v`
Expected: This test should already PASS if Tasks 2-5 are complete (serialization + course_change + step_turn all done). Run it to confirm; if it fails, it surfaces a real integration gap. If it passes, proceed — TDD here is the integration safety net rather than a new unit.

(If it unexpectedly fails on `pending_turn_xy` not being a `tuple`, re-check Task 2 step 3c's `tuple(pxy)` conversion.)

- [ ] **Step 3: No implementation change**

This task adds no source code — it is the integration assertion plus the regression gate. If Step 2 passed, there is nothing to implement.

- [ ] **Step 4: Run the full regression suite**

Run: `python -m unittest discover -s tests -t .`
Expected: OK — all existing tests plus the new `test_course_queue` classes pass, zero regressions.

Pay special attention that these unchanged tests still pass (they exercise the modified `course_change` / `step_turn` / `_resolve_encounter` / serialization):
- `tests/test_fleet_search.py` — `TestScheduleValidation.test_course_change_blocked_while_scheduled` (schedule mutex preserved), `TestEncounterRollback` (rollback to >vis substep unchanged), `TestSaveLoad` (round-trip unchanged).
- `tests/test_serialization.py` — formation fields + state round-trip (now also carries pending_* keys).
- `tests/test_post_encounter.py`, `tests/test_state_machine_loop.py` — CONTACT entry/exit (now also clears pending).

- [ ] **Step 5: Commit**

```bash
git add tests/test_course_queue.py
git commit -m "test(course-queue): file save/load round-trip + regression gate

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review notes (coverage vs spec §5)

- §5.2 three pending fields — Task 2.
- §5.3 `next_cell_center_along` (projection + ceil, EPS=1e-6) — Task 1.
- §5.4 step_turn arrival detection inserted after history, before encounter detection; `arc_prev < turn_arc <= arc_now+EPS`; float `t_hit` — Task 5.
- §5.5 `course_change` registers pending; schedule mutex still raises; same-course-no-speed-change returns; override keeps `pending_turn_xy` — Task 3.
- §5.6 180° queues to forward centre — Task 5 (`test_180_reversal_queues_to_forward_centre`); `_end_schedule` non-centre anchor — Task 6 (`TestPendingAfterEndSchedule`); enter CONTACT clears pending — Task 6.
- §8 serialization adds three fields with `d.get` backward-compat — Task 2.
- Acceptance: new `test_course_queue.py` green + full suite zero-regression — Task 7.
- Locked conventions (§9): turn point is a kinematic centre (not display snapping); float `anchor_substep`; `DIRVEC`/`hex_center_xy`/`xy_to_hex` reused; 18kn=6/12kn=9/24kn=4.5 substeps verified in tests; cross-side detection and >vis rollback paths untouched.

## Known risk points

1. **Single-level pending (not a queue):** a second `course` before the first turn point is reached overwrites the target but keeps `pending_turn_xy` (spec §5.5). If the user issues two turns expecting both to take effect at successive centres, only the latest target applies. Spec explicitly defers a multi-level queue ("扩展点:升级为队列"). Tests pin the overwrite semantics.
2. **`arc_prev < turn_arc <= arc_now+EPS` boundary:** relies on monotonic non-decreasing arc within a step and the single-trigger-per-step guarantee (max step arc ≈ 8000 < 36000). If a future change lets a fleet move backward in arc within a step, this window logic would need revisiting. Safe under current kinematics.
3. **`_end_schedule` leaving `course` set but anchor possibly mid-segment:** `next_cell_center_along` is designed not to require P on the centre line, but if a fleet's heading and lateral offset ever diverge by > APOTHEM the projection could pick a surprising centre (spec §5.6 flags this as not-occurring in pure-course mode). Phase C does not add the assert; covered descriptively only.
4. **Interaction with float `anchor_substep` downstream:** `_arc_at` and `lead_xy` already accept float anchors (used by `_end_schedule`), so `t_hit` floats are safe; the regression gate (Task 7) is the guard.
