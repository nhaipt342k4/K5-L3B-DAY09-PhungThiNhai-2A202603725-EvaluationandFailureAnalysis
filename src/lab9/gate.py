"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    graded = _graded_ids(spec)
    for who, rep in (("PR", pr), ("baseline", base)):
        problems += [f"{who}: {p}" for p in _report_problems(rep, graded, spec)]
    # Same trial set as the baseline: no cherry-picked seeds or items, nothing added or dropped.
    pk, bk = _trial_keys(pr), _trial_keys(base)
    if pk != bk:
        missing, extra = sorted(bk - pk), sorted(pk - bk)
        problems.append(f"(item, seed) set differs from the baseline: {len(missing)} missing "
                        f"{_fmt(missing)}, {len(extra)} extra {_fmt(extra)}")
    if sorted(pr.get("manifest", {}).get("seeds") or []) != sorted(base.get("manifest", {}).get("seeds") or []):
        problems.append(f"manifest seeds {pr.get('manifest', {}).get('seeds')} != baseline "
                        f"{base.get('manifest', {}).get('seeds')}")
    # Slice tags come from the label; an item may not leave (or join) a slice between runs.
    ps, bsl = _slice_tags(pr), _slice_tags(base)
    for item in sorted(set(ps) & set(bsl)):
        if ps[item] != bsl[item]:
            problems.append(f"{item}: slice tags {sorted(ps[item])} != baseline {sorted(bsl[item])}")
    if base_spec is not None:
        problems += _ratchet(spec, base_spec)
    return problems


def _graded_ids(spec: dict) -> list[str]:
    from lab9.graders import GRADERS
    return [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]


def _trial_keys(rep: dict) -> set[tuple[str, int]]:
    return {(r.get("item_id"), r.get("seed")) for r in rep.get("rows") or []}


def _fmt(keys: list, n: int = 3) -> str:
    return "[" + ", ".join(f"{i}@{s}" for i, s in keys[:n]) + (" …" if len(keys) > n else "") + "]"


def _slice_tags(rep: dict) -> dict[str, frozenset]:
    out: dict[str, frozenset] = {}
    for r in rep.get("rows") or []:
        out.setdefault(r.get("item_id"), frozenset(r.get("slices") or []))
    return out


def _bad_number(v) -> bool:
    return isinstance(v, float) and (math.isnan(v) or math.isinf(v))


def _report_problems(rep: dict, graded: list[str], spec: dict) -> list[str]:
    """Self-consistency of one report: it must be exactly what lab9.eval would have written."""
    from lab9.eval import aggregate
    out: list[str] = []
    rows, man, metrics = rep.get("rows") or [], rep.get("manifest") or {}, rep.get("metrics") or {}
    if rep.get("evaluator_failures"):
        out.append(f"{len(rep['evaluator_failures'])} evaluator failure(s), e.g. {rep['evaluator_failures'][0]!s:.80}")
    out += [f"metric {k} is {v} (NaN/inf)" for k, v in metrics.items() if _bad_number(v)]
    seeds = man.get("seeds") or []
    want = (man.get("items") or 0) * len(seeds)
    if len(rows) != want:
        out.append(f"{len(rows)} rows != {man.get('items')} items x {len(seeds)} seeds = {want}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dup = sorted({k for k in keys if keys.count(k) > 1})
    if dup:
        out.append(f"{len(dup)} duplicated (item, seed) row(s) {_fmt(dup)}")
    stray = sorted({s for _, s in keys} - set(seeds))
    if stray:
        out.append(f"rows use seeds {stray} not in the manifest")
    if spec.get("seeds") and sorted(seeds) != sorted(spec["seeds"]):
        out.append(f"manifest seeds {seeds} != spec seeds {spec['seeds']}")
    items = {i for i, _ in keys}
    if man.get("items") is not None and len(items) != man["items"]:
        out.append(f"{len(items)} distinct items in rows != manifest items {man['items']}")
    # A crashed grader must not drop out of the mean: every graded value is a real bool.
    for m in graded:
        bad = [k for r, k in zip(rows, keys) if not isinstance(r.get(m), bool)]
        if bad:
            out.append(f"metric {m}: {len(bad)} row(s) not graded (None/missing/non-bool) {_fmt(sorted(bad))}")
    # Tags of one item must agree across its seeds.
    tags: dict[str, set] = {}
    for r in rows:
        tags.setdefault(r.get("item_id"), set()).add(frozenset(r.get("slices") or []))
    out += [f"{i}: slice tags differ across seeds" for i, t in sorted(tags.items()) if len(t) > 1]
    # The headline numbers must be the ones the rows produce (no hand-edited metrics).
    if rows and not out:
        ids = [m for m in graded if all(m in r for r in rows)]
        has_cost = all(isinstance(r.get("cost"), (int, float)) for r in rows)
        rec = aggregate([r if has_cost else {**r, "cost": 0.0} for r in rows], ids, k_values=spec.get("pass_k", []))
        for k, v in metrics.items():
            if k not in rec or (k == "cost_per_success" and not has_cost):
                continue
            r_ = rec[k]
            same = (v is None and r_ is None) or (isinstance(v, (int, float)) and isinstance(r_, (int, float))
                                                  and abs(v - r_) <= 1e-6)
            if not same:
                out.append(f"metric {k}={v} but the rows give {r_} (edited or stale report)")
    # The report must be on the eval set the spec points at, with that eval set's items and tags.
    path = Path(spec["eval_set"]) if spec.get("eval_set") else None
    if path is not None and path.is_file():
        from lab9.evalset import load_jsonl, sha12
        if man.get("eval_set_sha") != sha12(path):
            out.append(f"eval_set_sha {man.get('eval_set_sha')} != {path} ({sha12(path)})")
        ev = {it["item_id"]: frozenset(it.get("slices") or []) for it in load_jsonl(path)}
        if items != set(ev):
            out.append(f"items in rows differ from {path}: {len(set(ev) - items)} missing, {len(items - set(ev))} extra")
        relabelled = sorted(i for i, t in _slice_tags(rep).items() if i in ev and t != ev[i])
        if relabelled and any(ev.values()):
            out.append(f"slice tags differ from {path} for {relabelled[:3]}")
    return out


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    """Thresholds on the same eval set may only get stricter. Applied whenever base_spec is given:
    the gate already pins both reports to the same eval_set_sha, so renaming eval_set_version in the
    PR's spec does not make it a new eval set."""
    out: list[str] = []
    new = {m["id"]: m for m in spec.get("metrics", [])}
    for bm in base_spec.get("metrics", []):
        m = new.get(bm["id"])
        if m is None:
            out.append(f"ratchet: metric {bm['id']} was removed")
            continue
        out += [f"ratchet: metric {bm['id']} {p}" for p in _looser(bm.get("threshold") or {}, m.get("threshold") or {},
                                                                     bm.get("blocking"), m.get("blocking"))]
    new_sl = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for bs in base_spec.get("slices") or []:
        s = new_sl.get((bs["name"], bs["metric"]))
        if s is None:
            out.append(f"ratchet: slice {bs['name']}/{bs['metric']} was removed")
            continue
        out += [f"ratchet: slice {bs['name']}/{bs['metric']} {p}" for p in _looser(bs, s, bs.get("blocking"), s.get("blocking"))]
    if not set(base_spec.get("seeds") or []) <= set(spec.get("seeds") or []):
        out.append(f"ratchet: seeds {spec.get('seeds')} drop baseline seeds {base_spec.get('seeds')}")
    bc = (base_spec.get("bootstrap") or {}).get("confidence", 0.95)
    nc = (spec.get("bootstrap") or {}).get("confidence", 0.95)
    if nc > bc:
        out.append(f"ratchet: bootstrap confidence {nc} > {bc} (wider CI blocks less)")
    for k in ("eval_set", "labels", "adversarial_pack"):
        if base_spec.get(k) != spec.get(k):
            out.append(f"ratchet: {k} {spec.get(k)!r} != base {base_spec.get(k)!r}")
    return out


def _looser(old: dict, new: dict, old_blocking, new_blocking) -> list[str]:
    out = []
    if old_blocking and not new_blocking:
        out.append("is no longer blocking")
    if "min" in old and ("min" not in new or new["min"] < old["min"]):
        out.append(f"min {old['min']} -> {new.get('min')}")
    for k in ("max", "max_increase"):
        if k in old and (k not in new or new[k] > old[k]):
            out.append(f"{k} {old[k]} -> {new.get(k)}")
    for k in ("no_significant_drop", "no_new_failures"):
        if old.get(k) and not new.get(k):
            out.append(f"dropped {k}")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, metric = s["name"], s["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            # An empty slice cannot vouch for anything: items relabelled out of it, or a metric
            # that was never graded. Treat it as a failure, not as a vacuous pass.
            verdict, note = "fail", "empty slice (no graded rows)"
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in s and val < s["min"]:
                verdict = "fail"
            if "max" in s and val > s["max"]:
                verdict = "fail"
            if s.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                if keys:
                    d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                       n_resamples=bs.get("n_resamples", 1000),
                                                       rng=bs.get("rng", 2027),
                                                       confidence=bs.get("confidence", 0.95))
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}] n={len(keys)}"
                    if hi < 0:
                        verdict = "fail"
                else:
                    verdict, note = "fail", "no items shared with the baseline slice"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        label = "ok" if verdict == "ok" else ("BLOCK" if s.get("blocking") else "warn")
        th = {k: s[k] for k in ("min", "max", "no_significant_drop") if k in s}
        lines.append(f"  {sid:<34} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def new_failures(pr: dict, base: dict, metric: str, bad_is_true: bool = False) -> list[tuple[str, int]]:
    """(item_id, seed) trials that were good on the baseline and are bad in the PR.
    Averages can hide a regression that moves failures around: a PR that breaks E-002@33 while the
    baseline only fails E-002@55 has the same mean, the same pass^5 and a paired CI of exactly 0.
    On a deterministic harness (A/A delta = 0) a newly failing trial is a regression, not noise.
    With a real LLM this rule needs repeated runs per trial before it can block."""
    bad = (lambda v: v is True) if bad_is_true else (lambda v: v is False)
    was = {(r["item_id"], r["seed"]): r.get(metric) for r in base["rows"]}
    return sorted({(r["item_id"], r["seed"]) for r in pr["rows"]
                   if bad(r.get(metric)) and (r["item_id"], r["seed"]) in was
                   and was[(r["item_id"], r["seed"])] is not None and not bad(was[(r["item_id"], r["seed"])])})


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if th.get("no_new_failures") and val is not None:
            new = new_failures(pr, base, mid, bad_is_true="max" in th)
            if new:
                verdict = "fail"
                shown = ", ".join(f"{i}@{s}" for i, s in new[:3]) + (" …" if len(new) > 3 else "")
                note = (note + " · " if note else "") + f"{len(new)} new fail: {shown}"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
