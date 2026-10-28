"""Design (C63 step 2): reviews Polish's LA-day swap table and writes la_day_swap_review.json.
Usage: python la_day_swap_review.py   (reads the discs through chicago/inputs.py; writes only the json)
Rules (from the contact sheets out/laday/swaps_*.png):
 - SIGN_KEEP: LA textures that are neon/poster signs with their own identity: do not swap, keep (or day-grade).
 - BAD_DONORS: donor textures carrying readable branding / people / vehicles / other cities' landmarks.
 Everything else keeps its donor unless the donor is bad; then the table is recomputed with Polish's own matcher
 minus the bad donors and the new donor is given as replace-with."""
import sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "chicago"))
import polish_laday as L, inputs
SIGN_KEEP = {"UNTITLED_X", "DT3-04", "SS17B", "DT2-03", "SS2-28", "RODPOST", "SM01B", "SM27C", "SS10", "SS05B", "SS11B", "SS13", "SS09B", "SS06",
             "SS18", "SS2-08", "SS07B", "DT53", "DT2-08B", "DT2-12", "SS38", "SS21", "SS2-03", "SS2-11C"}
BAD_DONORS = {"TOP02", "TOP05", "TOP04", "TOP1", "NIKI", "FRONT", "NEWTRAN5", "MURAL01", "TRAMBUSB", "CHINAPCE", "CHINA1",
              "CCHINASN", "MICK81", "DIFFRNT", "CREAM1", "PISTON3", "PISTON4", "PISTON", "TRINSPI2", "POSTSTPS", "SE-FIN04"}
def main():
    old = json.load(open(os.path.join(inputs.WORK, "polish_la_day_table.json")))["swaps"]
    L.GROUND_WORDS = L.GROUND_WORDS + tuple(SIGN_KEEP)           # never swapped
    L.AD_WORDS = L.AD_WORDS + tuple(BAD_DONORS)                  # never donors (substring match)
    new = {(s["page"], s["k"]): s for s in L.build_table()["swaps"]}
    out = []
    for i, s in enumerate(old):
        e = {"i": i, "la": s["la"], "donor": s["donor_tex"], "from": s["donor"][:-4]}
        if s["la"] in SIGN_KEEP:
            e.update(verdict="exclude", repaint=True, why="LA sign/poster texture: no donor swap; day-repaint by la_day_repaint.EXTRA (CLUT remap)")
        elif s["donor_tex"] in BAD_DONORS:
            n = new.get((s["page"], s["k"]))
            if n:
                e.update(verdict="replace", replace_with=n["donor_tex"], replace_from=n["donor"][:-4], why="donor has branding/person/vehicle/other-city landmark")
            else:
                e.update(verdict="exclude", why="bad donor and no clean replacement")
        else:
            n = new.get((s["page"], s["k"]))
            e.update(verdict="keep", why="")
        out.append(e)
    json.dump({"bad_donors": sorted(BAD_DONORS), "sign_keep": sorted(SIGN_KEEP), "swaps": out}, open(os.path.join(HERE, "la_day_swap_review.json"), "w"), indent=1)
    import collections
    print(collections.Counter(e["verdict"] for e in out))
main()
