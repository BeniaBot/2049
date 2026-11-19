// The referee: judges every tip the coach gave in the simulated games
// (tools/review_tips.py writes them to events.jsonl) with two judges that
// are both far stronger than what the game can afford in real time:
//
//   1. a deep expectimax search (depth 4-5 instead of the game's 2, finer
//      probability cut-off), and
//   2. play-outs: the game is actually played on from each candidate move,
//      many times, by a depth-2 expectimax player, with the SAME random
//      spawns for every candidate (paired runs - a fair comparison).
//
// A tip is WRONG only when both judges agree it points the wrong way, and
// DOUBTFUL when only one of them does.
//
//   node tools/referee.js OUT_DIR/events.jsonl [OUT_DIR/verdicts.txt]
//
// What is asked, per tip:
//   * a recommended move (danger, trap, corner tips): is another move
//     clearly better?  Danger/trap: is it also among the safest?
//   * the moves a trap tip calls deadly: are they (5 rounds, exact)?
//   * "X would have kept it in the corner": was the move played clearly
//     better than X?
//   * praise: was the praised move itself a clear mistake?
//   * a stuck tile: does removing it really help, by a deeper search?
// and, for every move played with no warning on screen: was it a deadly
// move while a safe one existed?
"use strict";
const fs = require("fs");
const path = require("path");
const B = require(path.join(__dirname, "..", "brain2049.js"));

const DIRN = ["left", "right", "up", "down"];

// ---- judge 1: deep expectimax, independent of the game's own search -------
function deepValues(b, n, depth, cprob) {
  const tt = new Map();
  function chance(bb, d, prob) {
    if (d <= 0 || prob < cprob) return B.heuristic(bb, n);
    const key = bb.join(",") + "|" + d;
    const hit = tt.get(key);
    if (hit !== undefined) return hit;
    const cells = [];
    for (let i = 0; i < bb.length; i++) if (bb[i] === 0) cells.push(i);
    if (!cells.length) return B.heuristic(bb, n);
    const pc = prob / cells.length, lst = bb.slice();
    let total = 0;
    for (const i of cells) {
      lst[i] = 1; total += 0.9 * best(lst.slice(), d, pc * 0.9);
      lst[i] = 2; total += 0.1 * best(lst.slice(), d, pc * 0.1);
      lst[i] = 0;
    }
    const v = total / cells.length;
    tt.set(key, v);
    return v;
  }
  function best(bb, d, prob) {
    let top = null;
    for (let k = 0; k < 4; k++) {
      const nb = B.move(bb, n, k)[0];
      if (nb === bb) continue;
      const v = chance(nb, d - 1, prob);
      if (top === null || v > top) top = v;
    }
    return top === null ? 0 : top;
  }
  const out = {};
  for (let k = 0; k < 4; k++) {
    const nb = B.move(b, n, k)[0];
    if (nb === b) continue;
    out[k] = chance(nb, depth, 1.0);
  }
  return out;
}

// ---- judge 2: play-outs ------------------------------------------------------
function rng(seed) {
  let s = (seed >>> 0) || 1;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}
function spawn(b, r) {
  const cells = [];
  for (let i = 0; i < b.length; i++) if (b[i] === 0) cells.push(i);
  if (!cells.length) return b;
  const nb = b.slice();
  nb[cells[Math.floor(r() * cells.length)]] = r() < 0.9 ? 1 : 2;
  return nb;
}
// points gained in the next L moves; a lost game costs what the rest of
// the run would roughly have earned, and then some
function playout(b, n, first, L, depth, r) {
  let [nb, score] = B.move(b, n, first);
  nb = spawn(nb, r);
  for (let t = 1; t < L; t++) {
    const vals = B.moveValues(nb, n, depth);
    let d = null;
    for (let k = 0; k < 4; k++) if (vals[k] !== undefined && (d === null || vals[k] > vals[d])) d = k;
    if (d === null) return score - (L - t + 10) * 2 * (1 << Math.max(...b)) / 8;
    const res = B.move(nb, n, d);
    score += res[1];
    nb = spawn(res[0], r);
  }
  return B.canMove(nb, n) ? score : score - 10 * 2 * (1 << Math.max(...b)) / 8;
}
// paired: run i uses the same random stream for every candidate move
function playouts(b, n, moves, L, R, depth, seed) {
  const runs = {};
  for (const k of moves) {
    runs[k] = [];
    for (let i = 0; i < R; i++) runs[k].push(playout(b, n, k, L, depth, rng(seed * 100003 + i)));
  }
  return runs;
}
function mean(a) { return a.reduce((x, y) => x + y, 0) / a.length; }
function pairedGap(runs, x, y) {        // how much better x did than y, and its SE
  const d = runs[x].map((v, i) => v - runs[y][i]);
  const m = mean(d), sd = Math.sqrt(d.reduce((s, v) => s + (v - m) * (v - m), 0) / Math.max(1, d.length - 1));
  return { gap: m, se: sd / Math.sqrt(d.length), base: Math.abs(mean(runs[y])) + 1 };
}

// ---- comparing a move against the others -------------------------------------
const DEEP_T = 0.5;      // deep regret above this (harm units) = judge 1 objects
function examine(b, n, rec, seed, deepT) {
  deepT = deepT === undefined ? DEEP_T : deepT;
  const mx = Math.max(...b), unit = B.harmUnit(mx);
  const empties = b.filter(x => x === 0).length;
  const depth = n === 4 ? (empties <= 4 ? 5 : 4) : 3;
  const dv = deepValues(b, n, depth, 1e-5);
  const legal = Object.keys(dv).map(Number);
  const deepBest = legal.reduce((a, c) => (dv[c] > dv[a] ? c : a), legal[0]);
  const regret = d => (dv[deepBest] - dv[d]) / unit;
  // play-outs for every legal move: depth-2 player, 40 runs of 40 moves
  const runs = playouts(b, n, legal, 40, 40, 2, seed);
  const poBest = legal.reduce((a, c) => (mean(runs[c]) > mean(runs[a]) ? c : a), legal[0]);
  const objections = [];
  for (const x of legal) {
    if (x === rec) continue;
    const deepSays = (dv[x] - dv[rec]) / unit > deepT;
    const g = pairedGap(runs, x, rec);
    const poSays = g.gap > 2 * g.se && g.gap > 0.05 * g.base;
    if (deepSays || poSays) objections.push({ x, deepSays, poSays, g });
  }
  const both = objections.filter(o => o.deepSays && o.poSays);
  return { depth, dv, legal, deepBest, poBest, regret, runs, objections, both, unit };
}
function describe(e) {
  return e.legal.map(d => DIRN[d] + ": deep regret " + e.regret(d).toFixed(2) +
    ", play-outs " + mean(e.runs[d]).toFixed(0)).join(" | ");
}
function verdictOf(e) {
  if (e.both.length) return "WRONG";
  if (e.objections.length) return "DOUBTFUL";
  return "OK";
}

function judgeTip(ev) {
  const { b: pb, n } = B.toRanks(ev.before), { b: nb } = B.toRanks(ev.now);
  const k = ev.key, P = ev.params || {};
  const notes = [];
  let verdict = "OK";
  const worse = v => { if (v === "WRONG" || (v === "DOUBTFUL" && verdict === "OK")) verdict = v; };
  // the moves that put the biggest tile into a corner, best first (deep)
  const intoCorner = (b, except) => {
    const ds = [0, 1, 2, 3].filter(d => d !== except && B.move(b, n, d)[0] !== b &&
                                        B.maxInCorner(B.move(b, n, d)[0], n));
    if (ds.length < 2) return ds;
    const dv = deepValues(b, n, 3, 1e-4);
    return ds.sort((x, y) => dv[y] - dv[x]);
  };
  if (k === "tip_corner_goal" || k === "tip_corner_made" || (k === "tip_corner_lost" && P.dir === undefined)) {
    // general corner tips (0.18.1+) name no move; they claim a situation.
    if (k === "tip_corner_goal") {
      // "you can get it back now": the best way back is not clearly worse
      // than the best move on the board
      const ways = intoCorner(nb);
      if (!ways.length) { worse("WRONG"); notes.push("no move puts it into a corner"); }
      else {
        const e = examine(nb, n, ways[0], ev.id);
        const v = verdictOf(e);
        worse(v);
        notes.push("best way back " + DIRN[ways[0]] + ": " + v + "  (deep best " + DIRN[e.deepBest] +
                   ", play-outs best " + DIRN[e.poBest] + ")\n      " + describe(e));
      }
    } else {
      // "it left its corner - try to keep it there": leaving must not have
      // been clearly better than the best move that kept it
      const keep = intoCorner(pb, ev.played);
      const e = examine(pb, n, keep[0], ev.id, 0.25);
      const o = e.objections.find(o => o.x === ev.played);
      const v = !o ? "OK" : (o.deepSays && o.poSays ? "WRONG" : "DOUBTFUL");
      worse(v);
      notes.push("played " + DIRN[ev.played] + " vs keeping " + DIRN[keep[0]] + ": " + v +
                 "\n      " + describe(e));
    }
  } else if (k === "tip_danger" || k === "tip_trap" || k === "tip_corner_back" || k === "tip_corner_goal") {
    const e = examine(nb, n, P.dir, ev.id);
    let v = verdictOf(e);
    if (k === "tip_danger" || k === "tip_trap") {
      if (nb.filter(x => x === 0).length <= 5) {
        const sv = B.moveSurvival(nb, n, 5);
        const top = Math.max(...e.legal.map(d => sv[d]));
        notes.push("survival over 5 rounds: " + e.legal.map(d => DIRN[d] + " " + (sv[d] * 100).toFixed(0) + "%").join(", "));
        if (sv[P.dir] < top - 0.03) v = "WRONG";
        else if (v === "WRONG") v = "DOUBTFUL";   // the safest move may cost points: fine here
        if (k === "tip_trap") for (const bad of P.bad) {
          if (sv[bad] >= 0.5) { v = "WRONG"; notes.push("  but " + DIRN[bad] + " is not deadly"); }
        }
      }
    }
    worse(v);
    notes.push("recommends " + DIRN[P.dir] + ": " + v + "  (deep best " + DIRN[e.deepBest] +
               ", play-outs best " + DIRN[e.poBest] + ")\n      " + describe(e));
  } else if (k === "tip_corner_lost") {
    // "X would have kept it there": the move played must not be clearly better
    const e = examine(pb, n, P.dir, ev.id, 0.25);
    const o = e.objections.find(o => o.x === ev.played);
    const v = !o ? "OK" : (o.deepSays && o.poSays ? "WRONG" : "DOUBTFUL");
    worse(v);
    notes.push("says " + DIRN[P.dir] + " instead of the played " + DIRN[ev.played] + ": " + v +
               "\n      " + describe(e));
  } else if (k.startsWith("tip_good_")) {
    // praise must not reward a clear mistake
    const e = examine(pb, n, ev.played, ev.id, 1.0);
    const v = verdictOf(e);
    worse(v);
    notes.push("praised move " + DIRN[ev.played] + ": " + v + "\n      " + describe(e));
  } else if (k.startsWith("tip_stuck_")) {
    const cell = ev.track, unit = B.harmUnit(Math.max(...nb));
    const base = B.positionValue(nb, n, 2);
    const lst = nb.slice(); lst[cell] = 0;
    const harm = (B.positionValue(lst, n, 2) - base) / unit;
    const v = harm >= 0.5 ? "OK" : harm >= 0.25 ? "DOUBTFUL" : "WRONG";
    worse(v);
    notes.push("tile " + (1 << nb[cell]) + " at " + cell + ": deeper harm " + harm.toFixed(2) + " units: " + v);
  } else {
    notes.push("(not judged)");
  }
  return { verdict, notes };
}

function missedWarning(ev) {
  const { b: pb, n } = B.toRanks(ev.before);
  if (pb.filter(x => x === 0).length > 3) return null;
  const sv = B.moveSurvival(pb, n, 5);
  const legal = [0, 1, 2, 3].filter(d => sv[d] !== undefined);
  const top = Math.max(...legal.map(d => sv[d]));
  if (sv[ev.played] < 0.5 && top >= 0.8) return { sv, top };
  return null;
}

module.exports = { deepValues, playouts, pairedGap, mean, examine, DIRN };
if (require.main !== module) return;

// ---- main ------------------------------------------------------------------
const inFile = process.argv[2];
const outFile = process.argv[3] || path.join(path.dirname(inFile), "verdicts.txt");
const lines = fs.readFileSync(inFile, "utf8").split(/\r?\n/).filter(Boolean);
const out = [], tally = {};
let missed = 0, quiet = 0;
const grid = g => g.map(r => "      " + r.map(x => String(x || ".").padStart(5)).join("")).join("\n");
for (const line of lines) {
  const ev = JSON.parse(line);
  if (ev.type === "tip") {
    const t0 = Date.now();
    const v = judgeTip(ev);
    const t = tally[ev.key] || (tally[ev.key] = { OK: 0, DOUBTFUL: 0, WRONG: 0 });
    t[v.verdict]++;
    out.push("#" + ev.id + " game " + ev.game + " move " + ev.move + " played " + DIRN[ev.played] +
             "  " + ev.key + " " + JSON.stringify(ev.params) + "  -> " + v.verdict +
             "  (" + (Date.now() - t0) + " ms)\n    text: " + ev.text + "\n    " +
             v.notes.join("\n    ") + "\n    before:\n" + grid(ev.before) + "\n    now:\n" + grid(ev.now));
  } else if (ev.type === "quiet") {
    quiet++;
    const m = missedWarning(ev);
    if (m) {
      missed++;
      out.push("MISSED game " + ev.game + " move " + ev.move + ": played " + DIRN[ev.played] +
               " (survival " + (m.sv[ev.played] * 100).toFixed(0) + "%) while the best had " +
               (m.top * 100).toFixed(0) + "%, no warning on screen\n" + grid(ev.before));
    }
  }
}
let summary = "\n=== summary\n", ok = 0, doubt = 0, all = 0;
for (const [k, t] of Object.entries(tally)) {
  summary += k.padEnd(18) + " ok " + t.OK + "  doubtful " + t.DOUBTFUL + "  wrong " + t.WRONG + "\n";
  ok += t.OK; doubt += t.DOUBTFUL; all += t.OK + t.DOUBTFUL + t.WRONG;
}
summary += "tips judged: " + all + ", ok " + ok + ", doubtful " + doubt + ", wrong " + (all - ok - doubt) +
           " (right " + (all ? (100 * ok / all).toFixed(1) : "-") + "%, not wrong " +
           (all ? (100 * (ok + doubt) / all).toFixed(1) : "-") + "%)\n";
summary += "moves with no warning on screen: " + quiet + ", deadly ones among them: " + missed + "\n";
fs.writeFileSync(outFile, out.join("\n\n") + "\n" + summary, "utf8");
process.stdout.write(summary);
