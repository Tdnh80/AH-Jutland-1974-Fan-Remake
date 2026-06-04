# v6 阶段 B — 多 Formation + 编组导入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 v6 spec §6 / §3.5：新增解耦的 `orderparse.py`(中间 dataclass + `parse_relative_position` + `local_to_map` + 文本解析),把 `GBformation.txt`/`GEformation.txt` 解析并实例化到阶段 A 的三层运行期模型;在 `fleet_search.py` 加 `loadorder`/`add formation`/`del formation`/`list formations` CLI 与 `plot_order` 可视化;并把 `_cross_pairs` 遍历改为 `fleet→formation→ship`、接敌报告中心改为 Fleet 几何中心。

**Architecture:** `orderparse.py` 是**纯解析层**,无 matplotlib、无引擎依赖,只输出中间 dataclass(`OrderShip/OrderFormation/OrderFleet/Battle`)和两个纯几何函数(`parse_relative_position`、`local_to_map`),可独立单测。`fleet_search.py` 新增 `load_order_file()` 把中间模型实例化成阶段 A 的运行期 `Fleet/Formation/Ship`(每个 `OrderFormation` → 一个运行期 `Formation`,absolute 时懒冻结 `frozen_offset_xy`),以及 `loadorder` CLI、增量 `add/del/list formation` CLI、`plot_order` 校验图。接敌检测把 `_cross_pairs` 下沉一层遍历到 Ship,报告/状态机的中心从"旗舰 lead_xy"改为"Fleet 几何中心 lead_xy(=零偏移旗舰 Formation 中心)"。

**Tech Stack:** Python 3.10+;标准库 `math`/`re`/`dataclasses`/`shlex`/`json`;matplotlib 仅在 `plot_order` 内惰性 import(Agg 后端)。测试纯 stdlib `unittest`,放 `tests/`;运行 `python -m unittest discover -s tests -t .` 或单测 `python -m unittest tests.<mod> -v`。无 pytest、无 linter。

**前置依赖(阶段 A,假设已完成):** 阶段 A 已把单层 `Fleet` 上提为三层并保持零回归。本计划依赖 A 提供的以下运行期 API(spec §2.2 / §3):

- `fleet_search.Ship(name: str, index: int)` —— dataclass,叶子;`xy` 派生不落盘。
- `fleet_search.Formation(name, ships, offset_fwd, offset_left, relative, kind, spacing, deploy, echelon_deg, turning, frozen_offset_xy=None)` —— dataclass;`is_single` 派生属性;`name` 可挂 `note` 属性(A 已留 `note: str = ""` 字段,或本阶段任务 5 补)。
- `fleet_search.Fleet(name, side, activated_turn, anchor_xy, anchor_substep, course, speed, initial_course, formations: list, scheduled, schedule_end_substep, waypoints, display_history, ...)`,并提供:
  - `Fleet.lead_xy(substep)` —— Fleet 几何中心(旗舰 Formation 中心)精确 xy。
  - `Fleet.ship_positions(substep)` —— 返回 `[(name, (x,y)), ...]`,**遍历自身全部 Formation 的全部 Ship**(spec §3.4 接口不变性)。本阶段任务 6 验证此聚合在多 Formation 下成立;若 A 仅实现单 Formation 聚合,本阶段任务 6 的实现步骤补齐多 Formation 遍历。
- `fleet_search.TURN_FOLLOW="follow"`, `TURN_TOGETHER="together"`, `REL_ABSOLUTE="absolute"`, `REL_RELATIVE="relative"`, `KIND_AHEAD="ahead"`, `KIND_ABREAST="abreast"`, `KIND_ECHELON="echelon"`, `KIND_SINGLE="single"` —— 旋钮常量(spec §2.3)。
- `Game.add_fleet(...)` 默认建一个零偏移单 Formation 的 Fleet(A 已实现)。
- 序列化 `to_dict` 已 bump `version:6`,嵌套 `formations`(A 已实现);本阶段不再改序列化结构,只走 A 的路径。

> **若阶段 A 的常量/字段名与上表有出入**:以 A 的实际定义为准,在本阶段各任务的"实现"步骤里把名字替换为 A 的实名,但**行为契约(offset_fwd/offset_left 语义、ship_positions 聚合返回结构、absolute 懒冻结)不可变**。

**锁定约定核对(spec §9,本阶段全部不触碰):** axial 邻居增量统一(用 `DIRVEC`/`hex_center_xy`)、像素映射 `x=36000(q+r/2), y=√3/2·36000·r` +y 朝南、`HEX_SIDE=36000`、视距默认 20000/上限 36000(接敌路径不改阈值,仅遍历层数加深)、接敌=GB×GE 欧氏 <vis 只判跨阵营 / S→S−1 回退 / =vis 投影(粒度仍 Ship,涉及方记 Fleet)、精确 xy 不吸附格心、anchor_substep 可 float。

---

## 文件结构

| 文件 | 创建/修改 | 责任 |
|---|---|---|
| `orderparse.py` | Create | 纯解析层:中间 dataclass、`parse_relative_position`、`local_to_map`、`parse_battle` 文本解析。零 matplotlib / 零引擎依赖。 |
| `fleet_search.py` | Modify | `load_order_file` 实例化、`loadorder`/`add formation`/`del formation`/`list formations` CLI、`plot_order`、`_cross_pairs` 下沉遍历、接敌报告中心改 Fleet 几何中心。 |
| `tests/test_orderparse.py` | Create | `parse_relative_position`/`local_to_map`/整文件逐 Formation/端到端 loadorder/plot 冒烟。 |

---

## 坐标约定(本阶段所有几何统一,来自 spec §6.3)

```
forward_hat = DIRVEC[initial_course]          # 归一化地图单位向量(与引擎转向定义统一)
left_hat    = (forward_hat[1], -forward_hat[0])   # +y 朝南下的左舷法向 = formation 右舷法向 (-uy,ux) 之负
offset_xy   = offset_fwd * forward_hat + offset_left * left_hat
```

`forward_hat` 来自 `fleet_search.DIRVEC`(`E (1,0)`、`SE (0.5, +√3/2)`、`NW (-0.5,-√3/2)`)。
Relative Position 分量(spec §6.2):`F→+offset_fwd`、`B→−offset_fwd`、`L→+offset_left`、`R→−offset_left`、`0→(0,0)`。

> **left_hat 自洽验证(写进任务 3 测试)**:`initial_course="E"`,`forward_hat=(1,0)`,`left_hat=(0,-1)`。`offset_left=+1`(L,左舷)→ 地图 `(0,-1)` 即 +y 朝南时的"北/上",对 +x 朝东、+y 朝南的航向东而言左舷确在上方,正确。

---

### Task 1: orderparse 中间 dataclass + `parse_relative_position`

**Files:**
- Create: `orderparse.py`
- Test: `tests/test_orderparse.py`

- [ ] **Step 1: Write the failing test**

写入 `tests/test_orderparse.py`(本任务先放文件头 + 本任务两个测试类;后续任务往同一文件追加新类):

```python
import math
import os
import unittest

import orderparse as op

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GB_FILE = os.path.join(REPO, "GBformation.txt")
GE_FILE = os.path.join(REPO, "GEformation.txt")


class TestDataclasses(unittest.TestCase):
    def test_ordership_fields(self):
        s = op.OrderShip(name="GB1-1", index=0)
        self.assertEqual(s.name, "GB1-1")
        self.assertEqual(s.index, 0)

    def test_orderformation_defaults(self):
        fm = op.OrderFormation(name="3rd Div.", n_ships=4, kind="ahead",
                               offset_fwd=0.0, offset_left=-1125.0)
        self.assertEqual(fm.n_ships, 4)
        self.assertEqual(fm.kind, "ahead")
        self.assertEqual(fm.spacing, 500.0)        # default
        self.assertEqual(fm.deploy, "right")        # default
        self.assertEqual(fm.echelon_deg, 45.0)      # default
        self.assertEqual(fm.turning, "follow")      # default
        self.assertEqual(fm.relative, "absolute")   # default
        self.assertEqual(fm.note, "")               # default
        self.assertIsNone(fm.frozen_offset_xy)

    def test_orderfleet_and_battle(self):
        fl = op.OrderFleet(name="BS", side="GB", initial_course="SE",
                           formations=[])
        b = op.Battle(side="GB", fleets=[fl])
        self.assertEqual(b.side, "GB")
        self.assertEqual(b.fleets[0].initial_course, "SE")


class TestParseRelativePosition(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(op.parse_relative_position("0"), (0.0, 0.0))

    def test_single_forward(self):
        self.assertEqual(op.parse_relative_position("21000F"), (21000.0, 0.0))

    def test_single_backward(self):
        self.assertEqual(op.parse_relative_position("26000B"), (-26000.0, 0.0))

    def test_single_left(self):
        self.assertEqual(op.parse_relative_position("1125L"), (0.0, 1125.0))

    def test_single_right(self):
        self.assertEqual(op.parse_relative_position("5625R"), (0.0, -5625.0))

    def test_two_components_fl(self):
        self.assertEqual(op.parse_relative_position("8000F 10000L"),
                         (8000.0, 10000.0))

    def test_two_components_fr(self):
        self.assertEqual(op.parse_relative_position("5000F 12000R"),
                         (5000.0, -12000.0))

    def test_two_components_br(self):
        self.assertEqual(op.parse_relative_position("15000B 12000R"),
                         (-15000.0, -12000.0))

    def test_fullwidth_and_spacing_tolerant(self):
        # 全角空格 / 多空格 / 大小写都应被吞掉
        self.assertEqual(op.parse_relative_position("  26350F　28350L "),
                         (26350.0, 28350.0))

    # 实测既定决策值(spec §6.4)
    def test_6th_div_corrected_to_R(self):
        # 6th Div. 推断修正为 5625R
        self.assertEqual(op.parse_relative_position("5625R"), (0.0, -5625.0))

    def test_2cs_row1_R_deploy_28350L(self):
        # 2CS#1: 26350F 28350L -> (26350, +28350)
        self.assertEqual(op.parse_relative_position("26350F 28350L"),
                         (26350.0, 28350.0))

    def test_2cs_row2_L_deploy_28350R(self):
        # 2CS#2: 26350F 28350R -> (26350, -28350)
        self.assertEqual(op.parse_relative_position("26350F 28350R"),
                         (26350.0, -28350.0))

    def test_bad_token_raises(self):
        with self.assertRaises(ValueError):
            op.parse_relative_position("12345X")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_orderparse -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'orderparse'`(模块尚不存在)。

- [ ] **Step 3: Write minimal implementation**

创建 `orderparse.py`(本步只放 docstring、常量、dataclass、`parse_relative_position`;解析/换算在后续任务追加):

```python
"""编组文件解析层(纯文本 → 中间数据模型 → 局部坐标换算)。

与引擎解耦:本模块不 import fleet_search、不 import matplotlib。
中间 dataclass(OrderShip/OrderFormation/OrderFleet/Battle)只承载解析结果,
由 fleet_search.load_order_file 再实例化到运行期 Fleet/Formation/Ship。

坐标约定(spec §6.3):
  forward_hat = DIRVEC[initial_course]
  left_hat    = (forward_hat[1], -forward_hat[0])     # +y 朝南下的左舷法向
  offset_xy   = offset_fwd*forward_hat + offset_left*left_hat
Relative Position 分量:F→+fwd  B→−fwd  L→+left  R→−left  "0"→(0,0)。
"""

import math
import re
from dataclasses import dataclass, field

# pixel direction unit vectors (与 fleet_search.DIRVEC 一致;此处复制以保持本模块零引擎依赖)
_S3 = math.sqrt(3) / 2
DIRVEC = {
    'E':  (1.0, 0.0),
    'W':  (-1.0, 0.0),
    'NE': (0.5, -_S3),
    'NW': (-0.5, -_S3),
    'SE': (0.5, _S3),
    'SW': (-0.5, _S3),
}

DEFAULT_SPACING = 500.0

# 旋钮取值(与 fleet_search 常量字面值一致;本模块输出字符串,实例化时直接填运行期字段)
TURN_FOLLOW = "follow"
TURN_TOGETHER = "together"
REL_ABSOLUTE = "absolute"
REL_RELATIVE = "relative"
KIND_AHEAD = "ahead"
KIND_ABREAST = "abreast"
KIND_ECHELON = "echelon"
KIND_SINGLE = "single"


@dataclass
class OrderShip:
    name: str
    index: int


@dataclass
class OrderFormation:
    name: str
    n_ships: int
    kind: str
    offset_fwd: float = 0.0
    offset_left: float = 0.0
    spacing: float = DEFAULT_SPACING
    deploy: str = "right"
    echelon_deg: float = 45.0
    turning: str = TURN_FOLLOW
    relative: str = REL_ABSOLUTE
    note: str = ""
    frozen_offset_xy: tuple = None
    ships: list = field(default_factory=list)


@dataclass
class OrderFleet:
    name: str
    side: str
    initial_course: str
    formations: list = field(default_factory=list)


@dataclass
class Battle:
    side: str
    fleets: list = field(default_factory=list)


_RELPOS_RE = re.compile(r"^(\d+(?:\.\d+)?)([FBLR])$", re.IGNORECASE)


def parse_relative_position(text):
    """'8000F 10000L' -> (offset_fwd, offset_left).  '0' -> (0,0)。

    F→+fwd  B→−fwd  L→+left  R→−left;多分量矢量相加。
    容错全角空格(\\u3000)、多空格、首尾空白、大小写。
    """
    # 归一全角空格为半角,折叠空白
    norm = text.replace("　", " ").strip()
    if norm == "0":
        return (0.0, 0.0)
    fwd = 0.0
    left = 0.0
    for tok in norm.split():
        m = _RELPOS_RE.match(tok)
        if not m:
            raise ValueError(f"bad relative-position token {tok!r} in {text!r}")
        val = float(m.group(1))
        d = m.group(2).upper()
        if d == "F":
            fwd += val
        elif d == "B":
            fwd -= val
        elif d == "L":
            left += val
        else:  # "R"
            left -= val
    return (fwd, left)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_orderparse -v`
Expected: PASS — `TestDataclasses` 3 项 + `TestParseRelativePosition` 13 项全绿。

- [ ] **Step 5: Commit**

```bash
git add orderparse.py tests/test_orderparse.py
git commit -m "feat(orderparse): intermediate dataclasses + parse_relative_position

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `local_to_map` 局部→地图换算

**Files:**
- Modify: `orderparse.py`(在 `parse_relative_position` 之后追加 `local_to_map`)
- Test: `tests/test_orderparse.py`(追加 `TestLocalToMap`)

- [ ] **Step 1: Write the failing test**

往 `tests/test_orderparse.py` 末尾(`if __name__` 之前)追加:

```python
def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class TestLocalToMap(unittest.TestCase):
    def test_pure_forward_on_course_axis(self):
        # 纯 fwd 应落在 initial_course 射线上(与 forward_hat 同向)
        center = op.local_to_map((0.0, 0.0), "SE", 10000.0, 0.0)
        fwd = op.DIRVEC["SE"]
        # center 与 fwd 共线、同向
        self.assertAlmostEqual(center[0], 10000.0 * fwd[0], places=6)
        self.assertAlmostEqual(center[1], 10000.0 * fwd[1], places=6)

    def test_pure_left_orthogonal_to_forward(self):
        # 纯 left 偏移向量应与 forward_hat 正交
        off = op.local_to_map((0.0, 0.0), "SE", 0.0, 10000.0)
        fwd = op.DIRVEC["SE"]
        dot = off[0] * fwd[0] + off[1] * fwd[1]
        self.assertAlmostEqual(dot, 0.0, places=6)
        self.assertAlmostEqual(_dist(off, (0.0, 0.0)), 10000.0, places=6)

    def test_east_left_is_north_up(self):
        # 航向东 (1,0):left_hat=(0,-1);offset_left=+1125 -> 地图 y 减小(上/北)
        off = op.local_to_map((0.0, 0.0), "E", 0.0, 1125.0)
        self.assertAlmostEqual(off[0], 0.0, places=6)
        self.assertAlmostEqual(off[1], -1125.0, places=6)

    def test_nw_is_negative_se(self):
        # NW = SE 反向:同 (fwd,left) 的偏移向量应互为相反数
        a = op.local_to_map((0.0, 0.0), "SE", 8000.0, 10000.0)
        b = op.local_to_map((0.0, 0.0), "NW", 8000.0, 10000.0)
        self.assertAlmostEqual(a[0], -b[0], places=6)
        self.assertAlmostEqual(a[1], -b[1], places=6)

    def test_left_right_mirror_about_course_axis(self):
        # SE 航向下,左右对称 Division(+left vs -left)关于 Initial Course 轴镜像:
        # 二者之和应正好落在航向轴上(left 分量抵消)
        l = op.local_to_map((0.0, 0.0), "SE", 0.0, 5625.0)
        r = op.local_to_map((0.0, 0.0), "SE", 0.0, -5625.0)
        s = (l[0] + r[0], l[1] + r[1])
        self.assertAlmostEqual(s[0], 0.0, places=6)
        self.assertAlmostEqual(s[1], 0.0, places=6)

    def test_no_nan(self):
        for crs in ("E", "NE", "NW", "W", "SW", "SE"):
            off = op.local_to_map((100.0, 200.0), crs, 8000.0, 10000.0)
            self.assertFalse(math.isnan(off[0]) or math.isnan(off[1]))

    def test_center_offset_applied(self):
        # fleet_center_xy 非零时整体平移
        c = op.local_to_map((1000.0, 2000.0), "SE", 0.0, 0.0)
        self.assertEqual(c, (1000.0, 2000.0))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_orderparse.TestLocalToMap -v`
Expected: FAIL — `AttributeError: module 'orderparse' has no attribute 'local_to_map'`。

- [ ] **Step 3: Write minimal implementation**

在 `orderparse.py` 的 `parse_relative_position` 之后追加:

```python
def local_to_map(fleet_center_xy, course, offset_fwd, offset_left):
    """局部 (fwd,left) → 地图绝对 (x,y)(spec §6.3)。

    forward_hat = DIRVEC[course]
    left_hat    = (forward_hat.y, -forward_hat.x)       # +y 朝南下的左舷法向
    offset_xy   = offset_fwd*forward_hat + offset_left*left_hat
    return fleet_center_xy + offset_xy

    course 既可是 initial_course(absolute 冻结)也可是当前 course(relative 每拍重算);
    本函数不区分,调用方决定传哪个。
    """
    fx, fy = DIRVEC[course]
    lx, ly = (fy, -fx)
    cx, cy = fleet_center_xy
    ox = offset_fwd * fx + offset_left * lx
    oy = offset_fwd * fy + offset_left * ly
    return (cx + ox, cy + oy)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_orderparse.TestLocalToMap -v`
Expected: PASS — 7 项全绿。

- [ ] **Step 5: Commit**

```bash
git add orderparse.py tests/test_orderparse.py
git commit -m "feat(orderparse): local_to_map fwd/left -> map xy with left_hat=(uy,-ux)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: 整文件解析 `parse_battle`(表头/Fleet 行/数据行 + 全角破折号 + 既定决策)

**Files:**
- Modify: `orderparse.py`(追加 `parse_battle`、`parse_battle_file` 及内部辅助)
- Test: `tests/test_orderparse.py`(追加 `TestParseBattle`)

- [ ] **Step 1: Write the failing test**

往 `tests/test_orderparse.py` 末尾追加。注意:GB 文件有 BS(13 个 Formation,含 2CS 两行)+ BCF(6 个);GE 文件有 BS(12 个,含两个 München)+ SG(6 个)。

```python
class TestParseBattle(unittest.TestCase):
    def setUp(self):
        with open(GB_FILE, encoding="utf-8") as fh:
            self.gb = op.parse_battle(fh.read(), side="GB")
        with open(GE_FILE, encoding="utf-8") as fh:
            self.ge = op.parse_battle(fh.read(), side="GE")

    # --- fleet-level shape ---
    def test_gb_has_bs_and_bcf(self):
        names = [f.name for f in self.gb.fleets]
        self.assertEqual(names, ["BS", "BCF"])
        self.assertEqual(self.gb.side, "GB")

    def test_ge_has_bs_and_sg(self):
        names = [f.name for f in self.ge.fleets]
        self.assertEqual(names, ["BS", "SG"])

    def test_initial_course(self):
        gb_bs = self.gb.fleets[0]
        self.assertEqual(gb_bs.initial_course, "SE")
        ge_sg = self.ge.fleets[1]
        self.assertEqual(ge_sg.initial_course, "NW")

    def test_gb_bs_formation_count_13(self):
        # 11 named rows + 2CS appears twice = 13 (2CS 两行各成独立 Formation)
        self.assertEqual(len(self.gb.fleets[0].formations), 13)

    def test_gb_bcf_formation_count_6(self):
        self.assertEqual(len(self.gb.fleets[1].formations), 6)

    def test_ge_bs_formation_count_12(self):
        # 6 Div. + Stettin/Rostock/München#1/Frauenlob/Hamburg/München#2 = 12
        self.assertEqual(len(self.ge.fleets[0].formations), 12)

    def test_ge_sg_formation_count_6(self):
        self.assertEqual(len(self.ge.fleets[1].formations), 6)

    # --- field mapping on a representative Division ---
    def test_gb_3rd_div_fields(self):
        fm = self.gb.fleets[0].formations[0]
        self.assertEqual(fm.name, "3rd Div.")
        self.assertEqual(fm.n_ships, 4)
        self.assertEqual(fm.kind, "ahead")
        self.assertEqual(fm.spacing, 500.0)
        self.assertEqual(fm.turning, "together")
        self.assertEqual(fm.relative, "absolute")
        self.assertEqual((fm.offset_fwd, fm.offset_left), (0.0, 1125.0))  # 1125L

    def test_gb_4lcs_abreast_deploy_offset(self):
        fm = [f for f in self.gb.fleets[0].formations if f.name == "4LCS"][0]
        self.assertEqual(fm.kind, "abreast")
        self.assertEqual(fm.deploy, "right")
        self.assertEqual(fm.spacing, 4000.0)
        self.assertEqual((fm.offset_fwd, fm.offset_left), (8000.0, 10000.0))

    def test_gb_3bcs_follow(self):
        fm = [f for f in self.gb.fleets[0].formations if f.name == "3BCS"][0]
        self.assertEqual(fm.kind, "ahead")
        self.assertEqual(fm.turning, "follow")
        self.assertEqual((fm.offset_fwd, fm.offset_left), (32400.0, 13000.0))

    def test_gb_attached_lc_rel_relative(self):
        # BS 末行 Attached LC 是 Relative
        fms = [f for f in self.gb.fleets[0].formations if f.name == "Attached LC"]
        self.assertEqual(len(fms), 1)
        self.assertEqual(fms[0].relative, "relative")

    # --- 既定决策 (spec §6.4) ---
    def test_gb_6th_div_corrected_to_R_with_note(self):
        fm = [f for f in self.gb.fleets[0].formations if f.name == "6th Div."][0]
        self.assertEqual((fm.offset_fwd, fm.offset_left), (0.0, -5625.0))  # 5625R
        self.assertIn("5625", fm.note)
        self.assertNotEqual(fm.note, "")

    def test_ge_two_munchen_distinct(self):
        names = [f.name for f in self.ge.fleets[0].formations]
        self.assertIn("München#1", names)
        self.assertIn("München#2", names)
        m1 = [f for f in self.ge.fleets[0].formations if f.name == "München#1"][0]
        m2 = [f for f in self.ge.fleets[0].formations if f.name == "München#2"][0]
        self.assertEqual((m1.offset_fwd, m1.offset_left), (5000.0, -12000.0))  # 5000F 12000R
        self.assertEqual((m2.offset_fwd, m2.offset_left), (-26000.0, 0.0))     # 26000B
        self.assertNotEqual(m1.note, "")
        self.assertNotEqual(m2.note, "")

    def test_gb_2cs_two_formations(self):
        fms = [f for f in self.gb.fleets[0].formations if f.name.startswith("2CS")]
        self.assertEqual(len(fms), 2)
        names = sorted(f.name for f in fms)
        self.assertEqual(names, ["2CS#1", "2CS#2"])
        cs1 = [f for f in fms if f.name == "2CS#1"][0]
        cs2 = [f for f in fms if f.name == "2CS#2"][0]
        # #1: Deployment R, 28350L -> offset (26350, +28350), deploy right
        self.assertEqual((cs1.offset_fwd, cs1.offset_left), (26350.0, 28350.0))
        self.assertEqual(cs1.deploy, "right")
        # #2: Deployment L, 28350R -> offset (26350, -28350), deploy left
        self.assertEqual((cs2.offset_fwd, cs2.offset_left), (26350.0, -28350.0))
        self.assertEqual(cs2.deploy, "left")
        self.assertEqual(cs1.spacing, 12150.0)
        self.assertEqual(cs2.spacing, 12150.0)
        self.assertNotEqual(cs1.note, "")

    # --- single-ship units ---
    def test_ge_stettin_single(self):
        fm = [f for f in self.ge.fleets[0].formations if f.name == "Stettin"][0]
        self.assertEqual(fm.n_ships, 1)
        self.assertEqual(fm.kind, "single")
        self.assertEqual(fm.turning, "na")
        self.assertEqual((fm.offset_fwd, fm.offset_left), (21000.0, 0.0))

    def test_ge_sg_1sg_follow_relative(self):
        fm = [f for f in self.ge.fleets[1].formations if f.name == "1SG"][0]
        self.assertEqual(fm.n_ships, 5)
        self.assertEqual(fm.kind, "ahead")
        self.assertEqual(fm.turning, "follow")
        self.assertEqual(fm.relative, "relative")
        self.assertEqual((fm.offset_fwd, fm.offset_left), (0.0, 0.0))

    # --- ships populated ---
    def test_ships_indexed(self):
        fm = self.gb.fleets[0].formations[0]   # 3rd Div., 4 ships
        self.assertEqual(len(fm.ships), 4)
        self.assertEqual([s.index for s in fm.ships], [0, 1, 2, 3])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_orderparse.TestParseBattle -v`
Expected: FAIL — `AttributeError: module 'orderparse' has no attribute 'parse_battle'`。

- [ ] **Step 3: Write minimal implementation**

在 `orderparse.py` 的 `local_to_map` 之后追加。解析策略:逐行扫描;含 `：`(全角冒号)且以 `Initial Course` 关键字的行起一个新 Fleet;含全角破折号 `—`(`—`)的行为数据行,按 `—` 切列。表头 1-11 行(Fleet 块之前的说明)整体跳过 —— 通过"遇到 `XX：Initial Course ...` 才开始建 Fleet,之前的行全部忽略"自然实现。

```python
# 全角破折号(数据行分隔符)。文件实测用 EM DASH —。
_DASH = "—"
# Fleet 行:'BS：Initial Course SE（45°）' / 'SG：Initial Course NW'
_FLEET_RE = re.compile(r"^([A-Za-z0-9]+)\s*[:：]\s*Initial\s+Course\s+([A-Za-z]+)",
                       re.IGNORECASE)

# 既定决策注记(spec §6.4)
_NOTE_6TH = "推断修正:原文5625L,按左右对称应为5625R"
_NOTE_MUNCHEN = "同名舰两次,按字面各导,请核对笔误"
_NOTE_2CS = "原注'是否坐标变化至下一格/作为独立Fleet';本导入按同Fleet两Formation,未移格"


def _norm_course(token):
    """'SE（45°）' / 'NW' -> 'SE'/'NW'(取前缀字母方向键)。"""
    t = token.strip().upper()
    m = re.match(r"^(NE|NW|SE|SW|E|W|N|S)", t)
    if not m:
        raise ValueError(f"bad initial course {token!r}")
    return m.group(1)


def _split_cols(line):
    """按全角破折号切列并 strip(去掉首尾空白与全角空格)。"""
    return [c.replace("　", " ").strip() for c in line.split(_DASH)]


def _parse_kind(text):
    t = text.lower()
    if "abreast" in t:
        return KIND_ABREAST
    if "echelon" in t:
        return KIND_ECHELON
    return KIND_AHEAD   # 'line ahead' 及缺省


def _parse_turning(text):
    t = text.strip().lower()
    if t.startswith("together"):
        return TURN_TOGETHER
    if t.startswith("follow"):
        return TURN_FOLLOW
    return TURN_FOLLOW


def _parse_relative(text):
    return REL_RELATIVE if text.strip().lower().startswith("relative") else REL_ABSOLUTE


_SPACING_RE = re.compile(r"space\s*[:：]?\s*(\d+(?:\.\d+)?)\s*yds?", re.IGNORECASE)
_DEPLOY_RE = re.compile(r"Deployment\s+direction\s*[:：]?\s*([LR])", re.IGNORECASE)


def _parse_formation_row(cols):
    """单条数据行的列 -> OrderFormation(不含同名消歧/既定决策注记,那些在 parse_battle 里加)。

    列布局(实测,列数 5~7 不等;single 行只有 名/Ships/RelPos/Relative 4 列):
      name | Ships(n) | Formation类型 | [info: space/deploy] ... | Turning | RelPos | Relative
    策略:第 0 列=name,第 1 列=Ships;末列=Relative(absolute/relative);
    在剩余中列里按关键字提取 kind/spacing/deploy/turning/RelPos。
    """
    name = cols[0]
    n_ships = int(re.search(r"\d+", cols[1]).group(0))
    relative = _parse_relative(cols[-1])
    joined = " ".join(cols[2:-1])     # 中段合并,便于关键字扫描

    if n_ships == 1:
        kind = KIND_SINGLE
        turning = "na"
        spacing = DEFAULT_SPACING
        deploy = "right"
        echelon_deg = 45.0
        # single 行 RelPos = 倒数第二列(Relative 之前那列)
        relpos_text = cols[-2]
    else:
        kind = _parse_kind(joined)
        turning = _parse_turning(joined)
        sm = _SPACING_RE.search(joined)
        spacing = float(sm.group(1)) if sm else DEFAULT_SPACING
        dm = _DEPLOY_RE.search(joined)
        deploy = ("right" if dm.group(1).upper() == "R" else "left") if dm else "right"
        echelon_deg = 45.0
        # RelPos = Relative 列(末列)之前那列
        relpos_text = cols[-2]

    fwd, left = parse_relative_position(relpos_text)
    return OrderFormation(
        name=name, n_ships=n_ships, kind=kind,
        offset_fwd=fwd, offset_left=left, spacing=spacing,
        deploy=deploy, echelon_deg=echelon_deg,
        turning=turning, relative=relative,
    )


def _make_ships(formation):
    formation.ships = [OrderShip(name=f"{formation.name}-{i+1}", index=i)
                       for i in range(formation.n_ships)]


def parse_battle(text, side):
    """整文件文本 -> Battle(side 的若干 OrderFleet,各挂 OrderFormation)。

    既定决策(spec §6.4)在此层落地:6th Div. 改判 5625R + note;
    两个同名 München -> #1/#2 + note;2CS 两行 -> 2CS#1/#2 + note;
    其余同名行也按出现顺序加 #k 后缀消歧。
    """
    fleets = []
    cur = None
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        fm_fleet = _FLEET_RE.match(line.strip())
        if fm_fleet:
            cur = OrderFleet(name=fm_fleet.group(1),
                             side=side,
                             initial_course=_norm_course(fm_fleet.group(2)),
                             formations=[])
            fleets.append(cur)
            continue
        if cur is None or _DASH not in line:
            continue
        cols = _split_cols(line)
        if len(cols) < 4 or not cols[0]:
            continue
        fm = _parse_formation_row(cols)
        cur.formations.append(fm)

    for fl in fleets:
        _apply_decisions_and_dedup(fl)
        for fm in fl.formations:
            _make_ships(fm)
    return Battle(side=side, fleets=fleets)


def _apply_decisions_and_dedup(fleet):
    """落地 §6.4 既定决策 + 同名 Formation 加 #k 后缀。"""
    # 1) 6th Div. 修正(仅 GB BS):若 offset_left>0(误判 L)则翻成 R 并加 note
    for fm in fleet.formations:
        if fm.name == "6th Div." and fm.offset_left > 0:
            fm.offset_left = -fm.offset_left
            fm.note = _NOTE_6TH

    # 2) 同名去重:统计名字出现次数,>1 的按出现顺序加 #1/#2...
    from collections import Counter
    counts = Counter(fm.name for fm in fleet.formations)
    seen = {}
    for fm in fleet.formations:
        if counts[fm.name] > 1:
            base = fm.name
            seen[base] = seen.get(base, 0) + 1
            fm.name = f"{base}#{seen[base]}"
            if base == "München":
                fm.note = _NOTE_MUNCHEN
            elif base == "2CS":
                fm.note = _NOTE_2CS
            else:
                fm.note = fm.note or f"同名{base}第{seen[base]}个,请核对"


def parse_battle_file(path, side):
    with open(path, encoding="utf-8") as fh:
        return parse_battle(fh.read(), side)
```

> **关于 2CS 的 deploy/offset 自洽**:文件 line 23 `Deployment direction:R ... 28350L` → `_parse_formation_row` 得 `deploy=right`、`offset_left=+28350`(L)→ `(26350,+28350)`,与 §6.4 表"2CS#1 `(26350,+28350)`、deploy R"一致;line 24 `Deployment direction:L ... 28350R` → `deploy=left`、`offset_left=−28350`(R)→ `(26350,−28350)`,与表"2CS#2 `(26350,−28350)`、deploy L"一致。**无需在决策层翻符号**,解析规则天然正确。

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_orderparse.TestParseBattle -v`
Expected: PASS — 18 项全绿。

> 若某计数断言失败(13/6/12/6),先 `python -c "import orderparse,os; b=orderparse.parse_battle_file('GBformation.txt','GB'); print([(f.name,len(f.formations)) for f in b.fleets])"` 核实真实切列,再对照实测文件行修 `_split_cols`/正则(切勿改测试期望值)。

- [ ] **Step 5: Commit**

```bash
git add orderparse.py tests/test_orderparse.py
git commit -m "feat(orderparse): parse_battle full-file parse + 6.4 decisions (6th/Munchen/2CS)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `load_order_file` 实例化到运行期三层模型

**Files:**
- Modify: `fleet_search.py`(在 `Game` 类内 `add_fleet` 之后新增 `load_order_file` 方法;文件顶部 `import orderparse`)
- Test: `tests/test_orderparse.py`(追加 `TestLoadOrder`)

- [ ] **Step 1: Write the failing test**

往 `tests/test_orderparse.py` 末尾追加:

```python
import fleet_search as fs


class TestLoadOrder(unittest.TestCase):
    def test_fleet_count_equals_total_formations_gb(self):
        # 端到端:每个 OrderFormation -> 一个运行期 Fleet
        g = fs.Game()
        names = g.load_order_file(GB_FILE, "GB", "0,0")
        # GB: BS 13 + BCF 6 = 19
        self.assertEqual(len(names), 19)
        self.assertEqual(len(g.fleets), 19)

    def test_fleet_count_equals_total_formations_ge(self):
        g = fs.Game()
        names = g.load_order_file(GE_FILE, "GE", "0,0")
        # GE: BS 12 + SG 6 = 18
        self.assertEqual(len(names), 18)
        self.assertEqual(len(g.fleets), 18)

    def test_loaded_fleet_side_and_course(self):
        g = fs.Game()
        g.load_order_file(GB_FILE, "GB", "0,0")
        any_gb = next(iter(g.fleets.values()))
        self.assertEqual(any_gb.side, "GB")
        # initial_course propagated; default speed 18
        self.assertEqual(any_gb.initial_course, "SE")
        self.assertEqual(any_gb.course, "SE")
        self.assertEqual(any_gb.speed, 18)

    def test_anchor_matches_local_to_map(self):
        # 某个非零偏移 Formation 的 anchor_xy 应等于 local_to_map(中心, initial_course, fwd, left)
        g = fs.Game()
        g.load_order_file(GB_FILE, "GB", "0,0")
        center = fs.hex_center_xy(0, 0)
        # 3BCS: offset (32400F, 13000L), initial_course SE
        f = [f for f in g.fleets.values() if f.name.endswith("3BCS")][0]
        want = op.local_to_map(center, "SE", 32400.0, 13000.0)
        self.assertAlmostEqual(f.anchor_xy[0], want[0], places=3)
        self.assertAlmostEqual(f.anchor_xy[1], want[1], places=3)

    def test_zero_offset_formation_at_center(self):
        # GE SG 1SG offset 0 -> anchor 在起始格心
        g = fs.Game()
        g.load_order_file(GE_FILE, "GE", "0,0")
        center = fs.hex_center_xy(0, 0)
        f = [f for f in g.fleets.values() if f.name.endswith("1SG")][0]
        self.assertAlmostEqual(f.anchor_xy[0], center[0], places=3)
        self.assertAlmostEqual(f.anchor_xy[1], center[1], places=3)

    def test_each_loaded_fleet_single_formation_with_ships(self):
        g = fs.Game()
        g.load_order_file(GB_FILE, "GB", "0,0")
        f = [f for f in g.fleets.values() if f.name.endswith("3rd Div.")][0]
        self.assertEqual(len(f.formations), 1)
        self.assertEqual(len(f.formations[0].ships), 4)

    def test_save_load_roundtrip_preserves_anchor(self):
        import tempfile, os as _os
        g = fs.Game()
        g.load_order_file(GE_FILE, "GE", "0,0")
        f0 = [f for f in g.fleets.values() if f.name.endswith("Stettin")][0]
        anchor0 = tuple(f0.anchor_xy)
        fd, path = tempfile.mkstemp(suffix=".json")
        _os.close(fd)
        try:
            g.save(path)
            g2 = fs.Game()
            g2.load(path)
            f1 = [f for f in g2.fleets.values() if f.name.endswith("Stettin")][0]
            self.assertAlmostEqual(f1.anchor_xy[0], anchor0[0], places=3)
            self.assertAlmostEqual(f1.anchor_xy[1], anchor0[1], places=3)
        finally:
            _os.remove(path)
```

> **决策(命名)**:`load_order_file` 把每个 `OrderFormation` 提升为**一个独立运行期 Fleet**(spec §6.5:"一个 loadorder 通常产出一个文件 → 多个 Fleet … `Game.fleets` 数=总 Formation 数",对应 spec §10.C 端到端断言)。运行期 Fleet 名取 `"<OrderFleetName>/<FormationName>"`(如 `BS/3rd Div.`、`BS/2CS#1`),保证全局唯一且可读;测试用 `endswith` 匹配后缀。每个运行期 Fleet 内部正好挂 1 个运行期 Formation(承载 kind/spacing/deploy/turning/relative,offset 已在 `anchor_xy` 体现故运行期 Formation 自身 offset=0)。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_orderparse.TestLoadOrder -v`
Expected: FAIL — `AttributeError: 'Game' object has no attribute 'load_order_file'`。

- [ ] **Step 3: Write minimal implementation**

在 `fleet_search.py` 顶部 import 区(其它 `import` 旁)加:

```python
import orderparse
```

在 `Game` 类内 `add_fleet` 方法之后新增(用阶段 A 的运行期 `Fleet/Formation/Ship` 构造器;**下面字段名若与 A 实名不符,替换为 A 实名,语义不变**):

```python
    def load_order_file(self, path, side, start_hex="0,0", speed=18, activated=0):
        """读编组文件 -> 每个 OrderFormation 实例化为一个运行期 Fleet。

        返回创建的运行期 Fleet 名列表。Fleet 名 = '<OrderFleet>/<Formation>'。
        absolute 模式懒冻结 frozen_offset_xy(本处 offset 已并入 anchor_xy,
        运行期 Formation 自身 offset=0,故 frozen_offset_xy=(0,0))。
        """
        if side not in VALID_SIDES:
            raise ValueError("side must be GB or GE")
        battle = orderparse.parse_battle_file(path, side)
        h = parse_cell_or_hex(start_hex)
        center = hex_center_xy(*h)
        created = []
        for ofleet in battle.fleets:
            crs = ofleet.initial_course
            if crs not in NEIGH:
                raise ValueError(f"unsupported initial course {crs!r} in {ofleet.name}")
            for ofm in ofleet.formations:
                fleet_name = f"{ofleet.name}/{ofm.name}"
                if fleet_name in self.fleets:
                    raise ValueError(f"fleet {fleet_name!r} already exists")
                anchor = orderparse.local_to_map(center, crs,
                                                 ofm.offset_fwd, ofm.offset_left)
                ships = [Ship(name=f"{fleet_name}-{i+1}", index=i)
                         for i in range(ofm.n_ships)]
                kind = ofm.kind
                turning = ofm.turning if ofm.turning != "na" else TURN_FOLLOW
                relative = ofm.relative
                run_fm = Formation(
                    name=ofm.name, ships=ships,
                    offset_fwd=0.0, offset_left=0.0,
                    relative=relative, kind=kind,
                    spacing=ofm.spacing, deploy=ofm.deploy,
                    echelon_deg=ofm.echelon_deg, turning=turning,
                    frozen_offset_xy=((0.0, 0.0) if relative == REL_ABSOLUTE else None),
                )
                run_fm.note = ofm.note
                f = Fleet(
                    name=fleet_name, side=side, activated_turn=activated,
                    anchor_xy=anchor, anchor_substep=activated * 6,
                    course=crs, speed=speed, initial_course=crs,
                    formations=[run_fm],
                )
                f.display_history.append((activated * 6, *anchor))
                self.fleets[fleet_name] = f
                created.append(fleet_name)
        return created
```

> **若阶段 A 的 `Fleet`/`Formation`/`Ship` 构造器签名不同**(例如 A 仍要求传 `ships=` 到 Fleet,或字段名为 `offset_local`):按 A 的真实签名调整这段构造代码,保持"anchor=local_to_map 结果、运行期 Formation offset 归零、absolute 时 frozen_offset_xy=(0,0)、relative 时 None"三条契约。

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_orderparse.TestLoadOrder -v`
Expected: PASS — 7 项全绿。

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py tests/test_orderparse.py
git commit -m "feat(loadorder): Game.load_order_file instantiates one Fleet per Formation

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `_cross_pairs` 下沉遍历 + 接敌报告中心改 Fleet 几何中心

**Files:**
- Modify: `fleet_search.py`(`_cross_pairs` ≈ 437-448;`_resolve_encounter` ≈ 502-544 报告中心来源;确认 `ship_positions` 聚合全部 Formation)
- Test: `tests/test_orderparse.py`(追加 `TestCrossPairsLayers`)

- [ ] **Step 1: Write the failing test**

往 `tests/test_orderparse.py` 末尾追加。该测试构造两个零偏移单纵 Fleet 直接面对面,验证多 Formation 遍历 + 接敌零回归 + 报告中心是 Fleet 几何中心(`lead_xy`):

```python
class TestCrossPairsLayers(unittest.TestCase):
    def test_cross_pairs_traverses_all_ships(self):
        # 一个 GB Fleet 通过 add formation 挂两个 Formation,_cross_pairs 应展开全部 Ship
        g = fs.Game()
        g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 2)
        g.add_fleet("GE1", "GE", 0, "1,0", "W", 18, 2)
        pairs = g._cross_pairs(0)
        # GB 2 ship × GE 2 ship = 4 对(单 Formation 基线)
        self.assertEqual(len(pairs), 4)
        for d, fa, fb in pairs:
            self.assertEqual(fa.side, "GB")
            self.assertEqual(fb.side, "GE")

    def test_encounter_rollback_unchanged(self):
        # 两零偏移单纵 Fleet,某拍中心距 <vis,仍逐船判跨阵营、回退 S-1
        g = fs.Game()
        g.visibility = 20000.0
        # 放近一些:相隔 ~19000 < vis,应立刻在第 1 拍命中 -> 回退到 sub0
        g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 1)
        gb = g.fleets["GB1"]
        ge_anchor = (gb.anchor_xy[0] + 19000.0, gb.anchor_xy[1])
        g.add_fleet("GE1", "GE", 0, "1,0", "W", 18, 1)
        g.fleets["GE1"].anchor_xy = ge_anchor
        g.fleets["GE1"].display_history = [(0, *ge_anchor)]
        encs = g.step_turn()
        self.assertTrue(encs)
        self.assertEqual(g.state, fs.STATE_CONTACT)
        # 报告中心 = Fleet 几何中心 lead_xy(roll)
        e = encs[0]
        roll = g.current_substep
        self.assertAlmostEqual(e["gb_xy_roll"][0],
                               g.fleets["GB1"].lead_xy(roll)[0], places=3)
        self.assertAlmostEqual(e["gb_xy_roll"][1],
                               g.fleets["GB1"].lead_xy(roll)[1], places=3)

    def test_loaded_fleets_only_cross_side_pairs(self):
        # 导入 GB+GE 后,_cross_pairs 只产出 GB×GE,绝不含同阵营对
        g = fs.Game()
        g.load_order_file(GB_FILE, "GB", "0,0")
        g.load_order_file(GE_FILE, "GE", "20,0")
        pairs = g._cross_pairs(0)
        self.assertTrue(pairs)
        for d, fa, fb in pairs:
            self.assertEqual(fa.side, "GB")
            self.assertEqual(fb.side, "GE")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_orderparse.TestCrossPairsLayers -v`
Expected: 视阶段 A 现状而定 —— 若 A 已让 `ship_positions` 聚合全部 Formation 且报告中心已是 `lead_xy`,前两项可能已 PASS;`test_loaded_fleets_only_cross_side_pairs` 依赖 Task 4 的 `load_order_file`,应 PASS。**关键**:运行确认 `test_cross_pairs_traverses_all_ships` 与 `test_encounter_rollback_unchanged` 通过;若 `gb_xy_roll` 断言失败(报告中心还指向旗舰而非 Fleet 几何中心),则进入 Step 3 修。

> 若全部已通过(A 已满足契约),仍执行 Step 3 做**显式核对与文档注释**,确保 `_cross_pairs` 注释写明"fleet→formation→ship",再提交;不要跳过提交。

- [ ] **Step 3: Write minimal implementation**

确认/改造 `fleet_search.py` 的 `_cross_pairs`,使其经由 `fleet.ship_positions(sub)`(该方法已聚合全部 Formation 的全部 Ship,见前置依赖)展开,并加注释说明遍历层次:

```python
    def _cross_pairs(self, sub):
        # 遍历 fleet -> formation -> ship:ship_positions(sub) 已聚合该 Fleet
        # 下属全部 Formation 的全部 Ship 的精确 xy。接敌粒度仍是 Ship(顶点对顶点
        # 案例要求逐船真实欧氏距离);只判跨阵营 GB×GE。
        gb = [f for f in self.fleets.values() if f.side == 'GB' and f.is_active(sub)]
        ge = [f for f in self.fleets.values() if f.side == 'GE' and f.is_active(sub)]
        pairs = []
        for fa in gb:
            pa = fa.ship_positions(sub)
            for fb in ge:
                pb = fb.ship_positions(sub)
                for _, (ax, ay) in pa:
                    for _, (bx, by) in pb:
                        pairs.append((math.hypot(ax - bx, ay - by), fa, fb))
        return pairs
```

确认 `_resolve_encounter` 里 `entry` 的 `gb_xy_roll/ge_xy_roll/gb_xy_contact/ge_xy_contact` 全部取自 `fa.lead_xy(...)`/`fb.lead_xy(...)`(Fleet 几何中心),**不**取某条 Ship 位置。现有代码(`fleet_search.py:525-528`)已是 `fa.lead_xy(roll)`/`fa.lead_xy(contact_sub)`,阶段 A 已把 `lead_xy` 上移为 Fleet 几何中心,故此处**保持不变**即满足"报告中心=Fleet 几何中心"。若 A 把 `lead_xy` 改名或语义偏移,则把这四处统一指向 Fleet 几何中心 API。

> 若 Step 2 中 `ship_positions` 仅返回单 Formation,需在 `Fleet.ship_positions` 内改为遍历 `self.formations` 累加(spec §3.4)。该方法属阶段 A;若此处需补,改 `Fleet.ship_positions` 为:对每个 `formation in self.formations`,按其 `turning`/`relative` 算各 Ship xy,合并成一个 `[(name, xy), ...]` 列表返回。保持返回结构不变。

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_orderparse.TestCrossPairsLayers -v`
Expected: PASS — 3 项全绿。

并跑接敌相关回归确认零回归:

Run: `python -m unittest tests.test_fleet_search tests.test_post_encounter tests.test_state_machine_loop tests.test_view_filter -v`
Expected: PASS（全部原样通过）。

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py tests/test_orderparse.py
git commit -m "feat(detect): _cross_pairs traverses fleet->formation->ship; report center = fleet geometric center

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `loadorder` / `add formation` / `del formation` / `list formations` CLI

**Files:**
- Modify: `fleet_search.py`(`run_command` 分支区 ≈ 1024-1102;`HELP` 文本 ≈ 978-1002;`Game` 内新增 `add_formation`/`del_formation` 方法)
- Test: `tests/test_orderparse.py`(追加 `TestOrderCLI`)

- [ ] **Step 1: Write the failing test**

往 `tests/test_orderparse.py` 末尾追加。用阶段 A/现有的 `fs.execute_command(game, line)` 捕获输出做端到端 CLI 测试:

```python
class TestOrderCLI(unittest.TestCase):
    def test_loadorder_cli(self):
        g = fs.Game()
        out = fs.execute_command(g, f'loadorder GB "{GB_FILE}" 0,0')
        self.assertEqual(len(g.fleets), 19)
        self.assertIn("19", out)

    def test_add_formation_cli(self):
        g = fs.Game()
        fs.execute_command(g, "new GB1 GB 0 0,0 E 18 4")
        fs.execute_command(g, "add formation GB1 scouts ships 2 offset 8000F 10000L kind abreast spacing 4000 deploy right turning together rel absolute")
        f = g.fleets["GB1"]
        self.assertEqual(len(f.formations), 2)
        added = [fm for fm in f.formations if fm.name == "scouts"][0]
        self.assertEqual(len(added.ships), 2)
        self.assertEqual(added.kind, "abreast")
        self.assertEqual(added.spacing, 4000.0)
        self.assertEqual((added.offset_fwd, added.offset_left), (8000.0, 10000.0))
        self.assertEqual(added.turning, "together")
        self.assertEqual(added.relative, "absolute")

    def test_add_formation_single_auto(self):
        g = fs.Game()
        fs.execute_command(g, "new GB1 GB 0 0,0 E 18 4")
        fs.execute_command(g, "add formation GB1 picket ships 1 offset 21000F")
        added = [fm for fm in g.fleets["GB1"].formations if fm.name == "picket"][0]
        self.assertEqual(added.kind, "single")
        self.assertEqual(len(added.ships), 1)

    def test_del_formation_cli(self):
        g = fs.Game()
        fs.execute_command(g, "new GB1 GB 0 0,0 E 18 4")
        fs.execute_command(g, "add formation GB1 scouts ships 2")
        self.assertEqual(len(g.fleets["GB1"].formations), 2)
        fs.execute_command(g, "del formation GB1 scouts")
        self.assertEqual(len(g.fleets["GB1"].formations), 1)

    def test_list_formations_cli(self):
        g = fs.Game()
        fs.execute_command(g, "new GB1 GB 0 0,0 E 18 4")
        fs.execute_command(g, "add formation GB1 scouts ships 2")
        out = fs.execute_command(g, "list formations GB1")
        self.assertIn("scouts", out)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_orderparse.TestOrderCLI -v`
Expected: FAIL — `loadorder`/`add formation` 等未知命令(输出 `unknown command`),断言失败。

- [ ] **Step 3: Write minimal implementation**

在 `Game` 类内新增两个方法(放在 `load_order_file` 之后):

```python
    def add_formation(self, fleet_name, fm_name, n_ships, offset_fwd=0.0, offset_left=0.0,
                      kind=None, spacing=None, deploy="right", echelon_deg=45.0,
                      turning=None, relative=REL_ABSOLUTE):
        f = self._get(fleet_name)
        if any(fm.name == fm_name for fm in f.formations):
            raise ValueError(f"formation {fm_name!r} exists in {fleet_name!r}")
        if n_ships < 1:
            raise ValueError("need >= 1 ship")
        if n_ships == 1:
            kind = KIND_SINGLE
            turning = "na"
        else:
            kind = kind or KIND_AHEAD
            turning = turning or (TURN_FOLLOW if kind == KIND_AHEAD else TURN_TOGETHER)
        spacing = DEFAULT_SPACING if spacing is None else spacing
        ships = [Ship(name=f"{fleet_name}/{fm_name}-{i+1}", index=i) for i in range(n_ships)]
        run_fm = Formation(
            name=fm_name, ships=ships,
            offset_fwd=offset_fwd, offset_left=offset_left,
            relative=relative, kind=kind, spacing=spacing,
            deploy=deploy, echelon_deg=echelon_deg, turning=turning,
            frozen_offset_xy=None,
        )
        run_fm.note = ""
        f.formations.append(run_fm)
        return run_fm

    def del_formation(self, fleet_name, fm_name):
        f = self._get(fleet_name)
        before = len(f.formations)
        f.formations = [fm for fm in f.formations if fm.name != fm_name]
        if len(f.formations) == before:
            raise KeyError(f"no formation {fm_name!r} in {fleet_name!r}")
        if not f.formations:
            raise ValueError("cannot delete the last formation of a fleet")
```

在 `run_command` 里新增分支。`add`/`del`/`list` 是双词命令,需在分发前合并;最稳妥是在已有 `elif` 链里加专门分支。把下面分支插到 `elif cmd == 'list':` **之前**(`list` 单词命令需先判 `list formations`):

```python
    elif cmd == 'loadorder':
        # loadorder <GB|GE> <file> [q,r] [speed]
        side = args[0].upper()
        path = args[1]
        start = args[2] if len(args) > 2 else "0,0"
        spd = int(args[3]) if len(args) > 3 else 18
        created = g.load_order_file(path, side, start, speed=spd)
        print(f"  ok: loaded {len(created)} formation-fleets from {path!r}")
    elif cmd == 'add' and args and args[0].lower() == 'formation':
        # add formation <fleet> <fmname> ships <n> [offset <F/B..> <L/R..>] [kind ..]
        #   [spacing <yds>] [deploy left|right] [echelon <deg>] [turning ..] [rel ..]
        rest = args[1:]
        fleet_name = rest[0]; fm_name = rest[1]
        kw = rest[2:]
        n_ships = None; off_fwd = 0.0; off_left = 0.0
        kind = None; spacing = None; deploy = "right"; echdeg = 45.0
        turning = None; relative = REL_ABSOLUTE
        i = 0
        while i < len(kw):
            key = kw[i].lower()
            if key == 'ships':
                n_ships = int(kw[i+1]); i += 2
            elif key == 'offset':
                # 收集后续直到下一个已知关键字的 token 作为 relpos
                j = i + 1; toks = []
                known = {'ships', 'kind', 'spacing', 'deploy', 'echelon', 'turning', 'rel'}
                while j < len(kw) and kw[j].lower() not in known:
                    toks.append(kw[j]); j += 1
                off_fwd, off_left = orderparse.parse_relative_position(" ".join(toks))
                i = j
            elif key == 'kind':
                kind = kw[i+1].lower(); i += 2
            elif key == 'spacing':
                spacing = float(kw[i+1]); i += 2
            elif key == 'deploy':
                deploy = kw[i+1].lower(); i += 2
            elif key == 'echelon':
                echdeg = float(kw[i+1]); i += 2
            elif key == 'turning':
                turning = kw[i+1].lower(); i += 2
            elif key == 'rel':
                relative = kw[i+1].lower(); i += 2
            else:
                raise ValueError(f"unknown add-formation key {kw[i]!r}")
        if n_ships is None:
            raise ValueError("add formation requires 'ships <n>'")
        g.add_formation(fleet_name, fm_name, n_ships, off_fwd, off_left,
                        kind=kind, spacing=spacing, deploy=deploy,
                        echelon_deg=echdeg, turning=turning, relative=relative)
        print(f"  ok: added formation {fm_name!r} to {fleet_name!r}")
    elif cmd == 'del' and args and args[0].lower() == 'formation':
        g.del_formation(args[1], args[2])
        print(f"  ok: deleted formation {args[2]!r} from {args[1]!r}")
    elif cmd == 'list' and args and args[0].lower() == 'formations':
        f = g._get(args[1])
        for fm in f.formations:
            note = f"  [note: {fm.note}]" if getattr(fm, 'note', '') else ""
            print(f"  {fm.name:<16} ships={len(fm.ships)} kind={fm.kind} "
                  f"offset=({fm.offset_fwd:.0f}F,{fm.offset_left:.0f}L) "
                  f"turn={fm.turning} rel={fm.relative}{note}")
```

> **分支顺序坑**:现有 `elif cmd == 'list':` 会先吞掉所有 `list ...`。务必把 `elif cmd == 'list' and args and args[0].lower() == 'formations':` 放在裸 `elif cmd == 'list':` **之前**;`add`/`del` 同理放在任何裸 `add`/`del` 之前(现无裸 add/del,安全)。

在 `HELP` 文本里(`fleet_search.py` ≈ 985 行附近,`formation` 命令行旁)补四行说明:

```python
  loadorder <GB|GE> <file> [q,r] [speed]      import an order-of-battle file
  add formation <fleet> <fmname> ships <n> [offset ..F/B ..L/R] [kind ..] [spacing ..] [deploy ..] [echelon deg] [turning ..] [rel ..]
  del formation <fleet> <fmname>
  list formations <fleet>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_orderparse.TestOrderCLI -v`
Expected: PASS — 5 项全绿。

并跑 CLI 冒烟回归:

Run: `python -m unittest tests.test_cli_smoke tests.test_execute_command -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py tests/test_orderparse.py
git commit -m "feat(cli): loadorder + add/del/list formation commands

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: `plot_order` 编组校验可视化

**Files:**
- Modify: `fleet_search.py`(在 `plot_state` 之后新增 `plot_order`;`run_command` 加 `plot order` / `plotorder` 子命令)
- Test: `tests/test_orderparse.py`(追加 `TestPlotOrder`,Agg + skip-if-no-matplotlib)

- [ ] **Step 1: Write the failing test**

往 `tests/test_orderparse.py` 末尾追加:

```python
class TestPlotOrder(unittest.TestCase):
    def setUp(self):
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            self.skipTest("matplotlib not installed")

    def test_plot_order_gb_smoke(self):
        import tempfile, os as _os
        g = fs.Game()
        g.load_order_file(GB_FILE, "GB", "0,0")
        fd, path = tempfile.mkstemp(suffix=".png")
        _os.close(fd)
        try:
            fs.plot_order(g, path)
            self.assertGreater(_os.path.getsize(path), 0)
        finally:
            _os.remove(path)

    def test_plot_order_ge_smoke(self):
        import tempfile, os as _os
        g = fs.Game()
        g.load_order_file(GE_FILE, "GE", "0,0")
        fd, path = tempfile.mkstemp(suffix=".png")
        _os.close(fd)
        try:
            fs.plot_order(g, path)
            self.assertGreater(_os.path.getsize(path), 0)
        finally:
            _os.remove(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_orderparse.TestPlotOrder -v`
Expected: FAIL — `AttributeError: module 'fleet_search' has no attribute 'plot_order'`（或 matplotlib 缺失时 skip,此时本任务可仅做实现并以"导入无 NameError"为最低验收)。

- [ ] **Step 3: Write minimal implementation**

在 `fleet_search.py` 的 `plot_state` 之后新增(复用网格/颜色/`micro_str`;每个运行期 Fleet 内 1 个 Formation,画 Formation 中心 + 内部 Ship + Initial Course 箭头 + note 描边):

```python
def plot_order(game, filename):
    """编组校验图:画每个 Fleet(=一个 Formation)的中心、内部 Ship、
    Initial Course 箭头;带 note 的醒目描边 + 旁注。GB 红 / GE 蓝(锁定)。"""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon, Circle
    except ImportError:
        raise RuntimeError("matplotlib not installed; pip install matplotlib")

    fleets = list(game.fleets.values())
    if not fleets:
        raise RuntimeError("no fleets to plot; loadorder first")

    pts = []
    for f in fleets:
        pts.append(f.lead_xy(f.anchor_substep))
        for _, p in f.ship_positions(f.anchor_substep):
            pts.append(p)
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    m = HEX_SIDE * 1.5
    x_min, x_max = min(xs) - m, max(xs) + m
    y_min, y_max = min(ys) - m, max(ys) + m

    r_lo = int(math.floor(y_min / (HEX_SIDE * _S3))) - 1
    r_hi = int(math.ceil(y_max / (HEX_SIDE * _S3))) + 1
    fig, ax = plt.subplots(figsize=(13, 12))
    for r in range(r_lo, r_hi + 1):
        q_lo = int(math.floor(x_min / HEX_SIDE - r / 2.0)) - 1
        q_hi = int(math.ceil(x_max / HEX_SIDE - r / 2.0)) + 1
        for q in range(q_lo, q_hi + 1):
            cx, cy = hex_center_xy(q, r)
            if not (x_min <= cx <= x_max and y_min <= cy <= y_max):
                continue
            ax.add_patch(Polygon(_hex_corners(cx, cy), closed=True, fill=False,
                                 edgecolor='#d3d3d3', linewidth=0.5))

    colors = {'GB': '#a32020', 'GE': '#1f4e8a'}
    arrow_len = HEX_SIDE * 0.6
    for f in fleets:
        col = colors[f.side]
        center = f.lead_xy(f.anchor_substep)
        # 内部 Ship 点 + 连线
        ship_pts = [p for _, p in f.ship_positions(f.anchor_substep)]
        if len(ship_pts) >= 2:
            ax.plot([p[0] for p in ship_pts], [p[1] for p in ship_pts],
                    '-', color=col, alpha=0.4, linewidth=1.0)
        for sx, sy in ship_pts:
            ax.plot(sx, sy, 'o', color=col, markersize=4,
                    markeredgecolor='black', markeredgewidth=0.3)
        # Formation 中心大标记 + 标签
        ax.plot(center[0], center[1], 's', color=col, markersize=8,
                markeredgecolor='black', markeredgewidth=0.5, zorder=4)
        note = getattr(f.formations[0], 'note', '') if f.formations else ''
        label = f"{f.name}\n{micro_str(*center)}"
        if note:
            label += f"\n⚠ {note}"
            ax.add_patch(Circle(center, HEX_SIDE * 0.25, fill=False,
                                edgecolor='orange', linewidth=2.0, zorder=3))
        ax.annotate(label, center, textcoords='offset points', xytext=(6, 6),
                    fontsize=6, color=col,
                    weight=('bold' if note else 'normal'))
        # Initial Course 箭头
        ux, uy = DIRVEC[f.initial_course]
        ax.annotate("", xy=(center[0] + arrow_len * ux, center[1] + arrow_len * uy),
                    xytext=center,
                    arrowprops=dict(arrowstyle="->", color=col, alpha=0.6, lw=1.0))

    ax.set_xlim(x_min, x_max); ax.set_ylim(y_min, y_max)
    ax.set_aspect('equal'); ax.invert_yaxis()
    ax.set_title("Order of Battle — GB=red GE=blue  (⚠ = inferred decision, verify)")
    ax.set_xticks([]); ax.set_yticks([])
    plt.tight_layout(); plt.savefig(filename, dpi=110, bbox_inches='tight'); plt.close(fig)
```

在 `run_command` 里把现有 `elif cmd == 'plot':` 分支替换为支持 `plot order [file]`:

```python
    elif cmd == 'plot':
        if args and args[0].lower() == 'order':
            fn = args[1] if len(args) > 1 else 'order.png'
            plot_order(g, fn); print(f"  ok: saved {fn}")
        else:
            fn = args[0] if args else 'board.png'
            plot_state(g, fn); print(f"  ok: saved {fn}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_orderparse.TestPlotOrder -v`
Expected: PASS（或 matplotlib 缺失时 skip 2 项)。

人工出图核对(交付物,spec §6.4/§6.7):

```bash
python -c "import fleet_search as fs; g=fs.Game(); g.load_order_file('GBformation.txt','GB','0,0'); fs.plot_order(g,'order_GB.png')"
python -c "import fleet_search as fs; g=fs.Game(); g.load_order_file('GEformation.txt','GE','0,0'); fs.plot_order(g,'order_GE.png')"
```
Expected: 生成 `order_GB.png`/`order_GE.png`;肉眼核对 SE 全朝东南、SG 朝西北,6th Div./两 München/2CS 有橙圈描边。

- [ ] **Step 5: Commit**

```bash
git add fleet_search.py tests/test_orderparse.py
git commit -m "feat(plot): plot_order order-of-battle verification view + 'plot order' CLI

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: 全量回归 + 阶段验收

**Files:**
- Test: 全部 `tests/`(无新增文件;若回归暴露问题则定点修 `fleet_search.py`/`orderparse.py`)

- [ ] **Step 1: 跑全量回归**

Run: `python -m unittest discover -s tests -t .`
Expected: OK — 全部测试通过(零失败、零错误);matplotlib 相关用例若环境无 matplotlib 则 skip,不算失败。

- [ ] **Step 2: 定点核对重点回归(spec §10.F)**

Run: `python -m unittest tests.test_fleet_search tests.test_formation tests.test_formation_integration tests.test_serialization tests.test_post_encounter tests.test_state_machine_loop tests.test_view_filter -v`
Expected: PASS（全部原样通过,验证三层下沉零回归)。

> 若 `test_serialization` 因 version 不符失败:这是阶段 A 的范畴(A 已 bump version=6 + 读旧档升级);本阶段不改序列化结构,只确认 `load_order_file` 产物经 `save`/`load` 往返不变(已由 Task 4 `test_save_load_roundtrip_preserves_anchor` 覆盖)。若仍失败,说明 A 未就位,**停止并回报**,不要在本阶段绕过。

- [ ] **Step 3: 端到端导入冒烟(两文件可导入出图)**

Run:
```bash
python -c "import fleet_search as fs; g=fs.Game(); n=g.load_order_file('GBformation.txt','GB','0,0'); print('GB fleets:', len(n)); m=g.load_order_file('GEformation.txt','GE','30,0'); print('GE fleets:', len(g.fleets)-len(n))"
```
Expected: 打印 `GB fleets: 19` 与 `GE fleets: 18`,无异常。

- [ ] **Step 4: 确认无占位 / 提交收尾(若 Step 1-3 有定点修复)**

若前三步全绿且无改动,跳过提交;若有定点修复:

```bash
git add -A
git commit -m "test(phaseB): full regression green; order ingestion end-to-end verified

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review(写计划者自检结论)

**1. Spec coverage（§6 / §3.5 / §6.4）**
- §6.1 模块布局(`orderparse.py` 独立、`fleet_search` 加 loadorder/plot_order)→ Task 1/4/6/7。
- §6.2 表头/Fleet 行/数据行 + 全角破折号 + kind/turning/relative/Ships 映射 → Task 3。
- §6.2 `parse_relative_position` 多分量 → Task 1。
- §6.3 `local_to_map`(forward_hat/left_hat/offset)→ Task 2。
- §6.4 既定决策(6th Div.→5625R+note、两 München #1/#2、2CS 两 Formation `(26350,±28350)` deploy R/L)→ Task 3(`_apply_decisions_and_dedup` + `_parse_formation_row` deploy/RelPos 规则)。
- §6.5 loadorder 落地引擎(每 Formation 一个 Fleet、absolute 懒冻结、默认 speed 18)→ Task 4。
- §6.6 add/del/list formation CLI → Task 6。
- §6.7 plot_order(中心标记/Ship/Initial Course 箭头/note 描边/micro_str)→ Task 7。
- §3.5 `_cross_pairs` 下沉 fleet→formation→ship、报告中心改 Fleet 几何中心 → Task 5。
- §10.C 端到端 `Game.fleets` 数=总 Formation 数、local_to_map 对称性、plot 冒烟 skip → Task 4/2/7。

**2. Placeholder scan**：无 TBD/TODO/"类似 Task N";每步给完整测试代码与完整实现代码。两处显式标注"若阶段 A 实名/签名不同则替换名字、保持契约"——这是真实的跨阶段适配指令,非占位。

**3. Type consistency**:中间类 `OrderShip/OrderFormation/OrderFleet/Battle` 字段在 Task 1 定义、Task 3/4 一致使用;`parse_relative_position`(Task 1)、`local_to_map`(Task 2)、`parse_battle`/`parse_battle_file`(Task 3)、`Game.load_order_file`/`add_formation`/`del_formation`(Task 4/6)、`plot_order`(Task 7)签名前后一致;offset 语义统一为 `(offset_fwd, offset_left)`,`L→+left R→−left`。

**关键风险点**:
1. **依赖阶段 A 的运行期类签名**——若 A 的 `Fleet/Formation/Ship` 构造参数名或 `ship_positions` 聚合/`lead_xy` 语义与本计划假设不一致,Task 4/5 的实现需按 A 实名改写(契约不变)。Task 8 Step 2 设了"A 未就位则停止回报"的护栏。
2. **数据行真实切列**——实测文件全角破折号两侧空格、`Deployment direction` 与 `space:` 的列序、single 行只有 4 列;`_parse_formation_row` 用"末列=Relative、倒数第二列=RelPos、中段关键字扫描"容错,但若文件实际列序与假设偏移,计数断言(13/6/12/6)会先暴露——Task 3 Step 4 给了诊断命令(看真实切列,改解析勿改期望)。
