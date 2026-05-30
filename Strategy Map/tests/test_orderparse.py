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


class TestParseBattle(unittest.TestCase):
    def setUp(self):
        with open(GB_FILE, encoding="utf-8") as fh:
            self.gb = op.parse_battle(fh.read(), side="GB")
        with open(GE_FILE, encoding="utf-8") as fh:
            self.ge = op.parse_battle(fh.read(), side="GE")

    # --- fleet-level shape ---
    def test_gb_has_bs_and_bcf(self):
        names = [f.name for f in self.gb.fleets]
        self.assertEqual(names, ["BS", "BCF"])
        self.assertEqual(self.gb.side, "GB")

    def test_ge_has_bs_and_sg(self):
        names = [f.name for f in self.ge.fleets]
        self.assertEqual(names, ["BS", "SG"])

    def test_initial_course(self):
        gb_bs = self.gb.fleets[0]
        self.assertEqual(gb_bs.initial_course, "SE")
        ge_sg = self.ge.fleets[1]
        self.assertEqual(ge_sg.initial_course, "NW")

    def test_gb_bs_formation_count_13(self):
        # 11 named rows + 2CS appears twice = 13 (2CS 两行各成独立 Formation)
        self.assertEqual(len(self.gb.fleets[0].formations), 13)

    def test_gb_bcf_formation_count_6(self):
        self.assertEqual(len(self.gb.fleets[1].formations), 6)

    def test_ge_bs_formation_count_12(self):
        # 6 Div. + Stettin/Rostock/München#1/Frauenlob/Hamburg/München#2 = 12
        self.assertEqual(len(self.ge.fleets[0].formations), 12)

    def test_ge_sg_formation_count_6(self):
        self.assertEqual(len(self.ge.fleets[1].formations), 6)

    # --- field mapping on a representative Division ---
    def test_gb_3rd_div_fields(self):
        fm = self.gb.fleets[0].formations[0]
        self.assertEqual(fm.name, "3rd Div.")
        self.assertEqual(fm.n_ships, 4)
        self.assertEqual(fm.kind, "ahead")
        self.assertEqual(fm.spacing, 500.0)
        self.assertEqual(fm.turning, "together")
        self.assertEqual(fm.relative, "absolute")
        self.assertEqual((fm.offset_fwd, fm.offset_left), (0.0, 1125.0))  # 1125L

    def test_gb_4lcs_abreast_deploy_offset(self):
        fm = [f for f in self.gb.fleets[0].formations if f.name == "4LCS"][0]
        self.assertEqual(fm.kind, "abreast")
        self.assertEqual(fm.deploy, "right")
        self.assertEqual(fm.spacing, 4000.0)
        self.assertEqual((fm.offset_fwd, fm.offset_left), (8000.0, 10000.0))

    def test_gb_3bcs_follow(self):
        fm = [f for f in self.gb.fleets[0].formations if f.name == "3BCS"][0]
        self.assertEqual(fm.kind, "ahead")
        self.assertEqual(fm.turning, "follow")
        self.assertEqual((fm.offset_fwd, fm.offset_left), (32400.0, 13000.0))

    def test_gb_attached_lc_rel_relative(self):
        # BS 末行 Attached LC 是 Relative
        fms = [f for f in self.gb.fleets[0].formations if f.name == "Attached LC"]
        self.assertEqual(len(fms), 1)
        self.assertEqual(fms[0].relative, "relative")

    # --- 既定决策 (spec §6.4) ---
    def test_gb_6th_div_corrected_to_R_with_note(self):
        fm = [f for f in self.gb.fleets[0].formations if f.name == "6th Div."][0]
        self.assertEqual((fm.offset_fwd, fm.offset_left), (0.0, -5625.0))  # 5625R
        self.assertIn("5625", fm.note)
        self.assertNotEqual(fm.note, "")

    def test_ge_two_munchen_distinct(self):
        names = [f.name for f in self.ge.fleets[0].formations]
        self.assertIn("München#1", names)
        self.assertIn("München#2", names)
        m1 = [f for f in self.ge.fleets[0].formations if f.name == "München#1"][0]
        m2 = [f for f in self.ge.fleets[0].formations if f.name == "München#2"][0]
        self.assertEqual((m1.offset_fwd, m1.offset_left), (5000.0, -12000.0))  # 5000F 12000R
        self.assertEqual((m2.offset_fwd, m2.offset_left), (-26000.0, 0.0))     # 26000B
        self.assertNotEqual(m1.note, "")
        self.assertNotEqual(m2.note, "")

    def test_gb_2cs_two_formations(self):
        fms = [f for f in self.gb.fleets[0].formations if f.name.startswith("2CS")]
        self.assertEqual(len(fms), 2)
        names = sorted(f.name for f in fms)
        self.assertEqual(names, ["2CS#1", "2CS#2"])
        cs1 = [f for f in fms if f.name == "2CS#1"][0]
        cs2 = [f for f in fms if f.name == "2CS#2"][0]
        # #1: Deployment R, 28350L -> offset (26350, +28350), deploy right
        self.assertEqual((cs1.offset_fwd, cs1.offset_left), (26350.0, 28350.0))
        self.assertEqual(cs1.deploy, "right")
        # #2: Deployment L, 28350R -> offset (26350, -28350), deploy left
        self.assertEqual((cs2.offset_fwd, cs2.offset_left), (26350.0, -28350.0))
        self.assertEqual(cs2.deploy, "left")
        self.assertEqual(cs1.spacing, 12150.0)
        self.assertEqual(cs2.spacing, 12150.0)
        self.assertNotEqual(cs1.note, "")

    # --- single-ship units ---
    def test_ge_stettin_single(self):
        fm = [f for f in self.ge.fleets[0].formations if f.name == "Stettin"][0]
        self.assertEqual(fm.n_ships, 1)
        self.assertEqual(fm.kind, "single")
        self.assertEqual(fm.turning, "na")
        self.assertEqual((fm.offset_fwd, fm.offset_left), (21000.0, 0.0))

    def test_ge_sg_1sg_follow_relative(self):
        fm = [f for f in self.ge.fleets[1].formations if f.name == "1SG"][0]
        self.assertEqual(fm.n_ships, 5)
        self.assertEqual(fm.kind, "ahead")
        self.assertEqual(fm.turning, "follow")
        self.assertEqual(fm.relative, "relative")
        self.assertEqual((fm.offset_fwd, fm.offset_left), (0.0, 0.0))

    # --- ships populated ---
    def test_ships_indexed(self):
        fm = self.gb.fleets[0].formations[0]   # 3rd Div., 4 ships
        self.assertEqual(len(fm.ships), 4)
        self.assertEqual([s.index for s in fm.ships], [0, 1, 2, 3])


import fleet_search as fs


class TestLoadOrder(unittest.TestCase):
    def test_fleet_count_equals_total_formations_gb(self):
        # 端到端:每个 OrderFormation -> 一个运行期 Fleet
        g = fs.Game()
        names = g.load_order_file(GB_FILE, "GB", "0,0")
        # GB: BS 13 + BCF 6 = 19
        self.assertEqual(len(names), 19)
        self.assertEqual(len(g.fleets), 19)

    def test_fleet_count_equals_total_formations_ge(self):
        g = fs.Game()
        names = g.load_order_file(GE_FILE, "GE", "0,0")
        # GE: BS 12 + SG 6 = 18
        self.assertEqual(len(names), 18)
        self.assertEqual(len(g.fleets), 18)

    def test_loaded_fleet_side_and_course(self):
        g = fs.Game()
        g.load_order_file(GB_FILE, "GB", "0,0")
        any_gb = next(iter(g.fleets.values()))
        self.assertEqual(any_gb.side, "GB")
        # initial_course propagated; default speed 18
        self.assertEqual(any_gb.initial_course, "SE")
        self.assertEqual(any_gb.course, "SE")
        self.assertEqual(any_gb.speed, 18)

    def test_anchor_matches_local_to_map(self):
        # 某个非零偏移 Formation 的 anchor_xy 应等于 local_to_map(中心, initial_course, fwd, left)
        g = fs.Game()
        g.load_order_file(GB_FILE, "GB", "0,0")
        center = fs.hex_center_xy(0, 0)
        # 3BCS: offset (32400F, 13000L), initial_course SE
        f = [f for f in g.fleets.values() if f.name.endswith("3BCS")][0]
        want = op.local_to_map(center, "SE", 32400.0, 13000.0)
        self.assertAlmostEqual(f.anchor_xy[0], want[0], places=3)
        self.assertAlmostEqual(f.anchor_xy[1], want[1], places=3)

    def test_zero_offset_formation_at_center(self):
        # GE SG 1SG offset 0 -> anchor 在起始格心
        g = fs.Game()
        g.load_order_file(GE_FILE, "GE", "0,0")
        center = fs.hex_center_xy(0, 0)
        f = [f for f in g.fleets.values() if f.name.endswith("1SG")][0]
        self.assertAlmostEqual(f.anchor_xy[0], center[0], places=3)
        self.assertAlmostEqual(f.anchor_xy[1], center[1], places=3)

    def test_each_loaded_fleet_single_formation_with_ships(self):
        g = fs.Game()
        g.load_order_file(GB_FILE, "GB", "0,0")
        f = [f for f in g.fleets.values() if f.name.endswith("3rd Div.")][0]
        self.assertEqual(len(f.formations), 1)
        self.assertEqual(len(f.formations[0].ships), 4)

    def test_save_load_roundtrip_preserves_anchor(self):
        import tempfile, os as _os
        g = fs.Game()
        g.load_order_file(GE_FILE, "GE", "0,0")
        f0 = [f for f in g.fleets.values() if f.name.endswith("Stettin")][0]
        anchor0 = tuple(f0.anchor_xy)
        fd, path = tempfile.mkstemp(suffix=".json")
        _os.close(fd)
        try:
            g.save(path)
            g2 = fs.Game()
            g2.load(path)
            f1 = [f for f in g2.fleets.values() if f.name.endswith("Stettin")][0]
            self.assertAlmostEqual(f1.anchor_xy[0], anchor0[0], places=3)
            self.assertAlmostEqual(f1.anchor_xy[1], anchor0[1], places=3)
        finally:
            _os.remove(path)


if __name__ == "__main__":
    unittest.main()
