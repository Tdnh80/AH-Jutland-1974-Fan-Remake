import unittest
import fleet_search as fs


class TestCliTime(unittest.TestCase):
    def test_datestr_default_epoch(self):
        g = fs.Game()                      # start_minute=0
        self.assertEqual(g.datestr(0), "31/05/16 0000")
        self.assertEqual(g.datestr(6), "31/05/16 0100")   # 6 拍 = 60 min

    def test_datestr_with_start_minute(self):
        g = fs.Game()
        g.start_minute = 330               # 0530
        self.assertEqual(g.datestr(0), "31/05/16 0530")


if __name__ == '__main__':
    unittest.main()
