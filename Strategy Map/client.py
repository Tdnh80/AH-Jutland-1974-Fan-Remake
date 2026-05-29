"""CLI 客户端:连裁判机,声明 side,发命令,显示裁判回推的双盲视图。"""

import json
import socket
import sys


def _fmt_view(v):
    lines = [f"[{v['side']}] T{v['turn']} sub{v['substep']} state={v['state']}"]
    for f in v["own"]:
        lines.append(f"  own {f['name']} course={f['course']} speed={f['speed']}kn")
    for c in v["enemy_contacts"]:
        lines.append(f"  ENEMY {c['name']} @ {c['cell']}")
    return "\n".join(lines)


def run_client(host, port, side, infile=None):
    s = socket.create_connection((host, port))
    f = s.makefile("rwb")
    f.write((json.dumps({"side": side}) + "\n").encode()); f.flush()
    view = json.loads(f.readline())
    print(_fmt_view(view))
    src = infile if infile is not None else sys.stdin
    for line in src:
        line = line.strip()
        if not line:
            continue
        f.write((json.dumps({"cmd": line}) + "\n").encode()); f.flush()
        resp = json.loads(f.readline())
        if resp.get("output"):
            print(resp["output"], end="")
        print(_fmt_view(resp["view"]))
        if resp.get("output") == "__QUIT__":
            break
    s.close()


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    side = sys.argv[3].upper() if len(sys.argv) > 3 else "GB"
    run_client(host, port, side)
