import importlib, json, sys, pathlib
root = pathlib.Path(sys.argv[1]); out = {}
for v in sorted(root.iterdir()):
    sys.path.insert(0, str(v))
    for k in [m for m in sys.modules if m.startswith("pidpkg")]: del sys.modules[k]
    try:
        plan_mod = importlib.import_module("pidpkg.pid_plan")
        profiles = ["demo", "scale"] if "scale" in str(getattr(plan_mod, "Profile", "")) else ["demo"]
        rows = {}
        for prof in profiles:
            try:
                plan = plan_mod.build_plan(prof) if prof != "demo" else plan_mod.build_plan()
            except TypeError:
                plan = plan_mod.build_plan()
            seen = {}
            for e in plan.entities:
                t = getattr(e, "entity_type", None) or getattr(e, "type")
                nid = plan_mod.node_id(e.key)
                if nid in seen and seen[nid] != t:
                    print(f"{v.name} {prof}: WITHIN-PLAN collision {nid} {seen[nid]} vs {t} key={e.key}")
                seen[nid] = t
            rows[prof] = seen
        out[v.name] = rows
        print(v.name, {p: len(r) for p, r in rows.items()})
    except Exception as exc:
        print(v.name, "FAILED", type(exc).__name__, str(exc)[:150])
    sys.path.remove(str(v))
# across versions: every id -> set of types
across = {}
for v, rows in out.items():
    for prof, seen in rows.items():
        for nid, t in seen.items():
            across.setdefault(nid, {}).setdefault(t, []).append(f"{v}:{prof}")
moved = {nid: ts for nid, ts in across.items() if len(ts) > 1}
print("ids seen:", len(across), "ids on more than one type across versions/profiles:", len(moved))
for nid, ts in list(moved.items())[:20]: print(" ", nid, {t: vs[:3] for t, vs in ts.items()})
