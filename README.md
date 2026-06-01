# AH-Jutland-1974-Fan-Remake

**基于 The Avalon Hill Game Co. 的《JUTLAND》（1967/1974）的玩家自制重制项目**

本项目为**非营利性粉丝重制**，所有资料仅供游戏交流与学习使用。  
原游戏《JUTLAND》版权归 The Avalon Hill Game Co. 所有。

---

## 项目简介

本项目旨在对经典海战兵棋《JUTLAND》进行现代化重制，内容包括：

- 游戏组件（算子、测距尺、移动尺、罗盘、战术桌垫）的矢量重绘
- 所有结算表（炮击、鱼雷、命中、损伤）和机制的重制
- 规则书的翻译、修订与扩展
- 部分游戏功能的程序化实现（进行中）
- 历史资料整理（船只数据、编队、战术图等）

项目完全由爱好者驱动，欢迎任何形式的反馈、指正与参与。

---

## 仓库结构
- `AH-Jutland-1974-Fan-Remake/`
  - `1974Rules_ZH_Translation/` - 1974版原规则的中文翻译（PDF）
  - `Game Components Assets/` - 游戏组件矢量源文件与决算表
  - `Rule Book/` - 重制版规则书（.docx）
  - `Strategy Map/` - 战略搜索程序（未完成）
  - `WorkBook/` - 设计工程中的数据集与工作簿
  - `README.md` - 本文件
  - `工作日志.md` - 开发进度记录


---

## 组件清单（Game Components Assets）

| 文件 | 说明 | 状态 |
|------|------|----|
| `Battle Maneuver Gauge.ai` | 移动尺（机动测量尺） | 可用 |
| `CompassV2.ai` | 罗盘（方向指示） | 可用 |
| `GB Range Finder.ai` / `GE Range Finder.ai` | 英/德测距尺 | 可用 |
| `Range Gauge Template.ai` | 测距尺模板 | 素材 |
| `Jutland Gun ResolveV1.xlsx` | 火炮毁伤结算表（V1） | 可用 |
| `Jutland Torpedo ResolveV1.xlsx` | 鱼雷毁伤结算表（V1） | 可用 |
| `Ship Counters.ai` / `Ship Counters Add.ai` | 主力舰/轻型舰算子板 | 可用 |
| `Ship TableV1.xlsx` | 完整船表（英/德双方） | 可用 |
| `Ship Top View.zip` | 舰船俯视图合集 | 素材 |
| `Tactical Battle Mat.ai` | 战术桌垫（海图） | 可用 |

> **关于 Ship Top View**：该压缩包内包含重制过程中使用过的舰船俯视图，为每张图标注原始出处。欢迎使用。

---

## 战略搜索程序（Strategy Map）

> **状态：未完成**

---

## 设计工作簿（WorkBook）

该目录存放设计过程中的中间数据、实验性表格和绘图，包括：

- `Jutland Gun Resolve (working).xlsx`
- `Jutland Torpedo Resolve (working).xlsx`
- `Jutland gun data.xlsx`
- `Jutland ships.xlsx`
- `Ship Table (working).xlsx`
- `myplot.png`
- `工作簿1.xlsx`

这些文件为设计工程中的数据集，可能存在重复、未整理或实验性内容，不用于游戏推演。正式版本使用 `Game Components Assets` 中的 `V1` 文件。

---

## 规则书

- **重制版规则**：`Rule Book/Jutland Remake RuleBookV2 zh.docx`（中文，V2）
- **1974原版规则中译**：`1974Rules_ZH_Translation/《日德兰》（《JUTLAND》） 74版规则中译V1.pdf`


---

## 使用说明

   - 打印 `Game Components Assets` 中的 `.ai` 矢量文件。  
   - 打印 `Ship TableV1.xlsx` 作为船表记录。  
   - 参考 `Rule Book` 中的规则进行推演。
   - 所有 `.ai` 文件均保留图层，可自行修改配色、尺寸或添加额外标记。  

---

## 待完成 / 已知问题

- [ ] **Strategy Map** 程序开发
- [ ] 指挥通信规则尚需进一步测试与完善
- [ ] 中口径炮击结算需进一步测试与完善

---

## 致谢与版权声明

- 原游戏《JUTLAND》设计者：**James F. Dunnigan**  
- 原出版发行：**The Avalon Hill Game Company**  
- 本项目所有重制内容均为粉丝自行制作，**不用于商业用途**。  
- 历史数据及舰船图纸来源于 **战列舰论坛**、**NavWeaps**、**Naval-history.net**、公开出版物等公开资料，在此一并致谢。  
- 若本项目中任何内容侵犯了您的合法权益，请通过 GitHub Issues 联系，我将尽快处理。

---

## 参与贡献

欢迎以下形式的贡献：

- 规则校对与润色
- 规则勘误与设计
- 数据勘误（船表、弹道表等）
- 程序开发（战略搜索、结算辅助工具等）
- 美术优化（更清晰的算子、更美观的桌垫）


---

## 联系方式

- 项目维护者：Tdnh80
- 邮箱：teshdenis_inhovin@163.com
- GitHub 仓库：[AH-Jutland-1974-Fan-Remake](https://github.com/Tdnh80/AH-Jutland-1974-Fan-Remake)

---

*最后更新：2026年5月31日*