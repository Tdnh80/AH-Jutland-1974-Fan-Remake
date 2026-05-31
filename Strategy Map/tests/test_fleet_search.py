#!/usr/bin/env python3
"""
回归测试 —— 钉住 CLAUDE.md「锁定的约定」与核心不变量。

只依赖标准库(unittest)。matplotlib 在 fleet_search 里是惰性 import(仅 plot_state
用到),所以本测试无需安装 matplotlib。

跑法:
    python -m unittest test_fleet_search -v
    python test_fleet_search.py
"""

import math
import unittest

import fleet_search as fs


TOL = 1e-6


class TestLockedConstants(unittest.TestCase):
    """尺度/时间/速度/视距 —— 这些数值是反复确认过的,改动前必须有理由。"""

    def test_hex_scale(self):
        self.assertEqual(fs.HEX_SIDE, 36000.0)          # 对边距 = 邻格中心距
        self.assertEqual(fs.APOTHEM, 18000.0)           # 中心到边中点
        self.assertAlmostEqual(fs.HEX_SIZE, 36000.0 / math.sqrt(3), delta=TOL)

    def test_visibility_caps(self):
        # ⚠ 视距上限是 36000(1 格对边距),不是 18000(apothem)。
        self.assertEqual(fs.MAX_VISIBILITY, 36000.0)
        self.assertEqual(fs.DEFAULT_VISIBILITY, 20000.0)

    def test_18kn_covers_exactly_one_hex_per_six_substeps(self):
        # STEP_YARDS_PER_KNOT 选成 36000/108,使 18kn 恰好 6 拍走 1 格。
        self.assertAlmostEqual(fs.STEP_YARDS_PER_KNOT * 18 * 6, fs.HEX_SIDE, delta=1e-6)

    def test_speed_to_hex_per_cycle(self):
        # 12/18/24 kn = 3 回合走 2/3/4 格。
        self.assertEqual(fs.HEX_PER_CYCLE, {12: 2, 18: 3, 24: 4})


class TestAxialGeometry(unittest.TestCase):
    """axial (q,r),pointy-top,六方向统一邻居增量(无奇偶行)。"""

    def test_neighbour_spacing_is_hex_side(self):
        c0 = fs.hex_center_xy(0, 0)
        for d, (dq, dr) in fs.NEIGH.items():
            cn = fs.hex_center_xy(dq, dr)
            dist = math.hypot(cn[0] - c0[0], cn[1] - c0[1])
            self.assertAlmostEqual(dist, fs.HEX_SIDE, delta=1e-3,
                                   msg=f"邻居 {d} 中心距应为 1 格对边距")

    def test_nw_se_keep_q_invariant(self):
        # NW↔SE 斜线上 q 不变(朋友的设计要点)。
        self.assertEqual(fs.NEIGH['NW'][0], 0)
        self.assertEqual(fs.NEIGH['SE'][0], 0)

    def test_xy_to_hex_roundtrip(self):
        for q in range(-6, 7):
            for r in range(-6, 7):
                x, y = fs.hex_center_xy(q, r)
                self.assertEqual(fs.xy_to_hex(x, y), (q, r),
                                 msg=f"格心 ({q},{r}) 反解应回到自身")

    def test_direction_between_matches_neighbour(self):
        a = (2, -1)
        for d in fs.NEIGH:
            b = fs.hex_neighbour(a, d)
            self.assertEqual(fs.direction_between(a, b), d)

    def test_micro_position_edge_and_distance(self):
        # 报告改为相对「最近的边中心」:点在格心东 5000,最近边中心是 E 边(+18000),
        # 故距该边中心 = 13000。
        cx, cy = fs.hex_center_xy(0, 0)
        h, edge, dist = fs.micro_position(cx + 5000, cy)
        self.assertEqual(h, (0, 0))
        self.assertEqual(edge, 'E')
        self.assertAlmostEqual(dist, 13000.0, delta=TOL)


class TestLineAheadFormation(unittest.TestCase):
    """单纵阵 + 鱼贯:船 i 沿航迹回退 i×500 码。报告时不吸附格心。"""

    def test_ship_spacing_and_trailing_direction(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 3)
        ships = g.fleets["F"].ship_positions(0)
        self.assertEqual(len(ships), 3)
        for i in range(len(ships) - 1):
            (_, p0), (_, p1) = ships[i], ships[i + 1]
            gap = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            self.assertAlmostEqual(gap, fs.DEFAULT_SPACING, delta=TOL)
        # 航向 E,后船应在旗舰西侧(x 更小)
        self.assertLess(ships[1][1][0], ships[0][1][0])

    def test_position_not_snapped_to_centre(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 3)
        # 走 1 拍(6000 码,< 1 格),旗舰应在格内非格心处
        x, y = g.fleets["F"].lead_xy(1)
        self.assertAlmostEqual(x, 6000.0, delta=TOL)
        self.assertNotEqual((x, y), fs.hex_center_xy(*fs.xy_to_hex(x, y)))


class TestScheduleValidation(unittest.TestCase):
    """schedule:航路点数 = speed/6;相邻校验;允许 180° 掉头。"""

    def _fleet(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 3)
        return g

    def test_wrong_waypoint_count_rejected(self):
        g = self._fleet()
        with self.assertRaises(ValueError):
            g.schedule("F", 18, ["1,0", "2,0"])        # 18kn 需要 3 个

    def test_non_adjacent_waypoint_rejected(self):
        g = self._fleet()
        with self.assertRaises(ValueError):
            g.schedule("F", 18, ["1,0", "3,0", "4,0"])  # (1,0)->(3,0) 不相邻

    def test_valid_schedule_and_180_reversal_allowed(self):
        g = self._fleet()
        g.schedule("F", 18, ["1,0", "0,0", "1,0"])      # 含 180° 掉头,应允许
        self.assertTrue(g.fleets["F"].scheduled)

    def test_course_change_blocked_while_scheduled(self):
        g = self._fleet()
        g.schedule("F", 18, ["1,0", "2,0", "3,0"])
        with self.assertRaises(ValueError):
            g.course_change("F", "W")                   # 有 schedule 时禁止改向


class TestRandomWalk(unittest.TestCase):
    def test_length_bounds_and_adjacency(self):
        import random
        rng = random.Random(42)
        path = fs.random_walk_path((0, 0), 18, rng, prev_dir='E')
        self.assertEqual(len(path), fs.HEX_PER_CYCLE[18])
        chain = [(0, 0)] + path
        for a, b in zip(chain, chain[1:]):
            self.assertIsNotNone(fs.direction_between(a, b))  # 相邻
            self.assertLessEqual(abs(b[0]), 40)
            self.assertLessEqual(abs(b[1]), 40)


class TestEncounterRollback(unittest.TestCase):
    """接敌核心约定:首个出现某对 < vis 的拍 S → 回退到 S-1(干净的接触前状态),
    并对 S-1→S 线性插值给出 =vis 的投影接触点。检测是 10min 离散,非连续 CPA。"""

    def _head_on(self):
        # GB1 (0,0) 向 E,GE1 (4,0) 向 W,18kn 对冲,共线 → 距离随时间线性变化。
        g = fs.Game()                                   # vis 默认 20000
        g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 3)
        g.add_fleet("GE1", "GE", 0, "4,0", "W", 18, 2)
        g.schedule("GB1", 18, ["1,0", "2,0", "3,0"])
        g.schedule("GE1", 18, ["3,0", "2,0", "1,0"])
        return g

    def test_rollback_to_clean_substep(self):
        g = self._head_on()
        self.assertIsNone(g.step_turn())                # 第 1 回合 (→sub6) 无接触
        encs = g.step_turn()                            # 第 2 回合命中
        self.assertTrue(encs)

        # 定格在 S-1 = sub10(S=sub11 才首次 <vis)
        self.assertEqual(g.current_substep, 10)

        # 定格拍是「干净的」:所有跨阵营对都 >= vis
        for d, _, _ in g._cross_pairs(g.current_substep):
            self.assertGreaterEqual(d, g.visibility)

        # 而下一拍确实存在 <vis 的对(说明确实在临界点回退)
        self.assertTrue(any(d < g.visibility for d, _, _ in g._cross_pairs(11)))

        e = encs[0]
        self.assertGreaterEqual(e['dist_roll'], g.visibility)
        self.assertTrue(10 <= e['contact_sub'] <= 11)

    def test_projected_contact_is_at_visibility(self):
        g = self._head_on()
        g.step_turn()
        encs = g.step_turn()
        e = encs[0]
        fa, fb = g.fleets[e['gb']], g.fleets[e['ge']]
        # 共线对冲下距离随时间线性,投影接触拍上的最近距离应恰 = vis
        d_contact = g._min_dist_between(fa, fb, e['contact_sub'])
        self.assertAlmostEqual(d_contact, g.visibility, delta=1.0)

    def test_schedules_halted_after_encounter(self):
        g = self._head_on()
        g.step_turn()
        g.step_turn()
        self.assertFalse(g.fleets["GB1"].scheduled)
        self.assertFalse(g.fleets["GE1"].scheduled)
        self.assertIsNotNone(g.last_report)

    def test_only_cross_side_pairs_count(self):
        # 两支同为 GB 的舰队即使重叠也不算接敌(只判跨阵营)。
        g = fs.Game()
        g.add_fleet("A", "GB", 0, "0,0", "E", 18, 2)
        g.add_fleet("B", "GB", 0, "1,0", "W", 18, 2)    # 相向但同阵营
        self.assertIsNone(g.step_turn())
        self.assertIsNone(g.last_report)


class TestSaveLoad(unittest.TestCase):
    """save/load:JSON round-trip 保持舰队状态/当前拍/视距/时刻;不含随机种子。"""

    def test_roundtrip_preserves_state(self):
        import os
        import tempfile
        g = fs.Game()
        g.start_minute = 5 * 60 + 30
        g.visibility = 25000
        g.add_fleet("GB1", "GB", 0, "0,0", "E", 18, 3)
        g.add_fleet("GE1", "GE", 1, "4,2", "W", 24, 2)
        g.schedule("GB1", 18, ["1,0", "2,0", "3,0"])
        g.step_turn()                                   # 推进,产生 display_history

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "save.json")
            g.save(path)
            g2 = fs.Game()
            g2.load(path)

        self.assertEqual(g2.current_substep, g.current_substep)
        self.assertEqual(g2.visibility, g.visibility)
        self.assertEqual(g2.start_minute, g.start_minute)
        self.assertEqual(set(g2.fleets), set(g.fleets))

        f1, f2 = g.fleets["GB1"], g2.fleets["GB1"]
        self.assertEqual((f2.course, f2.speed, len(f2.ships)),
                         (f1.course, f1.speed, len(f1.ships)))
        self.assertEqual(f2.scheduled, f1.scheduled)
        self.assertEqual(f2.waypoints, f1.waypoints)
        # waypoints 必须反序列化成 tuple,否则 direction_between / 相邻校验会失效
        for w in f2.waypoints:
            self.assertIsInstance(w, tuple)
        # load 后位置一致,且能继续推进而不报错
        self.assertAlmostEqual(f2.lead_xy(g2.current_substep)[0],
                               f1.lead_xy(g.current_substep)[0], delta=TOL)
        g2.step_turn()

    def test_loaded_schedule_still_advances(self):
        import os
        import tempfile
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 3)
        g.schedule("F", 18, ["1,0", "1,1", "2,1"])      # 含拐弯
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            g.save(path)
            g2 = fs.Game(); g2.load(path)
        before = g2.fleets["F"].lead_xy(g2.current_substep)
        g2.step_turn()
        after = g2.fleets["F"].lead_xy(g2.current_substep)
        self.assertNotEqual(before, after)              # 计划航迹被正确恢复并推进


if __name__ == '__main__':
    unittest.main(verbosity=2)
