"""test_solver.py - run the CSP solver without Flask/DB and compare algorithms."""
from solver import CSPSolver

DATA = {
    "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
    "slots": ["9-10", "10-11", "11-12", "1-2", "2-3", "3-4"],
    "rooms": [{"name": "R101", "is_lab": 0}, {"name": "R102", "is_lab": 0}],
    "divisions": ["CE-A", "CE-B"],
    "subjects": [
        {"name": "AI",    "teacher": "Prof. A", "lectures": 3},
        {"name": "DBMS",  "teacher": "Prof. B", "lectures": 3},
        {"name": "CN",    "teacher": "Prof. C", "lectures": 3},
        {"name": "OS",    "teacher": "Prof. D", "lectures": 3},
        {"name": "Maths", "teacher": "Prof. E", "lectures": 3},
    ],
    # Prof. A is not available on Friday (example of unary constraint U2)
    "unavailable": {"Prof. A": [["Fri", s] for s in
                                ["9-10", "10-11", "11-12", "1-2", "2-3", "3-4"]]},
}


def print_grid(entries, data, division):
    slots = data["slots"]
    print(f"\n===== Timetable: {division} =====")
    print(f"{'':5}" + "".join(f"{s:^16}" for s in slots))
    for day in data["days"]:
        row = f"{day:5}"
        for slot in slots:
            cell = ""
            for e in entries:
                if e["division"] == division and e["day"] == day and e["slot"] == slot:
                    cell = f"{e['subject']}({e['room']})"
            row += f"{cell:^16}"
        print(row)


# ---------- 1. generate one timetable with the best configuration ----------
solver = CSPSolver(DATA, use_fc=True, use_soft=True, shuffle=True, seed=1)
entries, stats = solver.solve()
print("Result:", stats)

if entries:
    for div in DATA["divisions"]:
        print_grid(entries, DATA, div)
    problems = solver.verify(entries)
    print("\nVerification:", "VALID - 0 hard-constraint violations" if not problems
          else f"{len(problems)} violations!")

# ---------- 2. compare algorithms (for the evaluation table in the report) ----------
configs = {
    "Plain backtracking":    dict(use_fc=False),
    "Backtracking + FC":     dict(use_fc=True),
}

print("\n\n=== Algorithm comparison ===")
print(f"{'Algorithm':28}{'Status':12}{'Nodes':>9}{'Backtracks':>12}{'Time(s)':>10}")
for name, cfg in configs.items():
    s = CSPSolver(DATA, max_time=20, **cfg)
    _, st = s.solve()
    print(f"{name:28}{st['status']:12}{st['nodes']:>9}{st['backtracks']:>12}{st['time_sec']:>10}")
