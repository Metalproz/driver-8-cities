"""Ship pre-check on an exact copy of build-dev (runner run ship_check --copy shipcheck --reuse --port 4466):
Take a Ride Chicago and Miami (in level, the car drives, alive), the cheats screen with both pages."""
import os, time
SESSION = dict(day="var_polish_specdmg2_day.lev", night="var_polish_specdmg2_night.lev", s4=True)


def quit_to_menu(s):
    s.press("start", gap=1.5)
    for _ in range(7): s.press("down", gap=0.4)
    s.press("cross", gap=1.0); s.press("left", gap=0.4); s.press("cross", gap=1.0)
    time.sleep(5)


def run(s):
    for k, city in enumerate(os.environ.get("CITIES", "chicago").split(",")):    # one city per launch (the menu after a quit starts elsewhere)
        if k: quit_to_menu(s)
        s.menu("take_a_ride/" + city); s.wait_world(what="start")
        p0 = s.pos(); s.hold("cross"); time.sleep(3); s.release(); p1 = s.pos()
        s.screenshot(city)
        s.check("%s drives" % city, abs(p1[0] - p0[0]) + abs(p1[2] - p0[2]) > 1000, "moved %d" % (abs(p1[0] - p0[0]) + abs(p1[2] - p0[2])))
        s.check("%s alive" % city, s.alive(2.0))
