"""Bias-audit logic using ONLY the Python standard library (no pandas, numpy, pydantic).
Works on locked-down Windows PCs where compiled packages are blocked."""
import csv
import io
import math
import random
import re

PROT = [
    ("Gender", r"gender|(^|[_\s])sex($|[_\s])"),
    ("Age", r"(^|[_\s])age($|[_\s])"),
    ("Race", r"race|ethnic"),
    ("Religion", r"religio"),
    ("Socioeconomic", r"income|salary|wealth|socio"),
    ("Marital status", r"marital"),
    ("Disability", r"disab"),
    ("Nationality", r"national|citizen|origin"),
]
OUT_RE = r"approv|outcome|decision|hired|selected|target|label|admit|result|status|default|accept|shortlist"
POS_RE = r"^(1|yes|y|true|approved|approve|hired|accepted|admitted|selected|pass|passed|positive|granted|good)$"
AGE_RE = r"(^|[_\s])age($|[_\s])"


def protected_name(col):
    for name, pat in PROT:
        if re.search(pat, col, re.I):
            return name
    return None


def read_table(raw: bytes):
    """Parse CSV bytes -> (header list, list of rows). Raises ValueError on bad input."""
    text = raw.decode("utf-8-sig", errors="replace")
    first = text.split("\n", 1)[0]
    delim = max(",;\t", key=first.count)
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if r]
    if not rows:
        raise ValueError("The file is empty.")
    head = [h.strip() for h in rows[0]]
    body = [r for r in rows[1:] if len(r) == len(head)]
    if len(head) < 2:
        raise ValueError("The file needs at least 2 columns.")
    if len(body) < 10:
        raise ValueError("The file needs at least 10 rows of data.")
    return head, body


def guess_outcome(head):
    for c in head:
        if re.search(OUT_RE, c, re.I) and protected_name(c) is None:
            return c
    return head[-1]


def guess_favourable(values):
    vals = sorted({(v or "").strip() for v in values if (v or "").strip()})
    for v in vals:
        if re.match(POS_RE, v, re.I):
            return v
    return vals[-1] if vals else ""


def group_rates(head, rows, ci, oi, fav):
    """Favourable-outcome rate per group, best group first. None if untestable."""
    vals = [(r[ci] or "").strip() for r in rows]
    nums, allnum = [], True
    for v in vals:
        try:
            nums.append(float(v))
        except ValueError:
            allnum = False
            break
    uniq = set(vals)
    if allnum and len(uniq) > 8:
        if re.search(AGE_RE, head[ci], re.I):
            def lab(x):
                return "Under 25" if x < 25 else "25–44" if x < 45 else "45–59" if x < 60 else "60+"
        else:
            s = sorted(nums)
            q1, q2 = s[len(s) // 3], s[2 * len(s) // 3]

            def lab(x):
                return "Lowest third" if x < q1 else "Middle third" if x < q2 else "Top third"
        keys = [lab(x) for x in nums]
    elif len(uniq) > 12:
        return None
    else:
        keys = vals
    tally = {}
    for key, r in zip(keys, rows):
        if key == "":
            continue
        t = tally.setdefault(key, [0, 0])
        t[0] += 1
        if (r[oi] or "").strip() == fav:
            t[1] += 1
    out = [{"label": k, "n": n, "rate": p / n} for k, (n, p) in tally.items() if n >= 5]
    out.sort(key=lambda g: -g["rate"])
    return out if len(out) >= 2 else None


def run_audit(head, rows, name="dataset.csv", outcome=None, fav=None, attrs=None):
    if outcome not in head:
        outcome = guess_outcome(head)
    oi = head.index(outcome)
    if not fav:
        fav = guess_favourable(r[oi] for r in rows)
    if attrs is None:
        attrs = [c for c in head if c != outcome and protected_name(c)]
    results = []
    for col in attrs:
        if col not in head or col == outcome:
            continue
        g = group_rates(head, rows, head.index(col), oi, fav)
        if not g:
            continue
        hi, lo = g[0], g[-1]
        ratio = lo["rate"] / hi["rate"] if hi["rate"] > 0 else 1.0
        score = max(0, min(100, math.floor((1 - ratio) * 100 + 0.5)))
        results.append({"name": protected_name(col) or col, "column": col, "groups": g,
                        "hi": hi, "lo": lo, "ratio": ratio, "score": score})
    results.sort(key=lambda a: -a["score"])
    rate = sum(1 for r in rows if (r[oi] or "").strip() == fav) / len(rows)
    return {"name": name, "n": len(rows), "cols": len(head), "rate": rate, "outcome": outcome,
            "fav": fav, "attrs": results,
            "score": results[0]["score"] if results else 0,
            "ratio": min(a["ratio"] for a in results) if results else 1.0}


def sample_csv(n=600, seed=42):
    """Synthetic loan data with deliberate bias against women, young/old and groups B, C."""
    rnd = random.Random(seed)
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["applicant_id", "gender", "age", "race", "income", "credit_score",
                "years_employed", "approved"])
    for i in range(1, n + 1):
        gender = "Female" if rnd.random() < .5 else "Male"
        age = rnd.randint(18, 69)
        rr = rnd.random()
        race = "Group A" if rr < .5 else "Group B" if rr < .8 else "Group C"
        income = rnd.randint(20, 119) * 1000
        credit = rnd.randint(520, 819)
        years = rnd.randint(0, 19)
        p = .2 + (credit - 520) / 300 * .4 + income / 400000
        if gender == "Female": p *= .6
        if age < 25 or age >= 60: p *= .75
        if race == "Group B": p *= .85
        if race == "Group C": p *= .8
        w.writerow([1000 + i, gender, age, race, income, credit, years,
                    "Approved" if rnd.random() < min(p, 1) else "Rejected"])
    return out.getvalue()
