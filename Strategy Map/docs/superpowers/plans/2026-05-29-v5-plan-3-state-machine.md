# v5 Plan 3 — 接敌后状态机 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 给 `Game` 加显式状态(SEARCH / CONTACT),接敌后记录涉及的接敌格;新增「相邻格船只自动纳入接敌 + 驶入微观时间」、「脱离接触回到搜索」两条引擎逻辑;并用回归测试守住「连续接敌不叠加回合」。

**Architecture:** 纯引擎层改动,集中在 `fleet_search.py` 的 `Game`。沿用 v4 已有的接敌回退(roll back 到 >vis 拍)与同时多组结算(`_resolve_encounter` 的 `involved` 分组),只在其后挂上状态与接敌格;相邻格纳入用「向前按拍采样找首个进入接敌格的拍」(10min 离散,与全局检测同粒度,不做连续 CPA)。CLI/报告展示留待 Plan 5。

**Tech Stack:** Python 3.10+,stdlib `unittest`(`python -m unittest <module> -v`)。复用 `Game._cross_pairs / lead_xy`、模块级 `xy_to_hex / hex_neighbour / NEIGH`。

---

### Task 1: 状态字段 + 接敌设 CONTACT + 记录接敌格

**Files:**
- Modify: `fleet_search.py`(模块级常量;`Game.__init__`;`Game._resolve_encounter` 末尾)
- Test: `test_post_encounter.py`

**背景给实现者:** `Game._resolve_encounter(S)` 已实现回退到 `roll=S-1`、构造 `encounters`(每条含 `gb`,`ge`,`gb_xy_roll`,`ge_xy_roll`,`contact_sub` 等),设 `self.current_substep=max(roll,0)`、清 schedule、`self.last_report=dict(substep=..., encounters=...)`,并 `return encounters`。本任务只在其末尾追加状态记录,不改回退逻辑。

- [ ] **Step 1: Write the failing test**

写入 `test_post_encounter.py`:

```python
import unittest
import fleet_search as fs


def head_on_to_contact():
    """复刻回归用的正面对冲:接敌定格在 sub10,双方中心同格 (2,0)。"""
    g = fs.Game()                       # vis 默认 20000
    g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 3)
    g.add_fleet("GE1", "GE", 0, "4,0", "W", 18, 2)
    g.schedule("GB1", 18, ["1,0", "2,0", "3,0"])
    g.schedule("GE1", 18, ["3,0", "2,0", "1,0"])
    g.step_turn()                       # -> sub6, no contact
    encs = g.step_turn()                # -> contact, roll to sub10
    return g, encs


class TestContactState(unittest.TestCase):
    def test_initial_state_is_search(self):
        g = fs.Game()
        self.assertEqual(g.state, fs.STATE_SEARCH)
        self.assertEqual(g.contact_hexes, set())

    def test_encounter_enters_contact_with_hexes(self):
        g, encs = head_on_to_contact()
        self.assertTrue(encs)
        self.assertEqual(g.state, fs.STATE_CONTACT)
        self.assertIn((2, 0), g.contact_hexes)

    def test_no_double_turn_count(self):
        # 接敌只把 current_substep 设到 roll 一次,不叠加回合
        g, _ = head_on_to_contact()
        self.assertEqual(g.current_substep, 10)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test_post_encounter -v`
Expected: FAIL —— `AttributeError: 'Game' object has no attribute 'state'`

- [ ] **Step 3: Write minimal implementation**

在 `fleet_search.py` 模块级常量区(`VALID_SIDES` 附近)加:

```python
STATE_SEARCH = "SEARCH"
STATE_CONTACT = "CONTACT"
```

在 `Game.__init__` 里(已有 `self.last_report = None` 之后)加:

```python
        self.state = STATE_SEARCH
        self.contact_hexes = set()
```

在 `Game._resolve_encounter` 末尾,把:

```python
        self.last_report = dict(substep=self.current_substep, encounters=encounters)
        return encounters
```

改为:

```python
        self.last_report = dict(substep=self.current_substep, encounters=encounters)
        hexes = set()
        for e in encounters:
            hexes.add(xy_to_hex(*e['gb_xy_roll']))
            hexes.add(xy_to_hex(*e['ge_xy_roll']))
        self.contact_hexes = hexes
        self.state = STATE_CONTACT
        return encounters
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest test_post_encounter -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py test_post_encounter.py
git commit -m "feat: add SEARCH/CONTACT state + record contact hexes on encounter"
```

---

### Task 2: 相邻格船只自动纳入 + 驶入微观时间

**Files:**
- Modify: `fleet_search.py`(`Game` 新增方法 `adjacent_entrants`)
- Test: `test_post_encounter.py`(追加)

**背景:** spec §3.5 ——「接敌后保持接触时,相邻格若有其他船只,自动纳入接敌,并计算其驶入接敌格的微观时间(除非该船航向明确驶离接敌格则不纳入)」。用向前按拍采样实现:某未参与舰队中心当前在某接敌格的相邻格,且在 `lookahead` 拍内某拍其中心进入接敌格 → 纳入,记该拍为驶入时间;若始终未进入(驶离)→ 不纳入。

- [ ] **Step 1: Write the failing test(追加到 `test_post_encounter.py`)**

在 `test_post_encounter.py` 的 `if __name__` 之前追加:

```python
class TestAdjacentEntrants(unittest.TestCase):
    def test_entrant_heading_into_contact_hex_is_detected(self):
        g, _ = head_on_to_contact()       # state=CONTACT, contact_hexes={(2,0)}, sub=10
        # 第三舰队当前中心在相邻格 (3,0),航向 W(朝接敌格 (2,0))
        g.add_fleet("X", "GB", 0, "5,0", "W", 18, 1)
        g.relocate("X", "3,0", "W", 18)   # anchor at current sub, center=(3,0), course W
        entrants = g.adjacent_entrants()
        names = [e[0] for e in entrants]
        self.assertIn("X", names)
        entry_sub = dict((e[0], e[1]) for e in entrants)["X"]
        self.assertGreater(entry_sub, g.current_substep)

    def test_entrant_heading_away_is_not_detected(self):
        g, _ = head_on_to_contact()
        g.add_fleet("Y", "GB", 0, "5,0", "E", 18, 1)
        g.relocate("Y", "3,0", "E", 18)   # 航向 E,驶离接敌格
        names = [e[0] for e in g.adjacent_entrants()]
        self.assertNotIn("Y", names)

    def test_no_entrants_when_searching(self):
        g = fs.Game()
        self.assertEqual(g.adjacent_entrants(), [])
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest test_post_encounter -v`
Expected: FAIL —— `AttributeError: 'Game' object has no attribute 'adjacent_entrants'`

- [ ] **Step 3: Write implementation**

在 `Game` 类里(`_resolve_encounter` 之后、报告方法之前)新增:

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m unittest test_post_encounter -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py test_post_encounter.py
git commit -m "feat: auto-include adjacent-hex entrants with entry substep (spec 3.5)"
```

---

### Task 3: 脱离接触回到搜索

**Files:**
- Modify: `fleet_search.py`(`Game` 新增方法 `resume_search_if_clear`)
- Test: `test_post_encounter.py`(追加)

- [ ] **Step 1: Write the failing test(追加)**

在 `test_post_encounter.py` 的 `if __name__` 之前追加:

```python
class TestResumeSearch(unittest.TestCase):
    def test_resume_when_all_pairs_clear(self):
        g, _ = head_on_to_contact()
        self.assertEqual(g.state, fs.STATE_CONTACT)
        # 把双方拉远:所有跨阵营对都 > vis
        g.relocate("GB1", "0,0", "E", 18)
        g.relocate("GE1", "20,0", "W", 18)
        self.assertTrue(g.resume_search_if_clear())
        self.assertEqual(g.state, fs.STATE_SEARCH)
        self.assertEqual(g.contact_hexes, set())

    def test_no_resume_while_still_close(self):
        g, _ = head_on_to_contact()
        # 不移动:双方仍在接敌格附近,不应脱离
        self.assertFalse(g.resume_search_if_clear())
        self.assertEqual(g.state, fs.STATE_CONTACT)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest test_post_encounter -v`
Expected: FAIL —— `AttributeError: 'Game' object has no attribute 'resume_search_if_clear'`

- [ ] **Step 3: Write implementation**

在 `Game` 类里(`adjacent_entrants` 之后)新增:

```python
    def resume_search_if_clear(self):
        """CONTACT 态下,若当前所有跨阵营对都 >= vis,则脱离接触、回到 SEARCH。"""
        if self.state != STATE_CONTACT:
            return False
        pairs = self._cross_pairs(self.current_substep)
        if all(d >= self.visibility for d, _, _ in pairs):
            self.state = STATE_SEARCH
            self.contact_hexes = set()
            return True
        return False
```

- [ ] **Step 4: Run to verify it passes + full regression**

Run: `python -m unittest test_post_encounter -v`
Expected: PASS

Run: `python -m unittest discover -p "test_*.py" -v`
Expected: PASS —— 全量(v4 22 + Plan1 11 + Plan2 15 + 本 plan)全绿。

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py test_post_encounter.py
git commit -m "feat: resume SEARCH when contact broken (all pairs >= vis)"
```

---

## Self-Review

- **Spec 覆盖**:§3.5 —— SEARCH/CONTACT 状态(Task 1)、接敌定格沿用 v4(未改)、相邻格自动纳入 + 驶入微观时间(Task 2)、脱离回搜索(Task 3)、同时多处结算(v4 `_resolve_encounter` 的 `involved` 已支持,Task 1 的 `contact_hexes` 聚合多对)、回合计数防 bug(Task 1 `test_no_double_turn_count` 守住)。
- **占位符**:无;每步含完整代码与命令。
- **类型一致**:`STATE_SEARCH/STATE_CONTACT` 常量在实现与测试间一致;`adjacent_entrants` 返回 `[(name, entry_substep, hex)]`;`resume_search_if_clear` 返回 bool;均与测试断言匹配。
- **离散粒度**:相邻格驶入用按拍采样(10min),与全局检测同粒度,符合 spec「不做连续 CPA」。
- **延后**:把 entrants/状态展示进 CLI 与接敌报告 = Plan 5。
