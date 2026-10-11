"""
app.py - Flask backend for the Time-Table Scheduler using CSP.

Connects: frontend (browser)  <->  Flask  <->  SQLite  and  solver.py
"""
import random
import sqlite3

from flask import Flask, render_template, request, jsonify

from database import get_connection, init_db
from solver import CSPSolver

app = Flask(__name__)
init_db()

# Working days and lecture slots (change here to match your college)
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
SLOTS = ["9-10", "10-11", "11-12", "1-2", "2-3", "3-4"]
BREAK_AFTER = ["11-12"]     # lunch break comes after this slot (labs cannot span it)
MAX_PER_DAY = 4             # soft limit: lecture-slots per division per day

# Algorithm options (used for the comparison in the report)
ALGORITHMS = {
    "plain": dict(use_fc=False),     # plain backtracking
    "fc":    dict(use_fc=True),      # backtracking + forward checking (default)
}


# ------------------------------------------------------------------
# small helpers
# ------------------------------------------------------------------
def fetch_all(sql, params=()):
    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def execute(sql, params=()):
    """Run INSERT/UPDATE/DELETE. Returns (ok, message_or_id)."""
    conn = get_connection()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return True, cur.lastrowid
    except sqlite3.IntegrityError as e:
        return False, str(e)
    finally:
        conn.close()


def error(msg, code=400):
    return jsonify({"error": msg}), code


# ------------------------------------------------------------------
# pages + config
# ------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/config")
def config():
    return jsonify({"days": DAYS, "slots": SLOTS, "algorithms": list(ALGORITHMS)})


# ------------------------------------------------------------------
# TEACHERS
# ------------------------------------------------------------------
@app.route("/api/teachers", methods=["GET"])
def get_teachers():
    return jsonify(fetch_all("SELECT * FROM teachers ORDER BY name"))


@app.route("/api/teachers", methods=["POST"])
def add_teacher():
    name = (request.json or {}).get("name", "").strip()
    if not name:
        return error("Name required")
    ok, res = execute("INSERT INTO teachers (name) VALUES (?)", (name,))
    return (jsonify({"message": "Teacher added", "id": res}), 201) if ok \
        else error("Teacher already exists")


@app.route("/api/teachers/<int:tid>", methods=["DELETE"])
def delete_teacher(tid):
    execute("DELETE FROM availability WHERE teacher_id = ?", (tid,))
    ok, res = execute("DELETE FROM teachers WHERE id = ?", (tid,))
    return jsonify({"message": "Teacher deleted"}) if ok \
        else error("Delete the teacher's subjects first")


# ------------------------------------------------------------------
# ROOMS
# ------------------------------------------------------------------
@app.route("/api/rooms", methods=["GET"])
def get_rooms():
    return jsonify(fetch_all("SELECT * FROM rooms ORDER BY name"))


@app.route("/api/rooms", methods=["POST"])
def add_room():
    d = request.json or {}
    name = d.get("name", "").strip()
    if not name:
        return error("Room name required")
    ok, res = execute("INSERT INTO rooms (name, is_lab) VALUES (?, ?)",
                      (name, int(bool(d.get("is_lab", 0)))))
    return (jsonify({"message": "Room added", "id": res}), 201) if ok \
        else error("Room already exists")


@app.route("/api/rooms/<int:rid>", methods=["DELETE"])
def delete_room(rid):
    execute("DELETE FROM rooms WHERE id = ?", (rid,))
    return jsonify({"message": "Room deleted"})


# ------------------------------------------------------------------
# DIVISIONS
# ------------------------------------------------------------------
@app.route("/api/divisions", methods=["GET"])
def get_divisions():
    return jsonify(fetch_all("SELECT * FROM divisions ORDER BY name"))


@app.route("/api/divisions", methods=["POST"])
def add_division():
    name = (request.json or {}).get("name", "").strip()
    if not name:
        return error("Division name required")
    ok, res = execute("INSERT INTO divisions (name) VALUES (?)", (name,))
    return (jsonify({"message": "Division added", "id": res}), 201) if ok \
        else error("Division already exists")


@app.route("/api/divisions/<int:did>", methods=["DELETE"])
def delete_division(did):
    execute("DELETE FROM divisions WHERE id = ?", (did,))
    return jsonify({"message": "Division deleted"})


# ------------------------------------------------------------------
# SUBJECTS
# ------------------------------------------------------------------
@app.route("/api/subjects", methods=["GET"])
def get_subjects():
    return jsonify(fetch_all("""
        SELECT s.id, s.name, s.lectures_per_week, s.is_lab,
               s.teacher_id, t.name AS teacher
        FROM subjects s JOIN teachers t ON t.id = s.teacher_id
        ORDER BY s.name"""))


@app.route("/api/subjects", methods=["POST"])
def add_subject():
    d = request.json or {}
    name = d.get("name", "").strip()
    try:
        teacher_id = int(d.get("teacher_id"))
        lectures = int(d.get("lectures_per_week", 3))
    except (TypeError, ValueError):
        return error("teacher_id and lectures_per_week must be numbers")
    if not name:
        return error("Subject name required")
    if not 1 <= lectures <= len(DAYS):
        return error(f"Lectures per week must be between 1 and {len(DAYS)}")
    ok, res = execute(
        "INSERT INTO subjects (name, teacher_id, lectures_per_week, is_lab) VALUES (?,?,?,?)",
        (name, teacher_id, lectures, int(bool(d.get("is_lab", 0)))))
    return (jsonify({"message": "Subject added", "id": res}), 201) if ok \
        else error("Teacher does not exist")


@app.route("/api/subjects/<int:sid>", methods=["DELETE"])
def delete_subject(sid):
    execute("DELETE FROM subjects WHERE id = ?", (sid,))
    return jsonify({"message": "Subject deleted"})


# ------------------------------------------------------------------
# AVAILABILITY  (slots when a teacher is NOT available)
# ------------------------------------------------------------------
@app.route("/api/availability", methods=["GET"])
def get_availability():
    return jsonify(fetch_all("""
        SELECT a.id, a.teacher_id, t.name AS teacher, a.day, a.slot
        FROM availability a JOIN teachers t ON t.id = a.teacher_id
        ORDER BY t.name, a.day, a.slot"""))


@app.route("/api/availability", methods=["POST"])
def add_availability():
    d = request.json or {}
    day, slot = d.get("day"), d.get("slot")
    if day not in DAYS:
        return error(f"day must be one of {DAYS}")
    # slot can be one slot name or "all" (whole day off)
    slots = SLOTS if slot == "all" else [slot]
    if any(s not in SLOTS for s in slots):
        return error(f"slot must be one of {SLOTS} or 'all'")
    try:
        teacher_id = int(d.get("teacher_id"))
    except (TypeError, ValueError):
        return error("teacher_id required")
    for s in slots:
        exists = fetch_all("SELECT id FROM availability WHERE teacher_id=? AND day=? AND slot=?",
                           (teacher_id, day, s))
        if not exists:
            ok, res = execute("INSERT INTO availability (teacher_id, day, slot) VALUES (?,?,?)",
                              (teacher_id, day, s))
            if not ok:
                return error("Teacher does not exist")
    return jsonify({"message": "Unavailable time saved"}), 201


@app.route("/api/availability/<int:aid>", methods=["DELETE"])
def delete_availability(aid):
    execute("DELETE FROM availability WHERE id = ?", (aid,))
    return jsonify({"message": "Deleted"})


# ------------------------------------------------------------------
# SEED SAMPLE DATA (quick start for testing / demo)
# ------------------------------------------------------------------
@app.route("/api/seed", methods=["POST"])
def seed():
    if fetch_all("SELECT id FROM subjects LIMIT 1"):
        return error("Data already exists. Delete it first, or use a fresh database.")
    teachers = ["Prof. A", "Prof. B", "Prof. C", "Prof. D", "Prof. E"]
    subjects = ["AI", "DBMS", "CN", "OS", "Maths"]
    for t in teachers:
        execute("INSERT OR IGNORE INTO teachers (name) VALUES (?)", (t,))
    ids = {r["name"]: r["id"] for r in fetch_all("SELECT * FROM teachers")}
    for sub, t in zip(subjects, teachers):
        execute("INSERT INTO subjects (name, teacher_id, lectures_per_week, is_lab) VALUES (?,?,?,0)",
                (sub, ids[t], 3))
    for r in ["R101", "R102"]:
        execute("INSERT OR IGNORE INTO rooms (name, is_lab) VALUES (?, 0)", (r,))
    for dv in ["CE-A", "CE-B"]:
        execute("INSERT OR IGNORE INTO divisions (name) VALUES (?)", (dv,))
    for s in SLOTS:      # Prof. A off on Friday
        execute("INSERT INTO availability (teacher_id, day, slot) VALUES (?,?,?)",
                (ids["Prof. A"], "Fri", s))
    return jsonify({"message": "Sample data loaded"}), 201


# ------------------------------------------------------------------
# GENERATE TIMETABLE  (DB -> solver -> DB)
# ------------------------------------------------------------------
def load_solver_input():
    """Read everything from SQLite and convert to the plain dict the solver expects."""
    subjects = fetch_all("""
        SELECT s.name, s.lectures_per_week AS lectures, s.is_lab, t.name AS teacher
        FROM subjects s JOIN teachers t ON t.id = s.teacher_id ORDER BY s.id""")
    unavailable = {}
    for a in fetch_all("""SELECT t.name AS teacher, a.day, a.slot
                          FROM availability a JOIN teachers t ON t.id = a.teacher_id"""):
        unavailable.setdefault(a["teacher"], []).append([a["day"], a["slot"]])
    return {
        "days": DAYS,
        "slots": SLOTS,
        "rooms": fetch_all("SELECT name, is_lab FROM rooms ORDER BY id"),
        "divisions": [d["name"] for d in fetch_all("SELECT name FROM divisions ORDER BY id")],
        "subjects": subjects,
        "unavailable": unavailable,
        "break_after": BREAK_AFTER,
        "max_per_day": MAX_PER_DAY,
    }


def pre_check(data):
    """Catch obvious problems before running the solver. Returns a message or None."""
    if not data["divisions"]:
        return "Add at least one division."
    if not data["subjects"]:
        return "Add at least one subject."
    if not data["rooms"]:
        return "Add at least one room."
    total = sum(s["lectures"] * (2 if s["is_lab"] else 1) for s in data["subjects"])
    capacity = len(DAYS) * len(SLOTS)
    if total > capacity:
        return f"A division needs {total} slots (a lab counts as 2) but only {capacity} exist per week."
    # room capacity: total lectures of a room type cannot exceed (rooms x slots per week)
    for lab in (False, True):
        need = sum(s["lectures"] * (2 if lab else 1) for s in data["subjects"]
                   if bool(s["is_lab"]) == lab) * len(data["divisions"])
        have = sum(1 for r in data["rooms"] if bool(r["is_lab"]) == lab) * capacity
        if need > have:
            kind = "lab" if lab else "theory"
            return (f"Not enough {kind} rooms: {need} {kind} lectures per week need "
                    f"{need} room-slots but only {have} exist. Add rooms or reduce lectures.")
    if any(s["is_lab"] for s in data["subjects"]) and not any(r["is_lab"] for r in data["rooms"]):
        return "A lab subject exists but there is no lab room."
    if any(not s["is_lab"] for s in data["subjects"]) and all(r["is_lab"] for r in data["rooms"]):
        return "Theory subjects exist but all rooms are lab rooms."
    return None


def expand_entries(sessions):
    """A lab session covers 2 slots: store/show one row per occupied slot."""
    rows = []
    for e in sessions:
        i = SLOTS.index(e["slot"])
        for k in range(e.get("length", 1)):
            rows.append({"division": e["division"], "subject": e["subject"],
                         "day": e["day"], "slot": SLOTS[i + k], "room": e["room"]})
    return rows


@app.route("/api/generate", methods=["POST"])
def generate():
    body = request.json or {}
    algo = body.get("algorithm", "fc")
    if algo not in ALGORITHMS:
        return error(f"algorithm must be one of {list(ALGORITHMS)}")

    data = load_solver_input()
    problem = pre_check(data)
    if problem:
        return error(problem)

    shuffle = bool(body.get("shuffle", True))
    attempts = max(1, min(int(body.get("attempts", 10)), 50)) if shuffle else 1
    base_seed = body.get("seed")
    if base_seed is None:
        base_seed = random.randrange(10 ** 6)

    # run the solver several times (different random value orders) and keep the timetable
    # with the lowest soft-constraint penalty ("best of N")
    best = None
    ran = 0
    for k in range(attempts):
        ran += 1
        solver = CSPSolver(data, shuffle=shuffle, seed=base_seed + k,
                           max_time=int(body.get("max_time", 30)),
                           use_soft=bool(body.get("soft", True)), **ALGORITHMS[algo])
        found, stats = solver.solve()
        if found is None:
            if best is None:
                stats["algorithm"] = algo
                return jsonify({
                    "error": "No valid timetable found (" + stats["status"] + "). "
                             "Try adding rooms, reducing lectures, or removing unavailable slots.",
                    "stats": stats}), 422
            break
        pen = solver.penalty(found)
        if best is None or pen["total"] < best[2]["total"]:
            best = (found, stats, pen, solver)
        if pen["total"] == 0:
            break

    session_entries, stats, pen, solver = best
    stats["algorithm"] = algo
    stats["attempts"] = ran
    stats["gaps"] = pen["gaps"]
    stats["overload"] = pen["overload"]
    stats["penalty"] = pen["total"]
    stats["violations"] = len(solver.verify(session_entries))
    entries = expand_entries(session_entries)

    # save to DB
    name = body.get("name") or "Timetable"
    conn = get_connection()
    cur = conn.execute("INSERT INTO timetables (name) VALUES (?)", (name,))
    tid = cur.lastrowid
    conn.executemany(
        "INSERT INTO timetable_entries (timetable_id, division, subject, day, slot, room) "
        "VALUES (?,?,?,?,?,?)",
        [(tid, e["division"], e["subject"], e["day"], e["slot"], e["room"]) for e in entries])
    conn.commit()
    conn.close()

    return jsonify({"timetable_id": tid, "stats": stats, "entries": entries}), 201


# ------------------------------------------------------------------
# SAVED TIMETABLES
# ------------------------------------------------------------------
@app.route("/api/timetables", methods=["GET"])
def list_timetables():
    return jsonify(fetch_all("SELECT * FROM timetables ORDER BY id DESC"))


@app.route("/api/timetables/<int:tid>", methods=["GET"])
def get_timetable(tid):
    info = fetch_all("SELECT * FROM timetables WHERE id = ?", (tid,))
    if not info:
        return error("Timetable not found", 404)
    entries = fetch_all(
        "SELECT division, subject, day, slot, room FROM timetable_entries WHERE timetable_id = ?",
        (tid,))
    return jsonify({"timetable": info[0], "entries": entries,
                    "days": DAYS, "slots": SLOTS})


@app.route("/api/timetables/<int:tid>", methods=["DELETE"])
def delete_timetable(tid):
    execute("DELETE FROM timetable_entries WHERE timetable_id = ?", (tid,))
    execute("DELETE FROM timetables WHERE id = ?", (tid,))
    return jsonify({"message": "Timetable deleted"})


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
