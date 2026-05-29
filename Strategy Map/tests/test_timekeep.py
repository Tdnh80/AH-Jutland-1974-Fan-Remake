import unittest
import timekeep as tk


class TestTimekeep(unittest.TestCase):
    def test_turn_sub_minute_conversions(self):
        self.assertEqual(tk.turn_to_min(3), 180)
        self.assertEqual(tk.sub_to_min(5), 50)
        self.assertEqual(tk.min_to_turn(180), 3)
        self.assertEqual(tk.min_to_sub(50), 5)
        # 1 回合 = 6 拍 = 60 分钟
        self.assertEqual(tk.MIN_PER_TURN, 60)
        self.assertEqual(tk.SUB_PER_TURN, 6)

    def test_hhmm_to_min(self):
        self.assertEqual(tk.hhmm_to_min("0530"), 330)
        self.assertEqual(tk.hhmm_to_min("530"), 330)   # 容许缺前导 0
        self.assertEqual(tk.hhmm_to_min("0000"), 0)

    def test_fmt_clock(self):
        self.assertEqual(tk.fmt_clock(330), "0530")
        self.assertEqual(tk.fmt_clock(0), "0000")
        self.assertEqual(tk.fmt_clock(1500), "0100")   # 跨天回绕

    def test_fmt_date_uses_epoch_and_ddmmyy(self):
        # 默认 epoch = 1916-05-31 00:00,输出 DD/MM/YY HHMM
        self.assertEqual(tk.fmt_date(0), "31/05/16 0000")
        self.assertEqual(tk.fmt_date(90), "31/05/16 0130")
        self.assertEqual(tk.fmt_date(1440), "01/06/16 0000")   # +1 天

    def test_parse_time_three_forms(self):
        self.assertEqual(tk.parse_time("T3"), 180)     # 回合
        self.assertEqual(tk.parse_time("S5"), 50)      # 拍
        self.assertEqual(tk.parse_time("sub5"), 50)    # 拍(别名)
        self.assertEqual(tk.parse_time("0530"), 330)   # 当日 HHMM


if __name__ == '__main__':
    unittest.main()
