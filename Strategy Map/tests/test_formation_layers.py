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


if __name__ == '__main__':
    unittest.main()
