import math
import os
import unittest

import orderparse as op

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GB_FILE = os.path.join(REPO, "GBformation.txt")
GE_FILE = os.path.join(REPO, "GEformation.txt")


class TestDataclasses(unittest.TestCase):
    def test_ordership_fields(self):
        s = op.OrderShip(name="GB1-1", index=0)
        self.assertEqual(s.name, "GB1-1")
        self.assertEqual(s.index, 0)

    def test_orderformation_defaults(self):
        fm = op.OrderFormation(name="3rd Div.", n_ships=4, kind="ahead",
                               offset_fwd=0.0, offset_left=-1125.0)
        self.assertEqual(fm.n_ships, 4)
        self.assertEqual(fm.kind, "ahead")
        self.assertEqual(fm.spacing, 500.0)        # default
        self.assertEqual(fm.deploy, "right")        # default
        self.assertEqual(fm.echelon_deg, 45.0)      # default
        self.assertEqual(fm.turning, "follow")      # default
        self.assertEqual(fm.relative, "absolute")   # default
        self.assertEqual(fm.note, "")               # default
        self.assertIsNone(fm.frozen_offset_xy)

    def test_orderfleet_and_battle(self):
        fl = op.OrderFleet(name="BS", side="GB", initial_course="SE",
                           formations=[])
        b = op.Battle(side="GB", fleets=[fl])
        self.assertEqual(b.side, "GB")
        self.assertEqual(b.fleets[0].initial_course, "SE")


class TestParseRelativePosition(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(op.parse_relative_position("0"), (0.0, 0.0))

    def test_single_forward(self):
        self.assertEqual(op.parse_relative_position("21000F"), (21000.0, 0.0))

    def test_single_backward(self):
        self.assertEqual(op.parse_relative_position("26000B"), (-26000.0, 0.0))

    def test_single_left(self):
        self.assertEqual(op.parse_relative_position("1125L"), (0.0, 1125.0))

    def test_single_right(self):
        self.assertEqual(op.parse_relative_position("5625R"), (0.0, -5625.0))

    def test_two_components_fl(self):
        self.assertEqual(op.parse_relative_position("8000F 10000L"),
                         (8000.0, 10000.0))

    def test_two_components_fr(self):
        self.assertEqual(op.parse_relative_position("5000F 12000R"),
                         (5000.0, -12000.0))

    def test_two_components_br(self):
        self.assertEqual(op.parse_relative_position("15000B 12000R"),
                         (-15000.0, -12000.0))

    def test_fullwidth_and_spacing_tolerant(self):
        # 全角空格 / 多空格 / 大小写都应被吞掉
        self.assertEqual(op.parse_relative_position("  26350F　28350L "),
                         (26350.0, 28350.0))

    # 实测既定决策值(spec §6.4)
    def test_6th_div_corrected_to_R(self):
        # 6th Div. 推断修正为 5625R
        self.assertEqual(op.parse_relative_position("5625R"), (0.0, -5625.0))

    def test_2cs_row1_R_deploy_28350L(self):
        # 2CS#1: 26350F 28350L -> (26350, +28350)
        self.assertEqual(op.parse_relative_position("26350F 28350L"),
                         (26350.0, 28350.0))

    def test_2cs_row2_L_deploy_28350R(self):
        # 2CS#2: 26350F 28350R -> (26350, -28350)
        self.assertEqual(op.parse_relative_position("26350F 28350R"),
                         (26350.0, -28350.0))

    def test_bad_token_raises(self):
        with self.assertRaises(ValueError):
            op.parse_relative_position("12345X")


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class TestLocalToMap(unittest.TestCase):
    def test_pure_forward_on_course_axis(self):
        # 纯 fwd 应落在 initial_course 射线上(与 forward_hat 同向)
        center = op.local_to_map((0.0, 0.0), "SE", 10000.0, 0.0)
        fwd = op.DIRVEC["SE"]
        # center 与 fwd 共线、同向
        self.assertAlmostEqual(center[0], 10000.0 * fwd[0], places=6)
        self.assertAlmostEqual(center[1], 10000.0 * fwd[1], places=6)

    def test_pure_left_orthogonal_to_forward(self):
        # 纯 left 偏移向量应与 forward_hat 正交
        off = op.local_to_map((0.0, 0.0), "SE", 0.0, 10000.0)
        fwd = op.DIRVEC["SE"]
        dot = off[0] * fwd[0] + off[1] * fwd[1]
        self.assertAlmostEqual(dot, 0.0, places=6)
        self.assertAlmostEqual(_dist(off, (0.0, 0.0)), 10000.0, places=6)

    def test_east_left_is_north_up(self):
        # 航向东 (1,0):left_hat=(0,-1);offset_left=+1125 -> 地图 y 减小(上/北)
        off = op.local_to_map((0.0, 0.0), "E", 0.0, 1125.0)
        self.assertAlmostEqual(off[0], 0.0, places=6)
        self.assertAlmostEqual(off[1], -1125.0, places=6)

    def test_nw_is_negative_se(self):
        # NW = SE 反向:同 (fwd,left) 的偏移向量应互为相反数
        a = op.local_to_map((0.0, 0.0), "SE", 8000.0, 10000.0)
        b = op.local_to_map((0.0, 0.0), "NW", 8000.0, 10000.0)
        self.assertAlmostEqual(a[0], -b[0], places=6)
        self.assertAlmostEqual(a[1], -b[1], places=6)

    def test_left_right_mirror_about_course_axis(self):
        # SE 航向下,左右对称 Division(+left vs -left)关于 Initial Course 轴镜像:
        # 二者之和应正好落在航向轴上(left 分量抵消)
        l = op.local_to_map((0.0, 0.0), "SE", 0.0, 5625.0)
        r = op.local_to_map((0.0, 0.0), "SE", 0.0, -5625.0)
        s = (l[0] + r[0], l[1] + r[1])
        self.assertAlmostEqual(s[0], 0.0, places=6)
        self.assertAlmostEqual(s[1], 0.0, places=6)

    def test_no_nan(self):
        for crs in ("E", "NE", "NW", "W", "SW", "SE"):
            off = op.local_to_map((100.0, 200.0), crs, 8000.0, 10000.0)
            self.assertFalse(math.isnan(off[0]) or math.isnan(off[1]))

    def test_center_offset_applied(self):
        # fleet_center_xy 非零时整体平移
        c = op.local_to_map((1000.0, 2000.0), "SE", 0.0, 0.0)
        self.assertEqual(c, (1000.0, 2000.0))


if __name__ == "__main__":
    unittest.main()
