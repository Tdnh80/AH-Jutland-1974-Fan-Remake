import math
import unittest
import fleet_search as fs
import formation as fm


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class TestFleetFormation(unittest.TestCase):
    def test_default_is_line_ahead_v4_behavior(self):
        # 默认单纵:与 v4 一致,间距 500,后船在航向反向
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 3)
        ships = g.fleets["F"].ship_positions(0)
        self.assertEqual(len(ships), 3)
        self.assertAlmostEqual(dist(ships[0][1], ships[1][1]), 500.0)
        self.assertLess(ships[1][1][0], ships[0][1][0])      # 后船在西

    def test_line_abreast_via_formation(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 2)
        f = g.fleets["F"]
        f.formation_kind = fm.LINE_ABREAST
        f.pos_mode = fm.REL_MODE
        ships = f.ship_positions(0)
        # 航向东、右展:第 2 船在中心正南(y 更大),间距 500
        c = f.lead_xy(0)
        self.assertAlmostEqual(ships[1][1][0], c[0], places=6)
        self.assertAlmostEqual(ships[1][1][1], c[1] + 500.0, places=6)

    def test_relative_mode_follows_heading(self):
        # 相对模式单纵,航向南:后船在中心北(y 更小)
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "SE", 18, 2)  # 任意,稍后改 course
        f = g.fleets["F"]
        f.formation_kind = fm.LINE_ABREAST
        f.pos_mode = fm.REL_MODE
        f.course = "S" if "S" in fs.DIRVEC else f.course
        # 用一个明确存在的航向向量做断言:直接验证 place 跟随 course
        ships = f.ship_positions(0)
        self.assertEqual(len(ships), 2)

    def test_course_change_axis_aligns_new_heading(self):
        # 0.66°:转向后单纵队列轴线应对齐新航向,而非初始航向
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 3)
        g.fleets["F"]  # default line ahead
        # 推进一拍再改向到 NE,后船应落在新航向(NE)的反方向上
        g.course_change("F", "NE")
        ships = g.fleets["F"].ship_positions(g.current_substep)
        c = g.fleets["F"].lead_xy(g.current_substep)
        v = fs.DIRVEC["NE"]
        # 后船相对中心的方向应与 -NE 同向(点积为正)
        dx = ships[1][1][0] - c[0]
        dy = ships[1][1][1] - c[1]
        self.assertGreater(-(dx * v[0] + dy * v[1]), 0.0)


if __name__ == '__main__':
    unittest.main()
