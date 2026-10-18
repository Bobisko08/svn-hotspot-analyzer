# SVN Hotspot Analyzer

A Python tool that reads a project's SVN history and shows where the codebase is risky: which files change most, which files keep needing bug fixes, and which parts of the code only one developer knows.

I built the original version during my IT internship at a logistics company, for the development manager of a large Java enterprise system. It analysed one to three years of SVN history together with ticket data from Jira and Bugzilla, and was designed so the team could keep running it after I left. This repository is a clean rewrite of the same idea with an invented repository history. It contains no company code or data.

## What it answers

For the last 1, 2 and 3 years:

- **Change hotspots** – the files with the most commits. Files that change all the time are where bugs and merge conflicts tend to appear.
- **Bug hotspots** – the files most often touched by bug-fix commits. A commit counts as a bug fix if its ticket is a bug or incident in the ticket export (`--tickets`), or, without an export, if its message contains words like *fix* or *bug*.
- **Knowledge risk (bus factor)** – files with 5 or more changes that only one developer has ever touched, and areas where one developer made 70% or more of the changes. If that person leaves, nobody else knows that code.

The output is a JSON file for further processing and a self-contained HTML report.

## How it works

1. `svn log -v` output is split into commits and parsed with regular expressions (revision, author, date, changed paths, message).
2. Ticket keys such as `APP-123` are extracted from commit messages and matched against the ticket export to tell bug fixes from features.
3. For each time window, `collections.Counter` objects count changes per file, bug fixes per file and changes per developer per file and per area.

## Run it

Requires Python 3.10 or newer. No third-party packages are needed.

```bash
python generate_sample_data.py      # fake svn log + ticket export in sample_data/
python hotspots.py sample_data/svn_log.txt --tickets sample_data/tickets.csv --out output
```

Open `output/hotspot_report.html` in a browser.

On a real repository:

```bash
svn log -v https://svn.example.com/repo/trunk > svn_log.txt
python hotspots.py svn_log.txt --out output
```

## Tests

```bash
pip install pytest
pytest
```

## What I learned

- Version control history is a useful data source in its own right: it shows where the real maintenance effort goes.
- Combining two systems (commits and tickets) gives much better answers than either one alone.
- A tool someone else will run needs to work with what they have, so the ticket export is optional and the tool falls back to commit messages.
