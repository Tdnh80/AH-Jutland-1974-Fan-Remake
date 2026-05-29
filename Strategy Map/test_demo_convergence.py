import unittest
import fleet_search as fs


class TestDemoConvergence(unittest.TestCase):
    def test_demo_reaches_contact_within_turns(self):
        # 多个种子下,加了吸引因子后应在 max_turns 内接敌
        hits = 0
        for seed in range(8):
            g = fs.Game()
            files = fs.run_demo(g, seed=seed, max_turns=40, frame_prefix="_convtest")
            if g.last_report is not None and g.state == fs.STATE_CONTACT:
                hits += 1
        # 收敛应让绝大多数种子在 40 回合内接敌
        self.assertGreaterEqual(hits, 6)

    def tearDown(self):
        import glob, os
        for f in glob.glob("_convtest_*.png"):
            try: os.remove(f)
            except OSError: pass


if __name__ == '__main__':
    unittest.main()
