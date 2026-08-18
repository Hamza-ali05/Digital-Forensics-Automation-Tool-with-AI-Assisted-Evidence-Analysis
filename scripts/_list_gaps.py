import json
from pathlib import Path

data = json.loads(Path("coverage.json").read_text(encoding="utf-8"))
pkgs = ("database", "services", "forensic_engine", "pipeline")
rows = []
for path, info in data["files"].items():
    n = path.replace("\\", "/")
    if "src/dfat/" not in n:
        continue
    rest = n.split("src/dfat/", 1)[1]
    top = rest.split("/")[0]
    if top not in pkgs:
        continue
    s = info["summary"]
    if s["num_statements"] == 0:
        continue
    rows.append((s["percent_covered"], s["num_statements"], rest))
rows.sort()
for pct, st, rest in rows:
    if pct >= 90:
        continue
    print(f"{pct:5.1f}% n={st:4d} {rest}")
