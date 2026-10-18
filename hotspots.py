"""Find risky areas of a codebase from its SVN history.

Reads the text output of `svn log -v` and answers three questions for the
last 1, 2 and 3 years:
  * Which files change most often?            (change hotspots)
  * Which files are touched by bug fixes most? (bug hotspots)
  * Which files and areas depend on one person? (knowledge risk / bus factor)

Commits are classified as bug fixes either from a ticket export
(`--tickets`, a CSV with `key,type`) or, if no export is given, from words
such as "fix" or "bug" in the commit message.
"""

from __future__ import annotations

import csv
import html
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

SEPARATOR = "-" * 72
HEADER_RE = re.compile(r"^r(\d+) \| ([^|]+?) \| (\d{4}-\d{2}-\d{2})")
PATH_RE = re.compile(r"^\s+[AMDR] (/\S+)")
TICKET_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
BUG_WORDS_RE = re.compile(r"\b(fix(es|ed)?|bug|hotfix|defect|incident)\b", re.I)

PERIODS = [("last_1_year", 365), ("last_2_years", 730), ("last_3_years", 1095)]
SOURCE_EXTENSIONS = (".java", ".py", ".js", ".ts", ".sql", ".xml")
MIN_CHANGES_FOR_RISK = 5


@dataclass
class Commit:
    revision: int
    author: str
    day: date
    paths: list[str]
    message: str

    @property
    def tickets(self) -> list[str]:
        return TICKET_RE.findall(self.message)


def parse_svn_log(text: str) -> list[Commit]:
    commits = []
    for block in text.split(SEPARATOR):
        lines = [line.rstrip("\n") for line in block.strip("\n").splitlines()]
        if not lines:
            continue
        header = HEADER_RE.match(lines[0])
        if not header:
            continue
        paths = [m.group(1) for line in lines[1:] if (m := PATH_RE.match(line))]
        # The message starts after the first blank line.
        try:
            blank = lines.index("", 1)
            message = "\n".join(lines[blank + 1:]).strip()
        except ValueError:
            message = ""
        commits.append(Commit(int(header.group(1)), header.group(2).strip(),
                              date.fromisoformat(header.group(3)), paths, message))
    return commits


def load_ticket_types(path: Path | None) -> dict[str, str]:
    if not path:
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["key"].strip(): row["type"].strip().lower() for row in csv.DictReader(handle)}


def is_bug_fix(commit: Commit, ticket_types: dict[str, str]) -> bool:
    if ticket_types and commit.tickets:
        return any(ticket_types.get(key) in {"bug", "incident"} for key in commit.tickets)
    return bool(BUG_WORDS_RE.search(commit.message))


def area_of(path: str) -> str:
    """The folder a file lives in, e.g. /trunk/src/billing/Invoice.java -> billing."""
    parts = [p for p in path.split("/") if p]
    return parts[-2] if len(parts) > 1 else "(root)"


def analyse(commits: list[Commit], ticket_types: dict[str, str] | None = None, top_n: int = 15) -> dict:
    ticket_types = ticket_types or {}
    newest = max((c.day for c in commits), default=date.today())
    report = {"newest_commit": newest.isoformat(), "total_commits": len(commits), "periods": {}}

    for name, days in PERIODS:
        start = newest - timedelta(days=days)
        window = [c for c in commits if c.day > start]
        changes, bug_changes = Counter(), Counter()
        file_authors: dict[str, Counter] = defaultdict(Counter)
        area_authors: dict[str, Counter] = defaultdict(Counter)
        bug_commits = 0

        for commit in window:
            bug = is_bug_fix(commit, ticket_types)
            bug_commits += bug
            for path in commit.paths:
                if not path.endswith(SOURCE_EXTENSIONS):
                    continue
                changes[path] += 1
                bug_changes[path] += bug
                file_authors[path][commit.author] += 1
                area_authors[area_of(path)][commit.author] += 1

        single_owner = []
        for path, authors in file_authors.items():
            if changes[path] >= MIN_CHANGES_FOR_RISK and len(authors) == 1:
                single_owner.append({"path": path, "changes": changes[path], "developer": next(iter(authors))})
        single_owner.sort(key=lambda row: -row["changes"])

        areas = []
        for area, authors in area_authors.items():
            total = sum(authors.values())
            primary, primary_count = authors.most_common(1)[0]
            areas.append({"area": area, "changes": total, "developers": len(authors),
                          "primary_developer": primary, "primary_share": round(100 * primary_count / total, 1)})
        areas.sort(key=lambda row: -row["changes"])

        report["periods"][name] = {
            "commits": len(window),
            "bug_fix_commits": bug_commits,
            "top_changed_files": [{"path": p, "changes": n, "developers": len(file_authors[p])} for p, n in changes.most_common(top_n)],
            "top_bug_files": [{"path": p, "bug_fixes": n, "changes": changes[p]} for p, n in bug_changes.most_common(top_n) if n],
            "single_developer_files": single_owner[:top_n],
            "single_developer_file_count": len(single_owner),
            "areas": areas,
        }
    return report


def render_html(report: dict) -> str:
    def table(headers: list[str], rows: list[list]) -> str:
        head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
        body = "".join("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in row) + "</tr>" for row in rows)
        return f"<div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"

    sections = []
    for name, _ in PERIODS:
        p = report["periods"][name]
        risky_areas = [a for a in p["areas"] if a["primary_share"] >= 70]
        sections.append(f"""
<section>
  <h2>{name.replace('_', ' ').title()}</h2>
  <p>{p['commits']} commits, {p['bug_fix_commits']} of them bug fixes. {p['single_developer_file_count']} files with {MIN_CHANGES_FOR_RISK}+ changes were only ever changed by one developer.</p>
  <h3>Most changed files</h3>
  {table(['File', 'Changes', 'Developers'], [[r['path'], r['changes'], r['developers']] for r in p['top_changed_files']])}
  <h3>Files most touched by bug fixes</h3>
  {table(['File', 'Bug fixes', 'All changes'], [[r['path'], r['bug_fixes'], r['changes']] for r in p['top_bug_files']])}
  <h3>Areas and ownership</h3>
  {table(['Area', 'Changes', 'Developers', 'Main developer', 'Main developer share %'], [[a['area'], a['changes'], a['developers'], a['primary_developer'], a['primary_share']] for a in p['areas']])}
  <h3>Knowledge risk: files only one developer has changed</h3>
  {table(['File', 'Changes', 'Developer'], [[r['path'], r['changes'], r['developer']] for r in p['single_developer_files']])}
  <p class="note">Areas where one developer made 70% or more of the changes: {html.escape(', '.join(a['area'] for a in risky_areas) or 'none')}.</p>
</section>""")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Codebase Hotspot Report</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 0 auto; max-width: 1000px; padding: 24px 16px; color: #1c2430; }}
  h1 {{ margin-bottom: 4px; }} h2 {{ margin-top: 36px; border-bottom: 2px solid #1f3a63; padding-bottom: 4px; }}
  .scroll {{ overflow-x: auto; }} table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
  th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid #dde2ea; }}
  th {{ background: #eef2f8; }} td:not(:first-child) {{ font-variant-numeric: tabular-nums; }}
  .note {{ color: #5d6879; }}
</style></head><body>
<h1>Codebase Hotspot Report</h1>
<p>{report['total_commits']} commits analysed, newest on {report['newest_commit']}.</p>
{''.join(sections)}
</body></html>"""


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Find change hotspots, bug hotspots and knowledge risk in an SVN history.")
    parser.add_argument("log", type=Path, help="text output of `svn log -v`")
    parser.add_argument("--tickets", type=Path, help="optional CSV export with columns key,type")
    parser.add_argument("--out", type=Path, default=Path("output"))
    args = parser.parse_args()

    commits = parse_svn_log(args.log.read_text(encoding="utf-8", errors="replace"))
    report = analyse(commits, load_ticket_types(args.tickets))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "hotspots.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (args.out / "hotspot_report.html").write_text(render_html(report), encoding="utf-8")
    last = report["periods"]["last_1_year"]
    print(f"{len(commits)} commits parsed. Last year: {last['commits']} commits, {last['bug_fix_commits']} bug fixes, "
          f"{last['single_developer_file_count']} single-developer files.")
    print(f"Report: {args.out / 'hotspot_report.html'}")


if __name__ == "__main__":
    main()
