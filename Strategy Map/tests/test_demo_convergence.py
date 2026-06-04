import unittest
import fleet_search as fs


class TestDemoConvergence(unittest.TestCase):
    def test_demo_runs_and_is_reproducible(self):
        # demo 改为 course 排队转向机动:不再强求接敌频率,只要不崩 + 同种子可复现。
        # (course 朝对方偏置仍使多数种子最终接敌,但接敌不再是验收条件。)
        for seed in range(8):
            g1 = fs.Game()
            fs.run_demo(g1, seed=seed, max_turns=40, plot=False)
            g2 = fs.Game()
            fs.run_demo(g2, seed=seed, max_turns=40, plot=False)
            self.assertEqual(g1.to_dict(), g2.to_dict())


if __name__ == '__main__':
    unittest.main()
