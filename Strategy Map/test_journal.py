import unittest
from journal import Journal


class TestJournal(unittest.TestCase):
    def test_record_and_access(self):
        j = Journal(epoch_minute=330, visibility=20000.0)
        j.record_command(330, "new GB1 GB 0 A13 E 18 3")
        j.record_turn({"current_substep": 6, "tag": "t1"})
        j.record_turn({"current_substep": 12, "tag": "t2"})
        self.assertEqual(len(j.history), 1)
        self.assertEqual(len(j.turns), 2)
        self.assertEqual(j.latest_snapshot()["tag"], "t2")
        self.assertEqual(j.snapshot_at_turn(0)["tag"], "t1")
        self.assertIsNone(j.snapshot_at_turn(5))

    def test_json_roundtrip(self):
        j = Journal(epoch_minute=330, visibility=20000.0)
        j.record_command(340, "step")
        j.record_turn({"current_substep": 6})
        text = j.to_json()
        j2 = Journal.from_json(text)
        self.assertEqual(j2.epoch_minute, 330)
        self.assertEqual(j2.visibility, 20000.0)
        self.assertEqual(j2.history, [{"sim_min": 340, "cmd": "step"}])
        self.assertEqual(j2.turns, [{"current_substep": 6}])


if __name__ == '__main__':
    unittest.main()
