import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hotspots import Commit, analyse, area_of, is_bug_fix, parse_svn_log  # noqa: E402

LOG = """------------------------------------------------------------------------
r12 | alice | 2026-09-01 10:00:00 +0000 | 1 line
Changed paths:
   M /trunk/src/main/java/com/example/app/billing/Invoice.java
   A /trunk/src/main/java/com/example/app/billing/Tax.java

APP-7 Fix rounding in invoice totals
------------------------------------------------------------------------
r11 | ben | 2026-08-01 09:00:00 +0000 | 1 line
Changed paths:
   M /trunk/src/main/java/com/example/app/booking/BookingService.java

APP-8 Add booking validation
------------------------------------------------------------------------
"""


def test_parse_svn_log():
    commits = parse_svn_log(LOG)
    assert [c.revision for c in commits] == [12, 11]
    assert commits[0].author == "alice"
    assert commits[0].day == date(2026, 9, 1)
    assert len(commits[0].paths) == 2
    assert commits[0].tickets == ["APP-7"]


def test_bug_fix_detection_with_and_without_tickets():
    commit = parse_svn_log(LOG)[1]
    assert not is_bug_fix(commit, {})
    assert is_bug_fix(commit, {"APP-8": "bug"})
    assert is_bug_fix(parse_svn_log(LOG)[0], {})


def test_area_of_path():
    assert area_of("/trunk/src/main/java/com/example/app/billing/Invoice.java") == "billing"
    assert area_of("/trunk/src/billing/Invoice.java") == "billing"


def test_single_developer_files_are_reported():
    commits = [Commit(i, "chen", date(2026, 9, i + 1), ["/trunk/src/customs/Declaration.java"], "update") for i in range(6)]
    period = analyse(commits)["periods"]["last_1_year"]
    assert period["single_developer_files"][0]["developer"] == "chen"
    assert period["areas"][0]["primary_share"] == 100.0
