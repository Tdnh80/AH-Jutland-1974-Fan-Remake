"""操作日志:命令历史 + 每回合盘面快照 + JSON 读写 + 按回合取快照。

纯数据结构,不依赖引擎。快照是引擎给的 dict(Game.to_dict() 的产物)。

回合号口径(v6 §7):turn = snapshot['current_substep'] // 6。turn 0 = 初始局面
(substep 0)。`turns` 是 [{"turn": N, "snapshot": ...}] 列表,按 turn 号唯一:
同一回合号再记则**覆盖**(接敌回退快照 substep 非 6 倍数,如 11/17,归入其 //6
回合号下,作为该回合最终/接触前定格状态,不另占回合槽)。
"""

import json


def _turn_of(snapshot):
    if isinstance(snapshot, dict):
        return int(snapshot.get("current_substep", 0)) // 6
    return 0


def _normalize_turns(raw):
    """把任意 turns 列表规整为 [{"turn","snapshot"}],并兼容 v5 旧档(裸快照列表)。
    同回合号保留最后一次。"""
    by_turn = {}
    order = []
    for item in raw:
        if isinstance(item, dict) and "turn" in item and "snapshot" in item:
            turn, snap = item["turn"], item["snapshot"]
        else:                       # legacy: 裸快照
            turn, snap = _turn_of(item), item
        if turn not in by_turn:
            order.append(turn)
        by_turn[turn] = {"turn": turn, "snapshot": snap}
    return [by_turn[t] for t in order]


class Journal:
    def __init__(self, epoch_minute=0, visibility=0.0):
        self.epoch_minute = epoch_minute
        self.visibility = visibility
        self.history = []      # [{"sim_min": int, "cmd": str}]
        self.turns = []        # [{"turn": int, "snapshot": dict}]

    def record_command(self, sim_min, cmd):
        self.history.append({"sim_min": sim_min, "cmd": cmd})

    def record_turn(self, snapshot):
        """按 current_substep//6 归入回合号;同回合号覆盖。"""
        turn = _turn_of(snapshot)
        for rec in self.turns:
            if rec["turn"] == turn:
                rec["snapshot"] = snapshot
                return
        self.turns.append({"turn": turn, "snapshot": snapshot})

    def latest_snapshot(self):
        return self.turns[-1]["snapshot"] if self.turns else None

    def snapshot_at_turn(self, turn):
        for rec in self.turns:
            if rec["turn"] == turn:
                return rec["snapshot"]
        return None

    def to_json(self):
        return json.dumps({
            "epoch_minute": self.epoch_minute,
            "visibility": self.visibility,
            "history": self.history,
            "turns": self.turns,
        }, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text):
        d = json.loads(text)
        j = cls(d.get("epoch_minute", 0), d.get("visibility", 0.0))
        j.history = d.get("history", [])
        j.turns = _normalize_turns(d.get("turns", []))
        return j
