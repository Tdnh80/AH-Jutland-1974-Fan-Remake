import unittest
import fleet_search as fs


class TestCliCoords(unittest.TestCase):
    def test_parse_cell_or_hex_accepts_both(self):
        self.assertEqual(fs.parse_cell_or_hex("A13"), (13, 1))   # 字母数字
        self.assertEqual(fs.parse_cell_or_hex("13,1"), (13, 1))  # 开发者 q,r

    def test_display_cell_in_range_and_fallback(self):
        self.assertEqual(fs.display_cell(13, 1), "A13")
        # 地图外行号回退到 (q,r),不抛错
        self.assertEqual(fs.display_cell(0, -5), fs.hex_name(0, -5))

    def test_add_fleet_accepts_letter_number(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "A13", "E", 18, 1)
        # A13 -> (13,1);中心应落在该格中心
        self.assertEqual(fs.xy_to_hex(*g.fleets["F"].anchor_xy), (13, 1))

    def test_micro_str_uses_letter_number(self):
        x, y = fs.hex_center_xy(13, 1)
        self.assertIn("A13", fs.micro_str(x + 4000, y))


if __name__ == '__main__':
    unittest.main()
