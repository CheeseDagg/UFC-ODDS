# UFC Odds — hosted auto-refresh

This builds your scouting tool into a web page that **refreshes its odds on a
schedule and automatically rolls to the next UFC card** — no clicking, no sending
files. You open one bookmark that's always current.

The odds come from fightodds.io's public API. The query targets `nextEvent`, so
after each card finishes the next run automatically picks up the following card.

---

## One-time setup (~20 minutes)

### 1. Make a free GitHub account
Go to https://github.com and sign up. (Free tier is all you need.)

### 2. Create a repository
- Top-right **+** → **New repository**
- Name it anything, e.g. `ufc-odds`
- Set it to **Public**
- Do **not** add a README (you're uploading one)
- Click **Create repository**

### 3. Upload these files
- On the new repo page, click **uploading an existing file**
- **Drag the entire contents of this folder in** (all files AND the folders:
  `data`, `regional`, `output`, `vendor`, `odds`, `docs`, and the hidden
  `.github` folder). Drag the folders themselves so the structure is preserved.
- Scroll down, click **Commit changes**

> If the `.github` folder won't drag, create it manually: **Add file → Create new
> file**, type `.github/workflows/refresh.yml` as the name, and paste in the
> contents of that file from this folder.

### 4. Turn on Pages
- In the repo: **Settings** → **Pages** (left sidebar)
- Under **Source**, choose **GitHub Actions**
- That's it — nothing else to set

### 5. Watch the first build
- Go to the **Actions** tab. You'll see "Refresh UFC odds" running.
- When it finishes (green check, ~2 min), your page is live.
- The URL appears in **Settings → Pages** (looks like
  `https://YOURNAME.github.io/ufc-odds/`). **Bookmark it.**

Done. From now on it rebuilds every morning and after every card automatically.

---

## Using it

- **Open the bookmark** — always shows the next card with current odds + best
  prices. On a phone, add `/phone.html` to the URL for the mobile layout.
- **Want fresh odds right now** (e.g. just after weigh-ins)?
  **Actions** tab → **Refresh UFC odds** → **Run workflow**. ~2 min later the
  page is updated.

## If the first build FAILS

Open the failed run in **Actions** and look at the **Fetch odds + build site**
step. If it says `FETCH FAILED: HTTP 403` (or similar), it means fightodds.io is
**blocking GitHub's servers** — some odds sites block datacenter IPs even when a
home connection works. If that happens, the hosted route won't work and the
double-click `get_odds.bat` is the fallback. Send me the error and we'll look.

## What this version does NOT have

To roll over automatically, it rebuilds the card from the feed each run — so it
can't include your **manual weight-miss flags** or a hand-tuned **main-card /
prelim split** (everything shows in one list). For full hand-tuned handicapping,
do a manual rebuild instead.

## Notes
- The page is **public** (anyone with the link can see it). It's only odds.
- Ratings are baked in and don't change week to week; ping me to refresh them.
- If fightodds.io ever changes its API, the fetch breaks — send me the error.
