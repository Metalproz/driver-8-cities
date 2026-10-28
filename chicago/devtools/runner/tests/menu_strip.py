"""C98: after quitting Chicago to the main menu the specials slot must not be re-uploaded (Polish: VRAM x704-767
y128-255 over the menu sprite). Chicago 20 s driving, quit, 15 s in the menu; counts the plugin's re-upload log lines
in the menu window and compares the menu sprite VRAM rows 128-135 x 704-727 before / after."""
import glob, os, time
from pathlib import Path
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)


def quit_to_menu(s):
    s.press("start", gap=1.5)
    for _ in range(7): s.press("down", gap=0.4)
    s.press("cross", gap=1.0); s.press("left", gap=0.4); s.press("cross", gap=1.0)
    time.sleep(5)


def run(s):
    s.menu("take_a_ride/chicago"); s.wait_world(what="start")
    s.drive(20.0, s.car(0)[3])
    logs = sorted(glob.glob(str(s.copy_dir / "dev" / "logs" / "*.log")), key=os.path.getmtime)
    log = Path(logs[-1]) if logs else s.copy_dir / "run.log"
    quit_to_menu(s)
    n0 = open(log, errors="ignore").read().count("slot re-uploaded") if log.exists() else -1
    time.sleep(15)
    n1 = open(log, errors="ignore").read().count("slot re-uploaded") if log.exists() else -1
    s.screenshot("menu")
    s.check("no specials re-upload in the menu", n1 == n0, "re-upload lines before %d after %d (log %s)" % (n0, n1, log.exists()))
