import io
import unittest
from contextlib import redirect_stdout
import fleet_search as fs


def run_cli(lines):
    """把若干命令喂给 main(),返回 stdout。"""
    buf = io.StringIO()
    import builtins
    it = iter(lines + ["quit"])
    orig = builtins.input
    builtins.input = lambda *a, **k: next(it)
    try:
        with redirect_stdout(buf):
            fs.main()
    finally:
        builtins.input = orig
    return buf.getvalue()


class TestCliSmoke(unittest.TestCase):
    def test_formation_command_sets_kind(self):
        out = run_cli([
            "new F GB 0 A13 E 18 3",
            "formation F abreast right relative",
            "list",
        ])
        self.assertIn("ok", out.lower())
        self.assertNotIn("unknown command", out)

    def test_new_list_step_runs(self):
        out = run_cli([
            "new GB1 GB 0 A13 E 18 2",
            "new GE1 GE 0 A20 W 18 2",
            "step",
            "list",
        ])
        self.assertNotIn("unknown command", out)
        self.assertNotIn("error:", out)


if __name__ == '__main__':
    unittest.main()
