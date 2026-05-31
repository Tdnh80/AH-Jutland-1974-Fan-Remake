# 格边中心坐标基准 (edge-center basis) — 设计 Spec

> 把舰队"常态静止点"从**六角格心**改为**六角格边中心**。这是朋友指出的原则性问题:
> 整个兵棋的移动逻辑以"格边中心"为初始点,否则很多环节(尤其转向时机)对不上。
> 已与朋友确认 5 点(见 §2),本 spec 据此落地。仅写设计,不含实现代码。

---

## 1. 背景与动机

现状:`new`/`relocate`/`loadorder` 把舰队锚在**六角格心**;`course` 排队转向到**下一个格心**。
问题:舰队停在格心时,沿航向到下一个格心是**整整一格(36000)= 一整回合**,于是在格心下的转向命令要**下一回合**才生效,与兵棋规则不符。

兵棋的自然节奏是按**格边**走:18 节一回合恰好穿过一格,从一条边的中心进、到对边中心出,格心只是这一拍的**中点**。把静止点退到格边中心后,到下一个格心只剩**半格(18000)**,转向在**下半回合(18 节的 sub3)**即生效——问题自然消失。

关键发现:**引擎是锚点无关的**。位置全程存精确 `(x,y)`,运动按"从 `anchor_xy` 沿 `course` 的弧长"参数化(`_polyline`/`_arc_at`/`_xy_at_arc`/`lead_xy`),它不在乎静止点是格心还是格边中心。所以本次改动**不触碰运动/检测/队形/状态机内核**,只改三处语义 + 扫测试。

---

## 2. 已确认的模型(朋友拍板)

1. **静止/锚点 = 进入边的中心**。"进入 K10、航向 E" ⇒ 锚在 K10 的**西边**中心(航向后方那条边)。
2. **转向点仍是六角格中心**(不是边中心)。`course` 排队到沿当前航向**前方的下一个格心**生效——`next_cell_center_along` **逻辑不变**。
3. **微观坐标报告改为相对格边中心**。
4. **"回合首尾落在边中心"只对 18 节成立**。12/24 节一回合走 24000/48000,回合边界不落在边中心(与现在 12/24 节落不到格心同理),可接受。
5. **N/S 是顶点方向、没有边**,故航向只能是 6 个边方向(= `NEIGH`);`N` 维持"仅布局轴"。

### 自洽几何(18 节)
```
西边中心 ──18000──▶ [格心: sub3, 在此应用排队转向] ──18000──▶ (新)航向的边中心
```
- 直行(无转向):西边 → 格心 → 东边(= 下一格西边)。
- 转向:西边 → 格心(转向)→ 新航向边中心。因 `APOTHEM = HEX_SIDE/2 = 18000` 恰为半格,首尾必落在边中心。
- 6 条边的法向正好是 6 个航向:`边中心(dir) = 格心 + APOTHEM·DIRVEC[dir]`(代码已有 `APOTHEM`、`DIRVEC`)。

---

## 3. 实现设计

### 3.1 新增 helper(模块级)
```
entry_edge_center(q, r, course) -> (x, y)
    = hex_center_xy(q, r) + APOTHEM · DIRVEC[OPPOSITE[course]]      # 进入边 = 航向后方那条边
    若 course 不是 6 个边方向(如 N/S 布局轴):退化为 hex_center_xy(q, r)(顶点方向无边)。
```
配套:`edge_center(q, r, dir)` = `hex_center_xy(q,r) + APOTHEM·DIRVEC[dir]`(供报告/落点复用)。

### 3.2 落点改为格边中心(4 处)
| 函数 | 现状 | 改为 |
|---|---|---|
| `add_fleet(name,…,hex,course,…)` | `anchor_xy = hex_center_xy(hex)` | `anchor_xy = entry_edge_center(hex, course)` |
| `relocate(name, hex, course, …)` | `anchor_xy = hex_center_xy(hex)` | `anchor_xy = entry_edge_center(hex, course)` |
| `load_order_file(…, start_hex, …)` | Fleet 中心 = `hex_center_xy(start_hex)` | Fleet 几何中心 = `entry_edge_center(start_hex, fleet.course)`(course=N/S 退化为格心) |
| `schedule(…)`(下计划时 snap 起点) | `anchor_xy = hex_center_xy(cur_hex)` | `anchor_xy = entry_edge_center(cur_hex, dir(cur→w1))`(见 §3.5) |
| `_end_schedule`(schedule 收尾再锚) | `anchor_xy = lead_xy(end)`(精确终点) | **不变**(终点本就是边中心,见 §3.5) |

`anchor_substep`、`course`、`display_history` 首点等随锚点同步(`display_history` 首点改记锚点=边中心)。

### 3.3 转向点:不变
`course_change` 仍调 `next_cell_center_along(P, f.course)` 求**下一个格心**。
- 验证:从西边中心(P = 格心 − 18000·DIRVEC[E])求沿 E 的下一个格心 = 本格心(18000 处)。边界点 `xy_to_hex` 无论 round 到本格或前一格,结果都指向本格心(已数值验证)。
- 因此 18 节转向在 sub3(t_hit=3)生效,而非整回合后。`_check_pending_turns`/`_apply_pending_turn`/`incoming_dir` **均不变**。

### 3.4 报告改为相对格边中心(`micro_position`/`micro_str`)
- `micro_position(x, y)`:`hex = xy_to_hex(x,y)`;在该格 6 个边中心里取**最近**的,返回 `(hex, edge_dir, dist_from_edge_center)`。
- `micro_str(x, y)`:
  - 距某边中心 ≈ 0(阈值如 1e-3):`"(q,r) <dir>边中心"`(如 `K10 W边中心`)。
  - 否则:`"(q,r) <dir>边中心 +<dist>yd"`。
  - **特例**:恰在格心(到各边等距 = 18000,即 18 节 sub3),报 `"(q,r) 格心"`,避免任选一边的歧义。
- 影响面:接敌报告、`status_line`、特写图标注、`display_cell` 仍只管"哪个格"不变。

### 3.5 schedule 模式(本次一并转格边中心,改动极小)
`schedule` 用六角格航路点显式铺路。当前实现下计划时已把起点 **snap 到 `cur_hex` 格心**(`f.anchor_xy = hex_center_xy(cur_hex)`)。**唯一改动**:把这个 snap 目标从格心改为**进入边中心**:
```
f.anchor_xy = entry_edge_center(cur_hex, dir(cur_hex → w1))   # dir = chain[0]→chain[1]
```
其余**全不变**:`waypoints`(仍是航路点格心)、`f.course = dir(cur→w1)`、`total = need × HEX_SIDE`、折线 `[anchor] + [hex_center_xy(w) …]`、`schedule_end_substep`。

**几何为何自洽**(关键):锚点退到进入边后,折线整体沿航向后移 18000(=APOTHEM):
- 回合边界(18 节每 36000 弧长)**自动落在相邻格的公共边中心**(歇脚=边)。
- 航路点格心成为每拍**中点**,即**转向点**(转在心)。
- 总弧长 `N×36000` 不变 ⇒ 舰队终点落在**最后一个航路点的进入边**(= `w_{N-1}/w_N` 公共边,比 `w_N` 格心早 18000),与"落点整体后移 APOTHEM"一致。
- `_end_schedule` 锚在 `lead_xy(end)` = 该进入边中心,**天然是边中心,无需改**。

边界:下计划时 `cur_hex = xy_to_hex(lead)`,若舰队恰在边上,`cur_hex` 取整可能落到任一侧(§4 已述);snap 与 `dir(cur→w1)` 几何上仍成立。schedule 起点 snap 行为本就存在(原 snap 到格心),此处只换 snap 目标。

### 3.6 锁定约定的更新
- 原"位置存精确 (x,y),报告不吸附格心" → 更新为:**常态静止点 = 格边中心**;运动中仍存精确 (x,y)、不吸附;**报告基准 = 格边中心**(边中心本身是真实点,非吸附)。
- 其余锁定约定(视距上限 36000、回退 >vis 拍、axial 增量、18kn=6 拍/格、只判跨阵营、course 到格心才转)**不变**。

---

## 4. 边界与交互

- **12/24 节**:转向仍在下一个格心生效(`next_cell_center_along` 不变);回合边界不落在边中心(已确认可接受)。
- **N/S 航向(布局轴)**:无进入边,落点退化为格心;不可操舵(不在 `NEIGH`),`course_change` 仍拒绝 N/S。
- **边界点 `xy_to_hex` 取整**:边中心在两格交界,`xy_to_hex` 可能 round 到任一侧;§3.3 已验证转向点结果不受影响;报告里取"最近边中心"也对称稳定。
- **接敌检测/回退/队形/双盲/状态机**:全部基于精确 xy,**不变**。接敌报告中心(Fleet 几何中心 `lead_xy`)的微观坐标按新口径(§3.4)显示。
- **序列化/旧档**:`anchor_xy` 是精确点,存读不变;旧档(格心锚)载入后位置照旧(不自动平移),仅**新落点**用边中心。无需 bump 版本。

---

## 5. 测试影响(本次主要成本)

凡**硬编码绝对坐标**、或依赖"锚在格心/转向在整回合"的用例需更新(数值平移,语义不变):
- `test_course_queue`:`add_fleet "0,0" E` 锚点 → (−18000,0);`course SE` 在 **sub3**(非 sub6)、格心 (0,0) 转向;`next_cell_center_along` 单测不变。鱼贯/180°/清 pending 断言按新锚点平移。
- `test_formation_layers`:绝对位置断言平移;相对等价性(对 `_xy_at_arc`/`place_map` 公式)不变。
- `test_replay`:直行位置断言平移(锚点 −18000)。
- `test_orderparse`:`test_fleet_center_at_start_hex…`、`…zero_offset…at_fleet_center`、anchor 往返 → 改为断言**边中心**;3BCS/1SG 等渲染中心相对 Fleet 几何中心(=边中心)推导。
- `test_cli_coords`(`micro_str`/`micro_position`):改为新"边中心"格式。
- `test_closeup_smoke`/`test_post_encounter` 等用 `schedule` 造接敌的用例:位置整体后移,接敌仍发生(只断言 state/文件的不受影响;断位置的需平移)。
- 新增:`entry_edge_center` 单测(6 方向边中心、N/S 退化为格心、OPPOSITE 进入边)、`micro_str` 边中心格式、`relocate K10 E → 西边中心`、18 节 `course` 在 sub3 转向、**`schedule` 起点 snap 到进入边 + 回合边界落在公共边中心 + 终点在末航路点进入边**。
- 验收线:`python -m unittest discover -s tests -t .` 全绿;锁定约定测试相应更新断言(非迁就)。

---

## 6. 开放项 / 后续
- 微观报告里"恰在格心"特例的措辞、以及"+Xyd"是否要再标朝向(toward 哪条边),可在实现时按可读性微调,plot 校验。
- 原点 `(0,0)` 对应搜索图哪格(独立的老问题,不阻塞本次)。
- (schedule 已纳入本次,见 §3.5。)

---

## 7. 改动文件清单
- `fleet_search.py`:新增 `entry_edge_center`/`edge_center`;改 `add_fleet`/`relocate`/`load_order_file`/`schedule` 落点(统一锚到进入边中心);改 `micro_position`/`micro_str`;`next_cell_center_along`/course 排队/`_end_schedule`/检测/队形**不动**。
- 锁定约定文档(`CLAUDE.md`/`DEVELOPER.md`/`README.md`):更新"静止点=格边中心、报告相对格边中心"。
- `tests/`:按 §5 更新与新增。
