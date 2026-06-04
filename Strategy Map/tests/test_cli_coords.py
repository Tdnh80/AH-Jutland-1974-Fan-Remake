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
        # A13 -> (13,1);航向 E -> 锚在该格西边中心(进入边)
        self.assertEqual(g.fleets["F"].anchor_xy, fs.entry_edge_center(13, 1, "E"))

    def test_micro_str_uses_letter_number(self):
        x, y = fs.hex_center_xy(13, 1)
        self.assertIn("A13", fs.micro_str(x + 4000, y))


class TestMicroEdge(unittest.TestCase):
    def test_at_w_edge_centre_reports_zero(self):
        x, y = fs.edge_center(0, 0, 'W')
        s = fs.micro_str(x, y)
        self.assertIn("W edge-centre", s)
        self.assertNotIn("+", s)              # exactly at the edge centre -> no offset

    def test_at_hex_centre_reports_centre(self):
        x, y = fs.hex_center_xy(0, 0)
        self.assertIn("centre", fs.micro_str(x, y).lower())

    def test_offset_from_edge_centre_shows_distance(self):
        ex, ey = fs.edge_center(0, 0, 'E')
        s = fs.micro_str(ex - 1000.0, ey)     # 1000 yd off the E edge centre
        self.assertIn("E edge-centre", s)
        self.assertIn("1000", s)


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
