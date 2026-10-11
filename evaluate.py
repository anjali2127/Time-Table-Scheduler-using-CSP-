"""
evaluate.py - Evaluation of the CSP algorithms (for the Results chapter of the report).

Runs both algorithms (plain backtracking, backtracking + forward checking) on 3 problems
(Easy, Medium, Hard) and records:
  success rate, nodes explored, backtracks, time, and constraint violations.
Each algorithm is run several times with different random value orders; results are averaged.

Usage:
    python evaluate.py            full run  (5 runs per case, 8 s limit)   ~ 2-3 minutes
    python evaluate.py --quick    fast run  (1 run per case, 3 s limit)    ~ 30 seconds
Output:
    console tables, evaluation_results.csv and (if matplotlib is installed) evaluation_chart.png
"""
import argparse
import csv

from solver import CSPSolver

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
SLOTS = ["9-10", "10-11", "11-12", "1-2", "2-3", "3-4"]
WEEK_SLOTS = len(DAYS) * len(SLOTS)

ALGORITHMS = {
    "Plain backtracking":        dict(use_fc=False),
    "Backtracking + Forward Checking": dict(use_fc=True),
}


def make_case(divisions, subjects, lectures, rooms, teachers_off=0):
    """Build a problem. Subject i is taught by teacher i in every division."""
    data = {
        "days": DAYS, "slots": SLOTS, "break_after": ["11-12"], "max_per_day": 4,
        "divisions": [f"D{i + 1}" for i in range(divisions)],
        "subjects": [{"name": f"S{i + 1}", "teacher": f"T{i + 1}", "lectures": lectures, "is_lab": 0}
                     for i in range(subjects)],
        "rooms": [{"name": f"R{i + 1}", "is_lab": 0} for i in range(rooms)],
        "unavailable": {},
    }
    for t in range(teachers_off):          # teacher t is off on one whole day
        data["unavailable"][f"T{t + 1}"] = [[DAYS[t % len(DAYS)], s] for s in SLOTS]
    return data


CASES = {
    "Easy":   make_case(divisions=2, subjects=5, lectures=3, rooms=2),
    "Medium": make_case(divisions=5, subjects=6, lectures=4, rooms=5),
    "Hard":   make_case(divisions=5, subjects=6, lectures=4, rooms=5, teachers_off=1),
}


def describe(data):
    sessions = sum(s["lectures"] for s in data["subjects"]) * len(data["divisions"])
    room_load = sessions / (len(data["rooms"]) * WEEK_SLOTS)
    div_load = sum(s["lectures"] for s in data["subjects"]) / WEEK_SLOTS
    teacher_load = max(s["lectures"] * len(data["divisions"]) for s in data["subjects"]) / WEEK_SLOTS
    return {"variables": sessions, "rooms": len(data["rooms"]),
            "room_load": room_load, "division_load": div_load, "teacher_load": teacher_load}


def run_case(data, config, runs, time_limit):
    results = []
    for seed in range(1, runs + 1):
        solver = CSPSolver(data, shuffle=True, seed=seed, max_time=time_limit, **config)
        entries, stats = solver.solve()
        violations = len(solver.verify(entries)) if entries else None
        results.append({"solved": entries is not None, "nodes": stats["nodes"],
                        "backtracks": stats["backtracks"], "time": stats["time_sec"],
                        "violations": violations})
    n = len(results)
    return {
        "solved": sum(r["solved"] for r in results), "runs": n,
        "nodes": sum(r["nodes"] for r in results) / n,
        "backtracks": sum(r["backtracks"] for r in results) / n,
        "time": sum(r["time"] for r in results) / n,
        "violations": sum(r["violations"] or 0 for r in results),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="1 run per case, 3 second limit")
    args = parser.parse_args()
    runs, limit = (1, 3) if args.quick else (5, 8)

    print(f"Settings: {runs} run(s) per algorithm, time limit {limit} s "
          f"(a run that hits the limit counts as NOT solved)\n")

    print("PROBLEM SIZES")
    print(f"{'Case':11}{'Sessions':>9}{'Rooms':>7}{'Room load':>11}{'Division load':>15}{'Teacher load':>14}")
    for name, data in CASES.items():
        d = describe(data)
        print(f"{name:11}{d['variables']:>9}{d['rooms']:>7}{d['room_load']:>10.0%}"
              f"{d['division_load']:>15.0%}{d['teacher_load']:>14.0%}")

    rows = []
    for case_name, data in CASES.items():
        print(f"\n=== {case_name.upper()} ===")
        print(f"{'Algorithm':33}{'Solved':>8}{'Avg nodes':>12}{'Avg backtracks':>16}{'Avg time (s)':>14}{'Violations':>12}")
        for algo_name, config in ALGORITHMS.items():
            r = run_case(data, config, runs, limit)
            print(f"{algo_name:33}{str(r['solved']) + '/' + str(r['runs']):>8}{r['nodes']:>12.0f}"
                  f"{r['backtracks']:>16.0f}{r['time']:>14.3f}{r['violations']:>12}")
            rows.append({"case": case_name, "algorithm": algo_name, "solved": r["solved"],
                         "runs": r["runs"], "avg_nodes": round(r["nodes"]),
                         "avg_backtracks": round(r["backtracks"]),
                         "avg_time_sec": round(r["time"], 4), "violations": r["violations"]})

    with open("evaluation_results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print("\nSaved: evaluation_results.csv")

    make_chart(rows)
    print("\nNote: runs that hit the time limit are counted as unsolved; their nodes/time are the")
    print("work done until the limit, so the real cost of those algorithms is even higher.")


def make_chart(rows):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed - chart skipped (pip install matplotlib to enable)")
        return

    cases = list(CASES)
    algos = list(ALGORITHMS)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    width = 0.8 / len(algos)
    for ax, key, title in ((axes[0], "avg_nodes", "Nodes explored (log scale)"),
                           (axes[1], "avg_time_sec", "Average time in seconds (log scale)")):
        for i, algo in enumerate(algos):
            values = [next(r[key] for r in rows if r["case"] == c and r["algorithm"] == algo)
                      for c in cases]
            ax.bar([x + i * width for x in range(len(cases))], [max(v, 1e-4) for v in values],
                   width, label=algo)
        ax.set_xticks([x + 0.4 - width / 2 for x in range(len(cases))])
        ax.set_xticklabels(cases)
        ax.set_yscale("log")
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.3)
    axes[0].legend(fontsize=8)
    fig.suptitle("CSP timetable solver: algorithm comparison")
    fig.tight_layout()
    fig.savefig("evaluation_chart.png", dpi=150)
    print("Saved: evaluation_chart.png")


if __name__ == "__main__":
    main()
