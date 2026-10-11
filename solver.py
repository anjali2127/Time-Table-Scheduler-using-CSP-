"""
solver.py - Own CSP solver for the Time-Table Scheduler.

Pure Python: no Flask, no database code in here.
Input  : plain dict (days, slots, rooms, divisions, subjects, unavailable)
Output : list of timetable entries + statistics (nodes, backtracks, time)

CSP formulation
---------------
Variables : (division, subject, lecture_no)          e.g. ("CE-A", "AI", 1)
Domain    : (day, slot, room)                         e.g. ("Mon", "9-10", "R101")
Hard constraints
  C1  a division cannot have two lectures at the same time
  C2  a teacher cannot teach two lectures at the same time
  C3  a room cannot hold two lectures at the same time
  C4  the same subject cannot occur twice on the same day for a division
Unary constraints (applied before search)
  U1  lab subjects only in lab rooms, theory subjects only in normal rooms
  U2  teacher unavailable slots are removed
  U3  a lab session needs 2 consecutive slots (not across the lunch break)
Soft constraints (scored, not enforced): idle gaps in a day, too many lectures in a day
"""
import random
import time


class CSPSolver:
    def __init__(self, data, use_fc=True, use_soft=False, shuffle=False, seed=None, max_time=30):
        self.days = data["days"]
        self.slots = data["slots"]
        self.divisions = data["divisions"]
        self.subjects = data["subjects"]
        self.unavailable = data.get("unavailable", {})   # {teacher: [[day, slot], ...]}
        self.break_after = set(data.get("break_after", []))   # e.g. ["11-12"] = lunch after it
        self.max_per_day = data.get("max_per_day", 4)         # soft limit of lecture-slots per day
        self.slot_idx = {s: i for i, s in enumerate(self.slots)}

        # rooms can be plain names or dicts {"name":..., "is_lab":...}
        self.rooms = []
        for r in data["rooms"]:
            if isinstance(r, str):
                self.rooms.append({"name": r, "is_lab": False})
            else:
                self.rooms.append({"name": r["name"], "is_lab": bool(r.get("is_lab", 0))})

        # options (for comparing algorithms in the report)
        self.use_fc = use_fc
        self.use_soft = use_soft      # prefer values that keep a division's day compact
        self.shuffle = shuffle
        self.max_time = max_time
        self.rng = random.Random(seed)

        # statistics
        self.nodes = 0
        self.backtracks = 0
        self.time_taken = 0.0
        self.timed_out = False

        self._build_csp()

    # ------------------------------------------------------------------
    # 1. BUILD VARIABLES AND DOMAINS
    # ------------------------------------------------------------------
    def _build_csp(self):
        self.teacher_of = {s["name"]: s["teacher"] for s in self.subjects}
        self.variables = []
        self.domains = {}
        self.length = {}          # slots occupied by a variable: 1 (theory) or 2 (lab)

        for div in self.divisions:
            # labs are placed first: they need two consecutive slots, so they are the hardest to fit
            for sub in sorted(self.subjects, key=lambda x: not x.get("is_lab", 0)):
                is_lab = bool(sub.get("is_lab", 0))
                size = 2 if is_lab else 1
                busy = {tuple(x) for x in self.unavailable.get(sub["teacher"], [])}

                # domain = all (day, start_slot, room) that satisfy the unary constraints
                domain = []
                for day in self.days:
                    for i, slot in enumerate(self.slots):
                        covered = self.slots[i:i + size]
                        if len(covered) < size:                          # U3: runs past last slot
                            continue
                        if size == 2 and slot in self.break_after:       # U3: lunch in between
                            continue
                        if any((day, c) in busy for c in covered):       # U2
                            continue
                        for room in self.rooms:
                            if room["is_lab"] != is_lab:                 # U1
                                continue
                            domain.append((day, slot, room["name"]))

                for n in range(1, sub["lectures"] + 1):
                    var = (div, sub["name"], n)
                    self.variables.append(var)
                    self.domains[var] = list(domain)
                    self.length[var] = size

    # ------------------------------------------------------------------
    # 2. CONSTRAINT CHECK (binary)
    # ------------------------------------------------------------------
    def conflicts(self, v1, val1, v2, val2):
        """True if giving v1=val1 and v2=val2 breaks a hard constraint."""
        d1, s1, r1 = val1
        d2, s2, r2 = val2
        if d1 != d2:
            return False                                             # different days: no clash
        i1, i2 = self.slot_idx[s1], self.slot_idx[s2]
        overlap = i1 < i2 + self.length[v2] and i2 < i1 + self.length[v1]
        if overlap:                                                  # share a time slot
            if v1[0] == v2[0]:                                       # C1 division
                return True
            if self.teacher_of[v1[1]] == self.teacher_of[v2[1]]:     # C2 teacher
                return True
            if r1 == r2:                                             # C3 room
                return True
        if v1[0] == v2[0] and v1[1] == v2[1]:                        # C4 same subject, same day
            return True
        return False

    def _consistent(self, var, val, assignment):
        for other, oval in assignment.items():
            if self.conflicts(var, val, other, oval):
                return False
        return True

    # ------------------------------------------------------------------
    # 3. VARIABLE AND VALUE ORDER
    # ------------------------------------------------------------------
    def _select_var(self, assignment, domains):
        """Variables are taken in a fixed order: division by division, labs first, then theory."""
        for v in self.variables:
            if v not in assignment:
                return v

    def _order_values(self, var, assignment, domains):
        values = list(domains[var])
        if self.shuffle:
            self.rng.shuffle(values)                                 # random order of values
        if self.use_soft:                                            # soft constraints as value order
            values.sort(key=self._soft_cost_fn(var, assignment))     # (stable: keeps shuffle ties)
        return values

    def _soft_cost_fn(self, var, assignment):
        """Cost of putting `var` at a value, from the soft constraints only:
        new idle gaps + 2 x overload (+ tiny term to spread lectures over days)."""
        size = self.length[var]
        used = {}                                                    # day -> occupied slot indexes
        for other, oval in assignment.items():
            if other[0] == var[0]:
                for k in range(self.length[other]):
                    used.setdefault(oval[0], set()).add(self.slot_idx[oval[1]] + k)

        def cost(val):
            day, slot, _room = val
            occ = used.get(day, set())
            new = occ | {self.slot_idx[slot] + k for k in range(size)}
            gaps_before = (max(occ) - min(occ) + 1 - len(occ)) if occ else 0
            gaps_after = max(new) - min(new) + 1 - len(new)
            over = max(0, len(new) - self.max_per_day) - max(0, len(occ) - self.max_per_day)
            return (gaps_after - gaps_before) + 2 * over + 0.01 * len(occ)
        return cost

    # ------------------------------------------------------------------
    # 4. FORWARD CHECKING
    # ------------------------------------------------------------------
    def _forward_check(self, var, val, assignment, domains):
        """Remove conflicting values from unassigned domains.
        Returns (ok, removed). ok=False if some domain became empty."""
        removed = []
        for u in self.variables:
            if u in assignment:
                continue
            bad = [x for x in domains[u] if self.conflicts(var, val, u, x)]
            for x in bad:
                domains[u].remove(x)
                removed.append((u, x))
            if not domains[u]:
                return False, removed
        return True, removed

    @staticmethod
    def _restore(removed, domains):
        for u, uval in removed:
            if uval not in domains[u]:
                domains[u].append(uval)

    # ------------------------------------------------------------------
    # 5. BACKTRACKING SEARCH
    # ------------------------------------------------------------------
    def _backtrack(self, assignment, domains):
        if len(assignment) == len(self.variables):
            return True
        if time.time() - self._start > self.max_time:
            self.timed_out = True
            return False

        var = self._select_var(assignment, domains)
        for val in self._order_values(var, assignment, domains):
            self.nodes += 1
            if not self._consistent(var, val, assignment):
                continue

            assignment[var] = val
            removed = []
            ok = True
            if self.use_fc:
                ok, removed = self._forward_check(var, val, assignment, domains)

            if ok and self._backtrack(assignment, domains):
                return True

            if self.use_fc:
                self._restore(removed, domains)
            del assignment[var]
            if self.timed_out:
                return False

        self.backtracks += 1
        return False

    # ------------------------------------------------------------------
    # 6. PUBLIC API
    # ------------------------------------------------------------------
    def solve(self):
        self.nodes = 0
        self.backtracks = 0
        self.timed_out = False
        domains = {v: list(d) for v, d in self.domains.items()}

        if any(len(d) == 0 for d in domains.values()):
            return None, self.stats("empty domain")

        self._start = time.time()
        assignment = {}
        found = self._backtrack(assignment, domains)
        self.time_taken = time.time() - self._start

        if not found:
            return None, self.stats("timeout" if self.timed_out else "no solution")

        entries = [
            {"division": v[0], "subject": v[1], "lecture": v[2],
             "day": val[0], "slot": val[1], "room": val[2], "length": self.length[v]}
            for v, val in assignment.items()
        ]
        entries.sort(key=lambda e: (e["division"], self.days.index(e["day"]),
                                    self.slots.index(e["slot"])))
        self.assignment = assignment
        return entries, self.stats("solved")

    def stats(self, status):
        return {"status": status, "variables": len(self.variables),
                "nodes": self.nodes, "backtracks": self.backtracks,
                "time_sec": round(self.time_taken, 4)}

    def verify(self, entries):
        """Independent check: returns list of violated hard constraints (empty = valid)."""
        problems = []
        items = [((e["division"], e["subject"], e["lecture"]),
                  (e["day"], e["slot"], e["room"])) for e in entries]
        for var, val in items:                                       # unary constraints
            if val not in self.domains[var]:
                problems.append((var, val, "unary constraint"))
        for i in range(len(items)):                                  # binary constraints
            for j in range(i + 1, len(items)):
                if self.conflicts(items[i][0], items[i][1], items[j][0], items[j][1]):
                    problems.append((items[i], items[j]))
        return problems

    # ------------------------------------------------------------------
    # 7. SOFT CONSTRAINTS (score only; lower is better)
    # ------------------------------------------------------------------
    def penalty(self, entries):
        """gaps     = empty slots between the first and last lecture of a day (per division)
           overload = lecture-slots above max_per_day in a day (per division)
           total    = gaps + 2 * overload"""
        used = {}
        for e in entries:
            i = self.slot_idx[e["slot"]]
            for k in range(e.get("length", 1)):
                used.setdefault((e["division"], e["day"]), set()).add(i + k)
        gaps = overload = 0
        for slots in used.values():
            gaps += (max(slots) - min(slots) + 1) - len(slots)
            overload += max(0, len(slots) - self.max_per_day)
        return {"gaps": gaps, "overload": overload, "total": gaps + 2 * overload}
