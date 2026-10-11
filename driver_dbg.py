"""driver_dbg.py — talk to the running game's debug server (127.0.0.1:4370).

The server answers one JSON request per TCP connection and wants compact JSON.

  python driver_dbg.py ping
  python driver_dbg.py frame
  python driver_dbg.py read 0x800967E0 16        hex dump of guest RAM
  python driver_dbg.py watch 0x800967F8 4 0.5    print a value whenever it changes
  python driver_dbg.py shot C:/path/shot.png     native screenshot
  python driver_dbg.py snapshot                  same as F9 (needs Developer Mode)
  python driver_dbg.py raw '{"cmd":"gpu_state"}'  any server command

Full command list: psxrecomp/TCP_COMMANDS.md.
"""
import json
import os
import socket
import sys
import time

PORT = 4370
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cmd(name, **kw):
    kw["cmd"] = name
    kw.setdefault("id", 1)
    with socket.create_connection(("127.0.0.1", PORT), timeout=40) as s:
        s.sendall((json.dumps(kw, separators=(",", ":")) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(1 << 20)
            if not chunk:
                break
            buf += chunk
    return json.loads(buf.decode().splitlines()[0])


def read(addr, length):
    r = cmd("read_ram", addr="0x%08X" % addr, len=length)
    if not r.get("ok"):
        raise RuntimeError(r)
    return bytes.fromhex(r["hex"])


def main(argv):
    if not argv:
        print(__doc__)
        return
    op = argv[0]
    if op in ("ping", "frame"):
        print(cmd(op))
    elif op == "read":
        addr, length = int(argv[1], 0), int(argv[2], 0)
        data = read(addr, length)
        for i in range(0, len(data), 16):
            print("%08X: %s" % (addr + i, data[i:i + 16].hex(" ")))
    elif op == "watch":
        addr, length = int(argv[1], 0), int(argv[2], 0)
        delay = float(argv[3]) if len(argv) > 3 else 0.5
        last = None
        while True:
            v = read(addr, length)
            if v != last:
                print("%s frame %s  %08X: %s" % (time.strftime("%H:%M:%S"),
                      cmd("frame").get("frame"), addr, v.hex(" ")), flush=True)
                last = v
            time.sleep(delay)
    elif op == "shot":
        print(cmd("screenshot", path=os.path.abspath(argv[1])))
    elif op == "snapshot":
        os.makedirs(os.path.join(APP, "dev"), exist_ok=True)
        open(os.path.join(APP, "dev", "dump.request"), "w").close()
        print("requested; see", os.path.join(APP, "dev", "dumps"))
    elif op == "raw":
        req = json.loads(argv[1])
        print(cmd(req.pop("cmd"), **req))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
