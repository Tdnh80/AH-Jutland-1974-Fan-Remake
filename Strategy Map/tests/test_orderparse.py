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

    # 实测值
    def test_6th_div_5625R(self):
        # GB BS 6th Div. = 5625R(文件已为 R)-> (0, -5625)
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
        # GE BS 的 Initial Course 已改为 N(布局参考轴,N/S 不可操舵但可作 0° 轴)
        self.assertEqual(self.ge.fleets[0].initial_course, "N")

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

    # --- 文件直读(已是权威数据,无推断修正)---
    def test_gb_6th_div_is_R_no_note(self):
        fm = [f for f in self.gb.fleets[0].formations if f.name == "6th Div."][0]
        self.assertEqual((fm.offset_fwd, fm.offset_left), (0.0, -5625.0))  # 5625R
        self.assertEqual(fm.note, "")        # 文件已为 R,不再有推断修正注记

    def test_ge_munchen_and_stuttgart_distinct_singles(self):
        # 原重复的第二个 München 已在文件里更正为 Stuttgart
        names = [f.name for f in self.ge.fleets[0].formations]
        self.assertIn("München", names)
        self.assertIn("Stuttgart", names)
        self.assertNotIn("München#1", names)
        muc = [f for f in self.ge.fleets[0].formations if f.name == "München"][0]
        stu = [f for f in self.ge.fleets[0].formations if f.name == "Stuttgart"][0]
        self.assertEqual((muc.offset_fwd, muc.offset_left), (5000.0, -12000.0))  # 5000F 12000R
        self.assertEqual((stu.offset_fwd, stu.offset_left), (-26000.0, 0.0))     # 26000B
        self.assertEqual(muc.note, "")
        self.assertEqual(stu.note, "")

    def test_gb_2cs_two_formations(self):
        # 文件已用 2CS-A / 2CS-B 显式区分,无需去重后缀,也无 note
        fms = [f for f in self.gb.fleets[0].formations if f.name.startswith("2CS")]
        self.assertEqual(len(fms), 2)
        names = sorted(f.name for f in fms)
        self.assertEqual(names, ["2CS-A", "2CS-B"])
        cs1 = [f for f in fms if f.name == "2CS-A"][0]
        cs2 = [f for f in fms if f.name == "2CS-B"][0]
        # A: Deployment R, 28350L -> offset (26350, +28350), deploy right
        self.assertEqual((cs1.offset_fwd, cs1.offset_left), (26350.0, 28350.0))
        self.assertEqual(cs1.deploy, "right")
        # B: Deployment L, 28350R -> offset (26350, -28350), deploy left
        self.assertEqual((cs2.offset_fwd, cs2.offset_left), (26350.0, -28350.0))
        self.assertEqual(cs2.deploy, "left")
        self.assertEqual(cs1.spacing, 12150.0)
        self.assertEqual(cs2.spacing, 12150.0)
        self.assertEqual(cs1.note, "")

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
    def test_load_creates_two_nested_fleets_gb(self):
        # 端到端:每个 OrderFleet -> 一个运行期 Fleet,Division 嵌为其 formations
        g = fs.Game()
        names = g.load_order_file(GB_FILE, "GB", "0,0")
        self.assertEqual(len(names), 2)            # BS + BCF
        self.assertEqual(len(g.fleets), 2)
        bs = g.fleets["GB-BS"]
        bcf = g.fleets["GB-BCF"]
        self.assertEqual(len(bs.formations), 13)
        self.assertEqual(len(bcf.formations), 6)

    def test_load_creates_two_nested_fleets_ge(self):
        g = fs.Game()
        names = g.load_order_file(GE_FILE, "GE", "0,0")
        self.assertEqual(len(names), 2)            # BS + SG
        self.assertEqual(len(g.fleets), 2)
        self.assertEqual(len(g.fleets["GE-BS"].formations), 12)
        self.assertEqual(len(g.fleets["GE-SG"].formations), 6)

    def test_loadorder_ge_accepts_initial_course_N(self):
        # N 作 initial_course(布局轴)应能 loadorder 成功,不再因不在 6 个航向而报错
        g = fs.Game()
        g.load_order_file(GE_FILE, "GE", "0,0")
        self.assertEqual(g.fleets["GE-BS"].initial_course, "N")
        self.assertEqual(g.fleets["GE-BS"].course, "N")

    def test_loaded_fleet_side_and_course(self):
        g = fs.Game()
        g.load_order_file(GB_FILE, "GB", "0,0")
        bs = g.fleets["GB-BS"]
        self.assertEqual(bs.side, "GB")
        # initial_course propagated; default speed 18
        self.assertEqual(bs.initial_course, "SE")
        self.assertEqual(bs.course, "SE")
        self.assertEqual(bs.speed, 18)

    def test_fleet_anchor_at_entry_edge_formation_keeps_offset(self):
        # Fleet 几何中心锚在起始格的「进入边中心」(GB-BS course SE -> NW 进入边);
        # 非零偏移 Formation 保留 offset,渲染中心 = local_to_map(Fleet中心, course, fwd, left)。
        g = fs.Game()
        g.load_order_file(GB_FILE, "GB", "0,0")
        bs = g.fleets["GB-BS"]
        self.assertEqual(bs.anchor_xy, fs.entry_edge_center(0, 0, "SE"))
        # 3BCS: offset (32400F, 13000L), initial_course SE, absolute
        fm = [m for m in bs.formations if m.name == "3BCS"][0]
        self.assertEqual((fm.offset_fwd, fm.offset_left), (32400.0, 13000.0))
        want = op.local_to_map(bs.anchor_xy, "SE", 32400.0, 13000.0)
        got = bs._formation_center_xy(fm, bs.anchor_substep)
        self.assertAlmostEqual(got[0], want[0], places=3)
        self.assertAlmostEqual(got[1], want[1], places=3)

    def test_zero_offset_formation_at_fleet_center(self):
        # GE SG 1SG offset 0 -> 渲染中心 == Fleet 几何中心(= 进入边中心)
        g = fs.Game()
        g.load_order_file(GE_FILE, "GE", "0,0")
        sg = g.fleets["GE-SG"]
        fm = [m for m in sg.formations if m.name == "1SG"][0]
        self.assertEqual((fm.offset_fwd, fm.offset_left), (0.0, 0.0))
        got = sg._formation_center_xy(fm, sg.anchor_substep)
        self.assertAlmostEqual(got[0], sg.anchor_xy[0], places=3)
        self.assertAlmostEqual(got[1], sg.anchor_xy[1], places=3)

    def test_bs_fleet_holds_all_divisions_with_ships(self):
        g = fs.Game()
        g.load_order_file(GB_FILE, "GB", "0,0")
        bs = g.fleets["GB-BS"]
        third = [m for m in bs.formations if m.name == "3rd Div."][0]
        self.assertEqual(len(third.ships), 4)

    def test_save_load_roundtrip_preserves_offsets(self):
        import tempfile, os as _os
        g = fs.Game()
        g.load_order_file(GE_FILE, "GE", "0,0")
        bs = g.fleets["GE-BS"]
        anchor0 = tuple(bs.anchor_xy)
        st0 = [m for m in bs.formations if m.name == "Stettin"][0]
        off0 = (st0.offset_fwd, st0.offset_left)
        fd, path = tempfile.mkstemp(suffix=".json")
        _os.close(fd)
        try:
            g.save(path)
            g2 = fs.Game()
            g2.load(path)
            bs2 = g2.fleets["GE-BS"]
            self.assertAlmostEqual(bs2.anchor_xy[0], anchor0[0], places=3)
            self.assertAlmostEqual(bs2.anchor_xy[1], anchor0[1], places=3)
            self.assertEqual(len(bs2.formations), 12)
            st1 = [m for m in bs2.formations if m.name == "Stettin"][0]
            self.assertEqual((st1.offset_fwd, st1.offset_left), off0)
        finally:
            _os.remove(path)


class TestCrossPairsLayers(unittest.TestCase):
    def test_cross_pairs_traverses_all_ships(self):
        # 一个 GB Fleet 通过 add formation 挂两个 Formation,_cross_pairs 应展开全部 Ship
        g = fs.Game()
        g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 2)
        g.add_fleet("GE1", "GE", 0, "1,0", "W", 18, 2)
        pairs = g._cross_pairs(0)
        # GB 2 ship × GE 2 ship = 4 对(单 Formation 基线)
        self.assertEqual(len(pairs), 4)
        for d, fa, fb in pairs:
            self.assertEqual(fa.side, "GB")
            self.assertEqual(fb.side, "GE")

    def test_encounter_rollback_unchanged(self):
        # 两零偏移单纵 Fleet,某拍中心距 <vis,仍逐船判跨阵营、回退 S-1
        g = fs.Game()
        g.visibility = 20000.0
        # 放近一些:相隔 ~19000 < vis,应立刻在第 1 拍命中 -> 回退到 sub0
        g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 1)
        gb = g.fleets["GB1"]
        ge_anchor = (gb.anchor_xy[0] + 19000.0, gb.anchor_xy[1])
        g.add_fleet("GE1", "GE", 0, "1,0", "W", 18, 1)
        g.fleets["GE1"].anchor_xy = ge_anchor
        g.fleets["GE1"].display_history = [(0, *ge_anchor)]
        encs = g.step_turn()
        self.assertTrue(encs)
        self.assertEqual(g.state, fs.STATE_CONTACT)
        # 报告中心 = Fleet 几何中心 lead_xy(roll)
        e = encs[0]
        roll = g.current_substep
        self.assertAlmostEqual(e["gb_xy_roll"][0],
                               g.fleets["GB1"].lead_xy(roll)[0], places=3)
        self.assertAlmostEqual(e["gb_xy_roll"][1],
                               g.fleets["GB1"].lead_xy(roll)[1], places=3)

    def test_loaded_fleets_only_cross_side_pairs(self):
        # 导入 GB+GE 后,_cross_pairs 只产出 GB×GE,绝不含同阵营对
        g = fs.Game()
        g.load_order_file(GB_FILE, "GB", "0,0")
        g.load_order_file(GE_FILE, "GE", "20,0")
        pairs = g._cross_pairs(0)
        self.assertTrue(pairs)
        for d, fa, fb in pairs:
            self.assertEqual(fa.side, "GB")
            self.assertEqual(fb.side, "GE")


class TestOrderCLI(unittest.TestCase):
    def test_loadorder_cli(self):
        g = fs.Game()
        out = fs.execute_command(g, f'loadorder GB "{GB_FILE}" 0,0')
        self.assertEqual(len(g.fleets), 2)
        self.assertIn("2 fleets", out)
        self.assertIn("19 formations", out)

    def test_add_formation_cli(self):
        g = fs.Game()
        fs.execute_command(g, "new GB1 GB 0 0,0 E 18 4")
        fs.execute_command(g, "add formation GB1 scouts ships 2 offset 8000F 10000L kind abreast spacing 4000 deploy right turning together rel absolute")
        f = g.fleets["GB1"]
        self.assertEqual(len(f.formations), 2)
        added = [fm for fm in f.formations if fm.name == "scouts"][0]
        self.assertEqual(len(added.ships), 2)
        self.assertEqual(added.kind, "abreast")
        self.assertEqual(added.spacing, 4000.0)
        self.assertEqual((added.offset_fwd, added.offset_left), (8000.0, 10000.0))
        self.assertEqual(added.turning, "together")
        self.assertEqual(added.relative, "absolute")

    def test_add_formation_single_auto(self):
        g = fs.Game()
        fs.execute_command(g, "new GB1 GB 0 0,0 E 18 4")
        fs.execute_command(g, "add formation GB1 picket ships 1 offset 21000F")
        added = [fm for fm in g.fleets["GB1"].formations if fm.name == "picket"][0]
        self.assertEqual(added.kind, "single")
        self.assertEqual(len(added.ships), 1)

    def test_del_formation_cli(self):
        g = fs.Game()
        fs.execute_command(g, "new GB1 GB 0 0,0 E 18 4")
        fs.execute_command(g, "add formation GB1 scouts ships 2")
        self.assertEqual(len(g.fleets["GB1"].formations), 2)
        fs.execute_command(g, "del formation GB1 scouts")
        self.assertEqual(len(g.fleets["GB1"].formations), 1)

    def test_list_formations_cli(self):
        g = fs.Game()
        fs.execute_command(g, "new GB1 GB 0 0,0 E 18 4")
        fs.execute_command(g, "add formation GB1 scouts ships 2")
        out = fs.execute_command(g, "list formations GB1")
        self.assertIn("scouts", out)


class TestPlotOrder(unittest.TestCase):
    def setUp(self):
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            self.skipTest("matplotlib not installed")

    def test_plot_order_gb_smoke(self):
        import tempfile, os as _os
        g = fs.Game()
        g.load_order_file(GB_FILE, "GB", "0,0")
        fd, path = tempfile.mkstemp(suffix=".png")
        _os.close(fd)
        try:
            fs.plot_order(g, path)
            self.assertGreater(_os.path.getsize(path), 0)
        finally:
            _os.remove(path)

    def test_plot_order_ge_smoke(self):
        import tempfile, os as _os
        g = fs.Game()
        g.load_order_file(GE_FILE, "GE", "0,0")
        fd, path = tempfile.mkstemp(suffix=".png")
        _os.close(fd)
        try:
            fs.plot_order(g, path)
            self.assertGreater(_os.path.getsize(path), 0)
        finally:
            _os.remove(path)


if __name__ == "__main__":
    unittest.main()
