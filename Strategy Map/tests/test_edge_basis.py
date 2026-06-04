"""格边中心基准:落点=进入边中心,course 转向在格心(18 节 sub3),schedule 歇在边。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fleet_search as fs

AP = fs.APOTHEM   # 18000


class TestPlacementAtEntryEdge(unittest.TestCase):
    def test_new_fleet_anchors_at_entry_edge(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 2)
        f = g.fleets["F"]
        self.assertAlmostEqual(f.anchor_xy[0], -AP, places=3)   # W edge of (0,0)
        self.assertAlmostEqual(f.anchor_xy[1], 0.0, places=3)
        self.assertAlmostEqual(f.lead_xy(3)[0], 0.0, places=3)  # centre at sub3
        self.assertAlmostEqual(f.lead_xy(6)[0], AP, places=3)   # E edge at sub6

    def test_relocate_anchors_at_entry_edge(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 1)
        g.relocate("F", "5,0", "W", 18)             # heading W -> E edge of (5,0)
        c = fs.hex_center_xy(5, 0)
        f = g.fleets["F"]
        self.assertAlmostEqual(f.anchor_xy[0], c[0] + AP, places=3)
        self.assertAlmostEqual(f.anchor_xy[1], c[1], places=3)


class TestCourseTurnsAtCentreHalfTurn(unittest.TestCase):
    def test_18kn_turns_at_sub3(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 1)
        g.course_change("F", "SE")
        g.step_turn()
        f = g.fleets["F"]
        self.assertEqual(f.course, "SE")
        self.assertAlmostEqual(f.anchor_substep, 3.0, delta=1e-6)
        self.assertAlmostEqual(f.anchor_xy[0], 0.0, places=3)   # hex (0,0) centre
        self.assertAlmostEqual(f.anchor_xy[1], 0.0, places=3)


class TestScheduleRestsOnEdges(unittest.TestCase):
    def test_schedule_start_snaps_to_entry_edge_and_boundaries_on_edges(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 1)
        g.schedule("F", 18, ["1,0", "2,0", "3,0"])  # straight E, 3 hexes
        f = g.fleets["F"]
        self.assertAlmostEqual(f.anchor_xy[0], -AP, places=3)   # W edge of (0,0)
        # turn boundaries land on shared edge-centres:
        self.assertAlmostEqual(f.lead_xy(6)[0], AP, places=3)       # E edge of (0,0)
        self.assertAlmostEqual(f.lead_xy(18)[0], 5 * AP, places=3)  # E edge of (2,0) = 90000


if __name__ == "__main__":
    unittest.main()
