# 开发者文档 — 日德兰搜索·接敌裁判工具 (v6)

面向贡献者和二次开发者。使用者请看 [README.md](README.md)。

---

## 模块划分

| 文件 | 职责 |
|---|---|
| `coords.py` | 字母数字格名 ↔ axial (q,r) 的双向转换 |
| `timekeep.py` | 时间模型:绝对分钟 ↔ HHMM ↔ DD/MM/YY HHMM |
| `formation.py` | 队形纯几何:队内各船偏移、相对/绝对布局旋转 |
| `orderparse.py` | 读 `GB/GEformation.txt` → 中间 dataclass → 实例化三层模型 |
| `journal.py` | 操作日志:命令记录 + 回合快照(turn-key)+ JSON 序列化 |
| `server.py` / `client.py` | 双盲裁判机(TCP/JSON-line)+ CLI 客户端 |
| `fleet_search.py` | 引擎核心 + CLI:`Game`/`Fleet`/`Formation`/`Ship`、几何、course 排队、plot、demo、main() |

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

### 坐标基准:格边中心(v6)

舰队**常态静止点 = 六角格边中心**(非格心)。`edge_center(q,r,d) = hex_center_xy(q,r) + APOTHEM·DIRVEC[d]`(`APOTHEM=18000`);`entry_edge_center(q,r,course) = edge_center(q,r,OPPOSITE[course])`(进入边 = 航向后方那条边;course=N/S 无边 → 退化为格心)。`add_fleet`/`relocate`/`load_order_file`/`schedule` 一律锚到进入边中心。`micro_position`/`micro_str` 报告相对**最近的边中心**(恰在格心报 `centre`)。引擎其余部分锚点无关,不受影响。

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

## 三层编组模型(v6)

`Fleet → Formation → Ship` 三层(`fleet_search.py`):

- **`Fleet`**:阵营 + 运动学。几何中心精确 `anchor_xy`、`anchor_substep`(可 float)、`initial_course`、`course`、`speed`、`formations: list`(≥1)。一条中心折线是唯一真相源。
- **`Formation`**(= Division / 单舰单元):`offset_fwd`(F+/B−)、`offset_left`(L+/R−,基于 `initial_course` 为 0° 轴)、`relative`(absolute/relative)、`kind`(ahead/abreast/echelon/single)、`spacing`、`deploy`、`echelon_deg`、`turning`(follow/together)、`ships`、`frozen_offset_xy`(absolute 懒冻结)、`note`。`is_single` = 1 船或 kind==single。
- **`Ship`**:`name` + `index`;精确 xy 派生,不落盘。

**向后兼容(零回归关键)**:`Fleet` 的旧字段 `formation_kind/spacing/deploy/echelon_deg/pos_mode/layout_heading/ships` 都改成**委托到主 Formation(`formations[0]`)的 property**;`pos_mode` 无损因为 `formation.ABS_MODE/REL_MODE` 字符串值与 `REL_ABSOLUTE/REL_RELATIVE` 相同。读旧档 `upgrade_v5_fleet` 升级为单零偏移 Formation。

## 四种转向几何(给定时刻算每艘 Ship 精确 xy)

两个正交旋钮:`relative`(Formation 相对 Fleet)× `turning`(Formation 内 Ship)。

| 命名 | relative × turning | 几何 |
|---|---|---|
| Turn in Succession | absolute + follow | 沿 Fleet 折线鱼贯 + 冻结平移 |
| Turn Together | absolute + together | 刚体平移,偏移冻结地图方位 |
| Compass Turn | relative + follow | 整列随当前航向旋转 |
| 第四种(罕见) | relative + together | 退化为 Compass |

**解耦原则**:`turning` 管中心航迹 + 内部跟随,`relative` 仅管偏移基准航向,**不二次旋转**。

`formation.py` 常量:`LINE_AHEAD/ABREAST/ECHELON`、`ABS_MODE/REL_MODE`;`ship_offsets`/`to_map_offsets`/`place_map` 纯几何。
`fleet_search.py` 旋钮常量:`TURN_FOLLOW/TURN_TOGETHER`、`REL_ABSOLUTE/REL_RELATIVE`、`KIND_AHEAD/ABREAST/ECHELON/SINGLE`。

`Fleet.ship_positions(substep)` 两段式:
1. `_formation_center_xy(fo, sub)` = `lead_xy(sub)` + 旋转偏移(absolute 用 `initial_course` 懒冻结进 `frozen_offset_xy`;relative 用当前 `course` 实算)。
2. `_formation_ship_positions(fo, sub)`:`follow`+`ahead` 走弧长回退(`_xy_at_arc(lead_arc − i·spacing)` + 平移);其余走 `formation.ship_offsets`→`to_map_offsets`→`place_map` 刚体。
对外仍返回扁平 `[(name, xy), …]`,零偏移单 Formation 与旧鱼贯/刚体逐船等价。

## course 排队转向(v6)

`course` 不再原地即时转,而是登记待转向,旗舰驶到下一格心才 pivot:

- `Fleet.pending_course / pending_speed / pending_turn_xy`:`course_change` 用 `next_cell_center_along(P, 当前course)` 算转向格心并登记(speed 也排队到同一格心)。再发当前航向 = 取消排队;有 schedule 时仍抛错。
- `next_cell_center_along(P, course)`(模块级):P 投影到过所在格心、方向 `DIRVEC[course]` 的轴,取前方第一格心(EPS 防 P 在格心取自身)。相邻格心沿任一正方向间距 = `HEX_SIDE`。
- `_check_pending_turns(sub)`:每拍判 `arc_prev < turn_arc ≤ arc_now+EPS`,命中则在精确分数拍 `t_hit = anchor_substep + turn_arc/(speed·STEP)` 调 `_apply_pending_turn`。单拍弧长 ≤ 8000 < 36000,一拍最多触发一次。
- `_apply_pending_turn(f, t_hit)`:钉锚到格心、`anchor_substep=t_hit`、改 course/(speed)、记 `incoming_dir = DIRVEC[旧course]`、清 pending、**把 `(t_hit, 格心)` 插进 `display_history`**(绘图航迹在格心拐弯,不切角)。
- `_xy_at_arc` 负弧分支:非 scheduled 且有 `incoming_dir` 时沿旧航向反推,使后船在到达同一格心前留在进入腿上(真鱼贯)。
- 进 CONTACT(`_resolve_encounter`)清空所有 fleet 的 pending。180° 掉头简化为排队到前方格心反向。
- **格边中心基准下**:静止点退到进入边中心,格心只在前方半格,故 18 节 `course` 在 **sub3** 转向(12kn sub4.5、24kn sub2.25)——`next_cell_center_along` 本身不变,是落点改变带来的提前。

## 编组导入(orderparse)

`orderparse.parse_battle_file(path, side)` → `Battle`(若干 `OrderFleet`,各挂 `OrderFormation`)。
- `parse_relative_position("8000F 10000L")` → `(fwd, left)`(F+/B−/L+/R−,多分量相加,容错全角空格)。
- `local_to_map(center, course, fwd, left)`:`forward_hat=DIRVEC[course]`、`left_hat=(fy,−fx)`(+y 朝南的左舷法向)。
- 表头行只取每个 Fleet 的 Initial Course;数据行按全角破折号 `—` 切列,末列=Relative、倒二列=RelPos、中段扫 kind/spacing/deploy/turning。
- 仅当文件中确有重名 Formation 才加 `#k` 后缀消歧(GB 文件现已用 `2CS-A`/`2CS-B` 显式区分,故不触发)。**编组文件是权威数据,不做推断修正。**
- `initial_course` 接受 6 个六角航向 + **N/S**(布局参考轴;`_norm_course` 取前缀字母方向)。N/S 不在 `NEIGH`,不可操舵,只作队形偏移 F/B/L/R 的 0° 轴。

`Game.load_order_file(path, side, start_hex, speed, activated)`:**每个 OrderFleet → 一个运行期 Fleet**(GB→`GB-BS`+`GB-BCF`,GE→`GE-BS`+`GE-SG`;**名用连字符不含空格**,否则 CLI 按空格切词无法选中),Division 嵌为其 `formations`、各自保留 offset;Fleet 几何中心锚在 `start_hex` 格心。整组作为一个 Fleet 机动。`initial_course` 校验放宽到 `DIRVEC` 键(含 N/S)。

---

## 操作日志(Journal)— turn-key(v6)

`journal.Journal`:
- `history`:每条 CLI 命令的 `{sim_min, cmd}`。
- `turns`:`[{turn, snapshot}]`,**turn = `snapshot["current_substep"] // 6`**。`record_turn` 同回合号**覆盖**(接敌回退快照 substep 非 6 倍数,归入其 //6 回合作为该回合定格态,不另占槽)。`snapshot_at_turn(turn)` 按 turn 号查找(非裸下标)。`from_json` 规整旧档(裸快照列表)。

`Game.step_turn()` 入口:若 `journal.turns` 空,先补记 **turn 0**(初始局面),使 `replay 0` 还原起始盘面。
`Game.save/load`:`{"current": to_dict(), "journal": ...}`,version=6。
`Game.replay_to(turn)`:`snapshot_at_turn(turn)`→`load_dict`,恢复后 `current_substep`/clock/位置/state 自洽;越界抛 `IndexError`。

---

## 绘图

- `plot_state(game, filename)`:全局图,范围自适应所有舰队历史轨迹与计划路线。过去航迹由 `display_history` 连线(转向格心顶点已在 `_apply_pending_turn` 插入,故在格心拐弯)。
- `plot_order(game, filename)`:编组校验图,**每个 Fleet 一个自适应子图**;画 Fleet 几何中心(空心方块)+ Initial Course 箭头 + 各 Formation 中心/内部 Ship;带 `note` 的 Formation 橙圈高亮。自动挑 CJK 字体渲染中文 note。
- `plot_encounter_closeup(game, filename)`:接敌特写,范围限定 `contact_hexes` 及邻格;空则退化为 `plot_state`。CLI 命令 `plot closeup [file]`(别名 `plot encounter`)。
- 均 `matplotlib.use('Agg')`,`matplotlib` 不可用时抛 `RuntimeError`。

---

## 随机走 / demo

- `random_walk_path(start, speed, rng, prev_dir, straight_bias, bound)`:带直行偏置的随机走,返回 `HEX_PER_CYCLE[speed]` 个相邻格。`randwalk` 命令用。
- `_axial_dist(a, b)`:两 axial 格的六角格距(cube)。
- `run_demo(g, seed=0, max_turns=30, frame_prefix, plot=True)`:两队用 **course 排队转向**朝对方机动(`steer` 每回合朝目标方向下 `course`,40% 偏到相邻方向制造可见折线但不反向),产生折线航迹并多在 40 回合内接敌。**seed 默认 0 可复现**;`plot=False` 时不画图(测试用,快、无需 matplotlib)。
- `attracted_walk_path(...)` 仍在(早期 demo 用),现 `run_demo` 不再依赖。

---

## 运行测试

```bash
python -m unittest discover -s tests -t .
```

测试都在 `tests/`;`-t .` 让项目根进 import 路径。无需 pytest,均为 stdlib `unittest`;含 matplotlib 的用例 import 失败时 skip。

| 测试文件 | 覆盖内容 |
|---|---|
| `test_coords.py` | 字母数字格名双向转换、边界、异常 |
| `test_timekeep.py` | 时间格式化、hhmm_to_min、fmt_date |
| `test_fleet_search.py` | 几何函数、速度常量、接敌回退、存档 |
| `test_formation.py` | `formation.py` 偏移量、相对/绝对模式 |
| `test_formation_layers.py` | 三层模型 + 两段式 `ship_positions` + 四转向 + 零回归等价性 |
| `test_formation_integration.py` | 队形与 Fleet/Game 集成 |
| `test_course_queue.py` | `next_cell_center_along`、course 排队、`_apply_pending_turn`、到格心才转、鱼贯后船、180°、清 pending |
| `test_orderparse.py` | 编组解析、`local_to_map`、整文件 GB/GE、`loadorder` 嵌套、`_cross_pairs` 下沉 |
| `test_journal.py` | Journal turn-key、同回合覆盖、旧档规整 |
| `test_journal_integration.py` | 日志与 Game 集成、turn-0 补记 |
| `test_replay.py` | replay 时刻/位置/越界、接敌回合不占独立槽 |
| `test_demo_path.py` | demo 可复现 + 航迹真有转向 |
| `test_demo_convergence.py` | demo 多种子不崩 + 可复现 |
| `test_post_encounter.py` | 接敌后状态机(adjacent entrants、resume search) |
| `test_serialization.py` | 全量 save/load JSON 往返(version=6 + 兼容旧档) |
| `test_cli_coords.py` / `test_cli_time.py` / `test_cli_smoke.py` | CLI helper / 命令冒烟 |
| `test_closeup_smoke.py` | `plot_encounter_closeup` 写文件冒烟 |
| `test_view_filter.py` / `test_execute_command.py` / `test_server_*.py` / `test_state_machine_loop.py` / `test_journal_header.py` | 双盲视图 / 命令分发 / 裁判机回环与授权 / 状态机循环 / 日志头 |

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
