# Culture & Pulse — Site Setup Guide

**Sports × Black History × Culture**

---

## How the Approval Flow Works

```
Every day at 9am + 6pm Central
        ↓
GitHub fetches fresh RSS stories
        ↓
Claude polishes the excerpts (if API key is set)
        ↓
GitHub opens a Pull Request
        ↓
GitHub emails you: "📰 Stories for Review — May 22"
        ↓
You open the PR, read the story previews
        ↓
   MERGE  →  site deploys live instantly
   CLOSE  →  stories rejected, next run fetches fresh ones
```

**That's your approval loop. No extra apps, no extra services.**

---

## Repo Structure

```
culture-and-pulse/
├── culture-and-pulse.html           ← the site
├── monitor.py                       ← RSS pipeline script
├── stories.json                     ← current live stories
├── requirements.txt                 ← Python dependencies
├── README.md                        ← this file
└── .github/
    └── workflows/
        ├── fetch-stories.yml        ← runs on schedule, opens PR
        └── deploy.yml               ← runs on merge, deploys site
```

---

## One-Time Setup (15 minutes)

### Step 1 — Create a GitHub Repo

1. Go to [github.com](https://github.com) → **New repository**
2. Name it `cultureandpulse`
3. Set it **Public** (required for free GitHub Pages)
4. Click **Create repository**

---

### Step 2 — Upload Your Files

Upload these to repo root:
- `culture-and-pulse.html`
- `monitor.py`
- `requirements.txt`
- `stories.json`
- `README.md`

Upload these maintaining the folder path:
- `.github/workflows/fetch-stories.yml`
- `.github/workflows/deploy.yml`

> **Tip:** Use [GitHub Desktop](https://desktop.github.com) to drag and drop
> the entire folder — it handles the `.github/` structure automatically.

---

### Step 3 — Enable GitHub Pages

1. Repo → **Settings** → **Pages**
2. Source → **GitHub Actions**
3. Click **Save**

---

### Step 4 — Add Your API Key (optional but recommended)

Enables Claude to write polished, on-brand excerpts.

1. Repo → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret**
3. Name: `ANTHROPIC_API_KEY`  |  Value: `sk-ant-...`
4. Save

> Without this, the pipeline still runs — excerpts are just raw RSS text.

---

### Step 5 — Enable Email Notifications for PRs

This is what puts stories in your inbox.

1. Go to [github.com/settings/notifications](https://github.com/settings/notifications)
2. Under **Pull requests**, make sure **Email** is checked
3. Confirm your email is verified at [github.com/settings/emails](https://github.com/settings/emails)

From now on, every time the pipeline opens a PR you get an email like:

> **[cultureandpulse] 📰 Stories for Review — May 22, 2025 — 9:00 UTC**

Click the link → see the full story list → merge or close.

---

### Step 6 — First Deploy

1. Go to **Actions** tab
2. Click **📰 Fetch Stories for Review**
3. Click **Run workflow**
4. After it finishes, go to **Pull Requests** tab
5. Open the PR, read the stories, click **Merge pull request**
6. Site is live. Done.

---

## What the PR Looks Like

When GitHub emails you, the PR description contains:

```
📰 Culture & Pulse — Stories for Review
Generated: 2025-05-22 09:00 UTC

---

✅ Approve → Merge this PR
❌ Reject  → Close this PR

---

## Current Events Grid (4 stories going live)

1. [SPORTS] HBCU Athletics Sees 40% Spike in National TV Deals
   > Historic broadcast agreements signal a major shift in how
     HBCU sports are valued on the national stage.
   📅 May 22, 2025  |  🔗 ESPN

2. [COMMUNITY] Louisiana Lawmakers Advance Criminal Justice Reform Bill
   > New legislation targeting sentencing disparities clears
     committee with bipartisan support.
   📅 May 22, 2025  |  🔗 AP News

... and so on

---

## Ticker Headlines
- HBCU Athletics Sees 40% Spike...
- Black Entrepreneurs Raise $2.4B...
- (20 total)
```

---

## Day-to-Day Workflow

| You want to... | Do this |
|---|---|
| Approve stories | Merge the PR |
| Reject stories | Close the PR |
| Force a fresh fetch now | Actions → Run workflow |
| Update the hero story | Edit `culture-and-pulse.html` directly |
| Update Did You Know? cards | Edit `culture-and-pulse.html` directly |
| Change RSS keywords | Edit `FEEDS` array in `monitor.py` |
| Change schedule | Edit cron lines in `fetch-stories.yml` |

---

## Schedule

Default schedule — twice daily:
- `0 14 * * *` = 9am Central
- `0 23 * * *` = 6pm Central

To change, edit the cron lines in `fetch-stories.yml`:
```yaml
# Once daily at 8am Central
- cron: '0 13 * * *'

# Three times a day
- cron: '0 13 * * *'
- cron: '0 18 * * *'
- cron: '0 23 * * *'

# Weekdays only
- cron: '0 14 * * 1-5'
```

---

## Cost

| Service | Cost |
|---|---|
| GitHub repo + Actions + Pages | Free |
| rss2json fallback API | Free |
| Claude API (AI excerpts) | ~$0.01–0.05 per run |
| Custom domain | ~$12/year (optional) |

Twice daily with AI = roughly **$0.60–3.00/month** in API costs.
Without AI (`--no-ai`): **$0 forever**.

---

## Adding a Custom Domain

To use `cultureandpulse.com`:

1. Buy the domain (Namecheap, Google Domains, etc.)
2. Repo → **Settings** → **Pages** → **Custom domain** → enter your domain
3. In your domain registrar, add a CNAME record:
   - Type: `CNAME`  |  Name: `www`  |  Value: `YOUR-USERNAME.github.io`
4. GitHub handles SSL automatically

---

*Culture & Pulse — Built different.*
