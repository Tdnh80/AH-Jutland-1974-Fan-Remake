import unittest
import fleet_search as fs
import formation as fm


class TestSerialization(unittest.TestCase):
    def test_fleet_formation_fields_roundtrip(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "1,2", "E", 18, 3)
        f = g.fleets["F"]
        f.formation_kind = fm.LINE_ABREAST
        f.deploy = "left"
        f.echelon_deg = 30.0
        f.pos_mode = fm.ABS_MODE
        f.layout_heading = (1.0, 0.0)
        d = g.to_dict()
        g2 = fs.Game()
        g2.load_dict(d)
        f2 = g2.fleets["F"]
        self.assertEqual(f2.formation_kind, fm.LINE_ABREAST)
        self.assertEqual(f2.deploy, "left")
        self.assertEqual(f2.echelon_deg, 30.0)
        self.assertEqual(f2.pos_mode, fm.ABS_MODE)
        self.assertEqual(tuple(f2.layout_heading), (1.0, 0.0))

    def test_game_state_and_contact_hexes_roundtrip(self):
        g = fs.Game()
        g.state = fs.STATE_CONTACT
        g.contact_hexes = {(2, 0), (3, -1)}
        g2 = fs.Game()
        g2.load_dict(g.to_dict())
        self.assertEqual(g2.state, fs.STATE_CONTACT)
        self.assertEqual(g2.contact_hexes, {(2, 0), (3, -1)})

    def test_default_fleet_roundtrip_unchanged(self):
        g = fs.Game()
        g.add_fleet("F", "GB", 0, "0,0", "E", 18, 2)
        g2 = fs.Game()
        g2.load_dict(g.to_dict())
        self.assertEqual(g2.fleets["F"].formation_kind, fm.LINE_AHEAD)
        self.assertEqual(g2.fleets["F"].course, "E")
        self.assertEqual(len(g2.fleets["F"].ships), 2)


if __name__ == '__main__':
    unittest.main()
