import os
import tempfile
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


class TestCloseupSmoke(unittest.TestCase):
    def test_closeup_writes_file(self):
        g = head_on_to_contact()
        self.assertEqual(g.state, fs.STATE_CONTACT)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "closeup.png")
            try:
                fs.plot_encounter_closeup(g, path)
            except RuntimeError as e:
                self.skipTest(f"matplotlib unavailable: {e}")
            self.assertTrue(os.path.exists(path) and os.path.getsize(path) > 0)


if __name__ == '__main__':
    unittest.main()
