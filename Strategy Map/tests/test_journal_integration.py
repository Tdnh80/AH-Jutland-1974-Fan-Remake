import os
import tempfile
import unittest
import fleet_search as fs


def two_fleets():
    g = fs.Game()
    g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 2)
    g.add_fleet("GE1", "GE", 0, "10,0", "W", 18, 2)
    return g


class TestJournalIntegration(unittest.TestCase):
    def test_step_records_turn_snapshots(self):
        g = two_fleets()
        g.step_turn()
        g.step_turn()
        self.assertEqual(len(g.journal.turns), 2)
        self.assertEqual(g.journal.turns[0]["current_substep"], 6)
        self.assertEqual(g.journal.turns[1]["current_substep"], 12)

    def test_save_load_roundtrip_with_journal(self):
        g = two_fleets()
        g.step_turn()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "log.json")
            g.save(path)
            g2 = fs.Game()
            g2.load(path)
        self.assertEqual(g2.current_substep, g.current_substep)
        self.assertEqual(set(g2.fleets), set(g.fleets))
        self.assertEqual(len(g2.journal.turns), len(g.journal.turns))

    def test_replay_to_earlier_turn(self):
        g = two_fleets()
        g.step_turn()      # snapshot turn 0 -> sub6
        g.step_turn()      # snapshot turn 1 -> sub12
        self.assertEqual(g.current_substep, 12)
        g.replay_to(0)
        self.assertEqual(g.current_substep, 6)


if __name__ == '__main__':
    unittest.main()
