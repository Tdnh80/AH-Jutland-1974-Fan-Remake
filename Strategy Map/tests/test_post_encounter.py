import unittest
import fleet_search as fs


def head_on_to_contact():
    """正面对冲:边锚后两队各后移 18000,接敌定格在 sub13,双方中心同格 (2,0)。"""
    g = fs.Game()                       # vis 默认 20000
    g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 3)
    g.add_fleet("GE1", "GE", 0, "4,0", "W", 18, 2)
    g.schedule("GB1", 18, ["1,0", "2,0", "3,0"])
    g.schedule("GE1", 18, ["3,0", "2,0", "1,0"])
    g.step_turn()                       # -> sub6, no contact
    g.step_turn()                       # -> sub12, no contact
    encs = g.step_turn()                # -> contact, roll to sub13
    return g, encs


class TestContactState(unittest.TestCase):
    def test_initial_state_is_search(self):
        g = fs.Game()
        self.assertEqual(g.state, fs.STATE_SEARCH)
        self.assertEqual(g.contact_hexes, set())

    def test_encounter_enters_contact_with_hexes(self):
        g, encs = head_on_to_contact()
        self.assertTrue(encs)
        self.assertEqual(g.state, fs.STATE_CONTACT)
        self.assertIn((2, 0), g.contact_hexes)

    def test_no_double_turn_count(self):
        # 接敌只把 current_substep 设到 roll 一次,不叠加回合
        g, _ = head_on_to_contact()
        self.assertEqual(g.current_substep, 13)


class TestAdjacentEntrants(unittest.TestCase):
    def _place_at_center(self, g, name, side, q, r, course):
        # 直接置于格心(边锚落在格边界会被 xy_to_hex round 到一侧,这里要明确在 (q,r) 内)
        g.add_fleet(name, side, 0, "0,0", course, 18, 1)
        f = g.fleets[name]
        f.anchor_xy = fs.hex_center_xy(q, r)
        f.anchor_substep = g.current_substep
        f.course = course
        f.display_history = [(g.current_substep, *f.anchor_xy)]

    def test_entrant_heading_into_contact_hex_is_detected(self):
        g, _ = head_on_to_contact()       # state=CONTACT, contact_hexes={(2,0)}, sub=13
        # 第三舰队明确在相邻格 (3,0) 格心,航向 W(朝接敌格 (2,0))
        self._place_at_center(g, "X", "GB", 3, 0, "W")
        entrants = g.adjacent_entrants()
        names = [e[0] for e in entrants]
        self.assertIn("X", names)
        entry_sub = dict((e[0], e[1]) for e in entrants)["X"]
        self.assertGreater(entry_sub, g.current_substep)

    def test_entrant_heading_away_is_not_detected(self):
        g, _ = head_on_to_contact()
        self._place_at_center(g, "Y", "GB", 3, 0, "E")   # 航向 E,驶离接敌格
        names = [e[0] for e in g.adjacent_entrants()]
        self.assertNotIn("Y", names)

    def test_no_entrants_when_searching(self):
        g = fs.Game()
        self.assertEqual(g.adjacent_entrants(), [])


class TestResumeSearch(unittest.TestCase):
    def test_resume_when_all_pairs_clear(self):
        g, _ = head_on_to_contact()
        self.assertEqual(g.state, fs.STATE_CONTACT)
        # 把双方拉远:所有跨阵营对都 > vis
        g.relocate("GB1", "0,0", "E", 18)
        g.relocate("GE1", "20,0", "W", 18)
        self.assertTrue(g.resume_search_if_clear())
        self.assertEqual(g.state, fs.STATE_SEARCH)
        self.assertEqual(g.contact_hexes, set())

    def test_no_resume_while_still_close(self):
        g, _ = head_on_to_contact()
        # 不移动:双方仍在接敌格附近,不应脱离
        self.assertFalse(g.resume_search_if_clear())
        self.assertEqual(g.state, fs.STATE_CONTACT)


if __name__ == '__main__':
    unittest.main()
