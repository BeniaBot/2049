// Deep-referee half of the corner-tip calibration (see calib_corner.py).
//   node tools/calib_corner.js IN.jsonl [max_per_type] [seed]
// Prints, for each threshold the coach could use, how many tips it would
// give and how many of them the referee calls wrong.
"use strict";
const fs = require("fs");
const path = require("path");
const B = require(path.join(__dirname, "..", "brain2049.js"));
const R = require(path.join(__dirname, "referee.js"));

const inFile = process.argv[2];
const MAX = +(process.argv[3] || 120);
const cases = fs.readFileSync(inFile, "utf8").split(/\r?\n/).filter(Boolean).map(JSON.parse);

function spread(list, k, key) {        // k cases spread over the metric's range
  list.sort((a, b) => a[key] - b[key]);
  if (list.length <= k) return list;
  const out = [];
  for (let i = 0; i < k; i++) out.push(list[Math.floor(i * list.length / k)]);
  return out;
}

function judgeLost(c, seed) {
  const { b, n, played } = c;
  const unit = B.harmUnit(Math.max(...b));
  const legal = [0, 1, 2, 3].filter(d => B.move(b, n, d)[0] !== b);
  const keeps = legal.filter(d => d !== played && B.maxInCorner(B.move(b, n, d)[0], n));
  const empties = b.filter(x => x === 0).length;
  const dv = R.deepValues(b, n, n === 4 ? (empties <= 4 ? 5 : 4) : 3, 1e-5);
  const k = keeps.reduce((a, x) => (dv[x] > dv[a] ? x : a), keeps[0]);
  const runs = R.playouts(b, n, [played, k], 40, 40, 2, seed);
  const deepDiff = (dv[played] - dv[k]) / unit;          // >0: leaving was better
  const g = R.pairedGap(runs, played, k);
  const deepSays = deepDiff > 0.25, poSays = g.gap > 2 * g.se && g.gap > 0.05 * g.base;
  const keepDeep = -deepDiff > 0.25, gk = R.pairedGap(runs, k, played);
  const keepPo = gk.gap > 2 * gk.se && gk.gap > 0.05 * gk.base;
  return { wrong: deepSays && poSays, doubt: deepSays !== poSays && (deepSays || poSays),
           right: keepDeep && keepPo, deepDiff, po: g.gap };
}

function judgeGoal(c, seed) {
  const e = R.examine(c.b, c.n, c.rec, seed, 0.5);
  const objected = e.both.length > 0, one = e.objections.length > 0;
  return { wrong: objected, doubt: !objected && one, right: !one, regret: e.regret(c.rec) };
}

const out = { lost: [], goal: [] };
const t0 = Date.now();
for (const type of ["lost", "goal"]) {
  const key = type === "lost" ? "gain" : "cost";
  const sel = spread(cases.filter(c => c.type === type), MAX, key);
  sel.forEach((c, i) => {
    const v = type === "lost" ? judgeLost(c, 1000 + i) : judgeGoal(c, 2000 + i);
    out[type].push(Object.assign({ m: c[key] }, v));
  });
}

let report = "";
const TH = [-0.01, 0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0, 1.5];
report += "LOST (tip if gain >= t): t | tips | wrong | doubtful | keep clearly right\n";
for (const t of TH) {
  const s = out.lost.filter(x => x.m >= t);
  report += "  " + String(t).padStart(5) + " | " + String(s.length).padStart(4) + " | " +
    String(s.filter(x => x.wrong).length).padStart(5) + " | " + String(s.filter(x => x.doubt).length).padStart(8) +
    " | " + s.filter(x => x.right).length + "\n";
}
report += "GOAL (tip if cost <= t): t | tips | wrong | doubtful | ok\n";
for (const t of [0, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2, 99]) {
  const s = out.goal.filter(x => x.m <= t);
  report += "  " + String(t).padStart(5) + " | " + String(s.length).padStart(4) + " | " +
    String(s.filter(x => x.wrong).length).padStart(5) + " | " + String(s.filter(x => x.doubt).length).padStart(8) +
    " | " + s.filter(x => x.right).length + "\n";
}
report += "(" + ((Date.now() - t0) / 1000).toFixed(0) + " s)\n";
fs.writeFileSync(inFile.replace(/\.jsonl$/, "") + "_report.txt", report + "\n" + JSON.stringify(out), "utf8");
process.stdout.write(report);
