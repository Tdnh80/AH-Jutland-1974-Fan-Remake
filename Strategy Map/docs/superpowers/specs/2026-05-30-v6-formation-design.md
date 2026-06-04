# JUTLAND 搜索/接敌裁判工具 — v6 设计 Spec

> 本文件把五个子系统设计(三层数据模型与序列化 / 四种转向几何与渲染 / course 排队转向 / 编组导入与 plot 校验 / replay & demo 修复)合并为一份连贯、可直接交付实现计划的设计。仅写设计,不含实现代码。所有[锁定约定]保留不动;凡推断/决策处以 **【决策】/【推断】/【待拍板】** 标注。

---

## 1. 概述与目标

v6 的五块工作彼此耦合,核心是把当前"单层 Fleet"(`fleet_search.py:243-262`,同时承担身份+运动学+队形三职)上提为 **Fleet → Formation → Ship** 三层,并在其上落地:

1. **三层数据模型** —— Fleet(阵营+运动学)/ Formation(相对偏移+队形+两旋钮)/ Ship(叶子)。
2. **四种转向几何** —— 两个正交旋钮 `turning`(follow/together)× `relative`(absolute/relative)统一两套坐标推导,避免双重旋转。
3. **course 排队转向** —— `course` 不再即时转,而是排队到旗舰抵达的下一格心再转(规则书单纵阵鱼贯回转点语义)。
4. **编组文件导入 + plot 校验** —— 读 `GBformation.txt`/`GEformation.txt`,实例化三层模型,出可视化让用户一眼看对错。
5. **replay & demo 修复** —— 修 `replay <turn>` 回合号错位/不重置,修 demo 只直走。

**统一目标**:重构以"现有全部回归测试原样通过"为正确性验收线(零回归);新行为以专门新增测试覆盖。所有[锁定约定]不被推翻。

**贯穿全 spec 的核心解耦原则**(消解四个子系统对"转向几何"的重叠表述):

> **`turning` 决定"每艘 Ship 的中心航迹是哪条折线、内部船怎么跟"(沿航迹弧长鱼贯 / 刚体);`relative` 仅决定"Formation 偏移向量旋转的基准航向"(冻结于 initial_course / 跟随当前 course)。两者作用在不同环节,绝不对同一向量二次旋转。**

---

## 2. 三层数据模型(Fleet / Formation / Ship)

### 2.1 职责划分(消解子系统1与子系统2的字段命名重叠)

两个子系统对三层字段给出了几乎一致但命名略有出入的方案。**统一裁定**采用以下字段名(以子系统1为主,吸收子系统2的 `offset_local` 命名为权威别名说明):

| 层 | 唯一职责 | 关键状态 |
|---|---|---|
| **Fleet** | 阵营身份 + 运动学(几何中心精确 xy、initial_course、course、speed、机动折线/schedule) | 一条中心折线 + 弧长参数化(唯一真相源) |
| **Formation**(=Division/单舰单元) | 相对 Fleet 中心的偏移 + 队形几何(三态+spacing+deploy)+ 两个转向旋钮 | `offset_fwd/offset_left`、`kind`、`turning`、`relative` |
| **Ship** | 名称 + Formation 内序号;精确 xy 是派生量(不落盘为真相源) | `name`、`index` |

### 2.2 字段定义(权威)

**Fleet**(运动学字段整组由现 `Fleet` 上移,语义不变):
- `name, side, activated_turn`
- `anchor_xy`(精确 (x,y),不吸附格心)、`anchor_substep`(**可为 float**,锁定不变量)
- `initial_course`(**新增**,布局时锚定的航向,六方向键;L/R/F/B 偏移的 0° 轴)
- `course`(当前航向)、`speed`(12/18/24)
- `scheduled, schedule_end_substep, waypoints, display_history`(原样)
- **course 排队转向新增**(§5):`pending_course`、`pending_speed`、`pending_turn_xy`
- `formations: list[Formation]`(**下层**)

**Formation**:
- `name`、`ships: list[Ship]`(len==1 即单舰单元)
- `offset_fwd`(F+/B−,码)、`offset_left`(L+/R−,码) —— 即子系统2的 `offset_local=(fwd,left)`
- `relative`(`absolute`/`relative`)
- `kind`(`ahead`/`abreast`/`echelon`/`single`)、`spacing`(默认 500)、`deploy`(`left`/`right`)、`echelon_deg`(ahead=0,abreast=90,echelon 取行内角默认 45)
- `turning`(`follow`/`together`;single 时 `na`,不影响)
- `frozen_offset_xy`(absolute 模式下布局时一次性算定并冻结的地图偏移向量;懒冻结,None=未算)
- 派生 `is_single = len(ships)==1 or kind=="single"`

**Ship**:`name`、`index`(Formation 内序号,0=该分队领舰)、缓存 `xy`(不持久化)。

### 2.3 旋钮常量与命名(统一两子系统术语)

```
TURN_FOLLOW="follow"  TURN_TOGETHER="together"
REL_ABSOLUTE="absolute"  REL_RELATIVE="relative"
KIND_AHEAD/ABREAST/ECHELON/SINGLE
```

四种组合的命名对照(权威表,合并子系统1/2):

| 命名 | relative × turning | 几何本质 | 编组文件出现 |
|---|---|---|---|
| **In Succession**(鱼贯) | absolute + follow | 各船沿同一航迹延迟弧长跟进,旗舰转向点依次转 | GB 3BCS、GE 各 Div.(Follow+Absolute) |
| **Turn Together**(同时转) | absolute + together | 整列刚体平移,偏移冻结于地图绝对方位 | GB BS 多数 Div.(Together+Absolute) |
| **Compass Turn**(罗经转) | relative + follow | 整列随当前航向旋转,各船沿折线鱼贯 | GE SG 1SG(Follow+Relative) |
| **第四种**(罕见) | relative + together | 偏移随航向转 + 刚体;**可退化为 Compass 等量代换** | GB BS Attached LC(Together+Relative)、GB BCF 1LCS 等 |

---

## 3. 四种转向几何(给定时刻算每艘 Ship 精确 xy)

统一的两段式管线(替代现 `ship_positions` 的两条硬编码分叉),对每个 Formation:

### 3.1 步骤 1 — Fleet 中心位置(沿用,上移)

`fleet.lead_xy(sub) = _xy_at_arc(_arc_at(sub))`(`fleet_search.py:299-300`)整体上移到 Fleet,语义、不变量完全不变(锚点+弧长参数化,anchor_substep 可 float)。

### 3.2 步骤 2 — Formation 中心 = Fleet 中心 + 旋转后偏移(`relative` 旋钮)

```
center = fleet.lead_xy(sub)
forward_hat = DIRVEC[fleet.course]            # relative 模式:当前航向
             或 DIRVEC[fleet.initial_course]   # absolute 模式:冻结
left_hat = (forward_hat.y, -forward_hat.x)    # +y 朝南下的左舷法向
                                              # = formation.py 右舷法向 (-uy,ux) 之负,自洽
offset_xy = offset_fwd*forward_hat + offset_left*left_hat
fcenter = center + offset_xy
```

- **absolute**:`offset_xy` 用 `initial_course` 算一次并冻结进 `frozen_offset_xy`(懒冻结);Fleet 转向后不再旋。等价现 `ABS_MODE + layout_heading`,但基准从"布局时 course"改为权威的 `initial_course`。
- **relative**:每拍用当前 `course` 重算。等价现 `REL_MODE`。

### 3.3 步骤 3 — Formation 内部船位(`turning` 旋钮)

**(A) follow(鱼贯/Compass)—— 沿折线回退弧长**
- **absolute+follow(In Succession)**:Formation 中心偏移在地图系恒定 ⇒ Formation 中心折线 = Fleet 折线整体平移常量 `frozen_offset_xy`。直接复用:`ship_i_xy = fleet._xy_at_arc(lead_arc − i*spacing) + frozen_offset_xy`。
- **relative+follow(Compass)**:偏移随航向转,不是简单平移。**快路径**:`offset==(0,0)`(旗舰队,如 GE SG 1SG)时 Compass 与 In Succession 完全等价,直接用 Fleet 折线鱼贯。非零偏移的 relative+follow:把 Fleet 折线每顶点 `V_k` 替换为 `V_k + rotate(offset, heading_of_segment_k)` 得新折线,再弧长回退 `i*spacing`。【推断】此情形在两编组文件中**不出现**(relative 的均为零偏移 1SG 或 together 的 LCS),故快路径覆盖全部真实数据;通用路径作为完备性实现,留测试覆盖。

**(B) together(同时转)—— 刚体偏移**
```
hat = DIRVEC[fleet.course](relative) 或 DIRVEC[fleet.initial_course](absolute)
offs = formation.ship_offsets(kind, n, spacing, deploy, echelon_deg)
map_offs = formation.to_map_offsets(hat, offs)
ship_xy[i] = fcenter + map_offs[i]
```
abreast/echelon 永远走 together(B);ahead+together 保留但搜索阶段视为非典型,不优化。

**第四种(relative+together)退化**:line ahead 且转向连续时,稳态直行下与 Compass 位置一致,实现上允许直接走 Compass 路径(B→A),文档标注为合规退化。

### 3.4 接口不变性(零回归保证)

`ship_positions(sub)` 对外返回 `[(name, xy), ...]` 结构不变 ⇒ `_cross_pairs`、绘图、双盲、接敌路径**零改动**。零偏移单 Formation 下:`ahead→follow→鱼贯` 等价现 4a;`abreast/echelon→together→刚体` 等价现 4b。

### 3.5 接敌检测/回退定格/双盲的适配(子系统1)

- **`_cross_pairs`**:遍历改为 `fleet → formation → ship`,展开全部 Ship 的 xy 做 GB×GE 配对。**接敌粒度仍是 Ship**(顶点对顶点案例要求逐船真实欧氏距离)。"涉及方"记到 **Fleet 级**(报告与状态机以舰队为单位)。
- **`_resolve_encounter`/`contact_hexes`/`resume_search`**:报告中心从"旗舰 lead_xy"改为 **Fleet 几何中心 lead_xy**(=旗舰 Formation 中心,通常零偏移那支)。回退到 >vis 的 S−1 拍定格、清空所有 schedule 的逻辑不变。
- **双盲 `view_for_side`**:己方暴露 Fleet 全量(含 formations);敌方仅 CONTACT 态暴露涉及 Fleet 的中心+格,不暴露下层 Formation/Ship。

---

## 4. 渲染/接敌适配

> 本节内容(`ship_positions` 接口不变性、`_cross_pairs`/接敌回退/双盲适配)已并入 §3.4–3.5,此处不重复。

---

## 5. course 排队转向(先到下一格心再转)

### 5.1 定位

现 `course_change` 即时转(锚点钉在任意中途点),违反单纵阵鱼贯回转点语义。改为:`course` 登记**待转向请求**,`step_turn` 检测旗舰**抵达下一格心**那一拍,把锚点钉到该格心并应用新 course。转向点=格心是**运动学事实**(格心本身是精确点),不违反"报告不吸附格心"。转弯半径 450yd ≈ 1.25% 格宽,**简化为零半径折角**。

### 5.2 新增 Fleet 字段(已列入 §2.2)

| 字段 | 语义 |
|---|---|
| `pending_course` | 待生效目标航向;None=无。 |
| `pending_speed` | 待生效目标速度;None=不变。**速度也排队到同一格心一起生效**(速度立即改会破坏"到格心"的弧长推算)。 |
| `pending_turn_xy` | 预算的下一格心精确像素坐标;缓存避免每拍重算。None=无。 |

不引入 `pending_substep`;到达时刻由弧长动态反算(避免 float anchor 同步风险)。三字段序列化、向后兼容(`d.get(...)` 默认 None)。

### 5.3 "下一格心"几何(模块级 `next_cell_center_along(P, course)`)

沿六正方向,相邻格心连线是该方向直线、间距 36000。算法:把 `P` 投影到"过 `xy_to_hex(P)` 格心、方向 `DIRVEC[course]`"的轴上,`s = (P − center(h0))·DIRVEC[course]`,前方第一格心轴坐标 `s_next = ceil((s+EPS)/36000)*36000`,`C = center(h0) + s_next*DIRVEC[course]`。P 恰在格心时取沿 course 相邻格心(turn_arc=36000)。EPS=1e-6 码。

### 5.4 step_turn 内判定

在每拍"记 history 之后、接敌检测之前"插入待转向到达检测(转向先于接敌判定生效):对有 `pending_course` 的 fleet,若 `arc_prev < turn_arc <= arc_now+EPS`(`turn_arc = (pending_turn_xy − anchor_xy)·DIRVEC[course]`),求精确分数拍 `t_hit = anchor_substep + turn_arc/(speed*STEP_YARDS_PER_KNOT)`,调 `_apply_pending_turn(f, t_hit)`(类比 `_end_schedule`):钉 `anchor_xy=pending_turn_xy`、`anchor_substep=t_hit`(float)、`course=pending_course`、speed 若有则改、清三个 pending 字段。转向后本拍剩余弧长由 `lead_xy(sub)` 自动按新折线派生。

单拍弧长 ≤ 24*333.33 ≈ 8000 < 36000,**一拍内最多触发一次**到达,安全。多次转向用单级 pending(扩展点:升级为队列)。

### 5.5 course_change 改造

`f.scheduled` 时仍抛错(与 schedule 互斥,保持现状)。否则用**当前 course**(转向前航向)求 `pending_turn_xy`,登记 `pending_course/speed`。`course==当前 course` 且 speed 无变化则 return。覆盖语义:再发 `course` 只更新目标 course/speed,`pending_turn_xy` 不重算(未到达前位置仍在原射线,格心不变)。list/status 显示 `pending → <course>`。

### 5.6 交互边界

- **180° 掉头**【决策 v6 简化】:仍排队到前方格心反向(物理等价"走到回转点再调头",符合鱼贯)。德军专属同时反转 180° 留 v6+ 状态机/转向模式一并做。
- **`_end_schedule` 后 anchor 非格心**:`next_cell_center_along` 投影算法不要求 P 在格心线上,仍取沿 course 前方第一格心。对"横向偏移 > APOTHEM"断言告警(纯 course 模式不该发生)。
- **接敌后状态机**【决策】:进入 CONTACT 时**一并清空所有 fleet 的 pending 转向**(与"清空 schedule"对称)。CONTACT 态下是否允许 `course` 由状态机定,v6 默认与现状一致。
- **三层/四转向兼容**:pending 落在"中心航迹层",与 `relative` 旋钮正交。单纵鱼贯天然兼容(`_apply_pending_turn` 只改旗舰 anchor/course,后船弧长回退自然在格心跟转)。abreast/echelon 刚体在格心瞬时改 course;absolute 模式 `frozen_offset_xy` 不受影响。

---

## 6. 编组文件导入与 plot 校验

### 6.1 模块布局

新增独立 `orderparse.py`(文本解析 + 中间数据模型 + 局部→地图换算,可单测、与引擎解耦);`fleet_search.py` 加 `loadorder` CLI 与 `plot_order`。

**注意命名消歧**:`orderparse.py` 用一组**中间 dataclass**(`OrderShip/OrderFormation/OrderFleet/Battle`)承载解析结果,再实例化到 §2 的运行期 `Fleet/Formation/Ship`。避免与运行期类同名混淆。`Battle` 仅文件级聚合(一个文件=一方的若干 Fleet)。

### 6.2 文本格式与解析

- **表头**(1-11 行):只跳过(给人读的说明)。唯一硬信息是每个 Fleet 行的 **Initial Course**。
- **Fleet 行**(`BS：Initial Course SE（45°）`):取 name + initial_course。SE=45°,NW=SE 反向。GE SG=NW。
- **数据行**(分隔符 `—`,实测文件用全角破折号):列 = `单元名 | Ships | Formation类型 | (space/deploy info) | Turning | Relative Position | Relative Patten`。映射:`line ahead→ahead`、`line abreast→abreast`、`echelon→echelon`、Ships==1→`single`;`Together→together`/`Follow→follow`/single→`na`;`Absolute→absolute`/`Relative→relative`。
- **Relative Position 多分量**(`parse_relative_position`):`F→+fwd, B→−fwd, L→+left, R→−left`,多分量矢量相加,`0→(0,0)`。例:`8000F 10000L→(8000,10000)`、`5000F 12000R→(5000,−12000)`、`26000B→(−26000,0)`、`15000B 12000R→(−15000,−12000)`。

### 6.3 局部→地图换算(`local_to_map`)

```
forward_hat = DIRVEC[initial_course]              # 归一化地图单位向量,与引擎转向定义统一
left_hat = (forward_hat.y, -forward_hat.x)         # +y 朝南下左舷
offset_xy = offset_fwd*forward_hat + offset_left*left_hat
center_xy = fleet_center_xy + offset_xy            # fleet_center_xy 由 loadorder 起始格给
```
absolute:用 initial_course 算一次冻结(= §2/§3 的 `frozen_offset_xy`);relative:每拍用当前 course。初始 plot 两者数值相同(当前 course=initial_course),差异在转向后显现。

### 6.4 既定决策的落地(**全部 plot 上高亮供人工校验**,与实测文件逐条核对)

| 项 | 文件实测 | v6 处理 | 标注 |
|---|---|---|---|
| GB BS 6th Div. | `5625L`(line 19) | 【推断】改判 `5625R` → `offset=(0,−5625)`,与 3rd/2nd/1st 左舷 1125/3375/5625L 和 4th/5th 右舷 1125/3375R 形成镜像 | `note="推断修正:原文5625L,按左右对称应为5625R"` |
| GE BS 两个 München | `5000F 12000R`(line22) 与 `26000B`(line25) | 各自独立 Formation,名 `München#1`/`München#2`,offset 分别 `(5000,−12000)`、`(−26000,0)` | `note="同名舰两次,按字面各导,请核对笔误"` |
| GB BS 2CS 两行 | deploy R `28350L`(line23)、deploy L `28350R`(line24) | **同一 BS Fleet 下两个独立 Formation**,不另起 Fleet、不移格;offset 分别 `(26350,+28350)`(R 行 28350L)、`(26350,−28350)`(L 行 28350R) | `note="原注'是否坐标变化至下一格/作为独立Fleet';本导入按同Fleet两Formation,未移格"` |

> **【修正子系统冲突】** 子系统1曾把 `2CS(L)` 写成 `+28350`(left)、子系统4把 `2CS(L)` deploy=left 配 `(+26350,+28350)`。实测文件 line 24 是 **deploy L 且 Relative Position 为 `28350R`**,按 §6.2 规则 `R→−left`,故 `2CS#2 offset=(26350, −28350)`、deploy=left。以本表为权威。

### 6.5 loadorder 落地到引擎

`loadorder <GB|GE> [起始格 q,r]`(默认 `(0,0)` 格心,【待拍板】原点对应哪格):解析 → 对每个 Fleet 建运行期 `Fleet`(`initial_course`、`side`、`course=initial_course`、`speed` 默认 18),其下挂多个 Formation(offset/kind/spacing/deploy/echelon_deg/turning/relative 直填,absolute 时懒冻结 `frozen_offset_xy`),每 Formation 建 n 个 Ship。一个 loadorder 通常产出**一个文件 → 2 个 Fleet**(GB:BS 含 13 个 Formation〔含 2CS 两行〕、BCF 含 6 个;GE:BS 含 12 个、SG 含 6 个)。导入后照常可 `course`/`schedule`/`step`/`save`/`plot`,与 `new fleet`/`add formation` 并存。

### 6.6 增量构建 CLI(子系统1)

```
new fleet <name> <side> at <q,r> course <DIR> speed <kn> [activate <turn>]
add formation <fleet> <fmname> ships <n> [offset <..F/B> <..L/R>] [kind ...] [spacing] [deploy] [echelon <deg>] [turning ...] [rel ...]
del formation <fleet> <fmname>
list formations <fleet>
```
ships=1 → 自动 single。旧 `new`/`formation` 命令保留为对"第一个/指定 Formation"的快捷修改,向后兼容用户习惯。

### 6.7 plot_order 可视化校验

在 `plot_state` 基础上加专用编组视图(或 `plot order` 子命令):
1. 一张图画整个 Battle/单 Fleet 的所有 Formation+Ship;Formation 中心大标记+标签 `Fleet/Division`,内部 Ship 小点按 kind 连线(ahead 串列、abreast/echelon 展开)。
2. **颜色 GB 红 / GE 蓝**(锁定);同 Fleet 不同 Formation 同色不同标记/深浅,图例标 Fleet 名。
3. 每个 Fleet 中心画 Initial Course 箭头,使"SE 全朝东南、SG 朝西北"一眼可见。
4. 叠六角网格+格心,Formation 中心标 `hex(q,r) + 距格心码数`(复用 `micro_str`)。
5. 带 `note` 的 Formation 醒目描边+旁注(6th Div. 修正、两 München、2CS 双行)。
6. 可选画过 Initial Course 轴的对称参考线,辅助校验左右翼镜像(尤其 6th Div. 修正)。
输出 PNG(Agg 后端,无显示环境 OK),如 `order_GB.png`。

---

## 7. replay & demo 修复

### 7.1 replay <turn> 回合号↔下标 + 时钟/位置重置

**口径**:`turn = current_substep // 6`。`turn 0`=初始局面(substep 0)。`replay N` 取"substep==6N 的快照"。接敌回退快照(substep 非 6 倍数,如 11/17)**不另占回合槽**,归入其 `//6` 回合号下作为该回合最终(接触前定格)状态。**初始局面必须有 turn 0 快照**,否则系统性 +1 错位。

**journal.py 改动**:`turns` 从裸快照列表升级为 `[{"turn":N, "snapshot":...}]`;`record_turn` 按 `snapshot["current_substep"]//6` 派生 turn,**同回合号覆盖不追加**;新增 `snapshot_at_turn(turn)`、`latest_snapshot()`;`from_json` 末尾 `_normalize_legacy()` 把旧裸快照按 `current_substep//6` 反推 turn(向后兼容旧档)。

**fleet_search.py 改动**:`step_turn` 入口"若 `journal.turns` 为空则先补记当前局面(turn 0)";`replay_to` 经 `load_dict` 恢复后,因 `snapshot_at_turn(N).current_substep==6N`,`clock()`/各 Fleet `lead_xy(current_substep)`/state 三者自洽;`replay_to` 越界抛 `IndexError`。

### 7.2 demo 只直走 → 确定性折线 + 明显转向

根因:`attracted_walk_path` 吸引分支无扰动贪心、回退分支 `straight_bias=0.65`,相向几何下近直线。**修复不靠随机抖动**(随机源可能被禁用),改用**固定脚本化折线**:

模块级新增(纯 axial,无 matplotlib、无真随机依赖):`DEMO_LEG_SCRIPTS`(预设带 ≥2 次转向的 `(dir,count)` 脚本:Z形/S形/大角度单折/锯齿)、`scripted_walk_path(start,script,bound)`、`demo_path_for(start,speed,rng,bound)`(rng 决定选哪条脚本,截到 `HEX_PER_CYCLE[speed]`,保证含转向 `_has_turn`)。

`run_demo` 改:`seed` **默认 0**(原 None 在禁用真随机环境不可复现/可能抛错),`g.rng=random.Random(seed)`;把 `attracted_walk_path` 换成 `demo_path_for`,经 `schedule` 下发格心航路 ⇒ `_polyline` 产生折角、鱼贯跟弯。**接敌不再保证发生**(回归"演示转向/队形"目的)。路径生成与绘图解耦:测试只调 `demo_path_for`/`scripted_walk_path`/`step_turn`,不触发 matplotlib。

---

## 8. 序列化与向后兼容

### 8.1 version=6 嵌套结构

`to_dict` bump `version:6`,Fleet 内嵌 `formations`,formation 内嵌 `ships`(只存 `name`+`index`,xy 派生不落盘)。Fleet 运动学字段照写,**新增 `initial_course`、`pending_course`、`pending_speed`、`pending_turn_xy`**(xy 存 list 或 null)。Formation 存 `offset_fwd/offset_left/relative/kind/spacing/deploy/echelon_deg/turning/frozen_offset_xy`。`last_report`、`rng` 仍不持久化(现状)。Journal 快照=`to_dict()` 产物,自动随之嵌套。

### 8.2 读旧档升级(version 分流)

`_fleet_from_dict` 按是否有 `formations` 分流:
- **v6**:直接读嵌套。
- **v5 及更早**(无 `formations`,有 `formation_kind/pos_mode/spacing/deploy/echelon_deg/layout_heading`):`upgrade_v5_fleet` 在读取时升级为**单 Formation Fleet**——offset=(0,0),`relative=REL_RELATIVE if pos_mode=="relative" else REL_ABSOLUTE`,`kind=formation_kind`,`turning=follow if kind==ahead else together`,`frozen_offset_xy=(0,0) if absolute else None`,`initial_course=course`(旧档无此字段)。沿用现 `d.get(默认)` 容错(连队形字段都没有也落默认)。pending 三字段 `d.get(...,None)`。
- **写出一律 v6**。【决策】**不提供导出回 v5**(单 Fleet 多 Formation 无法无损降级);若朋友坚持,仅在"每 Fleet 恰好 1 个零偏移 Formation"时允许,否则拒绝。

### 8.3 journal turns 结构升级(§7.1)

`turns` 升级为带 `turn` 键的记录列表,`from_json` 规范化旧裸快照。**已知波及面**:`tests/test_journal.py` 直接断言 `len(j.turns)==2`/裸下标语义,需同步改为按 `turn` 键或 `snapshot_at_turn` 断言。

---

## 9. 与锁定约定的兼容性逐条核对

| 锁定约定 | v6 是否触碰 | 说明 |
|---|---|---|
| axial (q,r) pointy-top,六方向邻居增量统一 | 否 | `next_cell_center_along`、`local_to_map` 全用 `DIRVEC`+`hex_center_xy` |
| 像素映射 x=36000(q+r/2), y=√3/2·36000·r,+y 朝南 | 否 | 沿用;left_hat=(uy,−ux) 与 +y 朝南一致 |
| HEX_SIDE=36000;邻格中心距=36000 | 否 | 格心间距=36000 是排队转向几何基础 |
| 1回合=6拍;3回合=18拍 | 否 | turn=substep//6 即此口径 |
| 速度 12/18/24=2/3/4 格;STEP=36000/108 | 否 | t_hit、demo HEX_PER_CYCLE 沿用 |
| 视距默认20000/上限36000 | 否 | 接敌路径未改 |
| 接敌=GB×GE 欧氏<vis,只判跨阵营,S→S−1 回退,=vis 投影 | 否(仅遍历层数变深) | 粒度仍 Ship;涉及方记 Fleet;进 CONTACT 清 pending |
| 单纵鱼贯=turn in succession;弧长回退 | **强化** | follow=弧长回退;排队转向使后船在旗舰真实格心跟转 |
| 位置存精确 xy,报告不吸附格心 | 否 | 转向点=格心是运动学到达点(精确坐标),非显示吸附 |
| anchor_substep 可 float | 否 | t_hit 为 float,`_apply_pending_turn` 与 `_end_schedule` 同构 |
| 纪元 1916-05-31 0000;DD/MM/YY HHMM | 否 | replay 修复使 clock 回到正确整点/接触前时刻 |
| 测试纯 stdlib unittest,放 tests/ | 否 | 全部新测试遵守;matplotlib 用例可 skip |

**不写死成四个分支**:四种转向=两正交旋钮,符合解耦原则。**v6 暂不落地**:严格 together 离散时机是否也排队到格心(与排队转向耦合)、阵营专属同时反转 180°、接敌后状态机的完整转移——旋钮接口已预留。

---

## 10. 测试计划(纯 stdlib unittest,tests/)

**A. 三层模型 + 几何 `test_formation_layers.py`(新)**
- 零偏移单 Formation 的 `ship_positions(sub)` 与现状 4a/4b 逐船相等(等价性验收)。
- In Succession:单纵 spacing=500,course=E,sub=6,旗舰 (36000,0)、后船 (35500,0)/(35000,0)。
- In Succession 转向后:转向瞬间(sub=6)后船仍在旧航向、旗舰前进后(sub=7)后船进入新段——转向点不动。
- Turn Together(absolute):line abreast 转向后展开方向冻结(仍东西向)。
- 第四种/Compass(relative):反向后展开方向跟着反向(与 absolute 镜像)。
- Compass 旗舰队退化(offset=0):任意 sub 与 In Succession 逐船相等。
- Formation 偏移合成 + absolute 冻结:用 GB 4LCS `offset=(8000,10000)`、initial_course=SE,断言冻结后转向不变。
- 接敌检测零回归:两零偏移单纵 Fleet,某拍中心距 19000<20000,`_cross_pairs` 仍逐船判跨阵营、回退 S−1。

**B. course 排队转向 `test_course_queue.py`(新)**
- 基础排队:格内非格心发 course,改向不立即生效,直到 `lead_xy` 抵下一格心那拍才变,转向点==`hex_center_xy(下一格)`。
- `next_cell_center_along` 单元(六方向、P=格心、P=格内偏移、ceil 边界)。
- t_hit 精度:18kn 从格心整 6 拍到下一格心(整拍);12/24kn 非整拍区间。
- 鱼贯后船在旗舰同一格心滞后 i·500 转向。
- 180° 掉头(简化):排队到前方格心反向。
- schedule 互斥仍抛 ValueError;`_end_schedule` 后 anchor 非格心仍正确求 pending_turn_xy。
- 接敌清 pending:`_resolve_encounter` 后 pending_* 全 None、state==CONTACT。
- save/load 往返 pending 恢复。

**C. 编组导入 `test_orderparse.py`(新)**
- `parse_relative_position` 各分量(含上文实测值,尤其 2CS 两行、6th Div.)。
- 整文件:GB→BS+BCF,GE→BS+SG;逐 Formation 校验字段;既定决策断言(6th `(0,−5625)`+note、两 München 名异 offset 异、2CS 两 Formation deploy R/L 且 offset `(26350,±28350)` 按 §6.4 表)。
- `local_to_map`:纯 fwd 落航向线、纯 left 与 forward 正交且在左舷、SE 左右对称 Division 关于 Initial Course 轴镜像、NW=−SE、无 NaN。
- 端到端 loadorder:`Game.fleets` 数=总 Formation 数;anchor_xy 与 local_to_map 一致;save/load 往返 anchor 不变。
- plot 冒烟(Agg,可 skip if no matplotlib)。

**D. replay `test_replay.py` / `test_journal_turnkey.py`(新)**
- turn 0 在首 step 前补记;turn 号匹配 substep(0..4 → 0/6/.../24);replay 重置 clock+position;replay 后继续推进一致;接敌回合不挤占下标;越界 IndexError。
- journal:按 turn 查找非下标、同回合覆盖、旧裸快照规范化。

**E. demo `test_demo_path.py`(新)**
- `demo_path_for` 同种子可复现;路径方向集合 ≥2(含转向);`scripted_walk_path` 越界停;`step_turn` 下发脚本后 display_history 轨迹拐弯。
- 调整 `test_demo_convergence.py`:去掉"接敌频率≥6"(依赖被删吸引行为),改断言"运行不崩+同种子可复现";plot 相关 try/except skip。

**F. 回归(全绿验收)**:`python -m unittest discover -s tests -t .`。重点确认 `test_fleet_search.py`、`test_formation.py`、`test_formation_integration.py`、`test_serialization.py`(需认 version=6 + 兼容旧档)、`test_post_encounter.py`、`test_state_machine_loop.py`、`test_journal*.py`(需同步 turn-key 断言)、`test_view_filter.py` 全部通过。

---

## 11. 迁移与分阶段实现建议

**策略:包装而非重写**——运动字段留在新 Fleet,队形字段裹进一个 Formation。

- **阶段 A(三层骨架,零回归)**:引入 `Formation/Ship` 类与 §3 两段几何;Fleet 强制持有 ≥1 Formation;`new` 默认建零偏移单 Formation;`upgrade_v5_fleet` + `_fleet_from_dict` 分流;序列化 bump v6 + 读旧档升级。**验收:全部旧测试原样通过 + test_formation_layers 等价性绿。**
- **阶段 B(多 Formation + 导入)**:`orderparse.py`、`loadorder`、`add formation`/`del formation`/`list formations`、`plot_order`;`_cross_pairs` 遍历 Formation;接敌报告中心改 Fleet 几何中心。**验收:test_orderparse 绿 + 两文件可导入出图人工核对。**
- **阶段 C(course 排队转向)**:Fleet 加 pending 三字段;`next_cell_center_along`/`_apply_pending_turn`;`course_change` 改登记;step_turn 插桩;进 CONTACT 清 pending。**验收:test_course_queue 绿。**
- **阶段 D(replay & demo)**:journal turn-key 升级 + 规范化;step_turn 补 turn 0;replay_to 边界;demo 脚本化;调整 test_demo_convergence/test_journal。**验收:test_replay/test_journal_turnkey/test_demo_path 绿。**

各阶段独立可测、可分别提交;A 是其余三者的地基,B/C/D 之间无强依赖(C/D 不依赖 B 的多 Formation,可并行)。

---

## 12. 开放问题与已做决策清单

### 已做决策(本 spec 内裁定)
1. **三层字段命名权威化**:Fleet 持 `initial_course`;Formation 用 `offset_fwd/offset_left`、`frozen_offset_xy`、`turning`/`relative`、`kind`。
2. **四转向=两正交旋钮**,不写死四分支;第四种允许退化为 Compass。
3. **解耦原则**:`turning` 管中心航迹+内部跟随,`relative` 仅管偏移基准,不二次旋转。
4. **接敌粒度仍 Ship,涉及方记 Fleet,报告中心=Fleet 几何中心**。
5. **course 排队 180° 掉头**:v6 简化为排队到前方格心反向;阵营专属同时反转留后续。
6. **进 CONTACT 清空 pending**(与清 schedule 对称)。
7. **GB BS 6th Div.** 推断改判 `5625R`(plot 高亮供校验)。
8. **GE BS 两个 München** 各自独立 Formation(`#1/#2`)。
9. **GB BS 2CS 两行**:同 Fleet 两 Formation、不移格;offset 按实测 `(26350,+28350)`R 行 / `(26350,−28350)`L 行(**修正子系统间符号冲突,以 §6.4 表为准**)。
10. **序列化一律写 v6,读旧档升级,不提供无损降级回 v5**。
11. **demo seed 默认 0**(可复现);demo 不再以接敌为目标。
12. **replay turn 口径** turn=substep//6,接敌快照不占独立回合槽。

### 待朋友拍板(不擅自处理)
1. **原点 (0,0) 对应搜索图哪个格**(影响 `loadorder ... at`)。
2. **GB BS 2CS** 是否真要"坐标变化至下一六角格 / 作为独立 Fleet"(文件 line 25 旁注)——v6 暂按同 Fleet 两 Formation、不移格。
3. **GB BS 6th Div. `5625L`** 是否确为笔误(应 5625R)——v6 按推断修正并 plot 高亮。
4. **`together` 同时转的离散时机**是否也排队到格心(与严格转向耦合)。
5. **接敌后状态机完整转移**(保持接触/脱离/连续 encounter 消解)——本 spec 仅预留接口、进 CONTACT 清 pending。
6. **子编队跨格时**是否拆为独立 Fleet。
7. **GE SG NW 的精确角度**与项目 course 角度定义对齐确认。

### 相关源文件(绝对路径)
- `C:\Users\Administrator\Documents\Fleet\fleet_search.py`(Fleet 243-262、折线/弧长 267-300、ship_positions 302-319、course_change/_end_schedule/step_turn/_resolve_encounter、序列化、run_demo)
- `C:\Users\Administrator\Documents\Fleet\formation.py`(ship_offsets/to_map_offsets/place_map)
- `C:\Users\Administrator\Documents\Fleet\journal.py`(record_turn/snapshot_at_turn/from_json)
- 新增:`C:\Users\Administrator\Documents\Fleet\orderparse.py`、`C:\Users\Administrator\Documents\Fleet\tests\test_formation_layers.py`、`test_course_queue.py`、`test_orderparse.py`、`test_replay.py`、`test_journal_turnkey.py`、`test_demo_path.py`
- 数据源:`C:\Users\Administrator\Documents\Fleet\GBformation.txt`、`C:\Users\Administrator\Documents\Fleet\GEformation.txt`
