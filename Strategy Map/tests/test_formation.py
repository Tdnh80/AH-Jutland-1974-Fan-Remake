import math
import unittest
import formation as fm


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class TestShipOffsets(unittest.TestCase):
    def test_line_ahead(self):
        offs = fm.ship_offsets(fm.LINE_AHEAD, 3, 500)
        self.assertEqual(offs, [(0.0, 0.0), (-500.0, 0.0), (-1000.0, 0.0)])

    def test_line_abreast_right(self):
        offs = fm.ship_offsets(fm.LINE_ABREAST, 3, 500, deploy="right")
        self.assertEqual(offs, [(0.0, 0.0), (0.0, 500.0), (0.0, 1000.0)])

    def test_line_abreast_left(self):
        offs = fm.ship_offsets(fm.LINE_ABREAST, 2, 500, deploy="left")
        self.assertEqual(offs, [(0.0, 0.0), (0.0, -500.0)])

    def test_echelon_0deg_equals_ahead(self):
        a = fm.ship_offsets(fm.ECHELON, 3, 500, echelon_deg=0)
        b = fm.ship_offsets(fm.LINE_AHEAD, 3, 500)
        for pa, pb in zip(a, b):
            self.assertAlmostEqual(pa[0], pb[0], places=6)
            self.assertAlmostEqual(pa[1], pb[1], places=6)

    def test_echelon_90deg_equals_abreast(self):
        a = fm.ship_offsets(fm.ECHELON, 3, 500, echelon_deg=90, deploy="right")
        b = fm.ship_offsets(fm.LINE_ABREAST, 3, 500, deploy="right")
        for pa, pb in zip(a, b):
            self.assertAlmostEqual(pa[0], pb[0], places=6)
            self.assertAlmostEqual(pa[1], pb[1], places=6)

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            fm.ship_offsets("blob", 2, 500)


class TestPlacement(unittest.TestCase):
    def test_relative_heading_east_trails_west(self):
        # 航向东 (1,0),单纵:后船在中心西侧(x 更小),间距 500
        offs = fm.ship_offsets(fm.LINE_AHEAD, 3, 500)
        pts = fm.place_relative((0.0, 0.0), (1.0, 0.0), offs)
        self.assertAlmostEqual(pts[0][0], 0.0)
        self.assertAlmostEqual(pts[1][0], -500.0)
        self.assertAlmostEqual(dist(pts[0], pts[1]), 500.0)

    def test_relative_follows_turn(self):
        # 相对模式:航向南 (0,1) 时,单纵后船在中心北侧(y 更小)
        offs = fm.ship_offsets(fm.LINE_AHEAD, 2, 500)
        pts = fm.place_relative((0.0, 0.0), (0.0, 1.0), offs)
        self.assertAlmostEqual(pts[1][0], 0.0, places=6)
        self.assertAlmostEqual(pts[1][1], -500.0, places=6)

    def test_relative_abreast_right_of_heading(self):
        # 航向东,单横右展:第 2 船在中心正南(右舷),y 更大
        offs = fm.ship_offsets(fm.LINE_ABREAST, 2, 500, deploy="right")
        pts = fm.place_relative((0.0, 0.0), (1.0, 0.0), offs)
        self.assertAlmostEqual(pts[1][0], 0.0, places=6)
        self.assertAlmostEqual(pts[1][1], 500.0, places=6)

    def test_absolute_mode_does_not_follow_turn(self):
        # 绝对模式:用布局航向(东)固化地图偏移;之后航向变南,船的地图偏移不变
        offs = fm.ship_offsets(fm.LINE_AHEAD, 2, 500)
        map_offs = fm.to_map_offsets((1.0, 0.0), offs)     # 布局时:东
        before = fm.place_map((0.0, 0.0), map_offs)
        after = fm.place_map((0.0, 0.0), map_offs)          # 航向变了也用同一组 map_offs
        self.assertEqual(before, after)
        self.assertAlmostEqual(before[1][0], -500.0)        # 仍在西侧(地图固定)

    def test_to_map_offsets_matches_place_relative(self):
        offs = fm.ship_offsets(fm.LINE_ABREAST, 3, 500)
        heading = (0.0, 1.0)
        via_map = fm.place_map((10.0, 20.0), fm.to_map_offsets(heading, offs))
        via_rel = fm.place_relative((10.0, 20.0), heading, offs)
        for a, b in zip(via_map, via_rel):
            self.assertAlmostEqual(a[0], b[0], places=6)
            self.assertAlmostEqual(a[1], b[1], places=6)


if __name__ == '__main__':
    unittest.main()
