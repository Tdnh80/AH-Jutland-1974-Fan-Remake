import unittest
import fleet_search as fs


def head_on_to_contact():
    """复刻回归用的正面对冲:接敌定格在 sub10,双方中心同格 (2,0)。"""
    g = fs.Game()                       # vis 默认 20000
    g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 3)
    g.add_fleet("GE1", "GE", 0, "4,0", "W", 18, 2)
    g.schedule("GB1", 18, ["1,0", "2,0", "3,0"])
    g.schedule("GE1", 18, ["3,0", "2,0", "1,0"])
    g.step_turn()                       # -> sub6, no contact
    encs = g.step_turn()                # -> contact, roll to sub10
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
        self.assertEqual(g.current_substep, 10)


if __name__ == '__main__':
    unittest.main()
