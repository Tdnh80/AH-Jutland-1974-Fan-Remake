# v5 Plan 4 — 操作日志 journal + replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 把 v4 的「单一状态快照 save/load」升级为「操作历史 + 每回合结果」日志(可回放);并补全序列化以包含 Plan 2/3 新增的队形与状态字段。

**Architecture:** 新增纯数据模块 `journal.py`(`Journal` 类:命令历史 + 每回合快照 + JSON 读写 + 按回合取快照)。`Game` 持有一个 `Journal`,每次 `step_turn` 推进后记录当回合快照;`save` 写出整本日志(含历史与全部回合快照)+ 最新状态,`load` 从中恢复,`replay_to(turn)` 跳到任意回合的盘面。每回合快照复用 `Game.to_dict()`(本 plan 先把它补全)。

**Tech Stack:** Python 3.10+,stdlib `json` / `unittest`。

---

### Task 1: 补全状态序列化(含队形 + 状态字段)

**Files:**
- Modify: `fleet_search.py`(`Game._fleet_to_dict` / `_fleet_from_dict` / `to_dict` / `load_dict`)
- Test: `test_serialization.py`

**背景给实现者:** `fleet_search.py` 的 `Game` 已有 `_fleet_to_dict`(staticmethod)、`_fleet_from_dict`(staticmethod)、`to_dict`、`load_dict`、`save`、`load`(v4 加的状态快照)。但 Plan 2 给 `Fleet` 加了 `formation_kind / spacing / deploy / echelon_deg / pos_mode / layout_heading`,Plan 3 给 `Game` 加了 `state / contact_hexes`——这些目前**没有**被序列化,save/load 会丢失。本任务把它们补进去。请用下面的完整方法体**替换**现有同名方法(保持方法位置与 `@staticmethod` 装饰不变)。

- [ ] **Step 1: Write the failing test**

写入 `test_serialization.py`:

```python
import unittest
import fleet_search as fs
import formation as fm


class TestSerialization(unittest.TestCase):
    def test_fleet_formation_fields_roundtrip(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "1,2", "E", 18, 3)
        f = g.fleets["F"]
        f.formation_kind = fm.LINE_ABREAST
        f.deploy = "left"
        f.echelon_deg = 30.0
        f.pos_mode = fm.ABS_MODE
        f.layout_heading = (1.0, 0.0)
        d = g.to_dict()
        g2 = fs.Game()
        g2.load_dict(d)
        f2 = g2.fleets["F"]
        self.assertEqual(f2.formation_kind, fm.LINE_ABREAST)
        self.assertEqual(f2.deploy, "left")
        self.assertEqual(f2.echelon_deg, 30.0)
        self.assertEqual(f2.pos_mode, fm.ABS_MODE)
        self.assertEqual(tuple(f2.layout_heading), (1.0, 0.0))

    def test_game_state_and_contact_hexes_roundtrip(self):
        g = fs.Game()
        g.state = fs.STATE_CONTACT
        g.contact_hexes = {(2, 0), (3, -1)}
        g2 = fs.Game()
        g2.load_dict(g.to_dict())
        self.assertEqual(g2.state, fs.STATE_CONTACT)
        self.assertEqual(g2.contact_hexes, {(2, 0), (3, -1)})

    def test_default_fleet_roundtrip_unchanged(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 2)
        g2 = fs.Game()
        g2.load_dict(g.to_dict())
        self.assertEqual(g2.fleets["F"].formation_kind, fm.LINE_AHEAD)
        self.assertEqual(g2.fleets["F"].course, "E")
        self.assertEqual(len(g2.fleets["F"].ships), 2)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest test_serialization -v`
Expected: FAIL —— 队形字段/`contact_hexes` 丢失(AssertionError 或 KeyError)。

- [ ] **Step 3: Replace the four methods**

把 `Game._fleet_to_dict` 替换为:

```python
    @staticmethod
    def _fleet_to_dict(f):
        return {
            'name': f.name, 'side': f.side, 'activated_turn': f.activated_turn,
            'anchor_xy': list(f.anchor_xy), 'anchor_substep': f.anchor_substep,
            'course': f.course, 'speed': f.speed,
            'ships': [s.name for s in f.ships],
            'scheduled': f.scheduled, 'schedule_end_substep': f.schedule_end_substep,
            'waypoints': [list(w) for w in f.waypoints],
            'display_history': [list(h) for h in f.display_history],
            'formation_kind': f.formation_kind, 'spacing': f.spacing,
            'deploy': f.deploy, 'echelon_deg': f.echelon_deg,
            'pos_mode': f.pos_mode,
            'layout_heading': list(f.layout_heading) if f.layout_heading is not None else None,
        }
```

把 `Game._fleet_from_dict` 替换为:

```python
    @staticmethod
    def _fleet_from_dict(d):
        lh = d.get('layout_heading')
        f = Fleet(
            name=d['name'], side=d['side'], activated_turn=d['activated_turn'],
            anchor_xy=tuple(d['anchor_xy']), anchor_substep=d['anchor_substep'],
            course=d['course'], speed=d['speed'],
            ships=[Ship(n) for n in d['ships']],
            scheduled=d['scheduled'], schedule_end_substep=d['schedule_end_substep'],
            waypoints=[tuple(w) for w in d['waypoints']],
            display_history=[tuple(h) for h in d['display_history']],
        )
        f.formation_kind = d.get('formation_kind', formation.LINE_AHEAD)
        f.spacing = d.get('spacing', DEFAULT_SPACING)
        f.deploy = d.get('deploy', 'right')
        f.echelon_deg = d.get('echelon_deg', 45.0)
        f.pos_mode = d.get('pos_mode', formation.REL_MODE)
        f.layout_heading = tuple(lh) if lh is not None else None
        return f
```

把 `Game.to_dict` 替换为:

```python
    def to_dict(self):
        return {
            'version': 5,
            'current_substep': self.current_substep,
            'visibility': self.visibility,
            'start_minute': self.start_minute,
            'state': self.state,
            'contact_hexes': sorted(list(h) for h in self.contact_hexes),
            'fleets': [self._fleet_to_dict(f) for f in self.fleets.values()],
        }
```

把 `Game.load_dict` 替换为:

```python
    def load_dict(self, data):
        self.current_substep = data['current_substep']
        self.visibility = data['visibility']
        self.start_minute = data.get('start_minute', 0)
        self.last_report = None
        self.state = data.get('state', STATE_SEARCH)
        self.contact_hexes = {tuple(h) for h in data.get('contact_hexes', [])}
        self.fleets = {f.name: f for f in (self._fleet_from_dict(d) for d in data['fleets'])}
```

- [ ] **Step 4: Run tests (new + full regression)**

Run: `python -m unittest test_serialization -v`  → PASS
Run: `python -m unittest discover -p "test_*.py" -v`  → 全量 PASS

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py test_serialization.py
git commit -m "feat: serialize formation + post-encounter state fields"
```

---

### Task 2: journal.py(操作历史 + 每回合快照)

**Files:**
- Create: `journal.py`
- Test: `test_journal.py`

- [ ] **Step 1: Write the failing test**

写入 `test_journal.py`:

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
        self.assertEqual(len(j.turns), 2)
        self.assertEqual(j.latest_snapshot()["tag"], "t2")
        self.assertEqual(j.snapshot_at_turn(0)["tag"], "t1")
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
        self.assertEqual(j2.turns, [{"current_substep": 6}])


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest test_journal -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'journal'`

- [ ] **Step 3: Write implementation**

写入 `journal.py`:

```python
"""操作日志:命令历史 + 每回合盘面快照 + JSON 读写 + 按回合取快照。

纯数据结构,不依赖引擎。快照是引擎给的 dict(Game.to_dict() 的产物)。
"""

import json


class Journal:
    def __init__(self, epoch_minute=0, visibility=0.0):
        self.epoch_minute = epoch_minute
        self.visibility = visibility
        self.history = []      # [{"sim_min": int, "cmd": str}]
        self.turns = []        # [snapshot dict]

    def record_command(self, sim_min, cmd):
        self.history.append({"sim_min": sim_min, "cmd": cmd})

    def record_turn(self, snapshot):
        self.turns.append(snapshot)

    def latest_snapshot(self):
        return self.turns[-1] if self.turns else None

    def snapshot_at_turn(self, turn):
        if 0 <= turn < len(self.turns):
            return self.turns[turn]
        return None

    def to_json(self):
        return json.dumps({
            "epoch_minute": self.epoch_minute,
            "visibility": self.visibility,
            "history": self.history,
            "turns": self.turns,
        }, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text):
        d = json.loads(text)
        j = cls(d.get("epoch_minute", 0), d.get("visibility", 0.0))
        j.history = d.get("history", [])
        j.turns = d.get("turns", [])
        return j
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m unittest test_journal -v`  → PASS

- [ ] **Step 5: Commit**

```bash
git add journal.py test_journal.py
git commit -m "feat: add journal module (command history + turn snapshots)"
```

---

### Task 3: Game 接入 journal + save/load 升级 + replay

**Files:**
- Modify: `fleet_search.py`(`import journal`;`Game.__init__`;`Game.step_turn`;`Game.save`/`load`;新增 `Game.replay_to`)
- Test: `test_journal_integration.py`

**背景:** `step_turn` 有两个返回点(接敌返回 encounters;正常返回 None)。在两个 `return` 之前都要 `self.journal.record_turn(self.to_dict())`。`save`/`load` 现在写/读整本日志 + 最新状态。

- [ ] **Step 1: Write the failing test**

写入 `test_journal_integration.py`:

```python
import os
import tempfile
import unittest
import fleet_search as fs


def two_fleets():
    g = fs.Game()
    g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 2)
    g.add_fleet("GE1", "GE", 0, "10,0", "W", 18, 2)
    return g


class TestJournalIntegration(unittest.TestCase):
    def test_step_records_turn_snapshots(self):
        g = two_fleets()
        g.step_turn()
        g.step_turn()
        self.assertEqual(len(g.journal.turns), 2)
        self.assertEqual(g.journal.turns[0]["current_substep"], 6)
        self.assertEqual(g.journal.turns[1]["current_substep"], 12)

    def test_save_load_roundtrip_with_journal(self):
        g = two_fleets()
        g.step_turn()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "log.json")
            g.save(path)
            g2 = fs.Game()
            g2.load(path)
        self.assertEqual(g2.current_substep, g.current_substep)
        self.assertEqual(set(g2.fleets), set(g.fleets))
        self.assertEqual(len(g2.journal.turns), len(g.journal.turns))

    def test_replay_to_earlier_turn(self):
        g = two_fleets()
        g.step_turn()      # snapshot turn 0 -> sub6
        g.step_turn()      # snapshot turn 1 -> sub12
        self.assertEqual(g.current_substep, 12)
        g.replay_to(0)
        self.assertEqual(g.current_substep, 6)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest test_journal_integration -v`
Expected: FAIL —— `AttributeError: 'Game' object has no attribute 'journal'`

- [ ] **Step 3: Write implementation**

在 `fleet_search.py` 顶部 import 段加(`import formation` 旁):

```python
import journal as journal_mod
```

在 `Game.__init__` 末尾(已有 `self.contact_hexes = set()` 之后)加:

```python
        self.journal = journal_mod.Journal(self.start_minute, self.visibility)
```

在 `Game.step_turn` 的**每个 `return` 之前**插入一行记录当回合快照。具体:把接敌分支的
`return self._resolve_encounter(sub)` 改为:

```python
            if hits:
                result = self._resolve_encounter(sub)
                self.journal.record_turn(self.to_dict())
                return result
```

并在正常推进末尾的 `return None` 之前加:

```python
        self.journal.record_turn(self.to_dict())
        return None
```

把 `Game.save` 替换为:

```python
    def save(self, filename):
        import json as _json
        payload = {"current": self.to_dict(), "journal": _json.loads(self.journal.to_json())}
        with open(filename, 'w', encoding='utf-8') as fh:
            _json.dump(payload, fh, ensure_ascii=False, indent=2)
```

把 `Game.load` 替换为:

```python
    def load(self, filename):
        import json as _json
        with open(filename, 'r', encoding='utf-8') as fh:
            payload = _json.load(fh)
        self.load_dict(payload["current"])
        self.journal = journal_mod.Journal.from_json(_json.dumps(payload["journal"]))
```

在 `Game` 类里(`load` 之后)新增:

```python
    def replay_to(self, turn):
        """把盘面恢复到日志里第 turn 个回合快照(0 起)。不改动日志本身。"""
        snap = self.journal.snapshot_at_turn(turn)
        if snap is None:
            raise IndexError(f"no snapshot for turn {turn}")
        self.load_dict(snap)
```

- [ ] **Step 4: Run tests (new + full regression)**

Run: `python -m unittest test_journal_integration -v`  → PASS
Run: `python -m unittest discover -p "test_*.py" -v`  → 全量 PASS

注意:`load_dict` 会把 `last_report` 置 None,所以 replay 后接敌标记不重建,但盘面状态(位置/拍/视距/队形/state)完整恢复——这符合 spec(日志记录每回合结果用于回放)。

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py test_journal_integration.py
git commit -m "feat: wire journal into Game; save/load full log; add replay_to"
```

---

## Self-Review

- **Spec 覆盖**:§3.6 —— 操作历史(`Journal.record_command` + history,CLI 钩子在 Plan 5)、每回合结果(`step_turn` 记录快照)、JSON 格式(`save` 写 current+journal)、replay(`replay_to`)、复用 to_dict 作为快照基元(Task 1 补全后复用)。
- **占位符**:无;每步含完整代码与命令。
- **类型一致**:`Journal` 的 `record_command/record_turn/latest_snapshot/snapshot_at_turn/to_json/from_json` 在实现、集成、测试间一致;快照 dict 用 `Game.to_dict()` 统一产出;`replay_to(turn)` 与测试匹配。
- **回归保护**:Task 1 用 `.get(...)` 容旧档;默认队形/状态不变;全量回归在 Task 1/3 跑。
- **延后**:CLI 在每条命令调用 `record_command`、`save/load/replay` 命令接线 = Plan 5。
