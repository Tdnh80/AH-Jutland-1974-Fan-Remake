import unittest
import coords as co


class TestCoords(unittest.TestCase):
    def test_letter_index_roundtrip(self):
        self.assertEqual(co.idx_to_letter(1), "A")
        self.assertEqual(co.idx_to_letter(26), "Z")
        self.assertEqual(co.idx_to_letter(27), "AA")
        self.assertEqual(co.idx_to_letter(30), "DD")
        self.assertEqual(co.letter_to_idx("A"), 1)
        self.assertEqual(co.letter_to_idx("z"), 26)   # 大小写不敏感
        self.assertEqual(co.letter_to_idx("AA"), 27)
        self.assertEqual(co.letter_to_idx("DD"), 30)

    def test_four_corners(self):
        # 映射公式:q=数字, r=字母行(A=1..DD=30)
        self.assertEqual(co.parse_cell("A13"), (13, 1))
        self.assertEqual(co.parse_cell("A34"), (34, 1))
        self.assertEqual(co.parse_cell("DD-1"), (-1, 30))
        self.assertEqual(co.parse_cell("DD19"), (19, 30))

    def test_cell_name_is_inverse(self):
        self.assertEqual(co.cell_name(13, 1), "A13")
        self.assertEqual(co.cell_name(34, 1), "A34")
        self.assertEqual(co.cell_name(-1, 30), "DD-1")
        self.assertEqual(co.cell_name(19, 30), "DD19")

    def test_labelled_cells_share_q_on_diagonal(self):
        # 图上同一数字的格必落在同一条「左上→右下」线(同 q)
        for name in ("E15", "I15", "N15", "S15", "X15"):
            self.assertEqual(co.parse_cell(name)[0], 15)
        # 字母行各不相同
        rows = {co.parse_cell(n)[1] for n in ("E15", "I15", "N15", "S15", "X15")}
        self.assertEqual(len(rows), 5)

    def test_full_roundtrip(self):
        for r in range(1, 31):
            for q in range(-1, 35):
                self.assertEqual(co.parse_cell(co.cell_name(q, r)), (q, r))

    def test_bad_input_raises(self):
        with self.assertRaises(ValueError):
            co.parse_cell("13A")       # 顺序反了
        with self.assertRaises(ValueError):
            co.letter_to_idx("AB")     # 非翻倍式,不合法


if __name__ == '__main__':
    unittest.main()
