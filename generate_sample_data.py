"""Create a fake `svn log -v` history and a fake ticket export.

The repository layout, developer names and tickets are all invented.
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

AREAS = {
    "billing": ["Invoice", "TaxCalculator", "CreditNote", "PaymentRun"],
    "booking": ["BookingService", "BookingValidator", "ContainerAssignment"],
    "customs": ["CustomsDeclaration", "TariffLookup", "ExportFiling"],
    "reporting": ["MonthlyReport", "ExcelExport"],
    "auth": ["LoginController", "PermissionCheck"],
    "edi": ["EdiParser", "EdiMapper"],
}
DEVELOPERS = ["alice", "ben", "chen", "dara", "emre", "farah"]
# Some areas are mostly looked after by one person, which is what the tool should notice.
AREA_OWNERS = {"customs": "chen", "auth": "farah"}
ONLY_ONE_DEVELOPER = {"edi": "emre"}  # nobody else has ever touched this code
HOT_FILES = {"Invoice", "BookingService", "CustomsDeclaration"}
SUMMARIES = ["rounding in totals", "null check on empty orders", "date format in export", "timeout on large requests",
             "wrong currency code", "missing validation", "duplicate rows", "slow query"]


def file_path(area: str, cls: str) -> str:
    return f"/trunk/src/main/java/com/example/app/{area}/{cls}.java"


def generate(count: int = 1500, seed: int = 3):
    rng = random.Random(seed)
    end = date(2026, 9, 30)
    tickets = {}
    entries = []
    for revision in range(10000, 10000 + count):
        area = rng.choice(list(AREAS))
        classes = AREAS[area]
        weights = [5 if c in HOT_FILES else 1 for c in classes]
        changed = set(rng.choices(classes, weights=weights, k=rng.randint(1, 3)))
        owner = AREA_OWNERS.get(area)
        author = owner if owner and rng.random() < 0.85 else rng.choice(DEVELOPERS)
        author = ONLY_ONE_DEVELOPER.get(area, author)
        day = end - timedelta(days=rng.randint(0, 3 * 365))

        key = f"APP-{rng.randint(100, 2999)}"
        kind = rng.choices(["bug", "story", "task", "incident"], weights=[4 if HOT_FILES & changed else 2, 4, 2, 1])[0]
        tickets[key] = kind
        verb = "Fix" if kind in {"bug", "incident"} else rng.choice(["Add", "Update", "Refactor"])
        message = f"{key} {verb} {rng.choice(SUMMARIES)}"
        paths = "\n".join(f"   {rng.choice('MMMA')} {file_path(area, c)}" for c in sorted(changed))
        entries.append((revision, author, day, paths, message))

    entries.sort(key=lambda e: e[0], reverse=True)
    lines = []
    for revision, author, day, paths, message in entries:
        lines += ["-" * 72, f"r{revision} | {author} | {day.isoformat()} 10:00:00 +0000 | 1 line", "Changed paths:", paths, "", message]
    lines.append("-" * 72)
    return "\n".join(lines) + "\n", tickets


if __name__ == "__main__":
    log, tickets = generate()
    out = Path("sample_data")
    out.mkdir(exist_ok=True)
    (out / "svn_log.txt").write_text(log, encoding="utf-8")
    with (out / "tickets.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["key", "type"])
        writer.writerows(sorted(tickets.items()))
    print("wrote sample_data/svn_log.txt and sample_data/tickets.csv")
