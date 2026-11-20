# -*- coding: utf-8 -*-
"""The browser's brain (brain2049.js) must think exactly like the desktop's
(brain2049.py). Plays human-like games in Python, records every analysis and
every coach tip, then replays the same boards and moves in Node and compares.

    python tools/parity_check.py [games]
"""
import json
import os
import random
import subprocess
import sys
import tempfile

from diag_common import B, ROOT, policy_corner_human, policy_lazy_corner, spawn

GAMES = int(sys.argv[1]) if len(sys.argv) > 1 else 6


def moved_map(b, n, d):
    out = {}
    for k in range(n):
        if d == B.LEFT:
            cells = [k * n + j for j in range(n)]
        elif d == B.RIGHT:
            cells = [k * n + j for j in range(n - 1, -1, -1)]
        elif d == B.UP:
            cells = [j * n + k for j in range(n)]
        else:
            cells = [j * n + k for j in range(n - 1, -1, -1)]
        ent = [(b[c], c) for c in cells if b[c]]
        dest = i = 0
        while i < len(ent):
            if i + 1 < len(ent) and ent[i][0] == ent[i + 1][0]:
                out[ent[i][1]] = (cells[dest], True)
                out[ent[i + 1][1]] = (cells[dest], True)
                i += 2
            else:
                out[ent[i][1]] = (cells[dest], False)
                i += 1
            dest += 1
    return out


def summary(a, tip):
    return {
        "values": [a.values.get(d) for d in B.DIRS],
        "best": a.best, "survival": a.survival,
        "safety": [a.safety.get(d) for d in B.DIRS],
        "deadly": list(a.deadly), "corner": a.corner,
        "harms": [[h, i] for h, i in a.harms], "problem": a.problem,
        "stuck": sorted(a.stuck), "kinds": sorted([[k, list(v)] for k, v in a.stuck_info.items()]), "safest": a.safest(),
        "tip": None if tip is None else [tip.key, tip.params, tip.track],
    }


def main():
    games = []
    coach = B.Coach()          # one coach for all games, as in a session: the
    for gi in range(GAMES):    # course of general tips goes on from game to game
        n = (4, 4, 5, 4, 6, 4)[gi % 6]
        rng = random.Random(900 + gi)
        pol = policy_corner_human if gi % 2 == 0 else policy_lazy_corner
        b = spawn(spawn(tuple([0] * (n * n)), n, rng), n, rng)
        a = B.Analysis(b, n)
        coach.new_game(a)
        steps = [{"board": list(b), "expect": summary(a, coach.current)}]
        for mv in range(160 if n == 4 else 70):
            if not a.values:
                break
            d = pol(b, n, rng)
            mm = moved_map(b, n, d)
            b, _ = B.move(b, n, d)
            b = spawn(b, n, rng)
            a = B.Analysis(b, n)
            tip = coach.on_move(d, mm, a)
            steps.append({"board": list(b), "dir": d,
                          "moved": [[k, v[0], v[1]] for k, v in mm.items()],
                          "expect": summary(a, tip)})
        games.append({"n": n, "steps": steps})
    probe = os.path.join(tempfile.mkdtemp(), "parity.json")
    with open(probe, "w", encoding="utf-8") as f:
        json.dump(games, f)
    js = r"""
const B = require(process.argv[2]);
const games = JSON.parse(require('fs').readFileSync(process.argv[3], 'utf8'));
let checked = 0, bad = [];
const close = (x, y) => (x === null && y === undefined) || (x === undefined && y === null) ||
  (x === y) || (typeof x === 'number' && typeof y === 'number' && Math.abs(x - y) <= 1e-9 * Math.max(1, Math.abs(x)));
const same = (x, y) => JSON.stringify(x) === JSON.stringify(y);
const coach = new B.Coach();
for (const g of games) {
  g.steps.forEach((s, k) => {
    const a = new B.Analysis(s.board, g.n);
    let tip;
    if (k === 0) { coach.newGame(a); tip = coach.current; }
    else tip = coach.onMove(s.dir, new Map(s.moved.map(m => [m[0], [m[1], m[2]]])), a, false);
    const e = s.expect, why = [];
    for (let d = 0; d < 4; d++) {
      if (!close(e.values[d], a.values[d])) why.push('value ' + d + ' ' + e.values[d] + ' vs ' + a.values[d]);
      if (!close(e.safety[d], a.safety[d])) why.push('safety ' + d);
    }
    if (e.best !== a.best) why.push('best ' + e.best + ' vs ' + a.best);
    if (!close(e.survival, a.survival)) why.push('survival');
    if (!same(e.deadly, a.deadly)) why.push('deadly');
    if (e.corner !== a.corner) why.push('corner');
    if (e.harms.length !== a.harms.length || e.harms.some((h, i) => h[1] !== a.harms[i][1] || !close(h[0], a.harms[i][0]))) why.push('harms');
    if (e.problem !== a.problem()) why.push('problem');
    if (!same(e.stuck, Array.from(a.stuck).sort((x, y) => x - y))) why.push('stuck');
    if (e.safest !== a.safest()) why.push('safest');
    const jt = tip ? [tip.key, tip.params, tip.track] : null;
    if (!same(e.tip, jt)) why.push('tip ' + JSON.stringify(e.tip) + ' vs ' + JSON.stringify(jt));
    checked++;
    if (why.length) bad.push({ n: g.n, step: k, why });
  });
}
console.log(JSON.stringify({ checked, bad: bad.slice(0, 8), nbad: bad.length }));
"""
    jsf = os.path.join(os.path.dirname(probe), "parity.js")
    with open(jsf, "w", encoding="utf-8") as f:
        f.write(js)
    r = subprocess.run(["node", jsf, os.path.join(ROOT, "brain2049.js"), probe],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        print(r.stderr)
        sys.exit(1)
    res = json.loads(r.stdout)
    print("positions compared: %d   mismatches: %d" % (res["checked"], res["nbad"]))
    for b in res["bad"]:
        print("  ", b)
    sys.exit(1 if res["nbad"] else 0)


if __name__ == "__main__":
    main()
