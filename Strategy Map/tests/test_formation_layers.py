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


if __name__ == '__main__':
    unittest.main()
