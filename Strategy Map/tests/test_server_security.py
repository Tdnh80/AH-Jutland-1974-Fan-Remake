import json
import socket
import threading
import time
import unittest
from server import JutlandServer


def send_line(f, obj):
    f.write((json.dumps(obj) + "\n").encode()); f.flush()


def recv_obj(f):
    return json.loads(f.readline())


class TestServerSecurity(unittest.TestCase):
    def setUp(self):
        self.srv = JutlandServer(host="127.0.0.1", port=0)
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start(); time.sleep(0.05)

    def tearDown(self):
        self.srv.stop()

    def _connect(self, side):
        s = socket.create_connection(("127.0.0.1", self.srv.port))
        f = s.makefile("rwb")
        send_line(f, {"side": side}); recv_obj(f)
        return s, f

    def test_player_cannot_touch_enemy_fleet(self):
        sg, fg = self._connect("GB")
        se, fe = self._connect("GE")
        send_line(fe, {"cmd": "new GE1 GE 0 A20 W 18 2"}); recv_obj(fe)
        send_line(fg, {"cmd": "relocate GE1 A21 W 18"})
        resp = recv_obj(fg)
        self.assertIn("refused", resp["output"].lower())
        sg.close(); se.close()

    def test_player_cannot_create_enemy_fleet(self):
        sg, fg = self._connect("GB")
        send_line(fg, {"cmd": "new X GE 0 A20 W 18 2"})
        self.assertIn("refused", recv_obj(fg)["output"].lower())
        sg.close()

    def test_list_is_refused_no_enemy_leak(self):
        sg, fg = self._connect("GB")
        se, fe = self._connect("GE")
        send_line(fe, {"cmd": "new GE1 GE 0 A20 W 18 2"}); recv_obj(fe)
        send_line(fg, {"cmd": "list"})
        resp = recv_obj(fg)
        self.assertNotIn("GE1", resp["output"])     # output 不泄漏敌方
        sg.close(); se.close()


if __name__ == '__main__':
    unittest.main()
