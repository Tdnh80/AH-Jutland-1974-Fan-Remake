"""操作日志:命令历史 + 每回合盘面快照 + JSON 读写 + 按回合取快照。

纯数据结构,不依赖引擎。快照是引擎给的 dict(Game.to_dict() 的产物)。
"""

import json


class Journal:
    def __init__(self, epoch_minute=0, visibility=0.0):
        self.epoch_minute = epoch_minute
        self.visibility = visibility
        self.history = []      # [{"sim_min": int, "cmd": str}]
        self.turns = []        # [snapshot dict]

    def record_command(self, sim_min, cmd):
        self.history.append({"sim_min": sim_min, "cmd": cmd})

    def record_turn(self, snapshot):
        self.turns.append(snapshot)

    def latest_snapshot(self):
        return self.turns[-1] if self.turns else None

    def snapshot_at_turn(self, turn):
        if 0 <= turn < len(self.turns):
            return self.turns[turn]
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
        j.turns = d.get("turns", [])
        return j
