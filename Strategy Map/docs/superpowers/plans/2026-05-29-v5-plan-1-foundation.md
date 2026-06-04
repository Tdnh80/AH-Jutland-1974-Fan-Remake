# v5 Plan 1 — 基础层(时间 + 字母数字坐标) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增两个零依赖纯函数模块 —— `timekeep.py`(绝对游戏时间 ↔ 回合/拍/HHMM/日历日期)与 `coords.py`(字母数字格名 ↔ 内部 axial 坐标),作为 v5 其余模块的地基。

**Architecture:** 两个独立模块,不改动 `fleet_search.py`,不破坏现有 22 个回归测试。时间内部以「绝对分钟」计(epoch 默认 1916-05-31 00:00),坐标映射用规则书搜索图已确定的公式 `q=数字, r=字母行`(A=1…DD=30)。CLI 集成留待 Plan 5。

**Tech Stack:** Python 3.10+,标准库 `datetime` / `re`,测试用标准库 `unittest`(项目无 pytest)。

---

### Task 1: timekeep 模块(绝对时间互转)

**Files:**
- Create: `timekeep.py`
- Test: `test_timekeep.py`

- [ ] **Step 1: Write the failing test**

写入 `test_timekeep.py`:

```python
import unittest
import timekeep as tk


class TestTimekeep(unittest.TestCase):
    def test_turn_sub_minute_conversions(self):
        self.assertEqual(tk.turn_to_min(3), 180)
        self.assertEqual(tk.sub_to_min(5), 50)
        self.assertEqual(tk.min_to_turn(180), 3)
        self.assertEqual(tk.min_to_sub(50), 5)
        # 1 回合 = 6 拍 = 60 分钟
        self.assertEqual(tk.MIN_PER_TURN, 60)
        self.assertEqual(tk.SUB_PER_TURN, 6)

    def test_hhmm_to_min(self):
        self.assertEqual(tk.hhmm_to_min("0530"), 330)
        self.assertEqual(tk.hhmm_to_min("530"), 330)   # 容许缺前导 0
        self.assertEqual(tk.hhmm_to_min("0000"), 0)

    def test_fmt_clock(self):
        self.assertEqual(tk.fmt_clock(330), "0530")
        self.assertEqual(tk.fmt_clock(0), "0000")
        self.assertEqual(tk.fmt_clock(1500), "0100")   # 跨天回绕

    def test_fmt_date_uses_epoch_and_ddmmyy(self):
        # 默认 epoch = 1916-05-31 00:00,输出 DD/MM/YY HHMM
        self.assertEqual(tk.fmt_date(0), "31/05/16 0000")
        self.assertEqual(tk.fmt_date(90), "31/05/16 0130")
        self.assertEqual(tk.fmt_date(1440), "01/06/16 0000")   # +1 天

    def test_parse_time_three_forms(self):
        self.assertEqual(tk.parse_time("T3"), 180)     # 回合
        self.assertEqual(tk.parse_time("S5"), 50)      # 拍
        self.assertEqual(tk.parse_time("sub5"), 50)    # 拍(别名)
        self.assertEqual(tk.parse_time("0530"), 330)   # 当日 HHMM


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test_timekeep -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'timekeep'`

- [ ] **Step 3: Write minimal implementation**

写入 `timekeep.py`:

```python
"""绝对游戏时间 <-> 回合 / 拍(substep) / HHMM / 日历日期。

内部以「绝对分钟」计时,epoch(第 0 分钟)默认 1916-05-31 00:00(日德兰海战当日)。
输出日期格式 DD/MM/YY HHMM(日/月/年)。
"""

from datetime import datetime, timedelta

EPOCH = datetime(1916, 5, 31, 0, 0)
MIN_PER_SUB = 10
SUB_PER_TURN = 6
MIN_PER_TURN = MIN_PER_SUB * SUB_PER_TURN   # 60


def turn_to_min(n):
    return n * MIN_PER_TURN


def sub_to_min(n):
    return n * MIN_PER_SUB


def min_to_turn(m):
    return m // MIN_PER_TURN


def min_to_sub(m):
    return m // MIN_PER_SUB


def hhmm_to_min(s):
    s = str(s).zfill(4)
    return int(s[:2]) * 60 + int(s[2:])


def fmt_clock(m):
    h = (m // 60) % 24
    return f"{h:02d}{m % 60:02d}"


def fmt_date(m, epoch=EPOCH):
    d = epoch + timedelta(minutes=m)
    return f"{d.day:02d}/{d.month:02d}/{d.year % 100:02d} {d.hour:02d}{d.minute:02d}"


def parse_time(token):
    """'T<n>'=回合, 'S<n>'/'sub<n>'=拍, 4 位数字=当日 HHMM。-> 绝对分钟。"""
    t = str(token).strip().lower()
    if t.startswith('t'):
        return turn_to_min(int(t[1:]))
    if t.startswith('sub'):
        return sub_to_min(int(t[3:]))
    if t.startswith('s'):
        return sub_to_min(int(t[1:]))
    return hhmm_to_min(t)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest test_timekeep -v`
Expected: PASS(5 个测试全过)

- [ ] **Step 5: Commit**

```bash
git add timekeep.py test_timekeep.py
git commit -m "feat: add timekeep module (absolute time <-> turn/sub/hhmm/date)"
```

---

### Task 2: coords 模块(字母数字格名 ↔ axial)

**Files:**
- Create: `coords.py`
- Test: `test_coords.py`

- [ ] **Step 1: Write the failing test**

写入 `test_coords.py`:

```python
import unittest
import coords as co


class TestCoords(unittest.TestCase):
    def test_letter_index_roundtrip(self):
        self.assertEqual(co.idx_to_letter(1), "A")
        self.assertEqual(co.idx_to_letter(26), "Z")
        self.assertEqual(co.idx_to_letter(27), "AA")
        self.assertEqual(co.idx_to_letter(30), "DD")
        self.assertEqual(co.letter_to_idx("A"), 1)
        self.assertEqual(co.letter_to_idx("z"), 26)   # 大小写不敏感
        self.assertEqual(co.letter_to_idx("AA"), 27)
        self.assertEqual(co.letter_to_idx("DD"), 30)

    def test_four_corners(self):
        # 映射公式:q=数字, r=字母行(A=1..DD=30)
        self.assertEqual(co.parse_cell("A13"), (13, 1))
        self.assertEqual(co.parse_cell("A34"), (34, 1))
        self.assertEqual(co.parse_cell("DD-1"), (-1, 30))
        self.assertEqual(co.parse_cell("DD19"), (19, 30))

    def test_cell_name_is_inverse(self):
        self.assertEqual(co.cell_name(13, 1), "A13")
        self.assertEqual(co.cell_name(34, 1), "A34")
        self.assertEqual(co.cell_name(-1, 30), "DD-1")
        self.assertEqual(co.cell_name(19, 30), "DD19")

    def test_labelled_cells_share_q_on_diagonal(self):
        # 图上同一数字的格必落在同一条「左上→右下」线(同 q)
        for name in ("E15", "I15", "N15", "S15", "X15"):
            self.assertEqual(co.parse_cell(name)[0], 15)
        # 字母行各不相同
        rows = {co.parse_cell(n)[1] for n in ("E15", "I15", "N15", "S15", "X15")}
        self.assertEqual(len(rows), 5)

    def test_full_roundtrip(self):
        for r in range(1, 31):
            for q in range(-1, 35):
                self.assertEqual(co.parse_cell(co.cell_name(q, r)), (q, r))

    def test_bad_input_raises(self):
        with self.assertRaises(ValueError):
            co.parse_cell("13A")       # 顺序反了
        with self.assertRaises(ValueError):
            co.letter_to_idx("AB")     # 非翻倍式,不合法


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test_coords -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'coords'`

- [ ] **Step 3: Write minimal implementation**

写入 `coords.py`:

```python
"""字母数字格名 <-> 内部 axial (q, r)。

映射由规则书搜索图确定:q = 数字, r = 字母行(A=1..Z=26, AA=27, BB=28, CC=29, DD=30)。
字母为「翻倍式」(A..Z 之后是 AA, BB, CC, DD),非 Excel 进位。
"""

import re

_CELL_RE = re.compile(r"^([A-Za-z]+)(-?\d+)$")


def idx_to_letter(i):
    if not 1 <= i <= 52:
        raise ValueError(f"row index out of range: {i}")
    if i <= 26:
        return chr(64 + i)
    return chr(64 + (i - 26)) * 2          # 27 -> AA, 28 -> BB, ...


def letter_to_idx(s):
    s = s.upper()
    if len(s) == 1 and 'A' <= s <= 'Z':
        return ord(s) - 64
    if len(s) == 2 and s[0] == s[1] and 'A' <= s[0] <= 'Z':
        return 26 + (ord(s[0]) - 64)       # AA -> 27, DD -> 30
    raise ValueError(f"bad letter row: {s!r}")


def parse_cell(label):
    """'A13' -> (q=13, r=1);  'DD-1' -> (q=-1, r=30)."""
    m = _CELL_RE.match(str(label).strip())
    if not m:
        raise ValueError(f"bad cell {label!r}; use e.g. A13, DD-1")
    return (int(m.group(2)), letter_to_idx(m.group(1)))


def cell_name(q, r):
    """(q=13, r=1) -> 'A13'."""
    return f"{idx_to_letter(r)}{q}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest test_coords -v`
Expected: PASS(6 个测试全过)

- [ ] **Step 5: Commit**

```bash
git add coords.py test_coords.py
git commit -m "feat: add coords module (letter-number cell <-> axial)"
```

---

### Task 3: 确认全量回归无回退

**Files:**
- Test: 全部 `test_*.py`

- [ ] **Step 1: Run the full suite**

Run: `python -m unittest discover -p "test_*.py" -v`
Expected: PASS —— 原 22 个 `test_fleet_search` 用例 + 新增 timekeep/coords 用例全过,无失败。

- [ ] **Step 2: Commit(若有未提交的整理)**

```bash
git add -A
git commit -m "test: confirm full suite green after foundation modules" || echo "nothing to commit"
```

---

## Self-Review

- **Spec 覆盖**:本 plan 覆盖 spec §3.1(时间:epoch=1916-05-31、`DD/MM/YY HHMM`、回合/拍/HHMM 三式输入)与 §3.2(字母数字坐标、映射 `q=数字 r=字母行`、A–Z/AA/BB/CC/DD、四角校验)。CLI 把这些接进输入输出 = 留给 Plan 5(已在 spec §3.7 明确)。
- **占位符**:无 TBD/TODO;每步含完整代码与命令。
- **类型一致**:`timekeep` 与 `coords` 的函数名在测试与实现间一致(`parse_time`/`parse_cell`/`cell_name`/`fmt_date` 等);`coords.parse_cell` 返回 `(q, r)` 与 v4 axial 顺序一致。
- **依赖**:两个模块零外部依赖、互不依赖,可任意顺序实现;与 `fleet_search.py` 解耦,不触碰现有回归网。
