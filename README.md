# Clipping pipeline

Turns Content Rewards campaign footage into posted, submitted, tracked clips. See [PLAN.md](PLAN.md) for the full plan and [CLAUDE.md](CLAUDE.md) for decisions and lessons.

**Current milestone: M1 (manual end-to-end loop).** You cut and post by hand. The `clipper` CLI logs every step into SQLite.

## Layout

```
PLAN.md            the plan (source of scope)
CLAUDE.md          decisions + lessons log
clipper/
  schema.sql       SQLite schema (PLAN §4 + accounts table)
  db.py            connect / init / timestamp helpers
  cli.py           the `clipper` CLI
tests/             unittest end-to-end test of the M1 loop
data/clipper.db    the live DB (gitignored)
sources/           campaign source footage, sources/<campaign>/ (gitignored)
clips/             cut clips (gitignored)
screenshots/       24h / 72h / 7d proof screenshots (gitignored)
```

Planned later, not built yet: `dashboard/` (M3), `pipeline/` cut/format/score (M2), `publishers/` (M4).

## Setup

Python 3.11+, no dependencies.

```bash
python -m clipper init          # creates data/clipper.db
# optional: pip install -e .    # gives you a `clipper` command
```

Set `CLIPPER_DB=/path/to.db` to use a different DB file.

## The M1 loop

```bash
# M0: accounts (link to Whop BEFORE posting)
clipper account add tiktok @myhandle --whop-linked
clipper account add yt @myhandle
clipper account link 2                      # once you've linked it in Whop

# Scout: log a campaign
clipper campaign add "Podcast X" --rate 2 --budget 5000 --min 4 --max 300 \
  --platforms tt,yt,ig --tags "#ad,@podcastx" --rules "no reaction edits" --url https://whop.com/...
clipper campaign update 1 --budget-left 3200     # each posting session
clipper campaign list

# Source + cut
clipper source add 1 sources/podcastx/ep12.mp4 --duration 3600
clipper clip add 1 --source 1 --start 754 --end 790 --hook "He said WHAT" --file clips/podx-ep12-01.mp4

# Post, then submit straight away
clipper post add 1 tiktok https://www.tiktok.com/@myhandle/video/123 --caption "wild take #ad @podcastx"
clipper submit add 1
#   or: clipper post add ... --submitted   (logs both in one go)
clipper post list --unsubmitted              # money left on the table

# Track
clipper snap add 1 4500 --likes 310 --shot screenshots/post1-24h.png
clipper snap list 1

# Outcomes
clipper submit set 1 approved
clipper submit set 2 rejected --reason "missing credit tag"
clipper payout add 1 9.00
clipper time add 40 review
```

Platform names: `tiktok`/`tt`, `youtube`/`yt`/`shorts`, `instagram`/`ig`/`reels`. Times in `--at` accept `YYYY-MM-DD` or `YYYY-MM-DD HH:MM` (local time, stored as UTC).

Post URLs are normalised before storing: tracking params, trailing slash and fragment are stripped, and `vm.tiktok.com` short links are expanded (needs network). Logging the same post twice under a different URL is rejected.

`post add` prints **WARN** lines (and still logs the post) when:
- the account isn't linked to Whop, or the post is dated before the link (`account link <id> --at ...` to record when you really linked it)
- the platform isn't eligible for the campaign
- the caption is missing required tags or credits
- the campaign isn't active or its budget is used up
- the budget hasn't been checked in the last 24h
- the clip is already posted on that platform

## Tests

```bash
python -m unittest
```
