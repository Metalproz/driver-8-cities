"""C130: the Mods setting 'Rewind' (driver.personal feature rewind, default on) decides: the plugin logs and applies it on
the first vblank. WANT=on|off (run with CHI_FEATURES_OFF=driver.personal:rewind for off)."""
import glob, os, time
WANT = os.environ.get("WANT", "on")
SESSION = dict(day="var_polish_cheats6_day.lev", night="var_polish_cheats6_night.lev", s4=True)


def run(s):
    s.menu("take_a_ride/miami"); s.wait_world(what="miami")
    time.sleep(2)
    logs = sorted(glob.glob(str(s.copy_dir / "dev" / "logs" / "*.log")), key=os.path.getmtime)
    line = ""
    if logs:
        line = next((l.strip() for l in open(logs[-1], encoding="utf-8", errors="replace") if "(Mods setting)" in l), "")
    s.record("log", detail=line or "no rewind line")
    s.check("rewind %s from the Mods setting" % WANT, ("rewind %s" % WANT) in line, line)
