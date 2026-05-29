import unittest
import fleet_search as fs


def head_on_to_contact():
    g = fs.Game()
    g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 3)
    g.add_fleet("GE1", "GE", 0, "4,0", "W", 18, 2)
    g.schedule("GB1", 18, ["1,0", "2,0", "3,0"])
    g.schedule("GE1", 18, ["3,0", "2,0", "1,0"])
    g.step_turn(); g.step_turn()
    return g


class TestViewFilter(unittest.TestCase):
    def test_search_phase_only_own_fleets_visible(self):
        g = fs.Game()
        g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 2)
        g.add_fleet("GE1", "GE", 0, "10,0", "W", 18, 2)
        v = fs.view_for_side(g, "GB")
        names = [f["name"] for f in v["own"]]
        self.assertEqual(names, ["GB1"])
        self.assertEqual(v["enemy_contacts"], [])   # 搜索阶段看不到对方

    def test_contact_phase_reveals_enemy_center(self):
        g = head_on_to_contact()
        self.assertEqual(g.state, fs.STATE_CONTACT)
        v = fs.view_for_side(g, "GB")
        self.assertEqual([f["name"] for f in v["own"]], ["GB1"])
        enemy = [c["name"] for c in v["enemy_contacts"]]
        self.assertIn("GE1", enemy)                 # 接敌后可见对方中心

    def test_side_symmetry(self):
        g = head_on_to_contact()
        vge = fs.view_for_side(g, "GE")
        self.assertEqual([f["name"] for f in vge["own"]], ["GE1"])
        self.assertIn("GB1", [c["name"] for c in vge["enemy_contacts"]])


if __name__ == '__main__':
    unittest.main()
