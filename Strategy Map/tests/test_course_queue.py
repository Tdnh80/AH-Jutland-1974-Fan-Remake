"""阶段 C:course 排队转向(先驶到下一格心再转)的回归测试。纯 stdlib unittest。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fleet_search as fs

TOL = 1e-6
RATE18 = 18 * fs.STEP_YARDS_PER_KNOT   # 6000 yd/substep


class TestNextCellCenter(unittest.TestCase):
    def test_from_centre_along_each_dir(self):
        c0 = fs.hex_center_xy(0, 0)
        for d in ('E', 'W', 'NE', 'NW', 'SE', 'SW'):
            got = fs.next_cell_center_along(c0, d)
            # 沿 d 的相邻格心
            want = fs.hex_center_xy(*fs.hex_neighbour((0, 0), d))
            self.assertAlmostEqual(got[0], want[0], delta=1e-3, msg=d)
            self.assertAlmostEqual(got[1], want[1], delta=1e-3, msg=d)

    def test_east_centre(self):
        self.assertAlmostEqual(
            fs.next_cell_center_along((0.0, 0.0), 'E')[0], 36000.0, delta=1e-3)

    def test_partway_into_hex_returns_next_centre(self):
        # P 在 (0,0) 格内偏东 5000,沿 E -> 仍指向 (36000,0)
        got = fs.next_cell_center_along((5000.0, 0.0), 'E')
        self.assertAlmostEqual(got[0], 36000.0, delta=1e-3)
        self.assertAlmostEqual(got[1], 0.0, delta=1e-3)

    def test_on_a_centre_goes_to_following(self):
        got = fs.next_cell_center_along((36000.0, 0.0), 'E')
        self.assertAlmostEqual(got[0], 72000.0, delta=1e-3)


class TestCourseChangeQueues(unittest.TestCase):
    def test_course_not_applied_immediately(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 1)
        f = g.fleets["F"]
        g.course_change("F", "NE")
        self.assertEqual(f.course, "E")            # 未立即改向
        self.assertEqual(f.pending_course, "NE")
        self.assertAlmostEqual(f.pending_turn_xy[0], 36000.0, delta=1e-3)
        self.assertAlmostEqual(f.pending_turn_xy[1], 0.0, delta=1e-3)

    def test_pending_speed_recorded(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 1)
        g.course_change("F", "NE", 24)
        self.assertEqual(g.fleets["F"].pending_speed, 24)

    def test_reissue_current_course_cancels_pending(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 1)
        g.course_change("F", "NE")
        g.course_change("F", "E")                  # 回到当前航向 = 取消排队
        self.assertIsNone(g.fleets["F"].pending_course)

    def test_schedule_mutex_still_raises(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 1)
        g.schedule("F", 18, ["1,0", "2,0", "3,0"])
        with self.assertRaises(ValueError):
            g.course_change("F", "NE")


class TestApplyPendingTurn(unittest.TestCase):
    def _pending_fleet(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 3)
        f = g.fleets["F"]
        f.pending_course = "SE"
        f.pending_speed = 24
        f.pending_turn_xy = fs.hex_center_xy(1, 0)
        return g, f

    def test_apply_sets_anchor_course_and_clears_pending(self):
        g, f = self._pending_fleet()
        g._apply_pending_turn(f, 6.0)
        self.assertEqual(f.anchor_xy, fs.hex_center_xy(1, 0))
        self.assertEqual(f.anchor_substep, 6.0)
        self.assertEqual(f.course, "SE")
        self.assertEqual(f.speed, 24)
        self.assertIsNone(f.pending_course)
        self.assertIsNone(f.pending_speed)
        self.assertIsNone(f.pending_turn_xy)

    def test_keeps_speed_when_pending_speed_none(self):
        g, f = self._pending_fleet()
        f.pending_speed = None
        g._apply_pending_turn(f, 6.0)
        self.assertEqual(f.speed, 18)

    def test_anchor_substep_can_be_float(self):
        g, f = self._pending_fleet()
        g._apply_pending_turn(f, 4.5)
        self.assertEqual(f.anchor_substep, 4.5)
        x, y = f.lead_xy(4.5)
        self.assertAlmostEqual(x, 36000.0, delta=1e-3)
        self.assertAlmostEqual(y, 0.0, delta=1e-3)


class TestStepTurnArrival(unittest.TestCase):
    def test_turn_applied_at_next_centre_18kn(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 1)
        f = g.fleets["F"]
        g.course_change("F", "SE")
        g.step_turn()                       # sub0 -> sub6, reaches (36000,0) at sub6
        self.assertEqual(f.course, "SE")
        self.assertAlmostEqual(f.anchor_substep, 6.0, delta=TOL)
        self.assertAlmostEqual(f.anchor_xy[0], 36000.0, delta=1e-3)
        self.assertAlmostEqual(f.anchor_xy[1], 0.0, delta=1e-3)
        self.assertIsNone(f.pending_course)

    def test_turn_timing_12kn_needs_two_turns(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 12, 1)   # 4000/sub, reach at sub9
        f = g.fleets["F"]
        g.course_change("F", "SE")
        g.step_turn()                       # sub6: arc 24000 < 36000, not yet
        self.assertEqual(f.course, "E")
        self.assertEqual(f.pending_course, "SE")
        g.step_turn()                       # sub12: crosses at sub9
        self.assertEqual(f.course, "SE")
        self.assertAlmostEqual(f.anchor_substep, 9.0, delta=TOL)

    def test_turn_timing_24kn_half_substep(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 24, 1)   # 8000/sub, reach at sub4.5
        f = g.fleets["F"]
        g.course_change("F", "SE")
        g.step_turn()
        self.assertEqual(f.course, "SE")
        self.assertAlmostEqual(f.anchor_substep, 4.5, delta=TOL)

    def test_turn_point_is_a_hex_centre(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 1)
        f = g.fleets["F"]
        g.course_change("F", "SE")
        g.step_turn()
        self.assertEqual(f.anchor_xy, fs.hex_center_xy(1, 0))

    def test_succession_trailing_ship_stays_on_old_leg(self):
        # 鱼贯:旗舰在格心 (1,0) 转 SE 后,后船仍在旧 E 腿上(y≈0, x<36000)
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 3)
        f = g.fleets["F"]
        g.course_change("F", "SE")
        g.step_turn()
        ships = f.ship_positions(g.current_substep)   # sub6
        lead = ships[0][1]
        s2 = ships[1][1]
        self.assertAlmostEqual(lead[0], 36000.0, delta=1e-3)
        self.assertAlmostEqual(lead[1], 0.0, delta=1e-3)
        self.assertLess(s2[0], 36000.0)
        self.assertAlmostEqual(s2[1], 0.0, delta=1.0)
        # 再走一拍,旗舰进入 SE 段(y>0)
        self.assertGreater(f.lead_xy(g.current_substep + 1)[1], 0.0)

    def test_180_reversal_queues_to_forward_centre(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 1)
        f = g.fleets["F"]
        g.course_change("F", "W")
        self.assertEqual(f.pending_turn_xy, fs.hex_center_xy(1, 0))   # 前方格心
        g.step_turn()
        self.assertEqual(f.course, "W")
        self.assertEqual(f.anchor_xy, fs.hex_center_xy(1, 0))
        self.assertLess(f.lead_xy(g.current_substep + 1)[0], 36000.0)   # 折返向西


class TestEncounterClearsPending(unittest.TestCase):
    def test_pending_cleared_on_contact(self):
        g = fs.Game()
        g.visibility = 20000.0
        g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 1)
        gb = g.fleets["GB1"]
        g.add_fleet("GE1", "GE", 0, "1,0", "W", 18, 1)
        g.fleets["GE1"].anchor_xy = (gb.anchor_xy[0] + 19000.0, gb.anchor_xy[1])
        g.fleets["GE1"].display_history = [(0, gb.anchor_xy[0] + 19000.0, gb.anchor_xy[1])]
        g.course_change("GB1", "SE")
        self.assertEqual(gb.pending_course, "SE")
        encs = g.step_turn()
        self.assertTrue(encs)
        self.assertEqual(g.state, fs.STATE_CONTACT)
        self.assertIsNone(gb.pending_course)
        self.assertIsNone(gb.pending_turn_xy)


class TestSaveLoadPending(unittest.TestCase):
    def test_roundtrip_pending(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 2)
        g.course_change("F", "SE", 24)
        f = g.fleets["F"]
        pc, ps, ptx = f.pending_course, f.pending_speed, tuple(f.pending_turn_xy)
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            g.save(path)
            g2 = fs.Game()
            g2.load(path)
            f2 = g2.fleets["F"]
            self.assertEqual(f2.pending_course, pc)
            self.assertEqual(f2.pending_speed, ps)
            self.assertAlmostEqual(f2.pending_turn_xy[0], ptx[0], delta=1e-3)
            self.assertAlmostEqual(f2.pending_turn_xy[1], ptx[1], delta=1e-3)
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
