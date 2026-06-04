"""裁判机服务器:持全局 Game,接受 GB/GE 客户端,执行命令并回推双盲过滤视图。

协议(每条消息一行 JSON):
  client 连上后先发 {"side": "GB"|"GE"};server 回初始 view_for_side。
  之后 client 发 {"cmd": "<command line>"};server 回 {"output": str, "view": {...}}。
"""

import json
import socket
import threading

import fleet_search as fs


class JutlandServer:
    def __init__(self, host="127.0.0.1", port=0):
        self.game = fs.Game()
        self.lock = threading.Lock()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self._stop = False

    def _send(self, f, obj):
        f.write((json.dumps(obj, ensure_ascii=False) + "\n").encode())
        f.flush()

    def _handle(self, conn):
        f = conn.makefile("rwb")
        try:
            hello = json.loads(f.readline())
            side = hello.get("side", "GB")
            with self.lock:
                self._send(f, fs.view_for_side(self.game, side))
            for raw in f:
                msg = json.loads(raw)
                line = msg.get("cmd", "")
                with self.lock:
                    ok, reason = fs.authorize_player_command(self.game, side, line)
                    if ok:
                        out = fs.execute_command(self.game, line)
                    else:
                        out = f"  refused: {reason}"
                    view = fs.view_for_side(self.game, side)
                self._send(f, {"output": out, "view": view})
        except (OSError, ValueError):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def serve_forever(self):
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def stop(self):
        self._stop = True
        try:
            self.sock.close()
        except OSError:
            pass


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    srv = JutlandServer(port=port)
    print(f"referee server on 127.0.0.1:{srv.port}")
    srv.serve_forever()
