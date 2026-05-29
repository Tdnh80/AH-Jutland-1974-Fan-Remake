# 开发者文档 — 日德兰搜索·接敌裁判工具 (v5)

面向贡献者和二次开发者。使用者请看 [README.md](README.md)。

---

## 模块划分

| 文件 | 职责 |
|---|---|
| `coords.py` | 字母数字格名 ↔ axial (q,r) 的双向转换 |
| `timekeep.py` | 时间模型:绝对分钟 ↔ HHMM ↔ DD/MM/YY HHMM |
| `formation.py` | 队形几何:偏移量计算、相对/绝对两种布局模式 |
| `journal.py` | 操作日志:命令记录 + 回合快照 + JSON 序列化 |
| `fleet_search.py` | 引擎核心 + CLI:坐标/显示 helper、Game 类、plot、demo、main() |

---

## 坐标系

### 内部表示

内部统一用 **axial 坐标 (q, r)**,六方向邻居增量固定(无奇偶行之分):

```
E  → (q+1, r)       W  → (q−1, r)
NE → (q+1, r−1)     SW → (q−1, r+1)
NW → (q,   r−1)     SE → (q,   r+1)
```

像素坐标(+y 向下):

```
x = HEX_SIDE × (q + r/2)
y = HEX_SIDE × (√3/2) × r
```

`HEX_SIDE = 36000.0`(单位:码)。原点 `(0,0)` 是任意参考,改 `hex_center_xy` 的偏移即可重定位。

### I/O 边界格名

`coords.py` 提供双向转换:

- `parse_cell("A13")` → `(13, 1)`:字母行 A=1, B=2 ... Z=26, AA=27 ... DD=30(上限 52 行)
- `cell_name(13, 1)` → `"A13"`:超出范围抛 `ValueError`

`fleet_search.py` 的 `parse_cell_or_hex(s)` 先尝试 `coords.parse_cell`,失败再 fallback 到 `parse_hex(s)`,支持开发者直接用 `q,r`。`display_cell(q, r)` 对称地回退到 `hex_name(q, r)`。

---

## 时间模型

- **纪元**:1916 年 5 月 31 日 0000(即 `start_minute=0`)。
- **绝对分钟**:`game.start_minute + substep * 10`。
- 1 回合 = 6 个小拍 = 60 分钟;3 回合 = 1 个规划周期。
- `timekeep.fmt_date(abs_min)` → `"DD/MM/YY HHMM"`;`timekeep.hhmm_to_min("0530")` → `330`。
- `Game.datestr(substep)` 是对外暴露的一句话 helper。

---

## 速度与格子

```
STEP_YARDS_PER_KNOT = 36000 / 108 ≈ 333.33  # 10 分钟 1 节走多少码
```

| 航速 | 每拍码数 | 1 格(36000)用多少拍 | 3 回合(18 拍)走几格 |
|---|---|---|---|
| 12 kn | 4000 | 9 | 2 |
| 18 kn | 6000 | 6 | 3 |
| 24 kn | 8000 | 4.5 | 4 |

18 kn 刚好 6 拍走 1 格,是设计上的"整数锚点"。

---

## 接敌检测与回退

`Game.step_turn()` 每个小拍逐一:

1. 更新 `display_history`(精确 x,y,不贴格心)。
2. 枚举所有 GB×GE 舰队对的船级配对距离;任一对 `< visibility` 即触发。
3. 触发后调 `_resolve_encounter(S)`:
   - `S` = 第一个触发的小拍。
   - **回退**到 `S-1`(`roll`):这是"干净的接触前状态"。
   - 对每个涉及对,在 `[roll, S]` 间线性插值求 `d = visibility` 的精确时刻(aux 信息)。
   - 把 `current_substep` 置为 `roll`;清空所有在执行的 schedule。
   - 记录 `last_report`(含 roll 时双方中心坐标)和 `contact_hexes`(roll 时双方中心格)。
   - 状态机变 `STATE_CONTACT`。

接敌后:
- `adjacent_entrants(lookahead)`:找位于接敌格邻格、且在 `lookahead` 拍内会驶入接敌格的第三方舰队。
- `resume_search_if_clear()`:所有原涉及舰队的中心都已驶离接敌格时,回到 `STATE_SEARCH`。

---

## 队形模块

`formation.py` 常量:

- `LINE_AHEAD = "ahead"`, `LINE_ABREAST = "abreast"`, `ECHELON = "echelon"`
- `REL_MODE = "relative"`, `ABS_MODE = "absolute"`

`ship_offsets(kind, n, spacing, deploy, echelon_deg)` 返回在**队形坐标系**中各船相对中心的偏移(前后轴 × 左右轴)。

`to_map_offsets(heading, offsets)` 把队形坐标系的偏移旋转到地图像素坐标系。

`Fleet.ship_positions(substep)`:
- `LINE_AHEAD`:沿航迹鱼贯(turn in succession),各船延迟固定码数沿同一折线。
- 其余:以 `lead_xy` 为中心,按 `formation.py` 的几何计算各船绝对像素位置。
  - `REL_MODE`:布局方向跟随当前 `f.course`。
  - `ABS_MODE`:布局方向用 `f.layout_heading`(设 formation 命令时冻结)。

---

## 操作日志(Journal)

`journal.Journal` 维护两个列表:

- `commands`:每条 CLI 命令的 `(abs_minute, text)` 记录。
- `turn_snapshots`:每个 `step_turn()` 结束时的 `Game.to_dict()` 快照。

`Game.save(filename)` 把 `{"current": ..., "journal": ...}` 一起写入 JSON。
`Game.load(filename)` 恢复盘面 + 日志。
`Game.replay_to(turn)` 从 `journal.snapshot_at_turn(turn)` 恢复盘面(不改动日志本身)。

---

## 绘图

- `plot_state(game, filename)`:全局图,范围自适应所有舰队的历史轨迹与计划路线。
- `plot_encounter_closeup(game, filename)`:接敌特写图,范围限定在 `contact_hexes` 及其邻格。若 `contact_hexes` 为空则退化为 `plot_state`。
- 两者均用 `matplotlib.use('Agg')` 非交互模式,`matplotlib` 不可用时抛 `RuntimeError`。

---

## 随机走

- `random_walk_path(start, speed, rng, prev_dir, straight_bias, bound)`:带直行偏置的随机走,返回 `HEX_PER_CYCLE[speed]` 个相邻格的列表。
- `attracted_walk_path(start, target, speed, rng, prev_dir, pull, bound)`:每步以概率 `pull` 选择使到 `target` 轴向距离最小的邻格,否则退化为一步 `random_walk_path`。`run_demo` 用此函数实现随回合递增吸引因子(保证长 demo 收敛接敌)。

---

## 运行测试

```bash
python -m unittest discover -p "test_*.py" -v
```

无需 pytest。所有测试均为 stdlib `unittest`。

| 测试文件 | 覆盖内容 |
|---|---|
| `test_coords.py` | 字母数字格名双向转换、边界、异常 |
| `test_timekeep.py` | 时间格式化、hhmm_to_min、fmt_date |
| `test_fleet_search.py` | 几何函数、速度常量、接敌回退、队形、存档 |
| `test_formation.py` | 偏移量计算、相对/绝对模式 |
| `test_formation_integration.py` | 队形与 Fleet/Game 集成 |
| `test_journal.py` | Journal JSON 序列化 |
| `test_journal_integration.py` | 日志与 Game 集成、replay |
| `test_post_encounter.py` | 接敌后状态机(adjacent entrants、resume search) |
| `test_serialization.py` | 全量 save/load JSON 往返 |
| `test_cli_coords.py` | parse_cell_or_hex、display_cell、micro_str |
| `test_cli_time.py` | Game.datestr |
| `test_cli_smoke.py` | formation/replay CLI 命令冒烟测试 |
| `test_demo_convergence.py` | attracted_walk_path 收敛性(8 种子 ≥6 在 40 回合内接敌) |
| `test_closeup_smoke.py` | plot_encounter_closeup 写文件冒烟测试 |

---

## 关键常量(不要随意改)

```python
HEX_SIDE = 36000.0             # 格宽(码);决定像素比例
STEP_YARDS_PER_KNOT = 36000/108  # 10 min × 1 kn → 码
DEFAULT_VISIBILITY = 20000.0
MAX_VISIBILITY = HEX_SIDE      # = 36000
HEX_PER_CYCLE = {12: 2, 18: 3, 24: 4}
```

改动任何一个都需要同步更新 `test_fleet_search.TestLockedConstants` 里的对应断言。
