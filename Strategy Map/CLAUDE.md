# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **日德兰搜索/接敌裁判工具** — 给 Claude Code 的项目上下文。本文件浓缩了从需求到 v4 的全部关键决策、约定和待办。读完应能直接接手而无需重读全部历史。

---

## 项目是什么

为《日德兰(JUTLAND 1974)》微缩兵棋的**搜索/接敌阶段**做的命令行裁判工具。
英(GB)、德(GE)两方舰队在六角搜索图上各自机动、初始互不可见;程序按 10 分钟一拍
推进时间,逐船计算英德距离,**距离 < 视距即"接敌"**,报告时刻/位置/涉及哪两支舰队。
范围到"接敌"为止,**不含战斗**。

**为什么不能简单判"是否同格"**(这是程序存在的根本理由,勿推翻):视距(~20k–36k 码)
与格大小(36k 码对边距)同量级。同格两船最远差 ~41570 码(顶点对顶点)可互相看不见;
隔壁格两船贴公共边却近在咫尺、能看见。所以必须算真实欧氏距离,而非数格子。

代码:单文件 `fleet_search.py`(Python 3.10+,matplotlib 仅用于画图)。当前版本 **v4**。

---

## 运行与测试

```bash
pip install matplotlib
python3 fleet_search.py          # 交互式 CLI
```

快速冒烟:进去后 `demo 17`(随机摆位+随机走,碰上即停,每回合存 demo_tNN.png)。
脚本式测试:把命令写进文本文件 `python3 fleet_search.py < scenario.txt`。
无显示环境下画图 OK(matplotlib Agg 后端)。

**回归测试**(测试都在 `tests/`,纯 stdlib `unittest`,无需 matplotlib):

```bash
python -m unittest discover -s tests -t .
```

钉住了「锁定的约定」:尺度/视距上限 36000、18kn=6 拍/格、axial 邻居与反解、鱼贯队距、schedule 校验与 180° 掉头、**接敌回退到 >vis 拍 + =vis 投影**、只判跨阵营。**改这些行为前先看测试是否仍应通过**。无 linter。
**Windows / PowerShell 注意**:`python3` 可能要写成 `python`;PowerShell 不支持 `< file` 输入重定向,改用 `Get-Content scenario.txt | python fleet_search.py`。

---

## 锁定的约定(改动前先确认,多为深思熟虑的结果)

### 坐标
- **axial `(q,r)`,pointy-top**,六方向邻居增量对所有格统一(无奇偶行):
  `E(+1,0) W(-1,0) NE(+1,-1) NW(0,-1) SE(0,+1) SW(-1,+1)`。
- NW↔SE 斜线上 q 不变(朋友的设计要点)。
- 输入输出格式 `q,r`(逗号无空格,负数 OK)。**字母标号已弃用**。
- 像素映射:`x = 36000·(q + r/2)`,`y = 36000·(√3/2)·r`,+y 朝"南"(下)。
- **原点 `(0,0)` 是任意参考点,待朋友确认对应搜索图哪个格**(改 `hex_center_xy` 偏移即可重定位)。

### 尺度 / 时间 / 速度
- 1 格对边距 = 邻格中心距 = **36000 码**;`HEX_SIZE`(中心到顶点)= 36000/√3 ≈ 20785;`APOTHEM`(中心到边中点)= 18000。
- **1 回合 = 60 min = 6 个 10min 小拍(substep)**;**3 回合 = 1 规划周期 = 18 拍**。
- 时刻用 HHMM,默认 0000 起算,`time HHMM` 可设。
- 航速仅 **12/18/24 kn = 3 回合走 2/3/4 格**。`STEP_YARDS_PER_KNOT = 36000/108 = 333.33`(使 18kn 恰好 6 拍/格)。

### 视距 / 接敌
- 视距是**探测半径**,默认 **20000**,上限 **36000(= 1 格对边距)**。
  原始文档:"能见度最高 36k yards""能见度不大于六角格宽"。
- **⚠ 视距上限是 36000,不是 18000(apothem)。** 早期一度误用 18000,已纠正。视距圈直径可超 1 格,正常。
- 接敌 = 任一 GB 船与任一 GE 船欧氏距离 < 视距。只判跨阵营。

### 队形 / 运动学
- 舰队 = 单纵阵(line-ahead),船距 500 码;船名 `<fleet>-1`(旗舰)、`-2`…
- **鱼贯转向(turn in succession)**:船 i 的位置 = 旗舰沿航迹回退 `i×500 码` 弧长处。曲线行进时队形自然跟弯。对应规则书 [69] 单纵阵转向。
- 位置内部存**精确 (x,y)**,沿折线按弧长参数化;**报告时绝不吸附到格心**。

### 接敌判定与输出(朋友 0.6° / 6° / 7° 定的)
- 10 分钟小拍上**离散采样**,不做连续 CPA(战术阶段步长本就是 10min)。
- 首个出现"某对 < vis"的拍 S → **回退到 S−1**(干净的接触前状态,所有对仍 ≥ vis)定格于此。
- 报告:HHMM 时刻 + **每支舰队中心(旗舰)的微观坐标**`hex(q,r) <距格心码数> → <哪条格边>`,**不逐船配对**。
- 辅助信息:对接触对在 S−1→S 间线性插值,给出距离恰 = vis 的投影接触时刻与位置(仅供参考,不改定格)。

### 显示
- **GB = 红,GE = 蓝**(已按 9° 对调)。视距圈**每艘船都画**(10° all-or-nothing)。
- 过去航迹实线、计划航迹虚线+★、接敌金色 ✕。

---

## 代码结构

- `Game`:`fleets` dict、`current_substep`、`visibility`、`start_minute`、`last_report`、`rng`。
  - `add_fleet/delete_fleet/relocate/course_change/clear_schedule/schedule/randwalk`
  - `step_turn()`:逐拍记 `display_history`、检测、命中则 `_resolve_encounter(S)` 回退到 S−1
  - `_resolve_encounter`:算涉及的 fleet 对、各自 S−1 微观位置、`=vis` 插值接触点,清空所有 schedule
  - `list_status` / `status_line`
- `Fleet`:`anchor_xy`(精确)、`anchor_substep`、`course`、`speed`、`ships`、`scheduled`、`schedule_end_substep`、`waypoints`(轴坐标,不含起点)、`display_history`。
  - `_polyline()` → `_arc_at(sub)` → `_xy_at_arc(arc)`(支持负 arc 外推、超尾外推)→ `lead_xy`、`ship_positions`(弧长回退实现鱼贯)
- 模块级:axial 工具(`parse_hex/hex_name/hex_center_xy/xy_to_hex(cube round)/hex_neighbour/direction_between/micro_position/micro_str`)、`random_walk_path`(直行偏置 0.65)、`hhmm`、`plot_state`、`run_demo`、`main` REPL。

### 命令
`new delete relocate course schedule clear randwalk step list vis time plot demo save load help quit`
- `schedule`:航路点数 = speed/6;相邻校验;**允许中途拐弯和 180° 掉头**(4°,反向校验已移除)。
- `course`:有 schedule 时禁用,需先 `clear`。
- save/load:JSON,含舰队状态/当前拍/视距,不含随机种子。

---

## v4 已完成(对照朋友 修正.txt)

| 项 | 状态 |
|---|---|
| 坐标换 axial (q,r) | ✅ |
| 1° 视距上限回 36000、默认 20000 | ✅ |
| 0.6° 回退到 >vis 拍定格 + =vis 辅助 | ✅ |
| 6° HHMM 时刻输出 | ✅ |
| 7° 不逐船配对,只报中心点微观坐标 | ✅ |
| 0.5° `clear` 命令 | ✅ |
| 9° 英德颜色对调(GB 红 GE 蓝) | ✅ |
| 10° 视距圈全画 | ✅ |
| 4° 允许 180° 掉头 | ✅ |
| 3°/8° 微观位置不吸附、存精确 xy | ✅(见下方 v5 关于"严格转向"的残留) |
| 15° randwalk 直行偏置 | ✅ |
| 16° 文档详细化(给非 CS) | ✅ README.md 已重写 |

---

## v5 待办(等朋友补充资料)

1. **2° 队形三态 + 相对位置模式** —— 等朋友那**四张标注图**。
   - 三态:单纵(起点偏移+间距)、单横(起点+展开方向+间距)、梯形(起点+展开方向+展开角+间距)。
   - 两种相对位置模式:① 朝行进方向相对位置不变(转向后跟着转);② 坐标方位相对位置不变(转向后不跟转)。
2. **11°/0.65° 接敌后状态机** —— 等朋友写**状态转移**。
   - 保持接触:双方同行至某格(或原处,无航向/速度);若有舰队进入接敌相邻格 → 入场(战略→战术阶段,线下推演)。
   - 脱离接触:刷新回正常搜索流程,重新输入编组。
   - 可能出现"连续 encounter",需此状态机消解。
3. **3°/5° 严格"先到格心再转向"的排队逻辑** —— 当前 `course` 改向在精确位置即时生效(不吸附但未排队到下个格心)。与队形/状态机耦合,一并在 v5 做干净。
4. **13°** 朋友备忘录里可能的遗漏增补 —— 待发。
5. **14° 联网** —— P2P 或裁判机做服务器(全局视角)。朋友最初设想是双盲、双设备、PyQt + QtDesigner。

### 仍未做/已知简化
轻巡侦察幕(被有意抽掉,见下)、突破侦察幕、战斗、海岸/雷区/陆地识别、任意航向/航速、拆队/合队/新建分队。

---

## 待朋友拍板的开放问题
- 原点 `(0,0)` 对应搜索图哪个格?
- 四张队形标注图 + 编码方式。
- 接敌后的状态转移细节。

---

## 领域背景与原始材料

朋友提供的文件(若需重新查证,均为权威来源)。原始资料已从 `requirement.zip` 解压到 `requirement/`:
- `abstract.docx`(根目录):问题抽象,Q1–Q6。"能见度不大于六角格宽""相遇只在 2 格内发生"。
- `requirement/requirement.docx`:尺度与微观运动表。战术格 36000yd=1200mm;移动尺 1kn/10min≈11mm=330yd;转向半径 450yd;基准视距 20k、最高 36k;三档速度微观离散表;**轻巡侦察幕**(已抽掉)。
- `requirement/《日德兰》(《JUTLAND》)74版规则中译V1.docx`:规则书。转向模式:**单纵阵转向=鱼贯(turn in succession,后船在旗舰同一转向点转)**;纵阵变横阵=同时转(turn together);战斗转向脱离=德军专属同时反转 180°。主力舰 ≥45° 转向用转弯半径。
- `requirement/jutlandsearchmap.pdf`:大北海搜索图(原字母+数字命名,现已改 axial)。"德舰进阴影格被 spotted;雷区仅德舰可入"。
- `requirement/*.png`(四张队形图,GB/GE 战斗序列)+ 根目录 `修正.txt`(v4 改动来源)、`input.txt`(朋友最初的接口/交互草案)。

历史细节:1mm=30yd,算子 20×15mm,战术六角格 36000yd。命名规范曾不一致(原注 1h=6回合),已统一为 **1 回合=60min,内含 6 个 10min 小拍**。

---

## 交付物清单(/outputs)
- `fleet_search.py` —— v4 主程序
- `README.md` —— v4 面向玩家的使用说明(非 CS 友好)
- `CLAUDE.md` —— 本文件
- 示例图:`v4_t1.png`、`v4_enc.png`、`demo_t*.png`、`curve_t*.png` 等(可删,仅演示)

---

## 给接手 agent 的提醒
- 改动前对照本文件"锁定的约定";尤其**视距上限 36000(非 18000)**、**回退到 >vis 拍**、**axial 统一邻居增量**这几条是反复确认过的。
- 队形与接敌后状态机是 v5 大头,二者与"严格转向"耦合,设计时一起考虑。
- 检测是有意的 10min 离散(非连续 CPA),勿"优化"成连续。
- 面向玩家的文档要白话(朋友 16°);技术细节放 README 末尾"开发者备注"或本文件。
