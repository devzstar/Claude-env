# Clipping Pipeline — Plan

Owner: Deividas · Started: Nov 2026 · Status: not running yet
Platforms: TikTok, YouTube Shorts, Instagram Reels · Time budget: 2+ hrs/day around shifts

---

## 1. Goal and "done"

**v1 is done when:** every day the pipeline turns campaign source footage into ready-to-post 9:16 clips, I approve and post them in under an hour, every post is submitted to Content Rewards the same day, and one dashboard shows views, earnings, and what needs my attention.

**Not in v1:** fully hands-off posting, more than one account per platform, UGC / on-camera campaigns.

---

## 2. How Content Rewards pays (the rules the pipeline has to fit)

- Campaigns pay per 1,000 **verified** views, and only for clips the campaign owner **approves**.
- Each campaign sets a rate, a total budget, and a **min and max payout per submission**. Example seen: $2/1k, $4 min, $300 max per clip.
- Typical rates: a Sept 2026 snapshot of 50 live campaigns had a median of **$1.00/1k** (range $0.05–$3.00). Treat anything above ~$3 as having stricter rules.
- Views are tracked over a window (several days). They count only once the post is trackable, so **submit the link right after posting**.
- The posting account has to be **linked to Whop before posting**. Linking afterwards can leave views unverifiable.
- Eligible platforms are set per campaign. Check each one.
- Common rejections: missing required hashtags or credits, wrong source material, banned edit styles, near-duplicates of other clippers' clips, unlinked accounts, and posting after the budget ran out.

**Earnings reality check (at $1/1k):** 100k views = $100. 1M views = $1,000. Plan income at your blended rate **minus 20–30%** for rejections and unverified views.

---

## 3. Pipeline architecture

This reuses the pattern from the GTA 6 pipeline: **Sense → Triage → Produce → Publish → Learn**, with SQLite as the source of truth.

```
 SCOUT ──► SOURCE ──► CUT ──► SCORE ──► VARY ──► [YOU APPROVE] ──► POST ──► SUBMIT ──► TRACK ──► LEARN
campaigns  VODs      moments  rank top  per-platform    (human gate)   3 platforms  Whop link  views/day  weekly review
```

| Stage | What it does | Tooling (v1) | Automated? |
|---|---|---|---|
| **Scout** | Find campaigns and score them: rate, budget left, max per clip, platforms, rule strictness, whether source footage is provided | Manual daily check, logged to DB via CLI | Manual (automate only if Whop exposes an API — **check**) |
| **Source** | Pull only the source material the campaign allows (provided VODs or pre-edited clips) | Download script into `sources/<campaign>/` | Yes |
| **Cut** | Find candidate moments: transcribe, pick hooky segments, cut 15–60s | Whisper transcript + LLM moment picker, or Higgsfield clipper | Yes |
| **Format** | Reframe to 9:16, burn captions, put the hook in the first 1–2s, add campaign-required tags or credits | ffmpeg + caption script | Yes |
| **Score** | Rank candidates and keep the top N | Higgsfield virality predictor + simple rules (length, hook) | Yes |
| **Vary** | Make each post unique: caption, trim, opening frame, crop per platform | Variation script | Yes |
| **Approve** | Watch, approve or reject, pick captions | Dashboard queue | **Human gate** |
| **Post** | TikTok via Higgsfield publish (needs you to confirm in its form). Shorts via YouTube API. Reels via Instagram API or manual | Per-platform publishers | Semi |
| **Submit** | Submit each post URL to the campaign right away | Manual in Whop; the dashboard reminds you | Manual |
| **Track** | Daily view snapshots per post. Screenshots at 24h / 72h / 7d for disputes | Platform APIs where available, manual entry otherwise | Semi |
| **Learn** | Weekly: what earned most per hour (campaign, hook, length, time, platform) | Dashboard + weekly review | Manual |

**Rule:** don't automate a step until you've done it by hand at least 5 times. Doing it by hand first shows you the real rules.

---

## 4. Data model (SQLite)

```
campaigns     id, name, url, rate_per_1k, budget_total, budget_left, min_payout, max_payout,
              platforms, rules_notes, source_provided, status(active/paused/dead), joined_at
sources       id, campaign_id, path_or_url, duration_s, added_at
clips         id, campaign_id, source_id, start_s, end_s, hook_text, file_path,
              virality_score, status(candidate/approved/rejected/posted)
posts         id, clip_id, platform, account, post_url, caption, posted_at
submissions   id, post_id, submitted_at, status(pending/approved/rejected), reject_reason
view_snaps    id, post_id, taken_at, views, likes, source(api/manual), screenshot_path
payouts       id, campaign_id, amount, currency, paid_at
time_log      id, date, minutes, activity(scout/review/post/admin)
```

`time_log` exists so the dashboard can show **earnings per hour**, which is the number that matters.

---

## 5. Dashboard (v1: local web app on top of SQLite)

**Top row:** earnings this week vs last · verified views this week · £ (or $) per hour worked · approval rate.

**Action queue (most important panel):**
- Clips waiting for approval
- Posts not yet submitted to the campaign ← this is lost money
- Submissions rejected (with reason)
- Screenshots due (24h / 72h / 7d)
- Campaigns whose budget is nearly gone (stop posting there)

**Charts:** views per day by platform · earnings by campaign · top 10 clips by views · rate × views scatter (which campaigns are actually worth it).

**Entry forms:** add campaign · log submission status · log payout · log time. These cover anything an API can't give you.

Stack suggestion: FastAPI + a single HTML page (or Streamlit if faster), reading the same SQLite file the pipeline writes to.

---

## 6. Daily workflow (~2 hrs)

| When | Time | Task |
|---|---|---|
| Overnight / while at work | 0 | Pipeline runs: source → cut → format → score → vary |
| After shift | 15 min | Scout: new campaigns (fresh ones have the most budget), check budgets left |
| | 40 min | Review queue: approve the top clips, fix captions |
| | 30 min | Post, staggered across platforms, and **submit each link immediately** |
| | 15 min | Action queue: rejections, screenshots, dead campaigns |
| | 5 min | Log time |
| Sunday | 30 min | Weekly review: double down on what earned per hour, drop the rest |

---

## 7. Build order (each milestone has a clear "done")

**M0 — Accounts (day 1–2)**
One account per platform, focused on a single niche. Link all of them to Whop **before** the first post. Connect TikTok to Higgsfield.
*Done:* 3 accounts linked to Whop, TikTok connected in Higgsfield.

**M1 — Manual end-to-end (day 2–4)**
Pick 1–2 campaigns and do the whole loop by hand: cut 5 clips, post, submit, log in a bare SQLite DB via a CLI script.
*Done:* 5 clips posted and submitted, all logged in the DB.

**M2 — Cut + format automation (week 1)**
Source in → candidate 9:16 captioned clips out, ranked.
*Done:* one command turns a source VOD into 10 ranked candidate clips.

**M3 — Tracker + dashboard (week 2)**
Data model, entry forms, action queue, top KPIs.
*Done:* the dashboard shows this week's views and earnings, and the action queue lists everything waiting on you.

**M4 — Posting + view snapshots (week 3)**
Publish helpers per platform. Daily view pulls where the APIs allow, manual entry for the rest.
*Done:* views update daily without you typing them in, for at least 2 platforms.

**M5 — Learning loop (week 4)**
Weekly report: earnings per hour by campaign, hook type, length and platform. Feed winners back into the clip picker's prompt.
*Done:* the weekly report changes what gets cut the next week.

---

## 8. Risks and guardrails

- **Use only source material the campaign allows.** Content you're not authorized to clip doesn't get paid and puts your accounts at risk.
- **Duplicates get rejected and hurt reach.** Every post gets its own variation.
- **Platform rules on automation and multiple accounts.** Keep a human approving and posting until each platform's rules are clear.
- **Budget burn.** Check budget left before each posting session.
- **Verification disputes.** Take screenshots at 24h, 72h and 7d.
- **API details to verify while building:** whether Whop has a Content Rewards API; what view data TikTok's API exposes for your account; Instagram Reels publishing requires a Business or Creator account.

---

## 9. Kickoff prompt for the coding chat

> Read PLAN.md. We're building M1 then M3 first (manual loop + tracker), then M2. Start by proposing the repo layout and the SQLite schema from section 4, plus a tiny CLI to add campaigns, posts, submissions and view snapshots. Don't build anything past M1 until I confirm. Keep a CLAUDE.md with decisions and lessons as we go.
