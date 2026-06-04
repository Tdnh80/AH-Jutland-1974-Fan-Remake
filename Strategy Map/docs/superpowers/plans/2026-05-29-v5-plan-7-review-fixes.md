# v5 Plan 7 — Final-review 修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 修复 final code review 发现的 3 个 Critical + 2 个 Important 问题:接敌后状态机未接入主循环(死锁)、服务器双盲被 output 通道绕过、服务器无命令授权、journal 头部 epoch/visibility 不同步、`time` 命令不支持三式输入。

**Architecture:** 全部在 `fleet_search.py`(状态机接入 `step_turn`、`authorize_player_command`、`save` 同步、`time` 用 `parse_time`)与 `server.py`(授权 + 安全 output)。新增针对性测试覆盖此前的盲点(反复 `step` 走过 CONTACT、output 通道双盲、越权拒绝)。

**Tech Stack:** Python 3.10+,stdlib `unittest`。

---

### Task 1: 把接敌后状态机接入 step_turn(修 Critical 1 死锁)

**Files:**
- Modify: `fleet_search.py`(`Game.step_turn`)
- Test: `test_state_machine_loop.py`

**背景:** 现状 `step_turn` 永远走「检测→回退」路径;接敌后 `state=CONTACT` 但 `resume_search_if_clear`/`adjacent_entrants` 从不被调用,导致下一次 `step` 又回退到同一拍、永久卡死。修复:`step_turn` 开头先处理 CONTACT 态——若已脱离(涉及中心驶出接敌格)则回 SEARCH 并照常推进;否则推进时间、记录进入者、**不重复回退**。

- [ ] **Step 1: Write the failing test**

写入 `test_state_machine_loop.py`:

```python
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


class TestStateMachineLoop(unittest.TestCase):
    def test_step_after_contact_does_not_deadlock(self):
        g = head_on_to_contact()
        self.assertEqual(g.state, fs.STATE_CONTACT)
        self.assertEqual(g.current_substep, 10)
        g.step_turn()                       # 不能再卡在 sub10
        self.assertNotEqual(g.current_substep, 10)

    def test_sailing_on_eventually_resumes_search(self):
        g = head_on_to_contact()
        for _ in range(4):                  # 双方继续直线航行,会驶出接敌格
            g.step_turn()
        self.assertEqual(g.state, fs.STATE_SEARCH)

    def test_relocate_apart_then_step_resumes(self):
        g = head_on_to_contact()
        g.relocate("GB1", "0,0", "E", 18)
        g.relocate("GE1", "20,0", "W", 18)
        g.step_turn()
        self.assertEqual(g.state, fs.STATE_SEARCH)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest test_state_machine_loop -v`
Expected: FAIL —— `test_step_after_contact_does_not_deadlock`(current_substep 仍为 10)。

- [ ] **Step 3: Implement**

把 `Game.step_turn` 开头(`for offset in range(1, 7):` 之前)插入 CONTACT 处理:

```python
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
            ...
```

(保持 `for offset` 起的原有搜索/回退逻辑不变。)

- [ ] **Step 4: Run tests + full regression**

Run: `python -m unittest test_state_machine_loop -v` → PASS
Run: `python -m unittest discover -p "test_*.py" -v` → 全量 PASS

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py test_state_machine_loop.py
git commit -m "fix: wire post-encounter state machine into step_turn (no deadlock)"
```

---

### Task 2: 服务器命令授权 + output 双盲(修 Critical 2/3)

**Files:**
- Modify: `fleet_search.py`(新增 `PLAYER_COMMANDS`、`authorize_player_command`)、`server.py`(`_handle` 授权 + 安全 output)
- Test: `test_server_security.py`

**背景:** 现状服务器把 `execute_command` 的原始 output 直接回传(`list`/接敌报告会泄漏敌方位置),且不校验命令归属。修复:只允许「作用己方」的玩家命令(其 output 仅 `ok:`/`error:`,不含敌方);其余命令(`list`/`step`/`demo`/`save`/`load`/`plot`/`replay`/`vis`/`time`)对客户端拒绝(裁判专用)。客户端靠过滤后的 `view` 了解局面。

- [ ] **Step 1: Write the failing test**

写入 `test_server_security.py`:

```python
import json
import socket
import threading
import time
import unittest
from server import JutlandServer


def send_line(f, obj):
    f.write((json.dumps(obj) + "\n").encode()); f.flush()


def recv_obj(f):
    return json.loads(f.readline())


class TestServerSecurity(unittest.TestCase):
    def setUp(self):
        self.srv = JutlandServer(host="127.0.0.1", port=0)
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start(); time.sleep(0.05)

    def tearDown(self):
        self.srv.stop()

    def _connect(self, side):
        s = socket.create_connection(("127.0.0.1", self.srv.port))
        f = s.makefile("rwb")
        send_line(f, {"side": side}); recv_obj(f)
        return s, f

    def test_player_cannot_touch_enemy_fleet(self):
        sg, fg = self._connect("GB")
        se, fe = self._connect("GE")
        send_line(fe, {"cmd": "new GE1 GE 0 A20 W 18 2"}); recv_obj(fe)
        send_line(fg, {"cmd": "relocate GE1 A21 W 18"})
        resp = recv_obj(fg)
        self.assertIn("refused", resp["output"].lower())
        sg.close(); se.close()

    def test_player_cannot_create_enemy_fleet(self):
        sg, fg = self._connect("GB")
        send_line(fg, {"cmd": "new X GE 0 A20 W 18 2"})
        self.assertIn("refused", recv_obj(fg)["output"].lower())
        sg.close()

    def test_list_is_refused_no_enemy_leak(self):
        sg, fg = self._connect("GB")
        se, fe = self._connect("GE")
        send_line(fe, {"cmd": "new GE1 GE 0 A20 W 18 2"}); recv_obj(fe)
        send_line(fg, {"cmd": "list"})
        resp = recv_obj(fg)
        self.assertNotIn("GE1", resp["output"])     # output 不泄漏敌方
        sg.close(); se.close()


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest test_server_security -v`
Expected: FAIL —— relocate/new 未被拒绝;`list` output 含 `GE1`。

- [ ] **Step 3: Implement**

在 `fleet_search.py`(`run_command` 附近的模块级)新增:

```python
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
```

在 `server.py` 的 `_handle` 命令循环里,把:

```python
                with self.lock:
                    out = fs.execute_command(self.game, line)
                    view = fs.view_for_side(self.game, side)
```

改为:

```python
                with self.lock:
                    ok, reason = fs.authorize_player_command(self.game, side, line)
                    if ok:
                        out = fs.execute_command(self.game, line)
                    else:
                        out = f"  refused: {reason}"
                    view = fs.view_for_side(self.game, side)
```

- [ ] **Step 4: Run tests + full regression**

Run: `python -m unittest test_server_security test_server_loopback -v` → PASS
Run: `python -m unittest discover -p "test_*.py" -v` → 全量 PASS

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py server.py test_server_security.py
git commit -m "fix: server authorizes player commands; close output double-blind leak"
```

---

### Task 3: journal 头部同步 + `time` 三式(修 Important 4/5)

**Files:**
- Modify: `fleet_search.py`(`Game.save` 同步头部;`run_command` 的 `time` 分支用 `parse_time`)
- Test: `test_journal_header.py`

- [ ] **Step 1: Write the failing test**

写入 `test_journal_header.py`:

```python
import json
import os
import tempfile
import unittest
import fleet_search as fs


class TestJournalHeaderAndTime(unittest.TestCase):
    def test_time_accepts_three_forms(self):
        g = fs.Game()
        fs.execute_command(g, "time T3")
        self.assertEqual(g.start_minute, 180)      # 3 回合 = 180 min
        fs.execute_command(g, "time 0530")
        self.assertEqual(g.start_minute, 330)

    def test_saved_journal_header_is_current(self):
        g = fs.Game()
        fs.execute_command(g, "time 1200")
        fs.execute_command(g, "vis 30000")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "log.json")
            g.save(path)
            with open(path, encoding="utf-8") as fh:
                payload = json.load(fh)
        self.assertEqual(payload["journal"]["epoch_minute"], 720)   # 1200
        self.assertEqual(payload["journal"]["visibility"], 30000.0)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest test_journal_header -v`
Expected: FAIL —— `time T3` 误解析;journal 头部仍是初始值。

- [ ] **Step 3: Implement**

在 `run_command` 的 `time` 分支改用 `parse_time`:

```python
            elif cmd == 'time':
                g.start_minute = timekeep.parse_time(args[0])
                print(f"  ok: clock starts {g.datestr(0)}")
```

在 `Game.save` 写文件前同步 journal 头部:

```python
    def save(self, filename):
        import json as _json
        self.journal.epoch_minute = self.start_minute
        self.journal.visibility = self.visibility
        payload = {"current": self.to_dict(), "journal": _json.loads(self.journal.to_json())}
        with open(filename, 'w', encoding='utf-8') as fh:
            _json.dump(payload, fh, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: Run tests + full regression**

Run: `python -m unittest test_journal_header -v` → PASS
Run: `python -m unittest discover -p "test_*.py" -v` → 全量 PASS

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py test_journal_header.py
git commit -m "fix: time accepts turn/sub/HHMM; sync journal header on save"
```

---

## Self-Review

- **覆盖 review 的必修项**:Critical 1(Task 1 接入状态机 + 反复 step 测试)、Critical 2/3(Task 2 授权 + output 双盲 + 越权/泄漏测试)、Important 4/5(Task 3 header 同步 + time 三式)。
- **盲点补测**:此前测试只直接调方法或只看 `view`;本 plan 新增「反复 `step_turn` 穿过 CONTACT」「越权命令被拒」「`output` 不含敌方」三类测试,正对 review 指出的盲点。
- **占位符**:无;每步含完整代码与命令。
- **遗留 Minor(不阻塞,记为 backlog)**:journal 记录所有命令(含 list/quit)、`coords.idx_to_letter` 允许 1–52 越界行、`_end_schedule` 朝向推导稍绕、`hhmm()` 与 `timekeep.fmt_clock` 重复。这些是清洁度问题,不影响功能正确性,留待后续。
