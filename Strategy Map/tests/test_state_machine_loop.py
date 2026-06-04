import unittest
import fleet_search as fs


def head_on_to_contact():
    g = fs.Game()
    g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 3)
    g.add_fleet("GE1", "GE", 0, "4,0", "W", 18, 2)
    g.schedule("GB1", 18, ["1,0", "2,0", "3,0"])
    g.schedule("GE1", 18, ["3,0", "2,0", "1,0"])
    g.step_turn(); g.step_turn(); g.step_turn()   # 边锚后接敌在第 3 回合(sub13)
    return g


class TestStateMachineLoop(unittest.TestCase):
    def test_step_after_contact_does_not_deadlock(self):
        g = head_on_to_contact()
        self.assertEqual(g.state, fs.STATE_CONTACT)
        self.assertEqual(g.current_substep, 13)
        g.step_turn()                       # 不能再卡在 sub13
        self.assertNotEqual(g.current_substep, 13)

    def test_sailing_on_eventually_resumes_search(self):
        g = head_on_to_contact()
        for _ in range(4):                  # 双方继续直线航行,会驶出接敌格
            g.step_turn()
        self.assertEqual(g.state, fs.STATE_SEARCH)

    def test_relocate_apart_then_step_resumes(self):
        g = head_on_to_contact()
        g.relocate("GB1", "0,0", "E", 18)
        g.relocate("GE1", "20,0", "W", 18)
        g.step_turn()
        self.assertEqual(g.state, fs.STATE_SEARCH)


if __name__ == '__main__':
    unittest.main()
