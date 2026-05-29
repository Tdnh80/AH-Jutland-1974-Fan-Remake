# v5 Plan 5 — 表现 / 工具层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 把前几层的能力接到玩家面:CLI 输入/输出改用字母数字格名(A13)与三式时间(回合/拍/`DD/MM/YY HHMM`);新增队形、save log/replay、命令日志钩子;demo 长回合收敛;接敌放大特写图;文档拆使用者版/开发者版并修 README 加粗。

**Architecture:** 纯增量,集中在 `fleet_search.py`(显示/解析 helper + `main()` 命令分支)与文档。坐标内部仍 axial,仅在 I/O 边界用 `coords` 转换;时间显示用 `timekeep`;命令日志用 `Game.journal`。绘图/文档/demo 以 smoke + 全量回归不破为验收,纯函数(解析/显示 helper)仍 TDD。

**Tech Stack:** Python 3.10+,stdlib `unittest`;`matplotlib`(仅绘图,惰性 import)。`python -m unittest <module> -v`。

---

### Task 1: 坐标 I/O —— 输入接受 A13 / 显示用 A13

**Files:**
- Modify: `fleet_search.py`(新增 `parse_cell_or_hex`、`display_cell`;`micro_str`;`add_fleet`/`relocate`/`schedule` 内部解析;`randwalk` 与 `status_line` 的格名输出)
- Test: `test_cli_coords.py`

**背景:** 内部仍用 axial。`coords.parse_cell("A13")->(13,1)`、`coords.cell_name(13,1)->"A13"`(字母行仅 1..52 合法,地图外会抛错)。玩家面用字母数字,开发者仍可用 `q,r`。

- [ ] **Step 1: Write the failing test**

写入 `test_cli_coords.py`:

```python
import unittest
import fleet_search as fs


class TestCliCoords(unittest.TestCase):
    def test_parse_cell_or_hex_accepts_both(self):
        self.assertEqual(fs.parse_cell_or_hex("A13"), (13, 1))   # 字母数字
        self.assertEqual(fs.parse_cell_or_hex("13,1"), (13, 1))  # 开发者 q,r

    def test_display_cell_in_range_and_fallback(self):
        self.assertEqual(fs.display_cell(13, 1), "A13")
        # 地图外行号回退到 (q,r),不抛错
        self.assertEqual(fs.display_cell(0, -5), fs.hex_name(0, -5))

    def test_add_fleet_accepts_letter_number(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "A13", "E", 18, 1)
        # A13 -> (13,1);中心应落在该格中心
        self.assertEqual(fs.xy_to_hex(*g.fleets["F"].anchor_xy), (13, 1))

    def test_micro_str_uses_letter_number(self):
        x, y = fs.hex_center_xy(13, 1)
        self.assertIn("A13", fs.micro_str(x + 4000, y))


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest test_cli_coords -v`
Expected: FAIL —— `AttributeError: module 'fleet_search' has no attribute 'parse_cell_or_hex'`

- [ ] **Step 3: Implement**

在 `fleet_search.py` import 段加 `import coords`(若尚无)。在 `micro_str` 之前加两个 helper:

```python
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
```

把 `micro_str` 改为用 `display_cell`:

```python
def micro_str(x, y):
    h, edge, dist = micro_position(x, y)
    name = display_cell(*h)
    if edge is None:
        return f"{name} at centre"
    return f"{name}  {dist:.0f} yd from centre → {edge} edge"
```

在 `add_fleet`、`relocate`、`schedule`、`randwalk` 里,把内部对 `parse_hex(...)` 的调用换成 `parse_cell_or_hex(...)`(逐处:`add_fleet` 的 `h = parse_hex(hex_str)`;`relocate` 的 `parse_hex(hex_str)`;`schedule` 的 `wps = [parse_hex(h) for h in hex_strs]`)。`status_line` 里 `end = hex_name(*f.waypoints[-1])` 改为 `display_cell(*f.waypoints[-1])`;`main()` 的 `randwalk` 输出把 `hex_name` 改为 `display_cell`。

- [ ] **Step 4: Run tests + full regression**

Run: `python -m unittest test_cli_coords -v` → PASS
Run: `python -m unittest discover -p "test_*.py" -v` → 全量 PASS（若某旧测试断言含 `hex(...)` 文案而失败，说明它依赖旧显示——本 plan 允许更新这类**纯显示**断言为新格名；不要改数值/行为断言）

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py test_cli_coords.py
git commit -m "feat: CLI accepts and shows letter-number cells (A13)"
```

---

### Task 2: 三式时间显示

**Files:**
- Modify: `fleet_search.py`(新增 `Game.datestr`;`main()` prompt;`step`/`list` 输出;`time` 命令用 timekeep)
- Test: `test_cli_time.py`

- [ ] **Step 1: Write the failing test**

写入 `test_cli_time.py`:

```python
import unittest
import fleet_search as fs


class TestCliTime(unittest.TestCase):
    def test_datestr_default_epoch(self):
        g = fs.Game()                      # start_minute=0
        self.assertEqual(g.datestr(0), "31/05/16 0000")
        self.assertEqual(g.datestr(6), "31/05/16 0100")   # 6 拍 = 60 min

    def test_datestr_with_start_minute(self):
        g = fs.Game()
        g.start_minute = 330               # 0530
        self.assertEqual(g.datestr(0), "31/05/16 0530")


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest test_cli_time -v`
Expected: FAIL —— `AttributeError: 'Game' object has no attribute 'datestr'`

- [ ] **Step 3: Implement**

在 `fleet_search.py` import 段加 `import timekeep`。在 `Game` 里(`clock` 方法旁)加:

```python
    def datestr(self, substep):
        """绝对日期时刻 DD/MM/YY HHMM。"""
        return timekeep.fmt_date(self.start_minute + substep * 10)
```

把 `main()` 的 prompt 行改为同时显示 回合/拍/日期:

```python
            line = input(f"[T{g.current_turn} sub{g.current_substep} "
                         f"{g.datestr(g.current_substep)}] > ").strip()
```

把 `time` 命令分支改用 timekeep(接受 HHMM；保留设 `start_minute`):

```python
            elif cmd == 'time':
                g.start_minute = timekeep.hhmm_to_min(args[0])
                print(f"  ok: clock starts {g.datestr(0)}")
```

把 `step` 的无接敌输出与接敌抬头改为带日期(把 `g.clock(g.current_substep)` 处补上 `g.datestr(...)`,如 `f"  → T{g.current_turn} sub{g.current_substep} {g.datestr(g.current_substep)}, no contact"`;接敌抬头同理）。

- [ ] **Step 4: Run tests + full regression**

Run: `python -m unittest test_cli_time -v` → PASS
Run: `python -m unittest discover -p "test_*.py" -v` → 全量 PASS

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py test_cli_time.py
git commit -m "feat: show turn/sub/DD-MM-YY-HHMM time in CLI"
```

---

### Task 3: 队形命令 + 日志/回放命令 + 命令记录钩子

**Files:**
- Modify: `fleet_search.py`(`main()` 新增 `formation`/`replay` 命令;`save`/`load` 已存在;命令记录钩子;`HELP` 文本)
- Test: `test_cli_smoke.py`

**背景:** `Game` 已有 `journal`、`save`/`load`、`replay_to`、`Fleet.formation_kind/pos_mode/...`。`formation` 模块常量:`LINE_AHEAD/LINE_ABREAST/ECHELON`、`ABS_MODE/REL_MODE`。

- [ ] **Step 1: Write the failing smoke test**

写入 `test_cli_smoke.py`:

```python
import io
import unittest
from contextlib import redirect_stdout
import fleet_search as fs


def run_cli(lines):
    """把若干命令喂给 main(),返回 stdout。"""
    buf = io.StringIO()
    import builtins
    it = iter(lines + ["quit"])
    orig = builtins.input
    builtins.input = lambda *a, **k: next(it)
    try:
        with redirect_stdout(buf):
            fs.main()
    finally:
        builtins.input = orig
    return buf.getvalue()


class TestCliSmoke(unittest.TestCase):
    def test_formation_command_sets_kind(self):
        out = run_cli([
            "new F GB 0 A13 E 18 3",
            "formation F abreast right relative",
            "list",
        ])
        self.assertIn("ok", out.lower())
        self.assertNotIn("unknown command", out)

    def test_new_list_step_runs(self):
        out = run_cli([
            "new GB1 GB 0 A13 E 18 2",
            "new GE1 GE 0 A20 W 18 2",
            "step",
            "list",
        ])
        self.assertNotIn("unknown command", out)
        self.assertNotIn("error:", out)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest test_cli_smoke -v`
Expected: FAIL —— `formation` 命令未知(`unknown command` 出现在输出里)。

- [ ] **Step 3: Implement**

在 `main()` 命令链里(`elif cmd == 'randwalk'` 之后)新增:

```python
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
```

在命令分派处加「记录每条命令」钩子:在 `cmd, args = parts[0].lower(), parts[1:]` 之后、`try:` 块内最前面加:

```python
            g.journal.record_command(g.start_minute + g.current_substep * 10, line)
```

把 `HELP` 文本补上 `formation` 与 `replay` 两行说明(照现有风格简述)。

- [ ] **Step 4: Run tests + full regression**

Run: `python -m unittest test_cli_smoke -v` → PASS
Run: `python -m unittest discover -p "test_*.py" -v` → 全量 PASS

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py test_cli_smoke.py
git commit -m "feat: formation/replay CLI commands + journal command hook"
```

---

### Task 4: demo 长回合收敛(隐性吸引)

**Files:**
- Modify: `fleet_search.py`(`run_demo`,新增一个朝对方偏置的随机走辅助)
- Test: `test_demo_convergence.py`

**背景:** `run_demo(g, seed, max_turns)` 现在随机摆 GB1/GE1 并各自 randwalk,直到接敌或到 `max_turns`。spec 0.5°:回合越大,双方越倾向互相靠拢,保证长回合后必接敌(产样本)。做法:在 demo 内,每回合用「带吸引偏置」的路径——偏置强度随回合数上升,使中心朝对方方向移动的概率提高。

- [ ] **Step 1: Write the failing test**

写入 `test_demo_convergence.py`:

```python
import unittest
import fleet_search as fs


class TestDemoConvergence(unittest.TestCase):
    def test_demo_reaches_contact_within_turns(self):
        # 多个种子下,加了吸引因子后应在 max_turns 内接敌
        hits = 0
        for seed in range(8):
            g = fs.Game()
            files = fs.run_demo(g, seed=seed, max_turns=40, frame_prefix="_convtest")
            if g.last_report is not None and g.state == fs.STATE_CONTACT:
                hits += 1
        # 收敛应让绝大多数种子在 40 回合内接敌
        self.assertGreaterEqual(hits, 6)

    def tearDown(self):
        import glob, os
        for f in glob.glob("_convtest_*.png"):
            try: os.remove(f)
            except OSError: pass


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails (or is flaky)**

Run: `python -m unittest test_demo_convergence -v`
Expected: 可能 FAIL（当前无吸引,40 回合内未必有 6/8 接敌）。若偶然通过也继续实现吸引以保证稳定。

- [ ] **Step 3: Implement**

在 `fleet_search.py` 加一个带吸引的随机走(放在 `random_walk_path` 之后):

```python
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
                cur, cd = hex_neighbour(cur, best), best
                out.append(cur)
                continue
        # 否则普通直行偏置随机走一步
        step = random_walk_path(cur, 12, rng, prev_dir=cd)  # 12kn -> 1 步
        if step:
            cur, cd = step[0], direction_between(out[-1] if out else start, step[0]) or cd
            out.append(cur)
    return out[:n]
```

把 `run_demo` 改为:每回合给两队用 `attracted_walk_path`,目标设为对方中心当前格,`pull` 随回合数上升(如 `pull = min(0.8, 0.1 + 0.06 * t)`)。保留每回合存帧与接敌即停的逻辑。

- [ ] **Step 4: Run test**

Run: `python -m unittest test_demo_convergence -v` → PASS（≥6/8 接敌）
Run: `python -m unittest discover -p "test_*.py" -v` → 全量 PASS

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py test_demo_convergence.py
git commit -m "feat: demo attraction factor so long games converge to contact"
```

---

### Task 5: 接敌放大特写图

**Files:**
- Modify: `fleet_search.py`(新增 `plot_encounter_closeup`)
- Test: `test_closeup_smoke.py`

**背景:** 现有 `plot_state(game, filename)` 画全局图。新增只画涉及接敌的格 + 其邻格的特写。涉及格 = `game.contact_hexes`;范围 = 这些格中心的包围盒 + 1 圈邻格留白。复用 `plot_state` 的绘制风格即可,仅把坐标范围限制在接敌区域。

- [ ] **Step 1: Write the failing smoke test**

写入 `test_closeup_smoke.py`:

```python
import os
import tempfile
import unittest
import fleet_search as fs


def head_on_to_contact():
    g = fs.Game()
    g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 3)
    g.add_fleet("GE1", "GE", 0, "4,0", "W", 18, 2)
    g.schedule("GB1", 18, ["1,0", "2,0", "3,0"])
    g.schedule("GE1", 18, ["3,0", "2,0", "1,0"])
    g.step_turn(); g.step_turn()
    return g


class TestCloseupSmoke(unittest.TestCase):
    def test_closeup_writes_file(self):
        g = head_on_to_contact()
        self.assertEqual(g.state, fs.STATE_CONTACT)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "closeup.png")
            try:
                fs.plot_encounter_closeup(g, path)
            except RuntimeError as e:
                self.skipTest(f"matplotlib unavailable: {e}")
            self.assertTrue(os.path.exists(path) and os.path.getsize(path) > 0)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest test_closeup_smoke -v`
Expected: FAIL —— `AttributeError: module 'fleet_search' has no attribute 'plot_encounter_closeup'`

- [ ] **Step 3: Implement**

新增 `plot_encounter_closeup(game, filename)`,基于 `contact_hexes` 计算像素包围盒(用 `hex_center_xy` 取各接敌格中心,扩 `HEX_SIDE*1.5` 留白),其余绘制(网格、舰队、视距圈、接敌 ✕)复用 `plot_state` 的方式但把坐标范围设为该包围盒。matplotlib 不可用时抛 `RuntimeError`(与 `plot_state` 一致)。若 `contact_hexes` 为空则退化为 `plot_state`。

- [ ] **Step 4: Run test + full regression**

Run: `python -m unittest test_closeup_smoke -v` → PASS（或在无 matplotlib 时 skip）
Run: `python -m unittest discover -p "test_*.py" -v` → 全量 PASS

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py test_closeup_smoke.py
git commit -m "feat: encounter close-up plot of contact hexes"
```

---

### Task 6: 文档拆两版 + 修 README 加粗

**Files:**
- Modify: `README.md`(使用者版;修加粗渲染错误)
- Create: `DEVELOPER.md`(开发者版)

**背景:** spec 1°/16°:使用说明做两版。5°:README 现有加粗显示错误(检查诸如 `**文字 **`(右星号前多空格)、`** 文字**`、中英标点紧贴星号导致 Markdown 不渲染的情况)。

- [ ] **Step 1: 修 README 加粗 + 收敛为使用者版**

通读 `README.md`,修正所有加粗渲染错误(星号与文字间多余空格、星号紧贴中文标点导致不渲染),保持其「面向玩家、白话」定位;把坐标示例更新为字母数字(`A13`),时间示例更新为 `DD/MM/YY HHMM`,补上 `formation`、`replay`、save log 的玩家用法简述。

- [ ] **Step 2: 写开发者版 `DEVELOPER.md`**

新建 `DEVELOPER.md`,面向开发者:模块划分(`hexgrid`/坐标=`coords`、`timekeep`、`formation`、`journal`、引擎 `fleet_search`)、坐标映射公式(q=数字 r=字母行 A=1..DD=30)、时间模型(epoch 1916-05-31、绝对分钟)、接敌回退与 =vis 投影、接敌后状态机、队形两模式、save log/replay 格式、测试运行方式(`python -m unittest discover`)。内容与 spec/CLAUDE.md 一致,不重复使用者版的逐命令教程。

- [ ] **Step 3: 验证**

Run: `python -m unittest discover -p "test_*.py" -v` → 全量仍 PASS(文档改动不影响)。
人工检查:README 在 Markdown 预览里加粗均正确渲染。

- [ ] **Step 4: Commit**

```bash
git add README.md DEVELOPER.md
git commit -m "docs: split user/developer docs; fix README bold rendering"
```

---

## Self-Review

- **Spec 覆盖**:§3.7 全部 —— 0°接敌特写图(Task 5)、0.5° demo 收敛(Task 4)、0.6° 三式时间 I/O(Task 2,输入 `time` HHMM + 显示回合/拍/日期;回合/拍输入用于 `replay`)、1°/16° 文档两版(Task 6)、4° 调试 JSON——见下注、5° README 加粗(Task 6)、字母数字坐标 I/O(Task 1)、队形/日志命令(Task 3)。
- **调试 JSON(4°)说明**:Plan 4 的 `save/load`(JSON 全量日志)已覆盖「用 JSON 配置/恢复对局」的核心;独立的「地图/地形配置 JSON」因地形数据待朋友提供(spec §7),本版仅保留 `save/load` 的 JSON 通道,地图地形配置留待地形数据到位后补(不阻塞 v5 其余功能)。
- **占位符**:无;每步给出完整代码或精确改动 + 验收命令。
- **类型一致**:`parse_cell_or_hex`/`display_cell`/`Game.datestr`/`plot_encounter_closeup`/`attracted_walk_path` 命名在实现与测试间一致;CLI 命令名 `formation`/`replay` 与 smoke 测试一致。
- **回归保护**:每个 task 跑全量;显示文案断言允许更新为新格名,数值/行为断言不动。
