"""阶段 D:demo 改为 course 排队转向机动,可复现 + 真有转向(不再只直走)。"""
import math
import unittest
import fleet_search as fs


def _direction_set(fleet):
    """从 display_history 提取各段的(量化)行进方向集合。"""
    dirs = set()
    hist = fleet.display_history
    for (_, x0, y0), (_, x1, y1) in zip(hist, hist[1:]):
        dx, dy = x1 - x0, y1 - y0
        if abs(dx) > 1e-6 or abs(dy) > 1e-6:
            dirs.add(round(math.atan2(dy, dx), 1))
    return dirs


class TestDemoPath(unittest.TestCase):
    def test_reproducible_same_seed(self):
        g1 = fs.Game(); fs.run_demo(g1, seed=2, max_turns=12, plot=False)
        g2 = fs.Game(); fs.run_demo(g2, seed=2, max_turns=12, plot=False)
        self.assertEqual(g1.to_dict(), g2.to_dict())

    def test_track_actually_turns(self):
        # 跨两支舰队的整段航迹应出现 >=2 个不同方向(证明不是只直走)
        g = fs.Game(); fs.run_demo(g, seed=0, max_turns=20, plot=False)
        dirs = set()
        for f in g.fleets.values():
            dirs |= _direction_set(f)
        self.assertGreaterEqual(len(dirs), 2)

    def test_runs_all_seeds_without_crashing(self):
        for s in range(5):
            g = fs.Game()
            fs.run_demo(g, seed=s, max_turns=15, plot=False)
            self.assertTrue(g.fleets)


if __name__ == '__main__':
    unittest.main()
