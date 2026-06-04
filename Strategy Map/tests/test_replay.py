"""阶段 D:replay <turn> 时刻/位置自洽 + 回合号口径 的回归测试。"""
import unittest
import fleet_search as fs


def two_fleets():
    g = fs.Game()
    g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 2)     # straight E, 6000 yd/sub
    g.add_fleet("GE1", "GE", 0, "20,0", "W", 18, 2)    # far away, no contact
    return g


class TestReplay(unittest.TestCase):
    def test_turn0_is_primed_initial_board(self):
        g = two_fleets()
        g.step_turn()
        self.assertIsNotNone(g.journal.snapshot_at_turn(0))
        self.assertEqual(g.journal.snapshot_at_turn(0)["current_substep"], 0)

    def test_replay_restores_substep_and_position(self):
        g = two_fleets()
        for _ in range(3):
            g.step_turn()
        for k in (0, 1, 2, 3):
            g.replay_to(k)
            self.assertEqual(g.current_substep, 6 * k)        # clock 由 substep 派生 -> 自洽
            x, y = g.fleets["GB1"].lead_xy(g.current_substep)
            # 锚在 (0,0) 西边中心 (-18000),沿 E:x = -18000 + 6k·6000
            self.assertAlmostEqual(x, -18000.0 + 6 * k * 6000.0, delta=1.0)
            self.assertAlmostEqual(y, 0.0, delta=1.0)

    def test_replay_out_of_range_raises(self):
        g = two_fleets()
        g.step_turn()
        with self.assertRaises(IndexError):
            g.replay_to(99)

    def test_replay_then_continue(self):
        g = two_fleets()
        for _ in range(3):
            g.step_turn()
        g.replay_to(1)
        self.assertEqual(g.current_substep, 6)
        g.step_turn()
        self.assertEqual(g.current_substep, 12)

    def test_encounter_snapshot_replayable_not_extra_slot(self):
        g = fs.Game()
        g.visibility = 20000.0
        g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 1)
        g.add_fleet("GE1", "GE", 0, "1,0", "W", 18, 1)
        g.fleets["GE1"].anchor_xy = (19000.0, 0.0)
        g.fleets["GE1"].display_history = [(0, 19000.0, 0.0)]
        encs = g.step_turn()
        self.assertTrue(encs)
        self.assertEqual(g.state, fs.STATE_CONTACT)
        sub0, turn = g.current_substep, g.current_substep // 6
        # 接敌快照归入其 //6 回合号(不另占独立槽),可被 replay 还原为接触态
        g.state = fs.STATE_SEARCH
        g.replay_to(turn)
        self.assertEqual(g.current_substep, sub0)
        self.assertEqual(g.state, fs.STATE_CONTACT)


if __name__ == '__main__':
    unittest.main()
