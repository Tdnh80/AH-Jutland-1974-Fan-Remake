import math
import unittest
import fleet_search as fs
import formation as fm


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class TestShipLeaf(unittest.TestCase):
    def test_ship_has_name_and_index(self):
        s = fs.Ship("GB1-1", 0)
        self.assertEqual(s.name, "GB1-1")
        self.assertEqual(s.index, 0)

    def test_ship_index_defaults_to_zero(self):
        s = fs.Ship("solo")
        self.assertEqual(s.index, 0)


class TestFormationClass(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(fs.TURN_FOLLOW, "follow")
        self.assertEqual(fs.TURN_TOGETHER, "together")
        self.assertEqual(fs.REL_ABSOLUTE, "absolute")
        self.assertEqual(fs.REL_RELATIVE, "relative")

    def test_default_formation(self):
        fo = fs.Formation(name="d0", ships=[fs.Ship("a", 0), fs.Ship("b", 1)])
        self.assertEqual(fo.offset_fwd, 0.0)
        self.assertEqual(fo.offset_left, 0.0)
        self.assertEqual(fo.kind, fm.LINE_AHEAD)
        self.assertEqual(fo.spacing, 500.0)
        self.assertEqual(fo.deploy, "right")
        self.assertEqual(fo.echelon_deg, 45.0)
        self.assertEqual(fo.turning, fs.TURN_FOLLOW)
        self.assertEqual(fo.relative, fs.REL_RELATIVE)
        self.assertIsNone(fo.frozen_offset_xy)
        self.assertFalse(fo.is_single)

    def test_single_when_one_ship(self):
        fo = fs.Formation(name="solo", ships=[fs.Ship("only", 0)])
        self.assertTrue(fo.is_single)

    def test_single_when_kind_single(self):
        fo = fs.Formation(name="d", ships=[fs.Ship("a", 0), fs.Ship("b", 1)],
                          kind=fs.KIND_SINGLE)
        self.assertTrue(fo.is_single)


class TestFleetHoldsFormation(unittest.TestCase):
    def test_add_fleet_creates_single_zero_offset_formation(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 3)
        f = g.fleets["F"]
        self.assertEqual(len(f.formations), 1)
        prim = f.formations[0]
        self.assertEqual(prim.offset_fwd, 0.0)
        self.assertEqual(prim.offset_left, 0.0)
        self.assertEqual(len(prim.ships), 3)
        self.assertEqual([s.index for s in prim.ships], [0, 1, 2])
        self.assertEqual([s.name for s in prim.ships], ["F-1", "F-2", "F-3"])

    def test_initial_course_set_from_course(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "NE", 18, 2)
        self.assertEqual(g.fleets["F"].initial_course, "NE")
        self.assertEqual(g.fleets["F"].course, "NE")

    def test_legacy_ships_property_reads_primary(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 2)
        f = g.fleets["F"]
        self.assertEqual(len(f.ships), 2)
        self.assertEqual([s.name for s in f.ships], ["F-1", "F-2"])

    def test_legacy_formation_kind_delegates(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 2)
        f = g.fleets["F"]
        self.assertEqual(f.formation_kind, fm.LINE_AHEAD)
        f.formation_kind = fm.LINE_ABREAST
        self.assertEqual(f.formations[0].kind, fm.LINE_ABREAST)
        self.assertEqual(f.formation_kind, fm.LINE_ABREAST)

    def test_legacy_pos_mode_maps_to_relative_knob(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 2)
        f = g.fleets["F"]
        # default is line-ahead/relative -> pos_mode relative
        self.assertEqual(f.pos_mode, fm.REL_MODE)
        f.pos_mode = fm.ABS_MODE
        self.assertEqual(f.formations[0].relative, fs.REL_ABSOLUTE)
        self.assertEqual(f.pos_mode, fm.ABS_MODE)

    def test_legacy_spacing_deploy_echelon_layout_heading_delegate(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 2)
        f = g.fleets["F"]
        f.spacing = 700.0
        f.deploy = "left"
        f.echelon_deg = 30.0
        f.layout_heading = (1.0, 0.0)
        prim = f.formations[0]
        self.assertEqual(prim.spacing, 700.0)
        self.assertEqual(prim.deploy, "left")
        self.assertEqual(prim.echelon_deg, 30.0)
        self.assertEqual(f.layout_heading, (1.0, 0.0))


class TestTwoStagePipeline(unittest.TestCase):
    def _fleet(self, course="E", n=3, kind=fm.LINE_AHEAD, relative=fs.REL_RELATIVE,
               turning=fs.TURN_FOLLOW, deploy="right"):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", course, 18, n)
        f = g.fleets["F"]
        prim = f.formations[0]
        prim.kind = kind
        prim.relative = relative
        prim.turning = turning
        prim.deploy = deploy
        return f

    def test_in_succession_concrete_coords(self):
        # absolute+follow, course E, sub=6, 18kn -> lead at (36000,0); trailers rollback 500
        f = self._fleet(course="E", n=3, kind=fm.LINE_AHEAD,
                        relative=fs.REL_ABSOLUTE, turning=fs.TURN_FOLLOW)
        ships = dict(f.ship_positions(6))
        self.assertAlmostEqual(ships["F-1"][0], 36000.0, places=3)
        self.assertAlmostEqual(ships["F-1"][1], 0.0, places=3)
        self.assertAlmostEqual(ships["F-2"][0], 35500.0, places=3)
        self.assertAlmostEqual(ships["F-3"][0], 35000.0, places=3)

    def test_zero_offset_single_formation_equals_v4_line_ahead(self):
        # 4a equivalence: relative+follow line-ahead == old LINE_AHEAD arc-rollback
        f = self._fleet(course="E", n=3, kind=fm.LINE_AHEAD,
                        relative=fs.REL_RELATIVE, turning=fs.TURN_FOLLOW)
        got = f.ship_positions(6)
        # reference: arc rollback directly off the fleet polyline
        lead_a = f._arc_at(6)
        for i, (name, xy) in enumerate(got):
            ref = f._xy_at_arc(lead_a - i * 500.0)
            self.assertAlmostEqual(xy[0], ref[0], places=6)
            self.assertAlmostEqual(xy[1], ref[1], places=6)

    def test_zero_offset_single_formation_equals_v4_abreast_relative(self):
        # 4b equivalence: abreast/relative -> together rigid via formation helpers
        f = self._fleet(course="E", n=3, kind=fm.LINE_ABREAST,
                        relative=fs.REL_RELATIVE, turning=fs.TURN_TOGETHER,
                        deploy="right")
        got = f.ship_positions(6)
        center = f.lead_xy(6)
        offs = fm.ship_offsets(fm.LINE_ABREAST, 3, 500.0, "right", 45.0)
        ref = fm.place_map(center, fm.to_map_offsets(fs.DIRVEC["E"], offs))
        for (name, xy), rp in zip(got, ref):
            self.assertAlmostEqual(xy[0], rp[0], places=6)
            self.assertAlmostEqual(xy[1], rp[1], places=6)

    def test_in_succession_turn_point_does_not_move(self):
        # schedule a turn so the polyline bends, trailers turn at the lead's turn point
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 2)
        f = g.fleets["F"]
        f.formations[0].relative = fs.REL_ABSOLUTE
        # waypoints: go E one hex then SE one hex (line ahead, scheduled)
        f.scheduled = True
        f.waypoints = [(1, 0), (1, 1)]
        f.schedule_end_substep = 12.0
        # at sub=6 lead reaches first waypoint center; trailer still behind on first leg (due E)
        ships6 = dict(f.ship_positions(6))
        # trailer F-2 is 500 yd behind along arc -> still on first (E) leg, y==0
        self.assertAlmostEqual(ships6["F-2"][1], 0.0, places=3)

    def test_turn_together_absolute_freezes_spread(self):
        # abreast + together + absolute: after a course change, map spread stays E-W frozen
        f = self._fleet(course="E", n=3, kind=fm.LINE_ABREAST,
                        relative=fs.REL_ABSOLUTE, turning=fs.TURN_TOGETHER,
                        deploy="right")
        before = dict(f.ship_positions(0))
        # spread vector ship2-ship1 in absolute(E) frame -> due south (+y)
        v0 = (before["F-2"][0] - before["F-1"][0], before["F-2"][1] - before["F-1"][1])
        f.course = "SE"          # fleet turns; absolute freezes initial_course=E
        after = dict(f.ship_positions(0))
        v1 = (after["F-2"][0] - after["F-1"][0], after["F-2"][1] - after["F-1"][1])
        self.assertAlmostEqual(v0[0], v1[0], places=6)
        self.assertAlmostEqual(v0[1], v1[1], places=6)

    def test_compass_relative_follows_turn(self):
        # abreast + together + relative: spread rotates with course (mirror of absolute)
        f = self._fleet(course="E", n=3, kind=fm.LINE_ABREAST,
                        relative=fs.REL_RELATIVE, turning=fs.TURN_TOGETHER,
                        deploy="right")
        before = dict(f.ship_positions(0))
        v0 = (before["F-2"][0] - before["F-1"][0], before["F-2"][1] - before["F-1"][1])
        f.course = "SE"
        after = dict(f.ship_positions(0))
        v1 = (after["F-2"][0] - after["F-1"][0], after["F-2"][1] - after["F-1"][1])
        # relative -> spread direction changed (no longer identical)
        self.assertFalse(abs(v0[0] - v1[0]) < 1e-6 and abs(v0[1] - v1[1]) < 1e-6)

    def test_compass_zero_offset_follow_equals_in_succession(self):
        # relative+follow with zero offset == absolute+follow (both pure fleet-polyline rollback)
        fa = self._fleet(course="E", n=3, kind=fm.LINE_AHEAD,
                         relative=fs.REL_RELATIVE, turning=fs.TURN_FOLLOW)
        fb = self._fleet(course="E", n=3, kind=fm.LINE_AHEAD,
                         relative=fs.REL_ABSOLUTE, turning=fs.TURN_FOLLOW)
        for (na, xa), (nb, xb) in zip(fa.ship_positions(6), fb.ship_positions(6)):
            self.assertAlmostEqual(xa[0], xb[0], places=6)
            self.assertAlmostEqual(xa[1], xb[1], places=6)

    def test_offset_compose_then_absolute_freeze(self):
        # GB 4LCS style: offset (fwd=8000, left=10000), initial_course SE, absolute freeze
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "SE", 18, 2)
        f = g.fleets["F"]
        prim = f.formations[0]
        prim.offset_fwd = 8000.0
        prim.offset_left = 10000.0
        prim.relative = fs.REL_ABSOLUTE
        prim.turning = fs.TURN_TOGETHER
        center_before = f._formation_center_xy(prim, 0)
        f.course = "E"           # fleet turns; absolute offset frozen on SE
        center_after = f._formation_center_xy(prim, 0)
        # frozen: formation-center-minus-fleet-center stays constant after the turn
        fc_b = (center_before[0] - f.lead_xy(0)[0], center_before[1] - f.lead_xy(0)[1])
        fc_a = (center_after[0] - f.lead_xy(0)[0], center_after[1] - f.lead_xy(0)[1])
        self.assertAlmostEqual(fc_b[0], fc_a[0], places=6)
        self.assertAlmostEqual(fc_b[1], fc_a[1], places=6)
        self.assertIsNotNone(prim.frozen_offset_xy)


if __name__ == '__main__':
    unittest.main()
