# Momentum — weekly to-dos & long-term tasks

A personal Flask application for daily planning, longer-term tasks, and the original
skill/activity tracking. Uses the existing Flask 3.0.3, Flask-SQLAlchemy 3.1.1,
SQLAlchemy 2.0.35, SQLite, Jinja2, Bootstrap 5 and Chart.js stack.

## Run

```bash
cd momentum
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app app run --host 127.0.0.1 --port 5000
```

Open http://127.0.0.1:5000. Set `SECRET_KEY` and optionally `DATABASE_URL` in the
environment. The default database is `momentum/instance/momentum.db`.
The app is single-user, like the original: no authentication or user accounts.

In the supplied workspace, offline dependencies are already available:

```bash
cd /home/administrator/cptr-workspace
PYTHONPATH="$PWD/.momentum-deps:$PWD/momentum" .venv-momentum/bin/python -m flask --app momentum/app run --host 127.0.0.1 --port 5000
```

## Daily workflow

- `/`: seven date-only to-do lists, Saturday–Friday, previous/next week and Today.
  Add a title directly to any day; complete/reopen using its checkbox. Counters update
  after the server confirms the write. Edit and delete controls are on each row.
- `/daily-tasks/<id>`: title, description, notes, priority, day, creation timestamp,
  optional link to a long-term task, completion, deletion and restoration.
- `/tasks`: active/all/status/archived filters and search.
- `/tasks/<id>`: dates, priority, status, manual or checklist-derived progress,
  checklist CRUD, chronological comments, activity history and linked daily tasks.
- `/skills`, `/activities`: original skill management and logged activity CRUD remain available.
  Statistics, streaks and charts are now above the weekly board; `/insights` redirects to `/`.

Completing a daily task or every checklist item never completes its parent automatically.
A Completed parent disappears from active lists and the weekly dashboard, along with its
linked daily tasks; its details, comments, checklist and history remain accessible in
Tasks → Completed. Reopen restores the previous status. Archive is reversible.
Deleting a daily task does not delete its parent. The deleted details page offers Restore.

Dates are Gregorian; the weekly board has no time grid, start/end times or event scheduler.
Project management and project associations are no longer available in the application.
Skills remain a separate feature; existing optional skill links on tasks are retained.

## Persistence & compatibility

All writes are validated by Flask and committed to SQLite. JS enhances quick add, completion
and deletion; ordinary forms still work when JS is disabled. Every mutation requires CSRF.
`POST /daily-tasks/quick-add` accepts title, date and csrf_token as form data.
`POST /daily-tasks/<id>/action` accepts action (`toggle`, `delete`, `restore`); toggle also
accepts completed (`0` or `1`) to make checkbox retries idempotent. `Accept: application/json`
returns JSON, otherwise the response redirects to a server-rendered page.
`POST /api/daily-tasks/<id>/move` accepts JSON `{"date":"2026-11-18"}` and `X-CSRF-Token`.
Older `/events/...` and `/api/events/.../move` URLs are compatibility aliases to date-only
operations; they no longer implement scheduling. `/projects` has been removed.

Migrations in `migrations/` are immutable, checksum-verified SQL applied transactionally
and recorded in `schema_migrations`. Migration 003 adds daily notes. Every pending upgrade
of an existing database first makes a SQLite backup next to that database. Upgrades run on
startup; `flask --app app upgrade-db` also checks them. SQLite is the supported database.
Legacy project tables, task project IDs, and event time columns remain untouched in storage
for preservation, but are not mapped or used by the active application. Existing timed entries
appear as daily to-dos on the same dates. Rollback requires the pre-upgrade DB backup and source.

## Visual design

Original `static/css/style.css` is unchanged. `refinement.css` is scoped to `.momentum-ui`
and refines the original violet `#6366f1`, cyan `#22d3ee`, pale background `#f5f6fa`, white
cards and 14px corners. Larger, colorful day cards use four columns on desktops and reflow to three, two and one column
as the viewport narrows. Reduced-motion and keyboard focus styles are included.

The requested `todolist.rar` was not available in this environment. The visual reference
used was the original `momentum.zip`; matching the unavailable RAR is not verified.
Bootstrap, Bootstrap Icons and Chart.js retain their original CDN dependencies.

## Verification

```bash
python -m unittest discover -s tests -v
```

35 integration tests use temporary on-disk SQLite databases: legacy activity/skill behavior,
week navigation, quick add, counters, JSON checkbox writes, CRUD, notes, comments, checklist,
status/reopen, completion independence, search-related views, escaping, CSRF, validation,
refresh persistence, and migration preservation (including populated legacy project/time data).
`VALIDATION.json` records the supplied-database comparison and verification results.
No browser runtime is installed and DNS prevented downloading one; actual browser layout,
mobile interaction and JS execution remain unverified. See `BROWSER-CHECKLIST.md` for smoke steps.

## Unified dashboard update

The four original stats appear first, followed by Minutes — Last 7 Days and the unchanged
Time Distribution by Skill doughnut. Weekly minute bars are stacked by skill with exact
logged-minute heights and each skill's configured color. Other existing reports remain
below the weekly board. Checking a task never invents duration; use Log Activity for minutes.

Migration 004 links daily tasks to skills and adds a `(skill_id, date)` default-generation
ledger. Opening a week creates one daily task for each existing skill on each day, once.
The ledger and task are committed together; unique keys prevent duplicates. Deleted or
moved defaults do not reappear on refresh, and adding a new skill fills that week's defaults
on the next visit. Removing a skill preserves its daily task text (skill_id becomes NULL).
The ledger remembers generation separately from tasks, so permanent deletion cannot cause
a previously offered default to be regenerated.

Tasks now have **Delete task permanently**, separate from Archive. The confirmation page
lists the affected comments, checklist, history and linked daily tasks. Confirming physically
deletes all those records in one database transaction, including soft-deleted daily children.
It does not delete independent skill activity logs or unrelated tasks. GET never deletes data;
POST requires CSRF and explicit confirmation. Completed and archived tasks can also be deleted.

The update archive intentionally excludes instance/ and databases: overlay the source files
onto your existing installation, keep your own database, restart and hard-refresh the browser.

## 2026-11 improvements

- `python app.py` now binds to 127.0.0.1 with debug off (set `FLASK_DEBUG=1` for development).
  The secret key is generated once per install and stored in `instance/secret.key` (or set `SECRET_KEY`).
- Skills with logged activities can no longer be deleted; archive them instead (history preserved,
  hidden from dashboard/charts/daily lists, restorable). Migration 006 adds `skills.archived` and
  `skills.weekly_target_minutes`.
- Weekly goals: set a target in minutes per skill (Edit skill). The dashboard shows this
  Saturday–Friday week's minutes vs target with a progress bar, and flags skills idle for 7+ days.
- Export: `GET /export/activities.csv` (all activities as CSV) and `GET /export/database`
  (download a copy of the SQLite file). Buttons on the Activities and Skills pages.
- Activities list is paginated (25 per page). The 14-day trend chart uses one grouped query.
- Tests: 41 total (`tests/test_planning.py` + `tests/test_improvements.py`).
