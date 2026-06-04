import json
import socket
import threading
import time
import unittest
from server import JutlandServer


def send_line(f, obj):
    f.write((json.dumps(obj) + "\n").encode())
    f.flush()


def recv_obj(f):
    return json.loads(f.readline())


class TestServerLoopback(unittest.TestCase):
    def setUp(self):
        self.srv = JutlandServer(host="127.0.0.1", port=0)
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start()
        time.sleep(0.05)

    def tearDown(self):
        self.srv.stop()

    def _connect(self, side):
        s = socket.create_connection(("127.0.0.1", self.srv.port))
        f = s.makefile("rwb")
        send_line(f, {"side": side})
        recv_obj(f)            # initial view
        return s, f

    def test_double_blind_search_phase(self):
        sg, fg = self._connect("GB")
        se, fe = self._connect("GE")
        # GE 建立己方舰队
        send_line(fe, {"cmd": "new GE1 GE 0 A20 W 18 2"})
        recv_obj(fe)
        # GB 建立己方舰队并看自己的视图
        send_line(fg, {"cmd": "new GB1 GB 0 A13 E 18 2"})
        resp = recv_obj(fg)
        own = [f["name"] for f in resp["view"]["own"]]
        self.assertIn("GB1", own)
        self.assertNotIn("GE1", own)                       # 看不到对方舰队
        self.assertEqual(resp["view"]["enemy_contacts"], [])   # 搜索阶段双盲
        sg.close(); se.close()


if __name__ == '__main__':
    unittest.main()
