# CLAUDE.md — decisions and lessons

Read PLAN.md first. This file records **what we decided and why**, plus lessons learned while running the loop. Newest entries go at the top of each section.

## Scope gate

- Build order agreed: **M1 → M3 → M2**, then M4, M5.
- **Do not build past M1 until Deividas confirms.** Next up after confirmation: M3 (tracker + dashboard).
- Don't automate a step until it has been done by hand at least 5 times (PLAN §3).

## Conventions

- Python 3.11+, **stdlib only** for now (sqlite3, argparse, unittest). Add dependencies only when a milestone needs them (FastAPI for M3, Whisper and ffmpeg for M2).
- Run with `python -m clipper …`. `pip install -e .` gives you a `clipper` command.
- DB: `data/clipper.db` (gitignored). Override with `CLIPPER_DB`.
- Footage, clips, screenshots and the DB are never committed.
- Tests: `python -m unittest`. Each test uses a temp DB.

## Decisions

### 2026-11-10 — Post URL normalisation + Whop link timing
- **Post URLs are normalised before the duplicate check, and the normalised form is what's stored** (`clipper/urls.py`): force https, lowercase the host, drop the query string, fragment and trailing slash. Path case is kept because Shorts and Reels IDs are case-sensitive.
  - Exception: on `youtube.com/watch` URLs the `v=` param is kept, since it *is* the video ID. Stripping it would make every watch URL look like the same post.
  - `vm.tiktok.com` / `vt.tiktok.com` short links are expanded by following redirects (needs network), then normalised. If expansion fails, or lands on something that isn't `/video/<id>` or `/photo/<id>`, `post add` **errors out** and asks for the full URL rather than storing a short link that would defeat the duplicate check. This is the one place the CLI blocks instead of warning, and the workaround is just to paste the full URL.
  - Rows logged before this change were not re-normalised (no migration). The loop hadn't started yet, so it wasn't needed.
- **Whop warning also fires when `posted_at` < `whop_linked_at`**, not only when the account is unlinked. Both are ISO UTC text, so a string comparison is a time comparison. `account link` defaults to *now*, so if you linked in Whop earlier than you logged it, pass `--at` or you'll get false warnings.

### 2026-11-10 — M1 schema + CLI
- **Schema = PLAN §4 plus some extras:**
  - `accounts` table (platform, handle, `whop_linked_at`). `posts.account_id` references it, replacing free-text `posts.account`. Why: unlinked accounts are a top rejection cause, and M0's "done" is "accounts linked to Whop", so this needs to be queryable.
  - `campaigns.required_tags`: comma list, checked against captions on `post add`. Why: missing hashtags or credits is a common rejection.
  - `campaigns.currency` and `campaigns.budget_checked_at`, so the CLI can warn when a budget is stale (over 24h) before posting.
  - `submissions.decided_at`, so we can measure how long approvals take.
  - `clips.created_at`.
  - `time_log.activity` also allows `edit`, for manual cutting time in M1.
- `submissions.post_id` is **UNIQUE** (one submission per post). Submission commands take the **post id**, not the submission id, so there's one less id to track.
- `posts.post_url` is UNIQUE, to stop the same post being logged twice.
- Timestamps are stored as ISO-8601 UTC text. CLI `--at` input is treated as local time and converted.
- Money is stored as REAL in the campaign currency. That's fine at this scale; switch to integer cents if rounding ever shows up.
- Schema version lives in `PRAGMA user_version` (currently 1). Future changes become numbered migrations in `db.py`.
- **Guardrails warn, never block.** A post that happened must always be loggable, so the CLI prints `WARN:` to stderr instead.
- `clip add` defaults to `status=approved`, because M1 clips are hand-picked. M2's automated cutter will insert `candidate`.
- `post add` sets the clip to `posted` and prints the `submit add` command as a reminder (`--submitted` logs both at once).

## Open questions (verify while running M1)

- Does Whop expose a Content Rewards API? (Would automate Scout and Submit.)
- What view data does TikTok's API expose for our account?
- Instagram Reels publishing needs a Business or Creator account. Which one are we using?
- How exactly do campaigns define the view-tracking window? Record what we see in Lessons.
- TikTok short-link expansion is only tested with mocks. Check it works on a real `vm.tiktok.com` link during M1 (TikTok may treat the plain urllib request differently from a browser).

## Lessons (from running the loop)

_None yet. Add one after each M1 clip: rule surprises, rejection reasons, how long each step took._
