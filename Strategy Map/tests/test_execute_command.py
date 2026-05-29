import unittest
import fleet_search as fs


class TestExecuteCommand(unittest.TestCase):
    def test_new_and_list(self):
        g = fs.Game()
        out = fs.execute_command(g, "new GB1 GB 0 A13 E 18 2")
        self.assertIn("ok", out.lower())
        self.assertIn("GB1", g.fleets)
        listing = fs.execute_command(g, "list")
        self.assertIn("GB1", listing)

    def test_unknown_command_reported(self):
        g = fs.Game()
        out = fs.execute_command(g, "florb")
        self.assertIn("unknown command", out)

    def test_quit_raises_signal(self):
        g = fs.Game()
        with self.assertRaises(fs.QuitSignal):
            fs.run_command(g, "quit")

    def test_command_is_journaled(self):
        g = fs.Game()
        fs.execute_command(g, "new GB1 GB 0 A13 E 18 1")
        cmds = [h["cmd"] for h in g.journal.history]
        self.assertIn("new GB1 GB 0 A13 E 18 1", cmds)


if __name__ == '__main__':
    unittest.main()
