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


class TestEdgeCenter(unittest.TestCase):
    def test_edge_center_each_dir_is_apothem_from_centre(self):
        c = fs.hex_center_xy(3, 1)
        for d in ('E', 'W', 'NE', 'NW', 'SE', 'SW'):
            ec = fs.edge_center(3, 1, d)
            ux, uy = fs.DIRVEC[d]
            self.assertAlmostEqual(ec[0], c[0] + fs.APOTHEM * ux, places=3)
            self.assertAlmostEqual(ec[1], c[1] + fs.APOTHEM * uy, places=3)

    def test_entry_edge_is_behind_heading(self):
        # heading E -> entry edge is the W edge (= centre - APOTHEM along E)
        c = fs.hex_center_xy(0, 0)
        ee = fs.entry_edge_center(0, 0, 'E')
        self.assertAlmostEqual(ee[0], c[0] - fs.APOTHEM, places=3)
        self.assertAlmostEqual(ee[1], c[1], places=3)

    def test_entry_edge_ns_falls_back_to_centre(self):
        # N/S are vertex directions (no edge) -> fall back to hex centre
        c = fs.hex_center_xy(2, 2)
        self.assertEqual(fs.entry_edge_center(2, 2, 'N'), c)
        self.assertEqual(fs.entry_edge_center(2, 2, 'S'), c)


if __name__ == '__main__':
    unittest.main()
