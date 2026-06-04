# v5 Plan 6 — 裁判机服务器联网 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 实现「裁判机服务器 + 双客户端」联网:裁判机持全局 `Game`(权威、全局视角),GB/GE 客户端各自下己方命令、只收裁判过滤后的视图(双盲:接敌前看不到对方位置)。先在本机 loopback 跑通,CLI 客户端,无 GUI。

**Architecture:** 三步可测分解 ——(1)`view_for_side(game, side)` 纯函数做双盲过滤;(2)把命令执行从 `main()` 提取成 `run_command(game, line)` / `execute_command(game, line)->str`,使 CLI 与服务器共用同一套命令逻辑(DRY);(3)`server.py` 用 stdlib TCP + JSON-line 协议,收客户端命令→`execute_command`→回推 `view_for_side` 过滤后的视图;`client.py` 是 CLI 客户端。引擎/规则全部复用,服务器不重写规则。

**Tech Stack:** Python 3.10+,stdlib `socket` / `threading` / `json` / `io` / `unittest`。loopback `127.0.0.1`,端口 0(自动分配)。

---

### Task 1: 双盲视图过滤(纯函数)

**Files:**
- Modify: `fleet_search.py`(新增模块级 `view_for_side`)
- Test: `test_view_filter.py`

**背景:** 双盲规则(spec §3.8):各方只见己方舰队;接敌(CONTACT)后,才在视图里看到对方涉及接敌的中心位置(来自 `last_report`)。`Game._fleet_to_dict` 可序列化单支舰队;`Game.last_report['encounters']` 每条含 `gb`,`ge`,`gb_xy_roll`,`ge_xy_roll`。

- [ ] **Step 1: Write the failing test**

写入 `test_view_filter.py`:

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


class TestViewFilter(unittest.TestCase):
    def test_search_phase_only_own_fleets_visible(self):
        g = fs.Game()
        g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 2)
        g.add_fleet("GE1", "GE", 0, "10,0", "W", 18, 2)
        v = fs.view_for_side(g, "GB")
        names = [f["name"] for f in v["own"]]
        self.assertEqual(names, ["GB1"])
        self.assertEqual(v["enemy_contacts"], [])   # 搜索阶段看不到对方

    def test_contact_phase_reveals_enemy_center(self):
        g = head_on_to_contact()
        self.assertEqual(g.state, fs.STATE_CONTACT)
        v = fs.view_for_side(g, "GB")
        self.assertEqual([f["name"] for f in v["own"]], ["GB1"])
        enemy = [c["name"] for c in v["enemy_contacts"]]
        self.assertIn("GE1", enemy)                 # 接敌后可见对方中心

    def test_side_symmetry(self):
        g = head_on_to_contact()
        vge = fs.view_for_side(g, "GE")
        self.assertEqual([f["name"] for f in vge["own"]], ["GE1"])
        self.assertIn("GB1", [c["name"] for c in vge["enemy_contacts"]])


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest test_view_filter -v`
Expected: FAIL —— `AttributeError: module 'fleet_search' has no attribute 'view_for_side'`

- [ ] **Step 3: Implement**

在 `fleet_search.py`(`Game` 类之后、Visualization 之前的模块级)新增:

```python
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
```

- [ ] **Step 4: Run tests + full regression**

Run: `python -m unittest test_view_filter -v` → PASS
Run: `python -m unittest discover -p "test_*.py" -v` → 全量 PASS

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py test_view_filter.py
git commit -m "feat: double-blind view_for_side filter for referee server"
```

---

### Task 2: 把命令执行从 main() 提取(CLI 与服务器共用)

**Files:**
- Modify: `fleet_search.py`(新增 `QuitSignal`、`run_command(game, line)`、`execute_command(game, line)`;`main()` 改为调用 `run_command`)
- Test: `test_execute_command.py`

**背景:** 当前 `main()` 在 while 循环的 `try` 块里:记录命令日志钩子 + `if/elif` 命令分派(已含 new/relocate/course/clear/schedule/randwalk/formation/list/vis/time/save/load/replay/plot/demo/step/quit 等)。本任务把这套分派**移到**模块级 `run_command(game, line)`,让 `main()` 和服务器都能调用。**移动**逻辑、不要重写每个分支。

- [ ] **Step 1: Write the failing test**

写入 `test_execute_command.py`:

```python
import unittest
import fleet_search as fs


class TestExecuteCommand(unittest.TestCase):
    def test_new_and_list(self):
        g = fs.Game()
        out = fs.execute_command(g, "new GB1 GB 0 A13 E 18 2")
        self.assertIn("ok", out.lower())
        self.assertIn("GB1", g.fleets)
        listing = fs.execute_command(g, "list")
        self.assertIn("GB1", listing)

    def test_unknown_command_reported(self):
        g = fs.Game()
        out = fs.execute_command(g, "florb")
        self.assertIn("unknown command", out)

    def test_quit_raises_signal(self):
        g = fs.Game()
        with self.assertRaises(fs.QuitSignal):
            fs.run_command(g, "quit")

    def test_command_is_journaled(self):
        g = fs.Game()
        fs.execute_command(g, "new GB1 GB 0 A13 E 18 1")
        cmds = [h["cmd"] for h in g.journal.history]
        self.assertIn("new GB1 GB 0 A13 E 18 1", cmds)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest test_execute_command -v`
Expected: FAIL —— `AttributeError: module 'fleet_search' has no attribute 'execute_command'`

- [ ] **Step 3: Implement (refactor, move don't rewrite)**

在 `fleet_search.py` 顶部 import 段加 `import io` 和 `from contextlib import redirect_stdout`(若尚无)。在 `main()` 之前新增:

```python
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
    # === 把 main() 原有 if/elif 命令分派(从 'help' 开始的所有 elif)移动到这里 ===
    # 注意:原 main 里第一条是 `if cmd in ('quit'...)`,这里已处理;
    # 接着把原来的 `elif cmd in ('help','?')` 起的整条链原样粘过来(改成以 `if` 开头)。


def execute_command(game, line):
    """像 run_command,但捕获输出为字符串返回(供服务器用)。QuitSignal -> 返回 '__QUIT__'。"""
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            run_command(game, line)
    except QuitSignal:
        return "__QUIT__"
    return buf.getvalue()
```

把 `main()` 的 while 循环体改为:

```python
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
```

**实现者注意:** 把原 `main()` 里 `try:` 块中那条以 `if cmd in ('quit'...)` 开头、含全部 `elif` 的命令分派链,整体搬进 `run_command` 的标注处(把开头改成处理过 quit 之后的 `if cmd in ('help','?')`)。命令日志钩子(`record_command`)现在在 `run_command` 开头统一做,**删掉原 main 里重复的钩子**,避免双重记录。保持每个命令分支内部代码不变。

- [ ] **Step 4: Run tests + full regression**

Run: `python -m unittest test_execute_command -v` → PASS
Run: `python -m unittest discover -p "test_*.py" -v` → 全量 PASS（含之前的 `test_cli_smoke`,确认 `main()` 仍正常）

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py test_execute_command.py
git commit -m "refactor: extract run_command/execute_command shared by CLI and server"
```

---

### Task 3: 裁判机 server + CLI client(loopback 跑通)

**Files:**
- Create: `server.py`、`client.py`
- Test: `test_server_loopback.py`

- [ ] **Step 1: Write the failing test**

写入 `test_server_loopback.py`:

```python
import json
import socket
import threading
import time
import unittest
from server import JutlandServer


def send_line(f, obj):
    f.write((json.dumps(obj) + "\n").encode())
    f.flush()


def recv_obj(f):
    return json.loads(f.readline())


class TestServerLoopback(unittest.TestCase):
    def setUp(self):
        self.srv = JutlandServer(host="127.0.0.1", port=0)
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start()
        time.sleep(0.05)

    def tearDown(self):
        self.srv.stop()

    def _connect(self, side):
        s = socket.create_connection(("127.0.0.1", self.srv.port))
        f = s.makefile("rwb")
        send_line(f, {"side": side})
        recv_obj(f)            # initial view
        return s, f

    def test_double_blind_search_phase(self):
        sg, fg = self._connect("GB")
        se, fe = self._connect("GE")
        # GE 建立己方舰队
        send_line(fe, {"cmd": "new GE1 GE 0 A20 W 18 2"})
        recv_obj(fe)
        # GB 建立己方舰队并看自己的视图
        send_line(fg, {"cmd": "new GB1 GB 0 A13 E 18 2"})
        resp = recv_obj(fg)
        own = [f["name"] for f in resp["view"]["own"]]
        self.assertIn("GB1", own)
        self.assertNotIn("GE1", own)                       # 看不到对方舰队
        self.assertEqual(resp["view"]["enemy_contacts"], [])   # 搜索阶段双盲
        sg.close(); se.close()


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest test_server_loopback -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'server'`

- [ ] **Step 3: Implement**

写入 `server.py`:

```python
"""裁判机服务器:持全局 Game,接受 GB/GE 客户端,执行命令并回推双盲过滤视图。

协议(每条消息一行 JSON):
  client 连上后先发 {"side": "GB"|"GE"};server 回初始 view_for_side。
  之后 client 发 {"cmd": "<command line>"};server 回 {"output": str, "view": {...}}。
"""

import json
import socket
import threading

import fleet_search as fs


class JutlandServer:
    def __init__(self, host="127.0.0.1", port=0):
        self.game = fs.Game()
        self.lock = threading.Lock()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self._stop = False

    def _send(self, f, obj):
        f.write((json.dumps(obj, ensure_ascii=False) + "\n").encode())
        f.flush()

    def _handle(self, conn):
        f = conn.makefile("rwb")
        try:
            hello = json.loads(f.readline())
            side = hello.get("side", "GB")
            with self.lock:
                self._send(f, fs.view_for_side(self.game, side))
            for raw in f:
                msg = json.loads(raw)
                line = msg.get("cmd", "")
                with self.lock:
                    out = fs.execute_command(self.game, line)
                    view = fs.view_for_side(self.game, side)
                self._send(f, {"output": out, "view": view})
        except (OSError, ValueError):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def serve_forever(self):
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def stop(self):
        self._stop = True
        try:
            self.sock.close()
        except OSError:
            pass


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    srv = JutlandServer(port=port)
    print(f"referee server on 127.0.0.1:{srv.port}")
    srv.serve_forever()
```

写入 `client.py`:

```python
"""CLI 客户端:连裁判机,声明 side,发命令,显示裁判回推的双盲视图。"""

import json
import socket
import sys


def _fmt_view(v):
    lines = [f"[{v['side']}] T{v['turn']} sub{v['substep']} state={v['state']}"]
    for f in v["own"]:
        lines.append(f"  own {f['name']} course={f['course']} speed={f['speed']}kn")
    for c in v["enemy_contacts"]:
        lines.append(f"  ENEMY {c['name']} @ {c['cell']}")
    return "\n".join(lines)


def run_client(host, port, side, infile=None):
    s = socket.create_connection((host, port))
    f = s.makefile("rwb")
    f.write((json.dumps({"side": side}) + "\n").encode()); f.flush()
    view = json.loads(f.readline())
    print(_fmt_view(view))
    src = infile if infile is not None else sys.stdin
    for line in src:
        line = line.strip()
        if not line:
            continue
        f.write((json.dumps({"cmd": line}) + "\n").encode()); f.flush()
        resp = json.loads(f.readline())
        if resp.get("output"):
            print(resp["output"], end="")
        print(_fmt_view(resp["view"]))
        if resp.get("output") == "__QUIT__":
            break
    s.close()


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    side = sys.argv[3].upper() if len(sys.argv) > 3 else "GB"
    run_client(host, port, side)
```

- [ ] **Step 4: Run tests + full regression**

Run: `python -m unittest test_server_loopback -v` → PASS
Run: `python -m unittest discover -p "test_*.py" -v` → 全量 PASS

若 loopback 测试因沙箱网络限制无法绑定/连接 127.0.0.1,STOP 并报告 BLOCKED（说明是环境网络限制,不要删测试)。

- [ ] **Step 5: Commit**

```bash
git add server.py client.py test_server_loopback.py
git commit -m "feat: referee server + CLI client with double-blind loopback"
```

---

## Self-Review

- **Spec 覆盖**:§3.8 —— 裁判机持全局 Game(`JutlandServer.game`)、玩家只见己方/接敌后见对方(`view_for_side`,Task 1)、命令流协议(JSON-line,Task 3)、复用引擎与命令逻辑(`execute_command`,Task 2,DRY)、本机 loopback 跑通(Task 3 测试)、CLI 客户端(`client.py`)、GUI 不在范围(未做,符合 spec)。
- **占位符**:无;每步含完整代码与命令。唯一「移动代码」步骤(Task 2)给出了骨架与精确指引(搬 if/elif 链、去掉重复日志钩子)。
- **类型一致**:`view_for_side` 返回 `{side,state,turn,substep,own,enemy_contacts}`,字段在过滤函数、服务器、客户端、测试间一致;`run_command`/`execute_command`/`QuitSignal` 命名一致;协议消息 `{"side"}` / `{"cmd"}` / `{"output","view"}` 在 server/client/测试间一致。
- **并发**:服务器用单 `Lock` 串行化对 `Game` 的访问,避免两客户端竞态。
- **已知简化**:本版双盲在「视图」层(读)严格执行;命令权限(GB 不能下 GE 命令)裁判机暂信任,留作后续(spec 未要求强制)。断线重连、对局握手细节见 spec §7,留后续。
