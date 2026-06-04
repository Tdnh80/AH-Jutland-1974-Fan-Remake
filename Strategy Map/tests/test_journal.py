import unittest
from journal import Journal


class TestJournal(unittest.TestCase):
    def test_record_and_access_by_turn_key(self):
        j = Journal(epoch_minute=330, visibility=20000.0)
        j.record_command(330, "new GB1 GB 0 A13 E 18 3")
        j.record_turn({"current_substep": 6, "tag": "t1"})    # turn 1
        j.record_turn({"current_substep": 12, "tag": "t2"})   # turn 2
        self.assertEqual(len(j.history), 1)
        self.assertEqual(len(j.turns), 2)
        self.assertEqual(j.latest_snapshot()["tag"], "t2")
        # 按 turn 号(=substep//6)查找,而非裸下标
        self.assertEqual(j.snapshot_at_turn(1)["tag"], "t1")
        self.assertEqual(j.snapshot_at_turn(2)["tag"], "t2")
        self.assertIsNone(j.snapshot_at_turn(0))
        self.assertIsNone(j.snapshot_at_turn(5))

    def test_same_turn_overwrites(self):
        # 接敌回退快照(非 6 倍数)归入其 //6 回合号,覆盖该回合
        j = Journal()
        j.record_turn({"current_substep": 12, "tag": "clean"})   # turn 2
        j.record_turn({"current_substep": 11, "tag": "contact"})  # 11//6 = 1
        j.record_turn({"current_substep": 12, "tag": "frozen"})  # turn 2 覆盖
        self.assertEqual(len(j.turns), 2)
        self.assertEqual(j.snapshot_at_turn(2)["tag"], "frozen")
        self.assertEqual(j.snapshot_at_turn(1)["tag"], "contact")

    def test_json_roundtrip(self):
        j = Journal(epoch_minute=330, visibility=20000.0)
        j.record_command(340, "step")
        j.record_turn({"current_substep": 6})
        j2 = Journal.from_json(j.to_json())
        self.assertEqual(j2.epoch_minute, 330)
        self.assertEqual(j2.visibility, 20000.0)
        self.assertEqual(j2.history, [{"sim_min": 340, "cmd": "step"}])
        self.assertEqual(j2.turns, [{"turn": 1, "snapshot": {"current_substep": 6}}])

    def test_from_json_normalizes_legacy_bare_snapshots(self):
        # v5 旧档:turns 是裸快照列表,应被规整为 turn-key 结构
        import json
        legacy = json.dumps({
            "epoch_minute": 0, "visibility": 20000.0, "history": [],
            "turns": [{"current_substep": 6}, {"current_substep": 12}],
        })
        j = Journal.from_json(legacy)
        self.assertEqual(j.snapshot_at_turn(1)["current_substep"], 6)
        self.assertEqual(j.snapshot_at_turn(2)["current_substep"], 12)


if __name__ == '__main__':
    unittest.main()
