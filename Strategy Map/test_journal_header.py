import json
import os
import tempfile
import unittest
import fleet_search as fs


class TestJournalHeaderAndTime(unittest.TestCase):
    def test_time_accepts_three_forms(self):
        g = fs.Game()
        fs.execute_command(g, "time T3")
        self.assertEqual(g.start_minute, 180)      # 3 回合 = 180 min
        fs.execute_command(g, "time 0530")
        self.assertEqual(g.start_minute, 330)

    def test_saved_journal_header_is_current(self):
        g = fs.Game()
        fs.execute_command(g, "time 1200")
        fs.execute_command(g, "vis 30000")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "log.json")
            g.save(path)
            with open(path, encoding="utf-8") as fh:
                payload = json.load(fh)
        self.assertEqual(payload["journal"]["epoch_minute"], 720)   # 1200
        self.assertEqual(payload["journal"]["visibility"], 30000.0)


if __name__ == '__main__':
    unittest.main()
