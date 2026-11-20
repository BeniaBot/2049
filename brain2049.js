/*
 * brain2049.js - the thinking engine of 2049, for the browser.
 *
 * A faithful port of brain2049.py (same weights, same search, same
 * thresholds, same tie-breaking), checked against it on thousands of
 * positions by tools/parity_check.py. Works in a page (window.Brain2049)
 * and in Node (module.exports).
 *
 * Board = flat array of ranks (0 = empty, k = tile 2**k), row-major.
 */
(function (root) {
  "use strict";

  var LEFT = 0, RIGHT = 1, UP = 2, DOWN = 3;
  var DIRS = [LEFT, RIGHT, UP, DOWN];
  var DIR_NAMES = ["left", "right", "up", "down"];

  var LOST_PENALTY = 200000.0, MONO_W = 47.0, SUM_W = 11.0,
      MERGE_W = 700.0, EMPTY_W = 270.0;
  var PROB_FOUR = 0.1, CPROB = 1e-4;

  var SUMP = [], MONOP = [];
  for (var r0 = 0; r0 < 32; r0++) {
    SUMP.push(r0 * r0 * r0 * Math.sqrt(r0));
    MONOP.push(r0 * r0 * r0 * r0);
  }

  var SLIDE = new Map(), HEUR = new Map(), CACHE_LIMIT = 400000;

  function lineKey(line) {             // ranks < 32, length <= 6 -> exact
    var k = 0;
    for (var i = line.length - 1; i >= 0; i--) k = k * 32 + line[i];
    return k * 8 + line.length;
  }
  function boardKey(b) { return String.fromCharCode.apply(null, b); }
  function trimCaches() {
    if (SLIDE.size > CACHE_LIMIT) SLIDE.clear();
    if (HEUR.size > CACHE_LIMIT) HEUR.clear();
  }

  // ---- conversions -------------------------------------------------------
  function toRanks(grid) {
    var out = [];
    for (var r = 0; r < grid.length; r++)
      for (var c = 0; c < grid[r].length; c++) {
        var v = grid[r][c];
        out.push(v ? Math.round(Math.log2(v)) : 0);
      }
    return { b: out, n: grid.length };
  }
  function toGrid(b, n) {
    var g = [];
    for (var r = 0; r < n; r++) {
      var row = [];
      for (var c = 0; c < n; c++) { var x = b[r * n + c]; row.push(x ? Math.pow(2, x) : 0); }
      g.push(row);
    }
    return g;
  }

  // ---- moves ---------------------------------------------------------------
  function slide(line) {
    var key = lineKey(line);
    var res = SLIDE.get(key);
    if (res === undefined) {
      var vals = [], i;
      for (i = 0; i < line.length; i++) if (line[i]) vals.push(line[i]);
      var out = [], gain = 0;
      i = 0;
      while (i < vals.length) {
        if (i + 1 < vals.length && vals[i] === vals[i + 1]) {
          out.push(vals[i] + 1); gain += Math.pow(2, vals[i] + 1); i += 2;
        } else { out.push(vals[i]); i += 1; }
      }
      while (out.length < line.length) out.push(0);
      res = [out, gain];
      SLIDE.set(key, res);
    }
    return res;
  }

  /* -> [newBoard, gain]; newBoard === b (same object) when nothing moves */
  function move(b, n, d) {
    var out = new Array(n * n), gain = 0, r, c, k, line, res, nl;
    if (d === LEFT || d === RIGHT) {
      for (r = 0; r < n; r++) {
        line = b.slice(r * n, (r + 1) * n);
        if (d === RIGHT) line.reverse();
        res = slide(line); nl = res[0]; gain += res[1];
        for (k = 0; k < n; k++) out[r * n + (d === LEFT ? k : n - 1 - k)] = nl[k];
      }
    } else {
      for (c = 0; c < n; c++) {
        line = [];
        for (r = 0; r < n; r++) line.push(b[r * n + c]);
        if (d === DOWN) line.reverse();
        res = slide(line); nl = res[0]; gain += res[1];
        for (k = 0; k < n; k++) out[(d === UP ? k : n - 1 - k) * n + c] = nl[k];
      }
    }
    for (k = 0; k < out.length; k++) if (out[k] !== b[k]) return [out, gain];
    return [b, 0];
  }

  function legalMoves(b, n) {
    var out = [];
    for (var i = 0; i < 4; i++) if (move(b, n, DIRS[i])[0] !== b) out.push(DIRS[i]);
    return out;
  }
  function countZero(b) { var z = 0; for (var i = 0; i < b.length; i++) if (b[i] === 0) z++; return z; }
  function canMove(b, n) {
    if (countZero(b)) return true;
    for (var r = 0; r < n; r++) for (var c = 0; c < n; c++) {
      var v = b[r * n + c];
      if (c + 1 < n && b[r * n + c + 1] === v) return true;
      if (r + 1 < n && b[(r + 1) * n + c] === v) return true;
    }
    return false;
  }
  function maxOf(b) { var m = 0; for (var i = 0; i < b.length; i++) if (b[i] > m) m = b[i]; return m; }

  // ---- evaluation ----------------------------------------------------------
  function lineHeur(line) {
    var key = lineKey(line);
    var h = HEUR.get(key);
    if (h === undefined) {
      var s = 0.0, empty = 0, merges = 0, prev = 0, counter = 0, i;
      for (i = 0; i < line.length; i++) {
        var rank = line[i];
        s += SUMP[rank];
        if (rank === 0) empty += 1;
        else {
          if (prev === rank) counter += 1;
          else if (counter > 0) { merges += 1 + counter; counter = 0; }
          prev = rank;
        }
      }
      if (counter > 0) merges += 1 + counter;
      var ml = 0.0, mr = 0.0;
      for (i = 1; i < line.length; i++) {
        var a = line[i - 1], c = line[i];
        if (a > c) ml += MONOP[a] - MONOP[c];
        else mr += MONOP[c] - MONOP[a];
      }
      h = LOST_PENALTY + EMPTY_W * empty + MERGE_W * merges
          - MONO_W * Math.min(ml, mr) - SUM_W * s;
      HEUR.set(key, h);
    }
    return h;
  }
  function heuristic(b, n) {
    var h = 0.0, r, c, line;
    for (r = 0; r < n; r++) h += lineHeur(b.slice(r * n, (r + 1) * n));
    for (c = 0; c < n; c++) {
      line = [];
      for (r = 0; r < n; r++) line.push(b[r * n + c]);
      h += lineHeur(line);
    }
    return h;
  }

  // ---- expectimax ------------------------------------------------------------
  function Search(n) { this.n = n; this.tt = new Map(); this.nodes = 0; }
  Search.prototype.chance = function (b, depth, prob) {
    var n = this.n;
    if (depth <= 0 || prob < CPROB) { this.nodes++; return heuristic(b, n); }
    var key = boardKey(b) + "|" + depth;
    var v = this.tt.get(key);
    if (v !== undefined) return v;
    var cells = [], i;
    for (i = 0; i < b.length; i++) if (b[i] === 0) cells.push(i);
    if (!cells.length) { this.nodes++; return heuristic(b, n); }
    var k = cells.length, pCell = prob / k, total = 0.0, lst = b.slice();
    for (var j = 0; j < cells.length; j++) {
      i = cells[j];
      lst[i] = 1;
      total += (1 - PROB_FOUR) * this.best(lst.slice(), depth, pCell * (1 - PROB_FOUR));
      lst[i] = 2;
      total += PROB_FOUR * this.best(lst.slice(), depth, pCell * PROB_FOUR);
      lst[i] = 0;
    }
    v = total / k;
    this.tt.set(key, v);
    return v;
  };
  Search.prototype.best = function (b, depth, prob) {
    var n = this.n, best = null;
    for (var i = 0; i < 4; i++) {
      var nb = move(b, n, DIRS[i])[0];
      if (nb === b) continue;
      var v = this.chance(nb, depth - 1, prob);
      if (best === null || v > best) best = v;
    }
    return best === null ? 0.0 : best;
  };

  function pickDepth(b, n) {
    var e = countZero(b);
    if (n <= 4) return 2;
    if (n === 5) return e <= 10 ? 2 : 1;
    return e <= 6 ? 2 : 1;
  }

  /* -> array indexed by direction; undefined for illegal moves */
  function moveValues(b, n, depth) {
    trimCaches();
    if (depth === undefined || depth === null) depth = pickDepth(b, n);
    var s = new Search(n), out = [undefined, undefined, undefined, undefined];
    for (var i = 0; i < 4; i++) {
      var d = DIRS[i], nb = move(b, n, d)[0];
      if (nb === b) continue;
      out[d] = s.chance(nb, depth, 1.0);
    }
    return out;
  }
  function argmaxDir(vals) {           // first max in DIRS order, like Python
    var best = null;
    for (var i = 0; i < 4; i++) {
      var d = DIRS[i];
      if (vals[d] === undefined) continue;
      if (best === null || vals[d] > vals[best]) best = d;
    }
    return best;
  }
  function bestMove(b, n, depth) { return argmaxDir(moveValues(b, n, depth)); }
  function positionValue(b, n, depth) {
    trimCaches();
    if (depth === undefined) depth = 1;
    return new Search(n).best(b, depth + 1, 1.0);
  }

  // ---- survival odds -----------------------------------------------------------
  function survival(b, n, horizon) {
    if (countZero(b) > horizon) return 1.0;
    var tt = new Map();
    function best(bb, h) {
      if (h === 0) return canMove(bb, n) ? 1.0 : 0.0;
      var top = 0.0;
      for (var i = 0; i < 4; i++) {
        var nb = move(bb, n, DIRS[i])[0];
        if (nb === bb) continue;
        var v = chance(nb, h);
        if (v > top) { top = v; if (top >= 1.0) break; }
      }
      return top;
    }
    function chance(bb, h) {
      var key = boardKey(bb) + "|" + h;
      var v = tt.get(key);
      if (v !== undefined) return v;
      var cells = [], i;
      for (i = 0; i < bb.length; i++) if (bb[i] === 0) cells.push(i);
      if (!cells.length || cells.length > h) { tt.set(key, 1.0); return 1.0; }
      var lst = bb.slice(), total = 0.0;
      for (var j = 0; j < cells.length; j++) {
        i = cells[j];
        lst[i] = 1; total += (1 - PROB_FOUR) * best(lst.slice(), h - 1);
        lst[i] = 2; total += PROB_FOUR * best(lst.slice(), h - 1);
        lst[i] = 0;
      }
      v = total / cells.length;
      tt.set(key, v);
      return v;
    }
    return best(b, horizon);
  }
  function moveSurvival(b, n, horizon) {
    var out = [undefined, undefined, undefined, undefined];
    for (var i = 0; i < 4; i++) {
      var d = DIRS[i], nb = move(b, n, d)[0];
      if (nb === b) continue;
      if (countZero(nb) > horizon) { out[d] = 1.0; continue; }
      var cells = [], k;
      for (k = 0; k < nb.length; k++) if (nb[k] === 0) cells.push(k);
      var lst = nb.slice(), total = 0.0;
      for (var j = 0; j < cells.length; j++) {
        k = cells[j];
        lst[k] = 1; total += (1 - PROB_FOUR) * survival(lst.slice(), n, horizon - 1);
        lst[k] = 2; total += PROB_FOUR * survival(lst.slice(), n, horizon - 1);
        lst[k] = 0;
      }
      out[d] = cells.length ? total / cells.length : 1.0;
    }
    return out;
  }

  // ---- tile harm -------------------------------------------------------------------
  function harmUnit(maxRank) {
    if (maxRank < 2) return MONO_W;
    return MONO_W * (MONOP[maxRank] - MONOP[maxRank - 1]);
  }
  function tileHarms(b, n, depth, minRatio) {
    if (depth === undefined) depth = 1;
    if (minRatio === undefined) minRatio = 4;
    var mx = maxOf(b);
    if (mx < 3) return [];
    var base = positionValue(b, n, depth), out = [], lst = b.slice();
    for (var i = 0; i < b.length; i++) {
      var r = b[i];
      if (r === 0 || Math.pow(2, r) * minRatio > Math.pow(2, mx)) continue;
      lst[i] = 0;
      var v = positionValue(lst.slice(), n, depth);
      lst[i] = r;
      out.push([v - base, i]);
    }
    out.sort(function (x, y) { return (y[0] - x[0]) || (y[1] - x[1]); });
    return out;
  }

  // ---- structure ---------------------------------------------------------------------
  function corners(n) { return [0, n - 1, n * (n - 1), n * n - 1]; }
  function neighbours(i, n) {
    var r = Math.floor(i / n), c = i % n, out = [];
    if (r > 0) out.push(i - n);
    if (r < n - 1) out.push(i + n);
    if (c > 0) out.push(i - 1);
    if (c < n - 1) out.push(i + 1);
    return out;
  }
  function maxInCorner(b, n) {
    var mx = maxOf(b), cs = corners(n);
    for (var i = 0; i < 4; i++) if (b[cs[i]] === mx) return true;
    return false;
  }
  function edgeLines(ci, n) {
    var r = Math.floor(ci / n), c = ci % n;
    var dc = c === 0 ? 1 : -1, dr = r === 0 ? 1 : -1, row = [], col = [];
    for (var k = 0; k < n; k++) { row.push(r * n + (c + k * dc)); col.push((r + k * dr) * n + c); }
    return [row, col];
  }
  function chainBreaker(b, n, i) {
    var v = b[i], mx = maxOf(b);
    if (v === 0 || v >= mx) return false;
    var cs = corners(n);
    for (var q = 0; q < 4; q++) {
      var ci = cs[q];
      if (i === ci) {
        var nb = neighbours(i, n);
        for (var j = 0; j < nb.length; j++) if (b[nb[j]] === mx) return true;
      }
      if (b[ci] !== mx) continue;
      var lines = edgeLines(ci, n);
      for (var L = 0; L < 2; L++) {
        var line = lines[L], k = line.indexOf(i);
        if (k > 0 && k < n - 1 && b[line[k - 1]] > v && b[line[k + 1]] > v) return true;
      }
    }
    return false;
  }
  /* = brain2049.stuck_kind: ["block"|"chain"|"corner", bigRank] or null */
  function bigTilesScattered(b, n) {      // = Python big_tiles_scattered
    var mx = maxOf(b);
    if (mx < 6 || !maxInCorner(b, n)) return false;
    var big = [];
    for (var i = 0; i < b.length; i++) if (b[i] >= mx - 2) big.push(i);
    if (big.length < 2) return false;
    return big.some(function (c) {
      return !neighbours(c, n).some(function (j) { return big.indexOf(j) >= 0; });
    });
  }
  function stuckKind(b, n, i) {
    var v = b[i];
    if (v === 0) return null;
    var r = Math.floor(i / n), c = i % n, k, j, lines = [[], []];
    for (k = 0; k < n; k++) { lines[0].push(r * n + k); lines[1].push(k * n + c); }
    for (var L = 0; L < 2; L++) {
      var line = lines[L], pos = line.indexOf(i), left = 0, right = 0;
      for (j = pos - 1; j >= 0; j--) if (b[line[j]]) { left = b[line[j]]; break; }
      for (j = pos + 1; j < n; j++) if (b[line[j]]) { right = b[line[j]]; break; }
      if (left && left === right && left >= v + 2 && left >= 5) return ["block", left];
    }
    var mx = maxOf(b);
    if (v >= mx || mx < 6) return null;
    var cs = corners(n), inCorner = false, q;
    for (q = 0; q < 4; q++) if (b[cs[q]] === mx) inCorner = true;
    for (q = 0; q < 4; q++) {
      var ci = cs[q];
      if (b[ci] !== mx) continue;
      var el = edgeLines(ci, n);
      for (var e = 0; e < 2; e++) {
        var ln = el[e], kk = ln.indexOf(i);
        if (kk > 0 && kk < n - 1 && b[ln[kk - 1]] > v && b[ln[kk + 1]] > v) return ["chain", mx];
      }
    }
    if (!inCorner && cs.indexOf(i) >= 0) {
      var nb = neighbours(i, n), nextToMax = false;
      for (j = 0; j < nb.length; j++) if (b[nb[j]] === mx) nextToMax = true;
      if (nextToMax) {
        // only with ONE top tile (see brain2049.py)
        var tops = 0;
        for (var t = 0; t < n * n; t++) if (b[t] === mx) tops++;
        if (tops === 1) return ["corner", mx];
      }
    }
    return null;
  }
  var STUCK_ORDER = { block: 0, chain: 1, corner: 2 };

  /* = Python compose_moves: Maps from -> [to, merged] */
  function composeMoves(first, then) {
    var out = new Map(), mids = new Set();
    first.forEach(function (v) { mids.add(v[0]); });
    first.forEach(function (v, cell) {
      var t = then.has(v[0]) ? then.get(v[0]) : [v[0], false];
      out.set(cell, [t[0], v[1] || t[1]]);
    });
    then.forEach(function (v, cell) {
      if (!out.has(cell) && !mids.has(cell)) out.set(cell, v);
    });
    return out;
  }
  function placeOf(i, n) {
    var r = Math.floor(i / n), c = i % n;
    var top = r === 0, bottom = r === n - 1, left = c === 0, right = c === n - 1;
    if (top && left) return "corner_tl";
    if (top && right) return "corner_tr";
    if (bottom && left) return "corner_bl";
    if (bottom && right) return "corner_br";
    if (top) return "edge_top";
    if (bottom) return "edge_bottom";
    if (left) return "edge_left";
    if (right) return "edge_right";
    return "middle";
  }

  // ---- spawn choice (hidden assist) ----------------------------------------------------
  function bestSpawn(b, n, ranks, cells, shortlist) {
    if (!ranks) ranks = [1, 2];
    if (shortlist === undefined) shortlist = 8;
    var i;
    if (!cells) { cells = []; for (i = 0; i < b.length; i++) if (b[i] === 0) cells.push(i); }
    if (!cells.length) return null;
    var lst = b.slice(), rough = [];
    for (var a = 0; a < cells.length; a++) {
      i = cells[a];
      for (var q = 0; q < ranks.length; q++) {
        var r = ranks[q];
        lst[i] = r;
        var nb = lst.slice(), top = null;
        for (var t = 0; t < 4; t++) {
          var mb = move(nb, n, DIRS[t])[0];
          if (mb === nb) continue;
          var h = heuristic(mb, n);
          if (top === null || h > top) top = h;
        }
        rough.push([top === null ? -1e18 : top, i, r]);
        lst[i] = 0;
      }
    }
    // Python: rough.sort(reverse=True) on (score, cell, rank) tuples
    rough.sort(function (x, y) { return (y[0] - x[0]) || (y[1] - x[1]) || (y[2] - x[2]); });
    var best = null;
    for (var s = 0; s < Math.min(shortlist, rough.length); s++) {
      i = rough[s][1]; var rr = rough[s][2];
      lst[i] = rr;
      var v = positionValue(lst.slice(), n, 1);
      lst[i] = 0;
      if (best === null || v > best[0]) best = [v, i, rr];
    }
    return [best[1], best[2]];
  }

  // ---- analysis ------------------------------------------------------------------------
  var DANGER_ENTER = 0.85, DANGER_EXIT = 0.97, HORIZON = 3, TRAP_T = 0.5,
      CHEAT_T = 0.25, CHAIN_T = 0.5, STUCK_T = 1.2;

  function round6(x) { return Math.round(x * 1e6) / 1e6; }

  function Analysis(b, n, withHarms) {
    if (withHarms === undefined) withHarms = true;
    var d, i;
    this.b = b; this.n = n;
    this.maxRank = maxOf(b);
    this.empties = countZero(b);
    this.unit = harmUnit(this.maxRank);
    this.values = moveValues(b, n);
    this.legal = DIRS.filter(function (x) { return this.values[x] !== undefined; }, this);
    this.best = argmaxDir(this.values);
    if (this.legal.length && this.empties <= HORIZON) {
      this.safety = moveSurvival(b, n, HORIZON);
      this.survival = Math.max.apply(null, this.legal.map(function (x) { return this.safety[x]; }, this));
    } else {
      this.safety = [undefined, undefined, undefined, undefined];
      for (i = 0; i < this.legal.length; i++) this.safety[this.legal[i]] = 1.0;
      this.survival = this.legal.length ? 1.0 : 0.0;
    }
    this.deadly = [];
    for (i = 0; i < this.legal.length; i++) {
      d = this.legal[i];
      if (this.safety[d] < TRAP_T && this.survival >= TRAP_T) this.deadly.push(d);
    }
    this.deadly.sort(function (x, y) { return x - y; });
    this.corner = maxInCorner(b, n);
    this.harms = [];
    if (withHarms) {
      var hs = tileHarms(b, n, 1), u = this.unit;
      this.harms = hs.map(function (p) { return [p[0] / u, p[1]]; });
    }
    this.harmAt = new Map();
    this.problems = new Set();
    this.stuck = new Set();
    this.stuckInfo = new Map();
    var low = this.maxRank - 3;
    for (i = 0; i < this.harms.length; i++) {
      var h = this.harms[i][0], cell = this.harms[i][1];
      this.harmAt.set(cell, h);
      if (h >= CHEAT_T) this.problems.add(cell);
      if (h < CHAIN_T) continue;
      var kind = stuckKind(b, n, cell);
      if (kind === null) continue;
      if (kind[0] !== "block" && b[cell] > low) continue;
      this.stuckInfo.set(cell, kind);
      this.stuck.add(cell);
    }
  }
  Analysis.ofGrid = function (grid, withHarms) {
    var t = toRanks(grid);
    return new Analysis(t.b, t.n, withHarms);
  };
  Analysis.prototype.problem = function () {
    if (this.harms.length && this.harms[0][0] >= CHEAT_T) return this.harms[0][1];
    return null;
  };
  Analysis.prototype.safest = function () {
    var best = null, self = this;
    this.legal.forEach(function (d) {
      if (best === null) { best = d; return; }
      var a = round6(self.safety[d]), b0 = round6(self.safety[best]);
      if (a > b0 || (a === b0 && self.values[d] > self.values[best])) best = d;
    });
    return best;
  };
  Analysis.prototype.regret = function (d) {
    if (this.values[d] === undefined || this.best === null) return 0.0;
    return (this.values[this.best] - this.values[d]) / this.unit;
  };
  Analysis.prototype.keepsCorner = function (d) {
    var nb = move(this.b, this.n, d)[0];
    return nb !== this.b && maxInCorner(nb, this.n);
  };
  Analysis.prototype.hasValue = function (d) { return this.values[d] !== undefined; };
  Analysis.prototype.bringsMaxToCorner = function (d) {   // = Python brings_max_to_corner
    var nb = move(this.b, this.n, d)[0], mx = this.maxRank;
    if (nb === this.b || maxOf(nb) !== mx) return false;
    var cb = 0, cn = 0;
    for (var i = 0; i < nb.length; i++) { if (this.b[i] === mx) cb++; if (nb[i] === mx) cn++; }
    return cb === cn && maxInCorner(nb, this.n);
  };

  // ---- coach ------------------------------------------------------------------------
  var PRIO_OPEN = 0, PRIO_PRAISE = 1, PRIO_HINT = 2, PRIO_CORNER = 3,
      PRIO_STUCK = 4, PRIO_DANGER = 5;
  var COOLDOWN = {
    stuck: 8, tip_corner_lost: 6, tip_corner_made: 6, tip_corner_goal: 20,
    tip_good_escape: 10, tip_good_freed: 6, tip_good_corner: 20,
    tip_good_record: 0, tip_danger: 0, tip_hint_order: 40, tip_hint_dirs: 40, tip_early: 12
  };
  var SCATTER_MOVES = 3, DIRS_WINDOW = 12, DIRS_EACH = 2, GOAL_RANK = 5, OPEN_KEEP = 0.7;   // see brain2049.py
  var OPEN_TIPS = ["tip_open", "tip_open_order", "tip_open_dirs", "tip_open_row", "tip_open_small"];
  var EARLY_MOVES = 60;   // see brain2049.py
  var GAP = 5, URGENT = ["tip_danger", "tip_trap", "tip_good_record"];   // pacing: see brain2049.py
  var RECORD_RANK = 8, OFF_CORNER_MOVES = 4;
  var LOST_MARGIN = 0.25, GOAL_REGRET = 0.15;   // measured - see brain2049.py
  var STUCK_KEYS = ["tip_stuck_block", "tip_stuck_chain", "tip_stuck_corner"];
  function isStuckKey(k) { return STUCK_KEYS.indexOf(k) >= 0; }

  function Tip(key, prio, born, params, opts) {
    opts = opts || {};
    this.key = key; this.prio = prio; this.born = born; this.params = params || {};
    this.maxMoves = opts.maxMoves === undefined ? 4 : opts.maxMoves;
    this.kind = opts.kind || "warn";
    this.track = opts.track === undefined ? null : opts.track;
    this.maxSecs = opts.maxSecs === undefined ? 6.0 : opts.maxSecs;
  }
  function sameParams(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

  function Coach() { this.opened = false; this.habit = null; this.games = 0; this.reset(); }
  Coach.prototype.reset = function () {
    this.moveNo = 0; this.last = {}; this.prev = null; this.track = new Map();
    this.times = {}; this.lastAny = null;
    this.danger = false; this.cornerTold = null; this.offCorner = 0; this.current = null;
    this.scattered = 0; this.recentDirs = []; this.cornerMoves = 0; this.countedMoves = 0;
    this.offSeen = null; this.openShown = new Set();
  };
  Coach.prototype.newGame = function (a) {
    if (this.countedMoves >= 20) this.habit = this.cornerMoves / this.countedMoves;
    this.reset();
    this.prev = a;
    var self = this;
    var keys = OPEN_TIPS.filter(function (k) {
      return k !== "tip_open" || !self.opened || self.habit === null || self.habit < OPEN_KEEP;
    });
    var key = this.opened ? keys[this.games % keys.length] : "tip_open";
    this.opened = true;
    this.games++;
    this.current = new Tip(key, PRIO_OPEN, 0, {}, { maxMoves: 5, kind: "info", maxSecs: 7.0 });
    this.openShown = new Set([key]);
    this.last.tip_early = 0;
  };
  Coach.prototype.resync = function (a) {     // see brain2049.py
    this.prev = a;
    this.track = new Map();
    this.danger = a.survival < DANGER_ENTER;
    if (this.current && (this.current.key === "tip_danger" || this.current.key === "tip_trap" ||
                         !this.isValid(this.current, a))) this.current = null;   // re-derived below
    if (!a.legal.length) return;
    var tip;
    if (this.danger) {
      tip = new Tip("tip_danger", PRIO_DANGER, this.moveNo, { dir: a.safest() }, { maxMoves: 1, maxSecs: 8.0 });
    } else if (a.deadly.length) {
      tip = new Tip("tip_trap", PRIO_DANGER, this.moveNo, { dir: a.safest(), bad: a.deadly.slice() }, { maxMoves: 0, maxSecs: 10.0 });
    } else return;
    var cur = this.current;
    if (!cur || cur.key !== tip.key || !sameParams(cur.params, tip.params)) this.current = tip;
  };
  Coach.prototype.dismiss = function () { this.current = null; };
  Coach.prototype.ready = function (key) {
    if (isStuckKey(key)) key = "stuck";
    var last = this.last[key];
    var cd = (COOLDOWN[key] === undefined ? 5 : COOLDOWN[key]) <<
             Math.min(3, Math.max(0, (this.times[key] || 0) - 1));
    if (last !== undefined && this.moveNo - last < cd) return false;
    return URGENT.indexOf(key) >= 0 || this.lastAny === null || this.moveNo - this.lastAny >= GAP;
  };
  Coach.prototype.isValid = function (tip, a) {
    if (this.moveNo - tip.born > tip.maxMoves) return false;
    var k = tip.key;
    if (k === "tip_danger") return a.survival < DANGER_EXIT && a.hasValue(tip.params.dir);
    if (k === "tip_trap") return this.moveNo === tip.born && a.hasValue(tip.params.dir);
    if (isStuckKey(k)) return tip.track !== null && a.problems.has(tip.track);
    if (k === "tip_hint_order") return bigTilesScattered(a.b, a.n);
    if (k === "tip_corner_goal") return !a.corner && waysBack(a).length > 0;
    return true;          // general tips, praise, 'it left the corner': about what happened
  };
  /* = Python Coach._next_general */
  Coach.prototype.nextGeneral = function () {
    var keep = this.habit !== null && this.habit >= OPEN_KEEP;
    var start = this.games % OPEN_TIPS.length;
    for (var i = 0; i < OPEN_TIPS.length; i++) {
      var k = OPEN_TIPS[(start + i) % OPEN_TIPS.length];
      if (this.openShown.has(k) || (k === "tip_open" && keep)) continue;
      return k;
    }
    return null;
  };
  /* = Python Coach.still_true */
  Coach.prototype.stillTrue = function (tip, a) {
    var k = tip.key;
    if (k === "tip_danger" || k === "tip_trap") return false;
    if (isStuckKey(k)) {
      var rank = Math.round(Math.log2(tip.params.value || 1)), found = false;
      a.problems.forEach(function (c) { if (a.b[c] === rank) found = true; });
      return found;
    }
    if (k === "tip_corner_goal") return !a.corner && waysBack(a).length > 0;
    return true;          // general tips, praise, 'it left the corner': about what happened
  };
  function countOf(b, v) { var c = 0; for (var i = 0; i < b.length; i++) if (b[i] === v) c++; return c; }
  function waysBack(a) {     // = Python Coach._ways_back
    if (countOf(a.b, a.maxRank) !== 1) return [];
    return a.legal.filter(function (x) {
      return a.bringsMaxToCorner(x) && a.deadly.indexOf(x) < 0 && a.regret(x) <= GOAL_REGRET;
    });
  }
  /* moved: Map from_cell -> [to_cell, merged] */
  /* a burst of moves arrives as one call: steps, dirs, and moved composed
     through all of them (composeMoves) - see brain2049.py */
  Coach.prototype.onMove = function (d, moved, a, cheated, steps, dirs) {
    if (steps === undefined || steps === null) steps = 1;
    this.moveNo += steps;
    var p = this.prev, m = this.moveNo, cands = [], self = this;
    this.recentDirs = this.recentDirs.concat(dirs && dirs.length ? dirs : [d]).slice(-DIRS_WINDOW);
    if (a.maxRank >= GOAL_RANK) {
      this.countedMoves += steps;
      if (a.corner) this.cornerMoves += steps;
    }
    var mv = function (cell) { return moved.has(cell) ? moved.get(cell) : [cell, false]; };

    // stuck tracking through the move
    var newTrack = new Map(), freed = null;
    this.track.forEach(function (t, cell) {
      var res = mv(cell), to = res[0], merged = res[1];
      if (a.problems.has(to)) {
        var nt = { age: t.age + 1, told: t.told, kind: t.kind };
        if (newTrack.has(to)) nt.told = nt.told || newTrack.get(to).told;
        newTrack.set(to, nt);
      } else if (t.told && merged && !cheated) {
        freed = [to, t.kind];
      }
    });
    Array.from(a.stuck).sort(function (x, y) { return x - y; }).forEach(function (cell) {
      if (!newTrack.has(cell)) newTrack.set(cell, { age: 0, told: false });
      newTrack.get(cell).kind = a.stuckInfo.get(cell)[0];
    });
    this.track = newTrack;
    this.offCorner = a.corner ? 0 : this.offCorner + steps;
    if (!a.corner) this.offSeen = m;
    this.scattered = bigTilesScattered(a.b, a.n) ? this.scattered + steps : 0;

    // danger / trap
    var wasDanger = this.danger;
    if (a.survival < DANGER_ENTER) this.danger = true;
    else if (a.survival >= DANGER_EXIT) this.danger = false;
    if (this.danger && a.legal.length) {
      cands.push(new Tip("tip_danger", PRIO_DANGER, m, { dir: a.safest() }, { maxMoves: 1, maxSecs: 8.0 }));
    } else if (a.deadly.length) {
      cands.push(new Tip("tip_trap", PRIO_DANGER, m, { dir: a.safest(), bad: a.deadly.slice() }, { maxMoves: 0, maxSecs: 10.0 }));
    } else if (wasDanger && !this.danger && !cheated && this.ready("tip_good_escape")) {
      cands.push(new Tip("tip_good_escape", PRIO_PRAISE, m, {}, { maxMoves: 2, kind: "praise", maxSecs: 3.5 }));
    }

    // a stuck tile that stayed stuck, not right after a corner tip
    var cornerQuiet = this.cornerTold !== null && m - this.cornerTold <= 3;
    if (this.ready("stuck") && !cornerQuiet) {
      var bestCell = null;
      var better = function (x, y) {        // = Python's rank(x) < rank(y)
        var ox = STUCK_ORDER[a.stuckInfo.get(x)[0]], oy = STUCK_ORDER[a.stuckInfo.get(y)[0]];
        if (ox !== oy) return ox < oy;
        return -(a.harmAt.get(x) || 0) < -(a.harmAt.get(y) || 0);
      };
      this.track.forEach(function (t, cell) {
        if (t.age >= 1 && !t.told && a.stuck.has(cell)) {
          if (bestCell === null || better(cell, bestCell)) bestCell = cell;
        }
      });
      if (bestCell !== null) {
        var info = a.stuckInfo.get(bestCell);
        cands.push(new Tip("tip_stuck_" + info[0], PRIO_STUCK, m,
          { value: Math.pow(2, a.b[bestCell]), big: Math.pow(2, info[1]), place: placeOf(bestCell, a.n) },
          { maxMoves: 6, track: bestCell }));
      }
    }

    // the biggest tile left its corner
    if (p && p.corner && !a.corner && a.maxRank >= 6 && p.hasValue(d) && steps === 1) {
      // blamed only when avoidable AND it mattered (see brain2049.py)
      // made by this very move (a merge): built outside the corner, not "left"
      var ckey = a.maxRank > p.maxRank ? "tip_corner_made" : "tip_corner_lost";
      var keep = p.legal.filter(function (x) { return x !== d && p.keepsCorner(x); });
      if (ckey === "tip_corner_lost" && countOf(p.b, p.maxRank) !== 1) keep = [];   // see brain2049.py
      if (keep.length && this.ready(ckey)) {
        var kv = p.values[keep[0]];
        for (var i = 1; i < keep.length; i++) if (p.values[keep[i]] > kv) kv = p.values[keep[i]];
        if ((kv - p.values[d]) / p.unit >= LOST_MARGIN)
          cands.push(new Tip(ckey, PRIO_CORNER, m, { value: Math.pow(2, a.maxRank) }, { maxMoves: 3 }));
      }
    } else if (!a.corner && a.maxRank >= GOAL_RANK && this.offCorner >= OFF_CORNER_MOVES &&
               (this.cornerTold === null || m - this.cornerTold > 8) &&
               this.ready("tip_corner_goal")) {
      // out of a corner for a while, and one move brings it back at a fair price
      if (waysBack(a).length)
        cands.push(new Tip("tip_corner_goal", PRIO_CORNER, m, { value: Math.pow(2, a.maxRank) }, { maxMoves: 2 }));
    } else if (p && !p.corner && a.corner && this.cornerTold !== null &&
               m - this.cornerTold <= 6 && !cheated && this.ready("tip_good_corner")) {
      cands.push(new Tip("tip_good_corner", PRIO_PRAISE, m, { value: Math.pow(2, a.maxRank) }, { maxMoves: 2, kind: "praise", maxSecs: 3.5 }));
    }

    // a general tip, when the board shows exactly what it is about
    if (this.scattered >= SCATTER_MOVES && !this.danger && !a.deadly.length &&
        this.ready("tip_hint_order")) {
      cands.push(new Tip("tip_hint_order", PRIO_HINT, m, {}, { maxMoves: 4, kind: "info", maxSecs: 6.0 }));
    } else if (this.recentDirs.length >= DIRS_WINDOW && a.maxRank >= 4 && !this.danger &&
               !a.deadly.length && this.offSeen !== null && m - this.offSeen <= DIRS_WINDOW &&
               this.ready("tip_hint_dirs")) {
      var least = Infinity;
      for (var di = 0; di < 4; di++) {
        var cnt = 0;
        for (var dj = 0; dj < this.recentDirs.length; dj++) if (this.recentDirs[dj] === DIRS[di]) cnt++;
        if (cnt < least) least = cnt;
      }
      if (least >= DIRS_EACH)
        cands.push(new Tip("tip_hint_dirs", PRIO_HINT, m, {}, { maxMoves: 4, kind: "info", maxSecs: 6.0 }));
    }

    // early in the game: the next general tip, if nothing else speaks
    if (m <= EARLY_MOVES && !this.danger && !a.deadly.length && this.ready("tip_early")) {
      var nxt = this.nextGeneral();
      if (nxt !== null)
        cands.push(new Tip(nxt, PRIO_OPEN, m, {}, { maxMoves: 6, kind: "info", maxSecs: 6.0 }));
    }

    // earned praise
    if (freed !== null && (freed[1] === "block" || freed[1] === "chain") && a.corner &&
        !a.deadly.length && this.ready("tip_good_freed"))
      cands.push(new Tip("tip_good_freed", PRIO_PRAISE, m, {}, { maxMoves: 2, kind: "praise", maxSecs: 3.5 }));
    if (p && a.maxRank > p.maxRank && a.maxRank >= RECORD_RANK && !cheated)
      cands.push(new Tip("tip_good_record", PRIO_PRAISE, m, { value: Math.pow(2, a.maxRank) }, { maxMoves: 2, kind: "praise", maxSecs: 3.5 }));

    // choose
    var cur = this.current;
    if (cur && cur.track !== null) cur.track = mv(cur.track)[0];
    if (cur && !this.isValid(cur, a)) cur = null;
    if (!a.legal.length) { cands = []; cur = null; }   // game over: the board says it all
    if (cands.length) {
      var top = cands[0];
      for (var c = 1; c < cands.length; c++) if (cands[c].prio > top.prio) top = cands[c];
      if (cur === null || top.prio >= cur.prio) {
        if (!(cur !== null && cur.key === top.key && sameParams(cur.params, top.params))) {
          cur = top;
          var lk = isStuckKey(top.key) ? "stuck" : top.key;
          this.last[lk] = m;
          if (OPEN_TIPS.indexOf(top.key) >= 0) { this.last.tip_early = m; this.openShown.add(top.key); }
          this.times[lk] = (this.times[lk] || 0) + 1;
          if (URGENT.indexOf(lk) < 0) this.lastAny = m;
          if (isStuckKey(top.key)) this.track.get(top.track).told = true;
          if (top.key === "tip_corner_lost" || top.key === "tip_corner_made" ||
              top.key === "tip_corner_goal") this.cornerTold = m;
        }
      }
    }
    this.current = cur;
    this.prev = a;
    return cur;
  };

  var api = {
    LEFT: LEFT, RIGHT: RIGHT, UP: UP, DOWN: DOWN, DIRS: DIRS, DIR_NAMES: DIR_NAMES,
    toRanks: toRanks, toGrid: toGrid, move: move, legalMoves: legalMoves,
    canMove: canMove, heuristic: heuristic, moveValues: moveValues,
    bestMove: bestMove, positionValue: positionValue, pickDepth: pickDepth,
    survival: survival, moveSurvival: moveSurvival, harmUnit: harmUnit,
    tileHarms: tileHarms, chainBreaker: chainBreaker, placeOf: placeOf, composeMoves: composeMoves,
    maxInCorner: maxInCorner, bestSpawn: bestSpawn, stuckKind: stuckKind,
    Analysis: Analysis, Coach: Coach, Tip: Tip,
    DANGER_ENTER: DANGER_ENTER, DANGER_EXIT: DANGER_EXIT, CHEAT_T: CHEAT_T
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Brain2049 = api;
})(typeof window !== "undefined" ? window : this);
