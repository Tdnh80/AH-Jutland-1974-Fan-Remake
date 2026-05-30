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


if __name__ == "__main__":
    unittest.main()
