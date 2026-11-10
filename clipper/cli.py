"""clipper — tiny CLI for logging the manual M1 loop into SQLite.

Run `python -m clipper --help` (or `clipper --help` after `pip install -e .`).
Guardrail checks print WARN lines but never block logging: a post that
happened must always be recordable.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

from . import db

PLATFORM_ALIASES = {
    "tiktok": "tiktok", "tt": "tiktok",
    "youtube": "youtube", "yt": "youtube", "shorts": "youtube",
    "instagram": "instagram", "ig": "instagram", "reels": "instagram",
}
BUDGET_STALE_HOURS = 24


# ---------- helpers ----------

def platform(value: str) -> str:
    key = value.strip().lower()
    if key not in PLATFORM_ALIASES:
        raise argparse.ArgumentTypeError(
            f"unknown platform {value!r} (use tiktok/youtube/instagram or tt/yt/ig)")
    return PLATFORM_ALIASES[key]


def platform_list(value: str) -> str:
    return ",".join(sorted({platform(p) for p in value.split(",") if p.strip()}))


def ts(value: str) -> str:
    try:
        return db.normalize_ts(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


def split_csv(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def warn(msg: str) -> None:
    print(f"WARN: {msg}", file=sys.stderr)


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def get_one(conn, table: str, row_id: int) -> sqlite3.Row:
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    if row is None:
        die(f"no {table[:-1] if table.endswith('s') else table} with id {row_id}")
    return row


def print_table(rows, columns: list[str]) -> None:
    rows = [["" if r[c] is None else str(r[c]) for c in columns] for r in rows]
    if not rows:
        print("(none)")
        return
    widths = [max(len(c), *(len(r[i]) for r in rows)) for i, c in enumerate(columns)]
    widths = [min(w, 48) for w in widths]
    fmt = "  ".join(f"{{:<{w}.{w}}}" for w in widths)
    print(fmt.format(*columns))
    print(fmt.format(*("-" * w for w in widths)))
    for r in rows:
        print(fmt.format(*r))


def insert(conn, table: str, values: dict) -> int:
    values = {k: v for k, v in values.items() if v is not None}
    cols = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    cur = conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(values.values()))
    conn.commit()
    return cur.lastrowid


def update(conn, table: str, row_id: int, values: dict) -> None:
    values = {k: v for k, v in values.items() if v is not None}
    if not values:
        die("nothing to update")
    sets = ", ".join(f"{k} = ?" for k in values)
    conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*values.values(), row_id))
    conn.commit()


def parse_utc(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


# ---------- init ----------

def cmd_init(conn, args):
    print(f"DB ready at {db.db_path()}")


# ---------- accounts ----------

def cmd_account_add(conn, args):
    new_id = insert(conn, "accounts", {
        "platform": args.platform, "handle": args.handle,
        "whop_linked_at": db.now_utc() if args.whop_linked else None,
        "notes": args.notes,
    })
    print(f"account {new_id} added ({args.platform} {args.handle})")
    if not args.whop_linked:
        warn("not linked to Whop yet — link it BEFORE the first post, then run "
             f"`clipper account link {new_id}`")


def cmd_account_link(conn, args):
    get_one(conn, "accounts", args.id)
    update(conn, "accounts", args.id, {"whop_linked_at": args.at or db.now_utc()})
    print(f"account {args.id} marked as Whop-linked")


def cmd_account_list(conn, args):
    rows = conn.execute("SELECT * FROM accounts ORDER BY platform, id").fetchall()
    print_table(rows, ["id", "platform", "handle", "whop_linked_at", "notes"])


# ---------- campaigns ----------

def campaign_values(args) -> dict:
    return {
        "name": getattr(args, "name", None),
        "url": args.url,
        "rate_per_1k": args.rate,
        "budget_total": args.budget,
        "budget_left": args.budget_left,
        "min_payout": args.min_payout,
        "max_payout": args.max_payout,
        "currency": args.currency,
        "platforms": args.platforms,
        "required_tags": args.tags,
        "rules_notes": args.rules,
        "source_provided": None if args.source_provided is None else int(args.source_provided),
    }


def cmd_campaign_add(conn, args):
    values = campaign_values(args)
    if values["budget_left"] is None and values["budget_total"] is not None:
        values["budget_left"] = values["budget_total"]
    if values["budget_left"] is not None:
        values["budget_checked_at"] = db.now_utc()
    new_id = insert(conn, "campaigns", values)
    print(f"campaign {new_id} added: {args.name} @ {args.rate}/1k")
    if args.rate > 3:
        warn("rate above ~$3/1k usually means stricter rules — read them carefully")


def cmd_campaign_update(conn, args):
    get_one(conn, "campaigns", args.id)
    values = campaign_values(args)
    values["name"] = args.rename
    values["status"] = args.status
    if args.budget_left is not None:
        values["budget_checked_at"] = db.now_utc()
    update(conn, "campaigns", args.id, values)
    print(f"campaign {args.id} updated")


def cmd_campaign_list(conn, args):
    where = "" if args.all else "WHERE status = 'active'"
    rows = conn.execute(f"SELECT * FROM campaigns {where} ORDER BY id").fetchall()
    print_table(rows, ["id", "name", "status", "rate_per_1k", "budget_left", "min_payout",
                       "max_payout", "platforms", "required_tags", "budget_checked_at"])


# ---------- sources ----------

def cmd_source_add(conn, args):
    get_one(conn, "campaigns", args.campaign)
    new_id = insert(conn, "sources", {
        "campaign_id": args.campaign, "path_or_url": args.path, "duration_s": args.duration})
    print(f"source {new_id} added")


def cmd_source_list(conn, args):
    sql = "SELECT * FROM sources"
    params = ()
    if args.campaign:
        sql += " WHERE campaign_id = ?"
        params = (args.campaign,)
    print_table(conn.execute(sql + " ORDER BY id", params).fetchall(),
                ["id", "campaign_id", "path_or_url", "duration_s", "added_at"])


# ---------- clips ----------

def cmd_clip_add(conn, args):
    get_one(conn, "campaigns", args.campaign)
    if args.source:
        src = get_one(conn, "sources", args.source)
        if src["campaign_id"] != args.campaign:
            warn(f"source {args.source} belongs to campaign {src['campaign_id']}, "
                 f"not {args.campaign} — wrong source material gets rejected")
    new_id = insert(conn, "clips", {
        "campaign_id": args.campaign, "source_id": args.source,
        "start_s": args.start, "end_s": args.end, "hook_text": args.hook,
        "file_path": args.file, "virality_score": args.score, "status": args.status,
    })
    print(f"clip {new_id} added ({args.status})")
    if args.start is not None and args.end is not None and not 15 <= args.end - args.start <= 60:
        warn(f"clip is {args.end - args.start:.0f}s — plan targets 15–60s")


def cmd_clip_set(conn, args):
    get_one(conn, "clips", args.id)
    update(conn, "clips", args.id, {"status": args.status, "virality_score": args.score,
                                    "hook_text": args.hook, "file_path": args.file})
    print(f"clip {args.id} updated")


def cmd_clip_list(conn, args):
    sql = "SELECT * FROM clips WHERE 1=1"
    params: list = []
    if args.campaign:
        sql += " AND campaign_id = ?"
        params.append(args.campaign)
    if args.status:
        sql += " AND status = ?"
        params.append(args.status)
    print_table(conn.execute(sql + " ORDER BY id", params).fetchall(),
                ["id", "campaign_id", "status", "start_s", "end_s", "virality_score",
                 "hook_text", "file_path"])


# ---------- posts ----------

def resolve_account(conn, plat: str, account_arg: str | None) -> sqlite3.Row:
    if account_arg:
        if account_arg.isdigit():
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (int(account_arg),)).fetchone()
        else:
            row = conn.execute("SELECT * FROM accounts WHERE platform = ? AND handle = ?",
                               (plat, account_arg)).fetchone()
        if row is None:
            die(f"no account {account_arg!r} — add it with `clipper account add`")
        if row["platform"] != plat:
            die(f"account {row['id']} is a {row['platform']} account, not {plat}")
        return row
    rows = conn.execute("SELECT * FROM accounts WHERE platform = ?", (plat,)).fetchall()
    if len(rows) == 1:
        return rows[0]
    if not rows:
        die(f"no {plat} account yet — run `clipper account add {plat} <handle>` first")
    die(f"several {plat} accounts — pass --account")


def post_guardrails(conn, clip, camp, acct, plat: str, caption: str | None) -> None:
    if acct["whop_linked_at"] is None:
        warn(f"account {acct['handle']} is NOT linked to Whop — views may be unverifiable")
    if camp["status"] != "active":
        warn(f"campaign '{camp['name']}' is {camp['status']}")
    if plat not in split_csv(camp["platforms"]):
        warn(f"campaign '{camp['name']}' doesn't list {plat} as eligible ({camp['platforms']})")
    tags = split_csv(camp["required_tags"])
    missing = [t for t in tags if t.lower() not in (caption or "").lower()]
    if missing:
        warn(f"caption is missing required tags/credits: {', '.join(missing)}")
    if camp["budget_left"] is not None and camp["budget_left"] <= 0:
        warn("campaign budget is used up — posts after this may not get paid")
    checked = camp["budget_checked_at"]
    if checked is None or datetime.now(timezone.utc) - parse_utc(checked) > timedelta(hours=BUDGET_STALE_HOURS):
        warn(f"budget not checked in the last {BUDGET_STALE_HOURS}h — "
             f"`clipper campaign update {camp['id']} --budget-left N`")
    if clip["status"] == "rejected":
        warn(f"clip {clip['id']} was marked rejected")
    dup = conn.execute("SELECT id FROM posts WHERE clip_id = ? AND platform = ?",
                       (clip["id"], plat)).fetchone()
    if dup:
        warn(f"clip {clip['id']} is already posted on {plat} (post {dup['id']}) — "
             "duplicates get rejected")


def cmd_post_add(conn, args):
    clip = get_one(conn, "clips", args.clip)
    camp = get_one(conn, "campaigns", clip["campaign_id"])
    acct = resolve_account(conn, args.platform, args.account)
    post_guardrails(conn, clip, camp, acct, args.platform, args.caption)
    try:
        new_id = insert(conn, "posts", {
            "clip_id": clip["id"], "platform": args.platform, "account_id": acct["id"],
            "post_url": args.url, "caption": args.caption, "posted_at": args.at,
        })
    except sqlite3.IntegrityError:
        die(f"post URL already logged: {args.url}")
    conn.execute("UPDATE clips SET status = 'posted' WHERE id = ?", (clip["id"],))
    conn.commit()
    print(f"post {new_id} logged ({args.platform}, {acct['handle']})")
    if args.submitted:
        insert(conn, "submissions", {"post_id": new_id, "submitted_at": args.at})
        print(f"submission logged for post {new_id}")
    else:
        print(f">>> Submit it to the campaign NOW, then: clipper submit add {new_id}")


POST_LIST_SQL = """
SELECT p.id, p.platform, a.handle, c.name AS campaign, p.posted_at, p.post_url,
       COALESCE(s.status, 'NOT SUBMITTED') AS submission,
       (SELECT views FROM view_snaps v WHERE v.post_id = p.id
        ORDER BY taken_at DESC, v.id DESC LIMIT 1) AS last_views
FROM posts p
JOIN accounts a  ON a.id = p.account_id
JOIN clips cl    ON cl.id = p.clip_id
JOIN campaigns c ON c.id = cl.campaign_id
LEFT JOIN submissions s ON s.post_id = p.id
"""


def cmd_post_list(conn, args):
    sql = POST_LIST_SQL + (" WHERE s.id IS NULL" if args.unsubmitted else "")
    print_table(conn.execute(sql + " ORDER BY p.posted_at DESC").fetchall(),
                ["id", "platform", "handle", "campaign", "posted_at", "submission",
                 "last_views", "post_url"])


# ---------- submissions (keyed by post id) ----------

def cmd_submit_add(conn, args):
    post = get_one(conn, "posts", args.post)
    try:
        insert(conn, "submissions", {"post_id": args.post, "submitted_at": args.at})
    except sqlite3.IntegrityError:
        die(f"post {args.post} already has a submission — use `clipper submit set`")
    lag = parse_utc(args.at or db.now_utc()) - parse_utc(post["posted_at"])
    print(f"submission logged for post {args.post}")
    if lag > timedelta(hours=24):
        warn(f"submitted {lag.days}d {lag.seconds // 3600}h after posting — "
             "views before submit may not count")


def cmd_submit_set(conn, args):
    row = conn.execute("SELECT * FROM submissions WHERE post_id = ?", (args.post,)).fetchone()
    if row is None:
        die(f"post {args.post} has no submission — run `clipper submit add {args.post}` first")
    if args.status == "rejected" and not args.reason:
        warn("no --reason given; logging why it was rejected is how we learn")
    conn.execute("UPDATE submissions SET status = ?, reject_reason = ?, decided_at = ? WHERE id = ?",
                 (args.status, args.reason, db.now_utc(), row["id"]))
    conn.commit()
    print(f"submission for post {args.post} → {args.status}")


def cmd_submit_list(conn, args):
    sql = ("SELECT s.post_id, s.status, s.submitted_at, s.decided_at, s.reject_reason, p.post_url "
           "FROM submissions s JOIN posts p ON p.id = s.post_id")
    params = ()
    if args.status:
        sql += " WHERE s.status = ?"
        params = (args.status,)
    print_table(conn.execute(sql + " ORDER BY s.submitted_at DESC", params).fetchall(),
                ["post_id", "status", "submitted_at", "decided_at", "reject_reason", "post_url"])


# ---------- view snapshots ----------

def cmd_snap_add(conn, args):
    get_one(conn, "posts", args.post)
    prev = conn.execute("SELECT views FROM view_snaps WHERE post_id = ? "
                        "ORDER BY taken_at DESC, id DESC LIMIT 1", (args.post,)).fetchone()
    insert(conn, "view_snaps", {
        "post_id": args.post, "views": args.views, "likes": args.likes,
        "source": "api" if args.api else "manual", "screenshot_path": args.shot,
        "taken_at": args.at,
    })
    delta = f" (+{args.views - prev['views']:,})" if prev else ""
    print(f"post {args.post}: {args.views:,} views{delta}")
    if prev and args.views < prev["views"]:
        warn("views went down since the last snapshot — typo?")


def cmd_snap_list(conn, args):
    rows = conn.execute("SELECT * FROM view_snaps WHERE post_id = ? ORDER BY taken_at, id",
                        (args.post,)).fetchall()
    print_table(rows, ["id", "taken_at", "views", "likes", "source", "screenshot_path"])


# ---------- payouts / time ----------

def cmd_payout_add(conn, args):
    camp = get_one(conn, "campaigns", args.campaign)
    insert(conn, "payouts", {"campaign_id": args.campaign, "amount": args.amount,
                             "currency": args.currency or camp["currency"], "paid_at": args.at})
    print(f"payout {args.amount} logged for campaign {args.campaign}")


def cmd_time_add(conn, args):
    insert(conn, "time_log", {"minutes": args.minutes, "activity": args.activity,
                              "date": args.date})
    print(f"logged {args.minutes} min of {args.activity}")


# ---------- parser ----------

def add_campaign_fields(p, required: bool) -> None:
    p.add_argument("--url")
    p.add_argument("--rate", type=float, required=required, help="$ per 1k verified views")
    p.add_argument("--budget", type=float, help="total campaign budget")
    p.add_argument("--budget-left", type=float)
    p.add_argument("--min", dest="min_payout", type=float, help="min payout per submission")
    p.add_argument("--max", dest="max_payout", type=float, help="max payout per submission")
    p.add_argument("--currency")
    p.add_argument("--platforms", type=platform_list, help="e.g. tiktok,yt,ig")
    p.add_argument("--tags", help="required hashtags/credits, comma separated")
    p.add_argument("--rules", help="free-text rule notes")
    p.add_argument("--source-provided", action=argparse.BooleanOptionalAction, default=None)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="clipper", description="Log the clipping loop into SQLite.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create the DB").set_defaults(func=cmd_init)

    # account
    acc = sub.add_parser("account", help="posting accounts").add_subparsers(dest="sub", required=True)
    p = acc.add_parser("add")
    p.add_argument("platform", type=platform)
    p.add_argument("handle")
    p.add_argument("--whop-linked", action="store_true", help="already linked to Whop")
    p.add_argument("--notes")
    p.set_defaults(func=cmd_account_add)
    p = acc.add_parser("link", help="mark an account as linked to Whop")
    p.add_argument("id", type=int)
    p.add_argument("--at", type=ts)
    p.set_defaults(func=cmd_account_link)
    acc.add_parser("list").set_defaults(func=cmd_account_list)

    # campaign
    cam = sub.add_parser("campaign", help="Content Rewards campaigns").add_subparsers(dest="sub", required=True)
    p = cam.add_parser("add")
    p.add_argument("name")
    add_campaign_fields(p, required=True)
    p.set_defaults(func=cmd_campaign_add)
    p = cam.add_parser("update")
    p.add_argument("id", type=int)
    p.add_argument("--rename")
    p.add_argument("--status", choices=["active", "paused", "dead"])
    add_campaign_fields(p, required=False)
    p.set_defaults(func=cmd_campaign_update)
    p = cam.add_parser("list")
    p.add_argument("--all", action="store_true", help="include paused/dead")
    p.set_defaults(func=cmd_campaign_list)

    # source
    src = sub.add_parser("source", help="source footage").add_subparsers(dest="sub", required=True)
    p = src.add_parser("add")
    p.add_argument("campaign", type=int)
    p.add_argument("path", help="local path or URL")
    p.add_argument("--duration", type=float, help="seconds")
    p.set_defaults(func=cmd_source_add)
    p = src.add_parser("list")
    p.add_argument("--campaign", type=int)
    p.set_defaults(func=cmd_source_list)

    # clip
    clp = sub.add_parser("clip", help="cut clips").add_subparsers(dest="sub", required=True)
    p = clp.add_parser("add")
    p.add_argument("campaign", type=int)
    p.add_argument("--file")
    p.add_argument("--source", type=int)
    p.add_argument("--start", type=float, help="start second in source")
    p.add_argument("--end", type=float, help="end second in source")
    p.add_argument("--hook", help="hook text / first line")
    p.add_argument("--score", type=float, help="virality score")
    p.add_argument("--status", default="approved",
                   choices=["candidate", "approved", "rejected", "posted"],
                   help="default approved (M1 clips are hand-picked)")
    p.set_defaults(func=cmd_clip_add)
    p = clp.add_parser("set")
    p.add_argument("id", type=int)
    p.add_argument("--status", choices=["candidate", "approved", "rejected", "posted"])
    p.add_argument("--score", type=float)
    p.add_argument("--hook")
    p.add_argument("--file")
    p.set_defaults(func=cmd_clip_set)
    p = clp.add_parser("list")
    p.add_argument("--campaign", type=int)
    p.add_argument("--status")
    p.set_defaults(func=cmd_clip_list)

    # post
    pst = sub.add_parser("post", help="published posts").add_subparsers(dest="sub", required=True)
    p = pst.add_parser("add")
    p.add_argument("clip", type=int)
    p.add_argument("platform", type=platform)
    p.add_argument("url")
    p.add_argument("--account", help="account id or handle (optional if only one per platform)")
    p.add_argument("--caption")
    p.add_argument("--at", type=ts, help="when it was posted (default now)")
    p.add_argument("--submitted", action="store_true", help="also log the submission now")
    p.set_defaults(func=cmd_post_add)
    p = pst.add_parser("list")
    p.add_argument("--unsubmitted", action="store_true", help="only posts not yet submitted")
    p.set_defaults(func=cmd_post_list)

    # submit
    smt = sub.add_parser("submit", help="campaign submissions (by post id)").add_subparsers(dest="sub", required=True)
    p = smt.add_parser("add")
    p.add_argument("post", type=int)
    p.add_argument("--at", type=ts)
    p.set_defaults(func=cmd_submit_add)
    p = smt.add_parser("set", help="record the campaign's decision")
    p.add_argument("post", type=int)
    p.add_argument("status", choices=["pending", "approved", "rejected"])
    p.add_argument("--reason")
    p.set_defaults(func=cmd_submit_set)
    p = smt.add_parser("list")
    p.add_argument("--status", choices=["pending", "approved", "rejected"])
    p.set_defaults(func=cmd_submit_list)

    # snap
    snp = sub.add_parser("snap", help="view snapshots").add_subparsers(dest="sub", required=True)
    p = snp.add_parser("add")
    p.add_argument("post", type=int)
    p.add_argument("views", type=int)
    p.add_argument("--likes", type=int)
    p.add_argument("--shot", help="screenshot path")
    p.add_argument("--api", action="store_true", help="came from an API, not typed in")
    p.add_argument("--at", type=ts)
    p.set_defaults(func=cmd_snap_add)
    p = snp.add_parser("list")
    p.add_argument("post", type=int)
    p.set_defaults(func=cmd_snap_list)

    # payout
    pay = sub.add_parser("payout", help="money received").add_subparsers(dest="sub", required=True)
    p = pay.add_parser("add")
    p.add_argument("campaign", type=int)
    p.add_argument("amount", type=float)
    p.add_argument("--currency")
    p.add_argument("--at", type=ts)
    p.set_defaults(func=cmd_payout_add)

    # time
    tim = sub.add_parser("time", help="time worked").add_subparsers(dest="sub", required=True)
    p = tim.add_parser("add")
    p.add_argument("minutes", type=int)
    p.add_argument("activity", choices=["scout", "review", "post", "admin", "edit"])
    p.add_argument("--date", help="YYYY-MM-DD (default today)")
    p.set_defaults(func=cmd_time_add)

    return ap


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    conn = db.connect()
    try:
        args.func(conn, args)
    except sqlite3.IntegrityError as e:
        die(f"database rejected that: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
