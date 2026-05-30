# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **日德兰搜索/接敌裁判工具** — 给 Claude Code 的项目上下文。本文件浓缩了从需求到 **v6** 的全部关键决策、约定和待办。读完应能直接接手而无需重读全部历史。

---

## 项目是什么

为《日德兰(JUTLAND 1974)》微缩兵棋的**搜索/接敌阶段**做的命令行裁判工具。
英(GB)、德(GE)两方舰队在六角搜索图上各自机动、初始互不可见;程序按 10 分钟一拍
推进时间,逐船计算英德距离,**距离 < 视距即"接敌"**,报告时刻/位置/涉及哪两支舰队。
范围到"接敌"为止,**不含战斗**。

**为什么不能简单判"是否同格"**(这是程序存在的根本理由,勿推翻):视距(~20k–36k 码)
与格大小(36k 码对边距)同量级。同格两船最远差 ~41570 码(顶点对顶点)可互相看不见;
隔壁格两船贴公共边却近在咫尺、能看见。所以必须算真实欧氏距离,而非数格子。

代码:已从单文件拆成几个模块(见下)。当前版本 **v6**。Python 3.10+,matplotlib 仅画图用。

---

## 运行与测试

```bash
pip install matplotlib
python fleet_search.py            # 交互式 CLI(Windows 用 python,不是 python3)
```

快速冒烟:`demo`(默认 seed 0;两队用 course 排队转向朝对方机动,折线逼近、碰上即停,每回合存 demo_tNN.png)。
导入真实编组:`loadorder GB GBformation.txt` / `loadorder GE GEformation.txt`,再 `plot order`。

**回归测试**(测试都在 `tests/`,纯 stdlib `unittest`,无需 matplotlib;含 matplotlib 的用例会自动 skip):

```bash
python -m unittest discover -s tests -t .
```

测试钉住了「锁定的约定」(见下)。**改这些行为前先看测试是否仍应通过。** 无 linter。
**Windows / PowerShell 注意**:用 `python`(非 `python3`);PowerShell 不支持 `< file` 输入重定向,
改用 `Get-Content scenario.txt | python fleet_search.py`。

---

## 锁定的约定(改动前先确认,多为反复确认过的结果)

### 坐标
- **内部统一 axial `(q,r)`,pointy-top**,六方向邻居增量对所有格统一(无奇偶行):
  `E(+1,0) W(-1,0) NE(+1,-1) NW(0,-1) SE(0,+1) SW(-1,+1)`。NW↔SE 斜线上 q 不变。
- **I/O 边界用字母数字格名**(`coords.py`):`q`=数字、`r`=字母行。`A13`↔`(13,1)`;
  字母行 A=1…Z=26,**AA=27、BB=28、CC=29、DD=30**(翻倍式,**不是 Excel 进位**)。
  搜索图四角:左上 A13、右上 A34、左下 DD-1、右下 DD19。开发者也可直接输 `q,r`。
- 像素映射:`x = 36000·(q + r/2)`,`y = 36000·(√3/2)·r`,+y 朝"南"(下)。
- **原点 `(0,0)` 仍是任意参考点,待朋友确认对应搜索图哪个格**(改 `hex_center_xy` 偏移即可重定位)。

### 尺度 / 时间 / 速度
- 1 格对边距 = 邻格中心距 = **36000 码**(`HEX_SIDE`);中心到顶点 = 36000/√3 ≈ 20785;APOTHEM = 18000。
- **1 回合 = 60 min = 6 个 10min 小拍(substep)**;**3 回合 = 1 规划周期 = 18 拍**。
- **纪元 1916-05-31 0000**(日德兰海战日,已核实);对外日期格式 **DD/MM/YY HHMM**(日月年)。
  `time` 接受 `HHMM` / `T<n>` / `S<n>` / `sub<n>`(见 `timekeep.py`)。
- 航速仅 **12/18/24 kn = 3 回合走 2/3/4 格**。`STEP_YARDS_PER_KNOT = 36000/108 = 333.33`(18kn 恰 6 拍/格)。

### 视距 / 接敌
- 视距是**探测半径**,默认 **20000**,上限 **36000(= 1 格对边距,不是 18000 apothem)**。视距圈直径可超 1 格,正常。
- 接敌 = 任一 GB 船与任一 GE 船欧氏距离 < 视距。**只判跨阵营,粒度仍是 Ship**;遍历 `Fleet→Formation→Ship`。
- 10 分钟小拍上**离散采样**,不做连续 CPA。首个出现"某对 < vis"的拍 S → **回退到 S−1**(干净接触前态,所有对仍 ≥ vis)定格。
- 报告:HHMM 时刻 + **每支舰队几何中心的微观坐标** `hex(q,r) <距格心码数> → <哪条格边>`,**不逐船配对**。
- 辅助:对接触对在 S−1→S 间线性插值,给 = vis 的投影接触时刻/位置(仅参考,不改定格)。

### 三层编组模型(v6 核心,务必理解)
**`Fleet → Formation → Ship` 三层**(早期把 Formation 当 Fleet 处理,是 v6 修掉的根本误区):
- **Fleet** = 阵营身份 + 运动学:几何中心精确 `(x,y)`、`initial_course`、`course`、`speed`、一条中心折线(唯一真相源),含 ≥1 个 Formation。
- **Formation**(= 规则书里的 Division / 单舰单元):相对 Fleet 几何中心的偏移 `offset_fwd/offset_left`(基于 `initial_course` 为 0° 的前/左轴)、`relative`(absolute/relative)、队形三态 `kind`(ahead/abreast/echelon/single)+ `spacing` + `deploy` + `echelon_deg`、`turning`(follow/together)。
- **Ship** = 叶子:`name` + `index`;精确 xy 是派生量,不落盘。

### 四种转向 = 两个正交旋钮(不写死四分支)
- `relative`(Formation 相对 Fleet 中心):`absolute`=偏移在地图绝对方位冻结(懒冻结 `frozen_offset_xy`,基准 `initial_course`)/ `relative`=偏移随当前 `course` 旋转。
- `turning`(Formation 内 Ship 转向):`follow`=鱼贯/沿航迹弧长回退 / `together`=刚体同时转。

| 命名 | relative × turning |
|---|---|
| Turn in Succession(鱼贯) | absolute + follow |
| Turn Together(同时转) | absolute + together |
| Compass Turn(罗经转) | relative + follow |
| 第四种(罕见) | relative + together → 退化为 Compass |

**解耦原则**:`turning` 管"中心航迹 + 内部船怎么跟",`relative` 只管"偏移向量按哪个航向旋转",**绝不二次旋转**。

### course 排队转向(v6)
- `course` **不再原地即时转**,而是登记待转向(`pending_course/speed/turn_xy`),旗舰**驶到当前航向前方的下一个格心才 pivot**(`next_cell_center_along` 求点;`_check_pending_turns` 每拍检测、在精确分数拍 `t_hit` 调 `_apply_pending_turn`)。格心是精确到达点,**不违反"报告不吸附格心"**。
- `incoming_dir` 记下旧航向,使后船在到达**同一格心**前仍留在进入腿上(真鱼贯)。
- 转向应用时把**格心顶点 `(t_hit, 中心)`** 插进 `display_history`,绘图航迹才在格心拐弯(否则 10min 一拍的弦会切角)。
- 进接敌态(`_resolve_encounter`)清空所有 fleet 的 pending(与清 schedule 对称)。180° 掉头简化为排队到前方格心反向。

### 运动学 / 队形几何
- 单纵阵默认船距 500 码(编组文件里 GE 用 550、GE SG 用 600)。船名 `<fleet>-1`(旗舰)…
- 位置内部存**精确 (x,y)**,沿折线按弧长参数化;**报告时绝不吸附格心**。`anchor_substep` 可为 float。
- `ship_positions(sub)` 对外仍返回扁平 `[(name,xy),…]`;零偏移单 Formation 退化为旧的鱼贯/刚体,行为不变(零回归)。

### 接敌后状态机(v5)
- `STATE_SEARCH` / `STATE_CONTACT`;接敌定格时记 `contact_hexes`、转 CONTACT。
- `adjacent_entrants(lookahead)`:接敌格邻格、且 lookahead 拍内会驶入接敌格的第三方。
- `resume_search_if_clear()`:所有涉及舰队中心都驶离接敌格 → 回 SEARCH(判据是中心格是否离开 `contact_hexes`,**不是"距离 ≥ vis"**——后者在定格点恒成立会误判脱离)。

### 显示
- **GB = 红,GE = 蓝**。视距圈**每艘船都画**。过去航迹实线、计划航迹虚线 + ★、接敌金色 ✕。
- `plot order` 专用编组校验图:**每个 Fleet 一个子图**(避免多 Fleet 共起点叠一起),画 Fleet 几何中心 + Initial Course 箭头 + 各 Formation 中心/内部 Ship;同名消歧的 Formation 带橙圈 + note。note 含中文,绘图自动挑 CJK 字体回退。

### 日志 / 存档 / 回放(v6 口径)
- **`turn = current_substep // 6`**,turn 0 = 初始局面(`step_turn` 入口若日志空则补记)。`journal.turns` 是 `[{turn, snapshot}]`,**同回合号覆盖**(接敌回退快照 substep 非 6 倍数,归入其 //6 回合作为该回合定格态,不另占槽)。
- `replay <turn>` 经 `snapshot_at_turn(turn)`→`load_dict` 恢复,时刻/位置/状态自洽;越界抛 IndexError。旧档(裸快照列表)`from_json` 自动规整。
- save/load:JSON,version=6,嵌套 `formations/ships` + pending 字段;读旧档(无 formations)`upgrade_v5_fleet` 升级为单 Formation Fleet。**一律写 v6,不导出回 v5**。不含随机种子。

---

## 代码结构(模块)

| 文件 | 职责 |
|---|---|
| `fleet_search.py` | 引擎核心 + CLI:`Game`/`Fleet`/`Formation`/`Ship`、几何与接敌、course 排队、plot、demo、双盲视图、`main` REPL |
| `coords.py` | 字母数字格名 ↔ axial(`parse_cell`/`cell_name`/`idx_to_letter`/`letter_to_idx`) |
| `timekeep.py` | 时间模型:绝对分钟 ↔ HHMM ↔ DD/MM/YY HHMM;`parse_time` |
| `formation.py` | 队形纯几何:`ship_offsets`/`to_map_offsets`/`place_map`;常量 `LINE_AHEAD/ABREAST/ECHELON`、`ABS_MODE/REL_MODE` |
| `orderparse.py` | 读 `GB/GEformation.txt` → 中间 dataclass(`OrderShip/OrderFormation/OrderFleet/Battle`)→ 实例化三层模型;`parse_relative_position`/`local_to_map` |
| `journal.py` | 操作日志:命令历史 + 回合快照(turn-key)+ JSON 读写 |
| `server.py` / `client.py` | 双盲裁判机(TCP/JSON-line,127.0.0.1):己方全见、接敌后才见对方涉及中心;命令按阵营授权 |

- `Game`:`fleets` dict、`current_substep`、`visibility`、`start_minute`、`state`、`contact_hexes`、`last_report`、`journal`、`rng`。
  - `add_fleet/delete_fleet/relocate/course_change/clear_schedule/schedule/randwalk`、`load_order_file`、`add_formation/del_formation`
  - `step_turn()`:(turn0 补记 →)逐拍 `_check_pending_turns`、记 `display_history`、接敌检测;命中 `_resolve_encounter(S)` 回退 S−1;CONTACT 态走保持/脱离分支
  - `_check_pending_turns`/`_apply_pending_turn`、`_cross_pairs`(遍历到 Ship)、`adjacent_entrants`/`resume_search_if_clear`、`view_for_side`(双盲)、`to_dict`/`load_dict`/`save`/`load`/`replay_to`、`list_status`/`status_line`
- `Fleet`:运动学字段 + `initial_course`、`formations`、`pending_*`、`incoming_dir`;旧的 `formation_kind/spacing/deploy/echelon_deg/pos_mode/layout_heading/ships` 全是**委托到主 Formation 的 property**(零回归关键)。
  - `_polyline→_arc_at→_xy_at_arc(负弧用 incoming_dir 反推)→lead_xy`;`_offset_to_map`/`_formation_center_xy`/`_formation_ship_positions`/`ship_positions`(两段式)
- 模块级:axial 工具、`next_cell_center_along`、`_axial_dist`、`random_walk_path`、`hhmm`、`plot_state`、`plot_order`、`plot_encounter_closeup`、`run_demo`、`execute_command`/`run_command`、`main`。

### 命令
`new delete relocate course schedule clear randwalk formation loadorder add/del/list formation step list vis time plot demo save load replay help quit`
- `course`:登记排队转向(到下一格心生效);有 schedule 时禁用,需先 `clear`;再发当前航向 = 取消排队。
- `schedule`:航路点数 = speed/6;相邻校验;允许中途拐弯和 180° 掉头。
- `loadorder <GB|GE> <file> [q,r] [speed]`:一个 OrderFleet → 一个运行期 Fleet(GB→BS+BCF,GE→BS+SG),Division 嵌为其 Formation。
- `plot order`:编组校验图(每 Fleet 一子图)。

---

## v5 / v6 已完成

**v5**:坐标换字母数字格名(A13)、纪元 1916-05-31 + DD/MM/YY HHMM、`save/load` 全量(命令历史 + 回合快照)、接敌后状态机、双盲裁判机(server/client)。
**v6**(对照朋友的 Formation 资料 + 反馈):

| 项 | 状态 |
|---|---|
| 三层 Fleet/Formation/Ship 模型(改掉"Formation 当 Fleet") | ✅ |
| 四种转向 = `relative`×`turning` 两旋钮 + 两段式 `ship_positions` | ✅ |
| `course` 排队到下一格心再转(含鱼贯后船滞后、绘图过格心) | ✅ |
| 读 `GB/GEformation.txt` 导入三层编组(`loadorder`)+ `plot order` 校验 | ✅ |
| `replay <turn>` 回合号口径修正(turn=substep//6、补 turn0、时刻/位置自洽) | ✅ |
| demo 改 course 折线机动(seed 默认 0 可复现、`plot=False` 供测试) | ✅ |
| 编组文件笔误已由朋友更正(6th Div 5625R、München#2→Stuttgart),解析改回忠实 | ✅ |

---

## 待朋友拍板 / 后续(v7+)

- **原点 `(0,0)` 对应搜索图哪个格**(影响 `loadorder` 起始格;现两支 Fleet 默认同锚一格)。
- `together` 同时转的离散时机是否也排队到格心(与排队转向耦合);阵营专属同时反转 180°。
- **接敌后状态机的完整转移**(保持接触/脱离/连续 encounter 的细化)——现已可用,接口预留。
- 联网的握手/重连、PyQt GUI(server/client 已有 TCP 双盲原型)。
- 子编队跨格时是否拆为独立 Fleet。

### 仍未做 / 已知简化
轻巡侦察幕(被有意抽掉)、突破侦察幕、战斗、海岸/雷区/陆地识别、任意航向/航速、拆队/合队。

---

## 领域背景与原始材料

朋友提供的文件(权威来源)。原始资料已从 `requirement.zip` 解压到 `requirement/`:
- `abstract.docx`:问题抽象,Q1–Q6。"能见度不大于六角格宽""相遇只在 2 格内发生"。
- `requirement/requirement.docx`:尺度与微观运动表。战术格 36000yd=1200mm;移动尺 1kn/10min≈11mm=330yd;转向半径 450yd;基准视距 20k、最高 36k;三档速度微观离散表;轻巡侦察幕(已抽掉)。
- `requirement/《日德兰》(《JUTLAND》)74版规则中译V1.docx`:规则书。**单纵阵转向=鱼贯**(后船在旗舰同一转向点转);纵→横=同时转;战斗脱离=德军专属同时反转 180°;主力舰 ≥45° 转向用转弯半径。
- `requirement/jutlandsearchmap.pdf`:大北海搜索图。"德舰进阴影格被 spotted;雷区仅德舰可入"。
- `GBformation.txt` / `GEformation.txt`(根目录):GB/GE 完整战斗序列编组(Fleet→Division→Ships + Turning/Relative Pattern + Relative Position)。**已是权威数据,忠实解析。**
- `requirement/*.png`、根目录 `修正.txt`(v4 来源)、`input.txt`(接口草案);Formation 三态/四转向标注图见对话历史。

历史细节:1mm=30yd,算子 20×15mm,战术六角格 36000yd。命名已统一为 **1 回合=60min,内含 6 个 10min 小拍**。

---

## 交付物清单(/outputs)
- `fleet_search.py` + `coords.py` `timekeep.py` `formation.py` `orderparse.py` `journal.py` `server.py` `client.py` —— v6 程序
- `README.md`(玩家说明)、`DEVELOPER.md`(开发者文档)、`CLAUDE.md`(本文件)
- `docs/superpowers/specs/` 设计 spec、`docs/superpowers/plans/` 分阶段实现计划
- 示例图:`order_GB.png`、`order_GE.png`、`turn_succession.png`、`demo_t*.png` 等(可删,仅演示)

---

## 给接手 agent 的提醒
- 改动前对照"锁定的约定";尤其**三层模型(别把 Formation 当 Fleet)**、**视距上限 36000(非 18000)**、**回退到 >vis 拍**、**axial 统一邻居增量**、**course 到格心才转**这几条是反复确认过的。
- 四种转向是**两个正交旋钮**,别退化成四个硬分支;接敌检测是有意的 10min 离散(非连续 CPA),勿"优化"成连续。
- 编组文件是权威数据,忠实解析、勿再加推断修正。
- 面向玩家文档要白话(见 README);技术细节放 DEVELOPER.md 或本文件。
- 用户偏好:回复用简体中文;任务不大别上 workflow/subagent(烧 token),直接改。
