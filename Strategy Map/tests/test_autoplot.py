import os
import tempfile
import unittest
import fleet_search as fs


def _matplotlib_ok():
    try:
        import matplotlib  # noqa: F401
        return True
    except ImportError:
        return False


def head_on_to_contact_game():
    """两支正面对进、会在数回合内接敌的对局(沿用 closeup 测试的布局)。"""
    g = fs.Game()
    g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 3)
    g.add_fleet("GE1", "GE", 0, "4,0", "W", 18, 2)
    g.schedule("GB1", 18, ["1,0", "2,0", "3,0"])
    g.schedule("GE1", 18, ["3,0", "2,0", "1,0"])
    return g


class TestAutoplot(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_default_off_and_no_files(self):
        g = head_on_to_contact_game()
        # 默认关:step 后不应有 auto_*.png
        fs.execute_command(g, "step")
        autos = [f for f in os.listdir(".") if f.startswith("auto_")]
        self.assertEqual(autos, [], f"autoplot off should produce no files, got {autos}")

    def test_autoplot_command_toggles(self):
        g = head_on_to_contact_game()
        self.assertFalse(g.autoplot)
        out = fs.execute_command(g, "autoplot on")
        self.assertTrue(g.autoplot)
        self.assertIn("autoplot on", out)
        out = fs.execute_command(g, "autoplot off")
        self.assertFalse(g.autoplot)
        self.assertIn("autoplot off", out)

    def test_autoplot_bad_arg(self):
        g = head_on_to_contact_game()
        out = fs.execute_command(g, "autoplot maybe")
        self.assertIn("usage", out.lower())
        self.assertFalse(g.autoplot)

    def test_autoplot_on_writes_board_each_step(self):
        if not _matplotlib_ok():
            self.skipTest("matplotlib unavailable")
        g = head_on_to_contact_game()
        fs.execute_command(g, "autoplot on")
        fs.execute_command(g, "step")
        turn = g.current_turn
        fn = f"auto_t{turn}.png"
        self.assertTrue(os.path.exists(fn) and os.path.getsize(fn) > 0,
                        f"expected {fn} to be written")

    def test_autoplot_on_writes_encounter_closeup(self):
        if not _matplotlib_ok():
            self.skipTest("matplotlib unavailable")
        g = head_on_to_contact_game()
        fs.execute_command(g, "autoplot on")
        # 推进到接敌
        for _ in range(6):
            out = fs.execute_command(g, "step")
            if g.state == fs.STATE_CONTACT:
                break
        self.assertEqual(g.state, fs.STATE_CONTACT, "expected an encounter within 6 steps")
        turn = g.current_turn
        enc_fn = f"auto_enc_t{turn}.png"
        self.assertTrue(os.path.exists(enc_fn) and os.path.getsize(enc_fn) > 0,
                        f"expected {enc_fn} (encounter close-up) to be written")


if __name__ == '__main__':
    unittest.main()
