# v6 Phase D — Replay & Demo Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `replay <turn>` restore clock/position/state self-consistently with a correct turn↔substep mapping (turn = substep // 6, turn 0 recorded before first step, encounter-rollback snapshots never steal a turn slot), and make `demo` walk a deterministic scripted polyline with at least two real turns instead of a near-straight beeline.

**Architecture:** Two independent changes. (1) `journal.py`'s `turns` list becomes `[{"turn": N, "snapshot": ...}]`; `record_turn` derives `N` from `snapshot["current_substep"] // 6` and overwrites the same-turn slot rather than appending; `snapshot_at_turn` / `latest_snapshot` work by turn key; `from_json` normalizes legacy bare-snapshot lists. `fleet_search.py`'s `step_turn` records turn 0 on entry when the journal is empty; `replay_to` raises `IndexError` on a missing turn. (2) `fleet_search.py` gains module-level `DEMO_LEG_SCRIPTS` / `scripted_walk_path` / `demo_path_for`; `run_demo` defaults `seed=0` and feeds `demo_path_for` through `schedule`, replacing `attracted_walk_path`. No dependency on Phase B/C.

**Tech Stack:** Python 3.10+, stdlib only for tests (`unittest`). `matplotlib` is only touched indirectly by `run_demo`/`plot_state`; new tests never import or trigger matplotlib (they call `demo_path_for`/`scripted_walk_path`/`step_turn` directly).

**Locked conventions honored (spec §9):** visibility cap 36000 (untouched here), rollback to the `>vis` substep (untouched), unified axial neighbour deltas via `NEIGH`/`DIRVEC`, 18kn = 6 substeps/hex via `HEX_PER_CYCLE`/`STEP_YARDS_PER_KNOT`, cross-side-only encounter detection (untouched), exact xy never snapped, `anchor_substep` may be float (untouched). `turn = current_substep // 6` is the locked replay caliber.

**Test runner:** all suites `python -m unittest discover -s tests -t .`; single module `python -m unittest tests.<mod> -v`. No pytest. Run all commands from the repo root `C:\Users\Administrator\Documents\Fleet`.

---

## Reference: current state (verified against source)

`journal.py` today:
- `self.turns = []` is a list of **bare snapshot dicts**.
- `record_turn(snapshot)` does `self.turns.append(snapshot)`.
- `latest_snapshot()` returns `self.turns[-1] if self.turns else None`.
- `snapshot_at_turn(turn)` returns `self.turns[turn]` when `0 <= turn < len(self.turns)`, else `None` (positional index, NOT turn-keyed).
- `to_json` serializes `"turns": self.turns`; `from_json` reads `self.turns = d.get("turns", [])` with no normalization.

`fleet_search.py` today:
- `step_turn` (line 460): no turn-0 priming; appends a snapshot via `self.journal.record_turn(self.to_dict())` at each of its return points.
- `replay_to` (line 691): `snap = self.journal.snapshot_at_turn(turn)`; `if snap is None: raise IndexError(...)`; `self.load_dict(snap)`. Because `snapshot_at_turn` is positional and `snap` is a bare dict, this currently passes a bare snapshot to `load_dict`. After Phase D, `snapshot_at_turn` returns the snapshot for the matching `turn` key.
- `run_demo` (line 920): `seed=None`; builds GB1/GE1; uses nested `attracted_schedule` → `attracted_walk_path`; loops `step_turn` + `plot_state`.
- `random_walk_path` (line 179), `attracted_walk_path` (line 198): `attracted_walk_path` is replaced as the demo driver but **left in place** (other code/tests may reference it; do not delete).
- Constants: `HEX_SIDE=36000.0`, `STEP_YARDS_PER_KNOT=36000/108`, `HEX_PER_CYCLE={12:2,18:3,24:4}`, `DIRECTION_LIST=['E','NE','NW','W','SW','SE']`, `NEIGH`, `OPPOSITE`, `DIRVEC`. `hex_neighbour(h,d)`, `direction_between(a,b)`, `hex_name(q,r)` → `"(q,r)"`, `xy_to_hex`, `lead_xy`, `Game.clock(substep)=hhmm(start_minute+substep*10)`.
- `Game.schedule(name, speed, hex_strs)` requires exactly `HEX_PER_CYCLE[speed]` waypoint strings, each adjacent to the previous, parsed by `parse_cell_or_hex` (accepts `"q,r"` axial strings). It snaps the anchor to the current hex centre and sets `course` from the first leg.

**File structure for this phase:**
- Modify `journal.py` — turn-keyed `turns`, derive/overwrite, turn-keyed lookup, legacy normalize.
- Modify `fleet_search.py` — `step_turn` turn-0 priming; `replay_to` (already raises IndexError, keep); add `DEMO_LEG_SCRIPTS` / `scripted_walk_path` / `demo_path_for`; rewrite `run_demo` to `seed=0` + `demo_path_for`.
- Create `tests/test_journal_turnkey.py`, `tests/test_replay.py`, `tests/test_demo_path.py`.
- Modify `tests/test_journal.py` (turn-key assertions), `tests/test_demo_convergence.py` (drop "contacts >= 6", assert no-crash + reproducibility).

---

## Task 1: Journal turns become turn-keyed records (`record_turn`, `latest_snapshot`, `snapshot_at_turn`)

**Files:**
- Test: `tests/test_journal_turnkey.py` (Create)
- Modify: `journal.py:19-28` (`record_turn`, `latest_snapshot`, `snapshot_at_turn`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_journal_turnkey.py`:

```python
import unittest
from journal import Journal


class TestJournalTurnKey(unittest.TestCase):
    def test_turn_derived_from_substep(self):
        j = Journal()
        j.record_turn({"current_substep": 0, "tag": "t0"})
        j.record_turn({"current_substep": 6, "tag": "t1"})
        j.record_turn({"current_substep": 12, "tag": "t2"})
        # turns is now a list of {"turn": N, "snapshot": ...}
        self.assertEqual([rec["turn"] for rec in j.turns], [0, 1, 2])
        self.assertEqual(j.snapshot_at_turn(0)["tag"], "t0")
        self.assertEqual(j.snapshot_at_turn(1)["tag"], "t1")
        self.assertEqual(j.snapshot_at_turn(2)["tag"], "t2")

    def test_lookup_is_by_turn_key_not_index(self):
        # Only turns 0 and 2 recorded; turn 1 absent.
        j = Journal()
        j.record_turn({"current_substep": 0, "tag": "t0"})
        j.record_turn({"current_substep": 12, "tag": "t2"})
        self.assertEqual(j.snapshot_at_turn(0)["tag"], "t0")
        self.assertIsNone(j.snapshot_at_turn(1))
        # Positional index would wrongly return t2 for turn 1; turn-key must not.
        self.assertEqual(j.snapshot_at_turn(2)["tag"], "t2")

    def test_same_turn_overwrites_not_appends(self):
        # Encounter rollback: substep 11 -> turn 1, same slot as substep 6.
        j = Journal()
        j.record_turn({"current_substep": 6, "tag": "t1a"})
        j.record_turn({"current_substep": 11, "tag": "t1b"})
        self.assertEqual([rec["turn"] for rec in j.turns], [1])
        self.assertEqual(j.snapshot_at_turn(1)["tag"], "t1b")

    def test_encounter_snapshot_does_not_steal_a_slot(self):
        j = Journal()
        j.record_turn({"current_substep": 0, "tag": "t0"})
        j.record_turn({"current_substep": 6, "tag": "t1"})
        # rollback to substep 11 (turn 1) then a clean turn 2 at substep 12
        j.record_turn({"current_substep": 11, "tag": "t1roll"})
        j.record_turn({"current_substep": 12, "tag": "t2"})
        self.assertEqual([rec["turn"] for rec in j.turns], [0, 1, 2])
        self.assertEqual(j.snapshot_at_turn(1)["tag"], "t1roll")
        self.assertEqual(j.snapshot_at_turn(2)["tag"], "t2")

    def test_latest_snapshot(self):
        j = Journal()
        self.assertIsNone(j.latest_snapshot())
        j.record_turn({"current_substep": 6, "tag": "t1"})
        j.record_turn({"current_substep": 12, "tag": "t2"})
        self.assertEqual(j.latest_snapshot()["tag"], "t2")


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_journal_turnkey -v`
Expected: FAIL. `test_turn_derived_from_substep` errors with `TypeError: list indices must be integers... 'str'` or `KeyError: 'turn'` (current `turns` holds bare dicts, so `rec["turn"]` raises). Other tests fail on the same shape mismatch.

- [ ] **Step 3: Write minimal implementation**

In `journal.py`, replace the three methods (`record_turn`, `latest_snapshot`, `snapshot_at_turn`, currently lines 19-28):

```python
    def record_turn(self, snapshot):
        turn = snapshot["current_substep"] // 6
        for rec in self.turns:
            if rec["turn"] == turn:
                rec["snapshot"] = snapshot
                return
        self.turns.append({"turn": turn, "snapshot": snapshot})

    def latest_snapshot(self):
        return self.turns[-1]["snapshot"] if self.turns else None

    def snapshot_at_turn(self, turn):
        for rec in self.turns:
            if rec["turn"] == turn:
                return rec["snapshot"]
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_journal_turnkey -v`
Expected: PASS (5 tests OK).

- [ ] **Step 5: Commit**

```bash
git add journal.py tests/test_journal_turnkey.py
git commit -m "feat(journal): turn-keyed turns list; derive turn from substep and overwrite same slot

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Journal `from_json` normalizes legacy bare snapshots; `to_json` round-trips new shape

**Files:**
- Test: `tests/test_journal_turnkey.py` (Modify — append a class)
- Modify: `journal.py:38-44` (`from_json`; add `_normalize_legacy`)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_journal_turnkey.py` (before the `if __name__` block):

```python
class TestJournalLegacyNormalize(unittest.TestCase):
    def test_legacy_bare_snapshots_normalized(self):
        import json
        # Old on-disk shape: turns is a list of bare snapshot dicts.
        legacy = json.dumps({
            "epoch_minute": 330,
            "visibility": 20000.0,
            "history": [],
            "turns": [
                {"current_substep": 0, "tag": "t0"},
                {"current_substep": 6, "tag": "t1"},
                {"current_substep": 12, "tag": "t2"},
            ],
        })
        j = Journal.from_json(legacy)
        self.assertEqual([rec["turn"] for rec in j.turns], [0, 1, 2])
        self.assertEqual(j.snapshot_at_turn(0)["tag"], "t0")
        self.assertEqual(j.snapshot_at_turn(2)["tag"], "t2")

    def test_legacy_rollback_snapshot_folds_into_turn(self):
        import json
        legacy = json.dumps({
            "turns": [
                {"current_substep": 6, "tag": "t1"},
                {"current_substep": 11, "tag": "t1roll"},
                {"current_substep": 12, "tag": "t2"},
            ],
        })
        j = Journal.from_json(legacy)
        self.assertEqual([rec["turn"] for rec in j.turns], [1, 2])
        self.assertEqual(j.snapshot_at_turn(1)["tag"], "t1roll")

    def test_new_shape_roundtrip(self):
        j = Journal(epoch_minute=330, visibility=20000.0)
        j.record_turn({"current_substep": 6, "tag": "t1"})
        j.record_turn({"current_substep": 12, "tag": "t2"})
        j2 = Journal.from_json(j.to_json())
        self.assertEqual([rec["turn"] for rec in j2.turns], [1, 2])
        self.assertEqual(j2.snapshot_at_turn(1)["tag"], "t1")
        self.assertEqual(j2.snapshot_at_turn(2)["tag"], "t2")
        self.assertEqual(j2.epoch_minute, 330)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_journal_turnkey.TestJournalLegacyNormalize -v`
Expected: FAIL. `test_legacy_bare_snapshots_normalized` fails with `KeyError: 'turn'` (legacy bare snapshots loaded as-is, `rec["turn"]` missing). `test_new_shape_roundtrip` also fails because `from_json` does not yet preserve/normalize the record shape.

- [ ] **Step 3: Write minimal implementation**

In `journal.py`, replace `from_json` (lines 38-44) and add `_normalize_legacy`:

```python
    @classmethod
    def from_json(cls, text):
        d = json.loads(text)
        j = cls(d.get("epoch_minute", 0), d.get("visibility", 0.0))
        j.history = d.get("history", [])
        j.turns = d.get("turns", [])
        j._normalize_legacy()
        return j

    def _normalize_legacy(self):
        """Upgrade an old bare-snapshot turns list to [{"turn":N,"snapshot":...}].

        New shape (records already carry 'turn') is left untouched, except that
        same-turn duplicates collapse to the last (rollback-wins) entry.
        """
        if not self.turns:
            return
        if all(isinstance(rec, dict) and "turn" in rec and "snapshot" in rec
               for rec in self.turns):
            # already new shape; still collapse any accidental same-turn dups
            collapsed = []
            for rec in self.turns:
                for existing in collapsed:
                    if existing["turn"] == rec["turn"]:
                        existing["snapshot"] = rec["snapshot"]
                        break
                else:
                    collapsed.append({"turn": rec["turn"], "snapshot": rec["snapshot"]})
            self.turns = collapsed
            return
        # legacy: list of bare snapshot dicts
        snaps = self.turns
        self.turns = []
        for snap in snaps:
            self.record_turn(snap)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_journal_turnkey -v`
Expected: PASS (8 tests OK total in this module).

- [ ] **Step 5: Commit**

```bash
git add journal.py tests/test_journal_turnkey.py
git commit -m "feat(journal): from_json normalizes legacy bare-snapshot turns to turn-keyed records

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Update existing `tests/test_journal.py` to turn-keyed assertions

**Files:**
- Modify: `tests/test_journal.py:6-26` (both test methods)

- [ ] **Step 1: Write the failing test**

This task updates the existing suite to match the new shape (the old assertions of bare-dict equality and positional-index semantics are now incorrect). Replace the whole body of `tests/test_journal.py`:

```python
import unittest
from journal import Journal


class TestJournal(unittest.TestCase):
    def test_record_and_access(self):
        j = Journal(epoch_minute=330, visibility=20000.0)
        j.record_command(330, "new GB1 GB 0 A13 E 18 3")
        j.record_turn({"current_substep": 6, "tag": "t1"})
        j.record_turn({"current_substep": 12, "tag": "t2"})
        self.assertEqual(len(j.history), 1)
        # turns now keyed by turn = substep // 6 -> turns 1 and 2
        self.assertEqual([rec["turn"] for rec in j.turns], [1, 2])
        self.assertEqual(j.latest_snapshot()["tag"], "t2")
        self.assertEqual(j.snapshot_at_turn(1)["tag"], "t1")
        self.assertEqual(j.snapshot_at_turn(2)["tag"], "t2")
        self.assertIsNone(j.snapshot_at_turn(5))

    def test_json_roundtrip(self):
        j = Journal(epoch_minute=330, visibility=20000.0)
        j.record_command(340, "step")
        j.record_turn({"current_substep": 6})
        text = j.to_json()
        j2 = Journal.from_json(text)
        self.assertEqual(j2.epoch_minute, 330)
        self.assertEqual(j2.visibility, 20000.0)
        self.assertEqual(j2.history, [{"sim_min": 340, "cmd": "step"}])
        self.assertEqual(j2.turns, [{"turn": 1, "snapshot": {"current_substep": 6}}])


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails (before edit) / passes (after edit)**

This step has no separate "before" state — the edit in Step 1 both rewrites the assertions and is the implementation (no production code changes). Run:

Run: `python -m unittest tests.test_journal -v`
Expected: PASS (2 tests OK). If it FAILS, the production change in Tasks 1-2 is wrong — fix there, not here.

- [ ] **Step 3: (no production code) — confirm Tasks 1-2 cover it**

No new implementation; Tasks 1 and 2 already provide turn-keyed `record_turn`/`snapshot_at_turn`/`from_json`. This task only realigns the legacy test file.

- [ ] **Step 4: Run full journal + integration suites**

Run: `python -m unittest tests.test_journal tests.test_journal_turnkey tests.test_journal_header tests.test_journal_integration -v`
Expected: PASS (all OK). If `test_journal_integration` or `test_journal_header` assert old `turns` shape, read them and update those assertions the same way (turn-keyed); they currently do not index `turns` positionally, so they should pass unchanged — but verify.

- [ ] **Step 5: Commit**

```bash
git add tests/test_journal.py
git commit -m "test(journal): assert turn-keyed turns list shape

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `step_turn` primes turn 0 before the first step

**Files:**
- Test: `tests/test_replay.py` (Create)
- Modify: `fleet_search.py:460` (`step_turn`, add priming at function entry)

- [ ] **Step 1: Write the failing test**

Create `tests/test_replay.py`:

```python
import unittest
import fleet_search as fs


def _two_fleet_game():
    g = fs.Game()
    g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 2)
    g.add_fleet("GE1", "GE", 0, "20,20", "W", 18, 2)
    return g


class TestTurnZeroPriming(unittest.TestCase):
    def test_turn_zero_recorded_before_first_step(self):
        g = _two_fleet_game()
        self.assertEqual(g.journal.turns, [])
        g.step_turn()
        turns = [rec["turn"] for rec in g.journal.turns]
        # turn 0 (initial board) must exist plus turn 1 (after first step)
        self.assertIn(0, turns)
        self.assertIn(1, turns)

    def test_turn_zero_snapshot_is_initial_board(self):
        g = _two_fleet_game()
        g.step_turn()
        snap0 = g.journal.snapshot_at_turn(0)
        self.assertIsNotNone(snap0)
        self.assertEqual(snap0["current_substep"], 0)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_replay.TestTurnZeroPriming -v`
Expected: FAIL. `test_turn_zero_recorded_before_first_step` fails: `turns` after one step is `[{"turn":1,...}]` (turn 0 missing), so `assertIn(0, turns)` fails.

- [ ] **Step 3: Write minimal implementation**

In `fleet_search.py`, insert priming as the first statement of `step_turn` (currently line 460-461 begins with `if self.state == STATE_CONTACT:`):

```python
    def step_turn(self):
        if not self.journal.turns:
            self.journal.record_turn(self.to_dict())
        if self.state == STATE_CONTACT:
```

(Everything below `if self.state == STATE_CONTACT:` is unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_replay.TestTurnZeroPriming -v`
Expected: PASS (2 tests OK).

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py tests/test_replay.py
git commit -m "fix(step_turn): record turn 0 snapshot before first step to avoid replay off-by-one

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `replay_to` restores clock + position + state; turn numbers match substeps; out-of-range raises IndexError

**Files:**
- Test: `tests/test_replay.py` (Modify — append classes)
- Modify: `fleet_search.py:691-696` (`replay_to`) — verify behavior; no code change expected (it already raises IndexError and calls `load_dict` on the turn-keyed snapshot)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_replay.py` (before the `if __name__` block):

```python
class TestTurnNumbersMatchSubstep(unittest.TestCase):
    def test_recorded_turns_track_substep_over_6(self):
        g = _two_fleet_game()
        for _ in range(5):
            g.step_turn()
        turns = sorted(rec["turn"] for rec in g.journal.turns)
        # turn 0 primed, then turns 1..5 from five steps
        self.assertEqual(turns, [0, 1, 2, 3, 4, 5])
        # each snapshot's substep == 6 * its turn
        for rec in g.journal.turns:
            self.assertEqual(rec["snapshot"]["current_substep"], 6 * rec["turn"])


class TestReplayResetsClockAndPosition(unittest.TestCase):
    def test_replay_resets_clock_and_position(self):
        g = _two_fleet_game()
        for _ in range(4):
            g.step_turn()
        # capture truth at turn 2
        snap2 = g.journal.snapshot_at_turn(2)
        gb_xy_at2 = None
        # advance further so current state differs from turn 2
        g.step_turn()
        self.assertNotEqual(g.current_substep, 12)
        # now replay to turn 2
        g.replay_to(2)
        self.assertEqual(g.current_substep, 12)
        self.assertEqual(g.clock(g.current_substep), fs.hhmm(g.start_minute + 12 * 10))
        # position is lead_xy(current_substep) recomputed from restored anchors
        gb = g.fleets["GB1"]
        # GB1 started at hex 0,0 heading E at 18kn -> 12 substeps = 2 hexes east
        expect_x = 2 * fs.HEX_SIDE
        self.assertAlmostEqual(gb.lead_xy(g.current_substep)[0], expect_x, places=3)
        self.assertAlmostEqual(gb.lead_xy(g.current_substep)[1], 0.0, places=3)

    def test_replay_then_continue_is_consistent(self):
        g = _two_fleet_game()
        for _ in range(4):
            g.step_turn()
        g.replay_to(2)
        # continuing from replayed turn-2 board advances cleanly
        g.step_turn()
        self.assertEqual(g.current_substep, 18)

    def test_replay_state_restored(self):
        g = _two_fleet_game()
        g.step_turn()
        g.replay_to(0)
        self.assertEqual(g.state, fs.STATE_SEARCH)
        self.assertEqual(g.current_substep, 0)


class TestReplayOutOfRange(unittest.TestCase):
    def test_replay_out_of_range_raises_indexerror(self):
        g = _two_fleet_game()
        for _ in range(3):
            g.step_turn()
        with self.assertRaises(IndexError):
            g.replay_to(99)

    def test_replay_missing_turn_raises(self):
        # negative / never-recorded turn
        g = _two_fleet_game()
        g.step_turn()
        with self.assertRaises(IndexError):
            g.replay_to(-5)
```

- [ ] **Step 2: Run test to verify it fails / passes**

Run: `python -m unittest tests.test_replay -v`
Expected: After Task 4's priming and Tasks 1-2's turn-keyed lookup, these should largely PASS. If any FAIL, the most likely culprit is `replay_to` receiving a record dict instead of a snapshot. Confirm `replay_to` (lines 691-696) reads:

```python
    def replay_to(self, turn):
        """把盘面恢复到日志里第 turn 个回合快照(0 起)。不改动日志本身。"""
        snap = self.journal.snapshot_at_turn(turn)
        if snap is None:
            raise IndexError(f"no snapshot for turn {turn}")
        self.load_dict(snap)
```

`snapshot_at_turn` (Task 1) already returns the bare snapshot (`rec["snapshot"]`), so `load_dict(snap)` gets the correct dict and `IndexError` fires on missing turns. No code change should be needed.

- [ ] **Step 3: Write minimal implementation (only if Step 2 revealed a gap)**

If and only if Step 2 shows `replay_to` passing a record instead of a snapshot (i.e., a regression), ensure `snapshot_at_turn` returns `rec["snapshot"]` (already done in Task 1). Otherwise no production change in this task — it is a behavioral lock-in test over Tasks 1, 2, 4.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_replay -v`
Expected: PASS (all classes/tests OK).

- [ ] **Step 5: Commit**

```bash
git add tests/test_replay.py
git commit -m "test(replay): lock turn<->substep mapping, clock/position/state reset, out-of-range IndexError

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Encounter-rollback snapshot does not steal a turn slot (end-to-end replay)

**Files:**
- Test: `tests/test_replay.py` (Modify — append a class)
- Modify: none expected (Task 1 overwrite-by-turn already enforces this; this is an integration lock)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_replay.py` (before the `if __name__` block):

```python
class TestEncounterDoesNotStealSlot(unittest.TestCase):
    def _contact_game(self):
        # Place GB and GE close enough to contact within a few substeps.
        g = fs.Game()
        g.visibility = fs.DEFAULT_VISIBILITY  # 20000
        g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 2)
        # one hex east is 36000 yd; head-on closing should contact mid-turn
        g.add_fleet("GE1", "GE", 0, "1,0", "W", 18, 2)
        return g

    def test_rollback_snapshot_folds_into_its_turn(self):
        g = self._contact_game()
        # step until contact (rollback) or a few turns
        for _ in range(4):
            res = g.step_turn()
            if res:
                break
        self.assertEqual(g.state, fs.STATE_CONTACT)
        # every recorded turn key is unique and equals snapshot substep // 6
        keys = [rec["turn"] for rec in g.journal.turns]
        self.assertEqual(len(keys), len(set(keys)), "duplicate turn slots recorded")
        for rec in g.journal.turns:
            self.assertEqual(rec["turn"], rec["snapshot"]["current_substep"] // 6)

    def test_replay_to_rollback_turn_loads_frozen_board(self):
        g = self._contact_game()
        for _ in range(4):
            res = g.step_turn()
            if res:
                break
        self.assertEqual(g.state, fs.STATE_CONTACT)
        frozen_sub = g.current_substep
        contact_turn = frozen_sub // 6
        # advance is blocked in CONTACT unless cleared; just replay back to it
        g.replay_to(contact_turn)
        self.assertEqual(g.current_substep, frozen_sub)
        self.assertEqual(g.state, fs.STATE_CONTACT)
```

- [ ] **Step 2: Run test to verify it fails / passes**

Run: `python -m unittest tests.test_replay.TestEncounterDoesNotStealSlot -v`
Expected: PASS after Task 1 (same-turn overwrite). If `test_replay_to_rollback_turn_loads_frozen_board` fails on `current_substep`, it means a rollback snapshot at e.g. substep 11 (turn 1) was appended as a separate slot from substep 6 — re-check Task 1's `record_turn` overwrite branch.

Note on the scenario: GB at hex `0,0` heading E and GE at hex `1,0` (36000 yd east) heading W close at 2*18kn. With `STEP_YARDS_PER_KNOT=333.33`, each closes 6000 yd/substep, combined 12000 yd/substep; gap 36000 reaches `<20000` near substep 2 → contact and rollback inside turn 1. The test does not assert the exact substep, only that the turn slot is not duplicated and replay restores the frozen board.

- [ ] **Step 3: Write minimal implementation (only if needed)**

No production change expected. If a duplicate slot appears, the bug is in `journal.record_turn` (Task 1) — fix it there, not here.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_replay -v`
Expected: PASS (all tests OK).

- [ ] **Step 5: Commit**

```bash
git add tests/test_replay.py
git commit -m "test(replay): encounter rollback folds into its turn slot, replay restores frozen board

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Deterministic scripted demo paths (`DEMO_LEG_SCRIPTS`, `scripted_walk_path`, `demo_path_for`)

**Files:**
- Test: `tests/test_demo_path.py` (Create)
- Modify: `fleet_search.py` — add module-level `DEMO_LEG_SCRIPTS`, `scripted_walk_path`, `_has_turn`, `demo_path_for` immediately after `attracted_walk_path` (after line 225, before `def hhmm`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_demo_path.py`:

```python
import random
import unittest
import fleet_search as fs


class TestScriptedWalkPath(unittest.TestCase):
    def test_scripted_walk_follows_script(self):
        # script: 2 east then 2 southeast -> one turn
        path = fs.scripted_walk_path((0, 0), [("E", 2), ("SE", 2)], bound=40)
        self.assertEqual(path, [(1, 0), (2, 0), (2, 1), (2, 2)])

    def test_scripted_walk_stops_at_bound(self):
        # bound=2: stepping E from (0,0) hits |q|>2 after (2,0)
        path = fs.scripted_walk_path((0, 0), [("E", 10)], bound=2)
        self.assertEqual(path, [(1, 0), (2, 0)])

    def test_scripted_walk_each_step_is_neighbour(self):
        path = fs.scripted_walk_path((0, 0), [("E", 1), ("NE", 1), ("NW", 1)], bound=40)
        cur = (0, 0)
        for nxt in path:
            self.assertIsNotNone(fs.direction_between(cur, nxt))
            cur = nxt


class TestDemoPathFor(unittest.TestCase):
    def test_reproducible_same_seed(self):
        p1 = fs.demo_path_for((0, 0), 18, random.Random(0), bound=40)
        p2 = fs.demo_path_for((0, 0), 18, random.Random(0), bound=40)
        self.assertEqual(p1, p2)

    def test_length_matches_speed_cycle(self):
        for speed in (12, 18, 24):
            p = fs.demo_path_for((0, 0), speed, random.Random(0), bound=40)
            self.assertEqual(len(p), fs.HEX_PER_CYCLE[speed])

    def test_path_has_at_least_two_directions(self):
        # gather over the full untruncated script to guarantee >=2 turns exist
        for seed in range(6):
            full = fs.demo_full_script_path((0, 0), random.Random(seed), bound=40)
            dirs = []
            cur = (0, 0)
            for nxt in full:
                d = fs.direction_between(cur, nxt)
                if d is not None and (not dirs or dirs[-1] != d):
                    dirs.append(d)
                cur = nxt
            # at least 2 distinct adjacent legs -> at least one real turn;
            # spec requires >=2 turns in the full script
            self.assertGreaterEqual(len(set(dirs)), 2)

    def test_has_turn_helper(self):
        self.assertTrue(fs._has_turn([(1, 0), (2, 0), (2, 1)]))      # E then SE
        self.assertFalse(fs._has_turn([(1, 0), (2, 0), (3, 0)]))      # all E
        self.assertFalse(fs._has_turn([(1, 0)]))                     # too short


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_demo_path -v`
Expected: FAIL with `AttributeError: module 'fleet_search' has no attribute 'scripted_walk_path'` (and same for `demo_path_for`, `_has_turn`, `demo_full_script_path`).

- [ ] **Step 3: Write minimal implementation**

In `fleet_search.py`, immediately after `attracted_walk_path` (after its `return out[:n]` at line 225, before `def hhmm`), add:

```python
# ---------------------------------------------------------------------------
# Deterministic demo paths (scripted; no reliance on true randomness)
# ---------------------------------------------------------------------------

# Each script is a list of (direction, count) legs. Every script contains at
# least two distinct directions, i.e. >= 2 turns over its full length, so a demo
# fleet visibly turns instead of beelining.  Directions are axial NEIGH keys.
DEMO_LEG_SCRIPTS = [
    [("E", 2), ("SE", 2), ("E", 2), ("NE", 2)],    # zig-zag (S then back N)
    [("SE", 2), ("E", 2), ("NE", 2), ("E", 2)],    # S-curve
    [("E", 3), ("SE", 3), ("SW", 3)],              # wide single bend then back
    [("E", 1), ("SE", 1), ("E", 1), ("SE", 1),
     ("E", 1), ("SE", 1)],                         # fine sawtooth
    [("NE", 2), ("E", 2), ("SE", 2), ("E", 2)],    # N-then-S arc
]


def _has_turn(path):
    """True if the path (list of axial hexes) changes direction at least once."""
    if len(path) < 3:
        return False
    prev_dir = None
    cur = None
    seen = []
    # reconstruct leg directions between consecutive hexes
    for i in range(1, len(path)):
        d = direction_between(path[i - 1], path[i])
        if d is not None:
            seen.append(d)
    return len(set(seen)) >= 2


def scripted_walk_path(start, script, bound=40):
    """Walk `start` along a list of (direction, count) legs, one hex per step,
    stopping early if a step would exceed +/- `bound` on either axis.
    Returns the list of visited hexes (excluding start)."""
    cur = start
    out = []
    for d, count in script:
        for _ in range(count):
            nb = hex_neighbour(cur, d)
            if abs(nb[0]) > bound or abs(nb[1]) > bound:
                return out
            cur = nb
            out.append(cur)
    return out


def demo_full_script_path(start, rng, bound=40):
    """Pick one DEMO_LEG_SCRIPTS entry via rng and walk its full length."""
    script = rng.choice(DEMO_LEG_SCRIPTS)
    return scripted_walk_path(start, script, bound=bound)


def demo_path_for(start, speed, rng, bound=40):
    """Deterministic-per-rng demo path of exactly HEX_PER_CYCLE[speed] hexes,
    truncated from a scripted polyline that contains at least one turn.
    If truncation would drop all turns, rotate to the next script until the
    truncated head still turns (the fine sawtooth guarantees a turn within 2)."""
    n = HEX_PER_CYCLE[speed]
    scripts = list(DEMO_LEG_SCRIPTS)
    rng.shuffle(scripts)
    best = None
    for script in scripts:
        full = scripted_walk_path(start, script, bound=bound)
        head = full[:n]
        if len(head) == n:
            if best is None:
                best = head
            if _has_turn(head):
                return head
    # fall back: sawtooth turns within 2 hexes, so for n>=2 it always turns;
    # `best` holds a full-length head even if it failed _has_turn (n could be <2)
    return best if best is not None else scripted_walk_path(start, scripts[0], bound=bound)[:n]
```

Notes for the implementer:
- `_has_turn` for `n==2` (12kn) is `False` only if both legs share a direction; the sawtooth script `[("E",1),("SE",1),...]` yields head `[E, SE]` which turns, so the loop returns it. For 18/24kn (`n>=3`) most scripts turn within the head.
- `demo_path_for` is reproducible for a given `rng` because it only consumes `rng.shuffle` once.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_demo_path -v`
Expected: PASS (all tests OK).

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py tests/test_demo_path.py
git commit -m "feat(demo): deterministic scripted demo paths with >=2 turns

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: `run_demo` uses `seed=0` default and `demo_path_for` via `schedule`; step produces a turning track

**Files:**
- Test: `tests/test_demo_path.py` (Modify — append a class)
- Modify: `fleet_search.py:920-971` (`run_demo`)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_demo_path.py` (before the `if __name__` block):

```python
class TestStepTurnFollowsScript(unittest.TestCase):
    def test_schedule_from_demo_path_makes_track_turn(self):
        g = fs.Game()
        g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 2)
        rng = random.Random(0)
        path = fs.demo_path_for((0, 0), 18, rng, bound=40)
        g.schedule("GB1", 18, [fs.hex_name(*h) for h in path])
        # advance one full turn (6 substeps) so display_history records the bend
        g.step_turn()
        gb = g.fleets["GB1"]
        hist = [(x, y) for (_sub, x, y) in gb.display_history]
        # reconstruct hex sequence and confirm a direction change occurred
        hexes = [fs.xy_to_hex(x, y) for (x, y) in hist]
        dirs = []
        for i in range(1, len(hexes)):
            d = fs.direction_between(hexes[i - 1], hexes[i])
            if d is not None and (not dirs or dirs[-1] != d):
                dirs.append(d)
        self.assertGreaterEqual(len(set(dirs)), 2)


class TestRunDemoDefaults(unittest.TestCase):
    def tearDown(self):
        import glob, os
        for f in glob.glob("_demotest_*.png"):
            try:
                os.remove(f)
            except OSError:
                pass

    def test_run_demo_default_seed_runs(self):
        # seed defaults to 0; should run without raising even if no contact
        g = fs.Game()
        files = fs.run_demo(g, max_turns=5, frame_prefix="_demotest")
        self.assertTrue(len(files) >= 1)

    def test_run_demo_reproducible(self):
        g1 = fs.Game()
        fs.run_demo(g1, seed=3, max_turns=4, frame_prefix="_demotest")
        g2 = fs.Game()
        fs.run_demo(g2, seed=3, max_turns=4, frame_prefix="_demotest")
        self.assertEqual(g1.current_substep, g2.current_substep)
        # same fleet centre positions
        for name in g1.fleets:
            self.assertAlmostEqual(
                g1.fleets[name].lead_xy(g1.current_substep)[0],
                g2.fleets[name].lead_xy(g2.current_substep)[0], places=3)
```

Note: `TestStepTurnFollowsScript` does not import matplotlib (it never calls `run_demo`/`plot_state`). `TestRunDemoDefaults` calls `run_demo`, which calls `plot_state` (matplotlib). If matplotlib is unavailable in the runner, those two methods will error on import inside `plot_state` — to keep the suite stdlib-only and robust, wrap them as shown in Step 3 of Task 9 (skip-on-import-error). For Task 8 they are written assuming matplotlib is installed per CLAUDE.md (`pip install matplotlib`).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_demo_path.TestStepTurnFollowsScript tests.test_demo_path.TestRunDemoDefaults -v`
Expected: `TestStepTurnFollowsScript` PASSES already (it uses `demo_path_for` + `schedule`, both now present). `TestRunDemoDefaults.test_run_demo_default_seed_runs` may FAIL if the runner cannot reproduce because old `run_demo` had `seed=None` — but `seed=None` still runs; the real driver-replacement assertion is `test_run_demo_reproducible`, which can FAIL under the old `attracted_walk_path` if it relied on global RNG state differently. Treat any FAIL/ERROR here as the trigger for Step 3.

- [ ] **Step 3: Write minimal implementation**

In `fleet_search.py`, rewrite `run_demo` (lines 920-971). Replace the entire function with:

```python
def run_demo(g, seed=0, max_turns=30, frame_prefix='demo'):
    g.fleets.clear(); g.current_substep = 0; g.last_report = None
    g.rng = random.Random(seed); g.visibility = DEFAULT_VISIBILITY
    rng = g.rng
    g.add_fleet("GB1", "GB", 0, f"{rng.randint(-3,1)},{rng.randint(-2,2)}", "E", 18, 4)
    g.add_fleet("GE1", "GE", 0, f"{rng.randint(3,7)},{rng.randint(3,7)}", "W", 18, 3)

    def scripted_schedule(name):
        """Give `name` a deterministic scripted course with at least one turn."""
        f = g._get(name)
        speed = rng.choice([12, 18, 24])
        cur = xy_to_hex(*f.lead_xy(g.current_substep))
        path = demo_path_for(cur, speed, rng, bound=40)
        if len(path) == HEX_PER_CYCLE[speed]:
            try:
                g.schedule(name, speed, [hex_name(*h) for h in path])
            except Exception:
                pass

    # Initial schedules
    try: scripted_schedule("GB1")
    except Exception: pass
    try: scripted_schedule("GE1")
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
                try: scripted_schedule(n)
                except Exception: pass
    print(f"  demo: no contact in {max_turns} turns")
    return files
```

Key changes: `seed=0` default; `attracted_walk_path`/`attracted_schedule` replaced by `demo_path_for` via `scripted_schedule`; waypoints passed as axial `hex_name(*h)` strings (avoids `coords.cell_name` off-map `ValueError`); contact is no longer the goal. `attracted_walk_path` and `random_walk_path` remain defined for other callers.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_demo_path -v`
Expected: PASS (all tests OK).

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py tests/test_demo_path.py
git commit -m "fix(demo): run_demo defaults seed=0 and drives fleets with deterministic scripted turning paths

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Realign `tests/test_demo_convergence.py` (drop "contacts >= 6"; assert no-crash + reproducibility)

**Files:**
- Modify: `tests/test_demo_convergence.py:1-25` (replace body)

- [ ] **Step 1: Write the failing test**

The old test asserted demo reaches contact in >=6 of 8 seeds, which depended on the now-removed attraction behavior. Replace the whole body of `tests/test_demo_convergence.py`:

```python
import glob
import os
import unittest

try:
    import fleet_search as fs
    _HAVE_FS = True
    try:
        import matplotlib  # noqa: F401
        _HAVE_MPL = True
    except Exception:
        _HAVE_MPL = False
except Exception:
    _HAVE_FS = False
    _HAVE_MPL = False


@unittest.skipUnless(_HAVE_FS and _HAVE_MPL, "needs fleet_search + matplotlib")
class TestDemoConvergence(unittest.TestCase):
    def test_demo_runs_without_crashing(self):
        # Demo no longer guarantees contact; it must run cleanly for several seeds.
        for seed in range(4):
            g = fs.Game()
            files = fs.run_demo(g, seed=seed, max_turns=10, frame_prefix="_convtest")
            self.assertTrue(len(files) >= 1)

    def test_demo_reproducible_same_seed(self):
        g1 = fs.Game()
        fs.run_demo(g1, seed=2, max_turns=6, frame_prefix="_convtest")
        g2 = fs.Game()
        fs.run_demo(g2, seed=2, max_turns=6, frame_prefix="_convtest")
        self.assertEqual(g1.current_substep, g2.current_substep)
        self.assertEqual(g1.state, g2.state)
        self.assertEqual(set(g1.fleets), set(g2.fleets))
        for name in g1.fleets:
            x1 = g1.fleets[name].lead_xy(g1.current_substep)
            x2 = g2.fleets[name].lead_xy(g2.current_substep)
            self.assertAlmostEqual(x1[0], x2[0], places=3)
            self.assertAlmostEqual(x1[1], x2[1], places=3)

    def tearDown(self):
        for f in glob.glob("_convtest_*.png"):
            try:
                os.remove(f)
            except OSError:
                pass


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m unittest tests.test_demo_convergence -v`
Expected: PASS (2 tests OK, or SKIPPED if matplotlib is absent). It must NOT fail with the old `assertGreaterEqual(hits, 6)`.

- [ ] **Step 3: (no production change) — confirm Task 8 covers it**

No new implementation; this realigns the convergence suite to the new demo contract from Task 8.

- [ ] **Step 4: Run the full demo + replay + journal suites together**

Run: `python -m unittest tests.test_demo_path tests.test_demo_convergence tests.test_replay tests.test_journal tests.test_journal_turnkey -v`
Expected: PASS / SKIPPED (no failures).

- [ ] **Step 5: Commit**

```bash
git add tests/test_demo_convergence.py
git commit -m "test(demo): convergence suite asserts no-crash + reproducibility instead of contact frequency

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Full regression — zero regression gate

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `python -m unittest discover -s tests -t .`
Expected: `OK` (no failures, no errors; SKIPPED allowed only for matplotlib-gated demo cases). Counts should equal the prior baseline plus the new `test_journal_turnkey`, `test_replay`, `test_demo_path` tests.

- [ ] **Step 2: If anything fails, debug with systematic-debugging**

Likely suspects and resolutions:
- `tests/test_journal_integration.py` or `tests/test_journal_header.py` asserting old `turns` shape → update those assertions to turn-keyed (`rec["turn"]` / `snapshot_at_turn`), mirroring Task 3. Read the file first; only change assertions that index `turns` positionally or compare bare-dict equality.
- `tests/test_serialization.py` round-tripping a journal with old `turns` → if it constructs a Journal and asserts `turns` equality, update to the `{"turn":N,"snapshot":...}` shape.
- Any other suite that calls `run_demo` with positional/keyword `seed` → default is now `0`; explicit `seed=` calls are unaffected.

Do NOT change production behavior to satisfy a stale assertion — fix the assertion to the new (correct) contract.

- [ ] **Step 3: Re-run to confirm green**

Run: `python -m unittest discover -s tests -t .`
Expected: `OK`.

- [ ] **Step 4: Commit any test realignments**

```bash
git add tests/
git commit -m "test: realign remaining suites to turn-keyed journal and scripted demo

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

(If Step 1 was already green with no extra changes, skip this commit.)

---

## Self-Review

**Spec §7 coverage:**
- §7.1 `turns` → `[{turn,snapshot}]`: Task 1. `record_turn` derives `turn = current_substep // 6`, same-turn overwrite: Task 1. `snapshot_at_turn`/`latest_snapshot` by turn key: Task 1. `from_json` + `_normalize_legacy`: Task 2. `step_turn` primes turn 0 when empty: Task 4. `replay_to` self-consistent clock/position/state + IndexError: Tasks 5, 6 (no code change — already correct given Tasks 1/4). Encounter rollback not stealing a slot: Tasks 1, 6.
- §7.2 demo: `DEMO_LEG_SCRIPTS` + `scripted_walk_path` + `demo_path_for` (deterministic, >=2 turns): Task 7. `run_demo` `seed=0` default + `demo_path_for` replacing `attracted_walk_path`: Task 8. Adjust `test_demo_convergence` (no "contacts >= 6"): Task 9. Adjust `test_journal` turn-key: Task 3.

**Acceptance tests mapped:** turn-0 priming (Task 4), turn number matches substep (Task 5), replay resets clock+position (Task 5), encounter turn not crowding index (Task 6), out-of-range IndexError (Task 5), lookup by turn not index (Task 1), legacy bare-snapshot normalize (Task 2), `demo_path_for` reproducible + >=2 directions (Task 7), step_turn after scripted schedule produces a turning track (Task 8). Adjusted `test_demo_convergence` (Task 9), `test_journal` turn-key (Task 3).

**Placeholder scan:** none — every step has real code/commands.

**Type/name consistency:** `journal.turns` records are `{"turn": int, "snapshot": dict}` everywhere; `snapshot_at_turn` returns the bare snapshot dict (consumed by `Game.load_dict`); `demo_path_for(start, speed, rng, bound=40)`, `scripted_walk_path(start, script, bound=40)`, `demo_full_script_path(start, rng, bound=40)`, `_has_turn(path)` consistent across Tasks 7-8 and tests. `run_demo(g, seed=0, max_turns=30, frame_prefix='demo')` matches existing call sites (keyword `seed=`/`max_turns=`/`frame_prefix=`).

**Locked-convention check:** `turn = substep // 6` (spec §9), `anchor_substep` float untouched, axial `NEIGH`/`hex_neighbour`/`direction_between` for paths, `HEX_PER_CYCLE`/`hex_name` for schedule strings, visibility/rollback/cross-side detection all untouched.
