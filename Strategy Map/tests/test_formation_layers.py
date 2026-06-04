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
        # absolute+follow, course E, 锚在 (0,0) 西边(-18000), sub=6 18kn -> lead 18000;
        # trailers rollback 500
        f = self._fleet(course="E", n=3, kind=fm.LINE_AHEAD,
                        relative=fs.REL_ABSOLUTE, turning=fs.TURN_FOLLOW)
        ships = dict(f.ship_positions(6))
        self.assertAlmostEqual(ships["F-1"][0], 18000.0, places=3)
        self.assertAlmostEqual(ships["F-1"][1], 0.0, places=3)
        self.assertAlmostEqual(ships["F-2"][0], 17500.0, places=3)
        self.assertAlmostEqual(ships["F-3"][0], 17000.0, places=3)

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


class TestSerializationV6(unittest.TestCase):
    def test_to_dict_version_is_6_and_nested(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "1,2", "E", 18, 3)
        d = g.to_dict()
        self.assertEqual(d["version"], 6)
        fd = d["fleets"][0]
        self.assertIn("initial_course", fd)
        self.assertIn("formations", fd)
        self.assertEqual(len(fd["formations"]), 1)
        fo = fd["formations"][0]
        self.assertIn("offset_fwd", fo)
        self.assertIn("turning", fo)
        self.assertIn("relative", fo)
        self.assertEqual([s["index"] for s in fo["ships"]], [0, 1, 2])

    def test_v6_roundtrip_preserves_formation(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "1,2", "SE", 18, 3)
        prim = g.fleets["F"].formations[0]
        prim.kind = fm.LINE_ABREAST
        prim.offset_fwd = 8000.0
        prim.offset_left = 10000.0
        prim.relative = fs.REL_ABSOLUTE
        prim.turning = fs.TURN_TOGETHER
        prim.deploy = "left"
        prim.echelon_deg = 30.0
        g2 = fs.Game()
        g2.load_dict(g.to_dict())
        p2 = g2.fleets["F"].formations[0]
        self.assertEqual(p2.kind, fm.LINE_ABREAST)
        self.assertEqual(p2.offset_fwd, 8000.0)
        self.assertEqual(p2.offset_left, 10000.0)
        self.assertEqual(p2.relative, fs.REL_ABSOLUTE)
        self.assertEqual(p2.turning, fs.TURN_TOGETHER)
        self.assertEqual(p2.deploy, "left")
        self.assertEqual(p2.echelon_deg, 30.0)
        self.assertEqual(g2.fleets["F"].initial_course, "SE")

    def test_load_v5_save_upgrades_to_single_formation(self):
        # craft a legacy v5 fleet dict (no 'formations' key, flat fields)
        v5 = {
            "version": 5,
            "current_substep": 0,
            "visibility": 20000.0,
            "start_minute": 0,
            "state": "SEARCH",
            "contact_hexes": [],
            "fleets": [{
                "name": "F", "side": "GB", "activated_turn": 0,
                "anchor_xy": [0.0, 0.0], "anchor_substep": 0,
                "course": "E", "speed": 18,
                "ships": ["F-1", "F-2", "F-3"],
                "scheduled": False, "schedule_end_substep": 0.0,
                "waypoints": [], "display_history": [[0, 0.0, 0.0]],
                "formation_kind": "abreast", "spacing": 500.0,
                "deploy": "left", "echelon_deg": 30.0,
                "pos_mode": "absolute", "layout_heading": [1.0, 0.0],
            }],
        }
        g = fs.Game()
        g.load_dict(v5)
        f = g.fleets["F"]
        self.assertEqual(len(f.formations), 1)
        prim = f.formations[0]
        self.assertEqual(prim.offset_fwd, 0.0)
        self.assertEqual(prim.offset_left, 0.0)
        self.assertEqual(prim.kind, "abreast")
        self.assertEqual(prim.relative, fs.REL_ABSOLUTE)   # pos_mode absolute
        self.assertEqual(prim.turning, fs.TURN_TOGETHER)   # non-ahead -> together
        self.assertEqual(prim.frozen_offset_xy, (0.0, 0.0))  # absolute -> frozen zero
        self.assertEqual(f.initial_course, "E")            # old save: initial = course
        self.assertEqual(len(f.ships), 3)
        self.assertEqual([s.index for s in f.ships], [0, 1, 2])

    def test_load_v5_line_ahead_upgrades_to_follow(self):
        v5 = {
            "version": 5, "current_substep": 0, "visibility": 20000.0,
            "start_minute": 0, "state": "SEARCH", "contact_hexes": [],
            "fleets": [{
                "name": "F", "side": "GE", "activated_turn": 0,
                "anchor_xy": [0.0, 0.0], "anchor_substep": 0,
                "course": "E", "speed": 18, "ships": ["F-1", "F-2"],
                "scheduled": False, "schedule_end_substep": 0.0,
                "waypoints": [], "display_history": [[0, 0.0, 0.0]],
                "formation_kind": "ahead", "spacing": 500.0,
                "deploy": "right", "echelon_deg": 45.0,
                "pos_mode": "relative", "layout_heading": None,
            }],
        }
        g = fs.Game()
        g.load_dict(v5)
        prim = g.fleets["F"].formations[0]
        self.assertEqual(prim.turning, fs.TURN_FOLLOW)     # ahead -> follow
        self.assertEqual(prim.relative, fs.REL_RELATIVE)
        self.assertIsNone(prim.frozen_offset_xy)           # relative -> not frozen


class TestEncounterZeroRegression(unittest.TestCase):
    def test_cross_pairs_still_detects_and_rolls_back(self):
        g = fs.Game()
        g.visibility = 20000.0
        # GB heading E from (0,0); GE sitting still ~1 hex east so they close to <vis
        g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 2)
        g.add_fleet("GE1", "GE", 0, "1,0", "W", 18, 2)
        # step several turns; they approach head-on and must trigger CONTACT
        triggered = False
        for _ in range(6):
            g.step_turn()
            if g.state == fs.STATE_CONTACT:
                triggered = True
                break
        self.assertTrue(triggered, "expected an encounter between approaching fleets")
        # rollback invariant: at the frozen substep all GBxGE ship pairs are >= vis
        pairs = g._cross_pairs(g.current_substep)
        self.assertTrue(pairs, "expected cross-side pairs")
        self.assertTrue(all(d >= g.visibility - 1e-6 for d, _, _ in pairs),
                        "frozen state must be the pre-contact >vis substep")

    def test_cross_pairs_only_crosses_sides(self):
        g = fs.Game()
        g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 2)
        g.add_fleet("GB2", "GB", 0, "0,1", "E", 18, 2)
        # two same-side fleets -> no cross pairs at all
        self.assertEqual(g._cross_pairs(0), [])


if __name__ == '__main__':
    unittest.main()
