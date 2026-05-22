#!/usr/bin/env python3
"""
Culture & Pulse — monitor.py  (Option 4 Pipeline)
══════════════════════════════════════════════════
Pulls RSS feeds, optionally polishes content with Claude,
writes stories.json so the website reads YOUR data instead
of depending on the rss2json third-party service.

USAGE
─────
  python monitor.py               # auto mode — fetch, clean, write
  python monitor.py --review      # review each story before saving
  python monitor.py --no-ai       # skip Claude, use raw RSS text
  python monitor.py --dry-run     # print output, don't write file

SETUP
─────
  pip install feedparser anthropic requests

  Set your Anthropic API key:
    export ANTHROPIC_API_KEY="sk-ant-..."
  Or drop it in a .env file:
    ANTHROPIC_API_KEY=sk-ant-...

OUTPUT
──────
  stories.json — place this file in the SAME folder as
  culture-and-pulse.html. The site auto-reads it on every
  page load, replacing the rss2json API calls entirely.
"""

import json
import sys
import os
import re
import argparse
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from html import unescape

try:
    import feedparser
except ImportError:
    sys.exit("❌  Missing dependency: pip install feedparser")

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False
    print("⚠️  anthropic not installed — running in --no-ai mode.")
    print("   Install with: pip install anthropic\n")

# ══════════════════════════════════════════════════════════
# CONFIGURATION
# Edit keywords, tags, and colors here freely.
# Each feed entry pulls the latest stories for that search.
# ══════════════════════════════════════════════════════════

OUTPUT_FILE      = Path(__file__).parent / "stories.json"
STORIES_IN_GRID  = 4      # cards shown in Current Events
TICKER_HEADLINES = 20     # max lines in the scrolling ticker
ITEMS_PER_FEED   = 5      # how many items to pull per feed

FEEDS = [
    {
        "url":      "https://news.google.com/rss/search?q=HBCU+news&hl=en-US&gl=US&ceid=US:en",
        "tag":      "Sports",
        "tagClass": "tag-sports",
        "color":    "ev-ph1",
    },
    {
        "url":      "https://news.google.com/rss/search?q=Black+community+news&hl=en-US&gl=US&ceid=US:en",
        "tag":      "Community",
        "tagClass": "tag-community",
        "color":    "ev-ph2",
    },
    {
        "url":      "https://news.google.com/rss/search?q=WNBA+2025&hl=en-US&gl=US&ceid=US:en",
        "tag":      "Sports",
        "tagClass": "tag-sports",
        "color":    "ev-ph3",
    },
    {
        "url":      "https://news.google.com/rss/search?q=Black+culture+music&hl=en-US&gl=US&ceid=US:en",
        "tag":      "Culture",
        "tagClass": "tag-culture",
        "color":    "ev-ph4",
    },
    {
        "url":      "https://news.google.com/rss/search?q=Black+business+entrepreneurs&hl=en-US&gl=US&ceid=US:en",
        "tag":      "Business",
        "tagClass": "tag-news",
        "color":    "ev-ph1",
    },
    {
        "url":      "https://news.google.com/rss/search?q=Black+athletes+sports&hl=en-US&gl=US&ceid=US:en",
        "tag":      "Sports",
        "tagClass": "tag-sports",
        "color":    "ev-ph2",
    },
]


# ══════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════

def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def clean_title(title: str) -> str:
    """Remove ' - Source Name' suffixes Google News adds."""
    if not title:
        return ""
    return re.sub(r"\s+-\s+[^-]+$", "", title).strip()


def format_date(struct_time) -> str:
    """Convert feedparser time struct to readable date."""
    try:
        dt = datetime(*struct_time[:6], tzinfo=timezone.utc)
        return dt.strftime("%b %-d, %Y")
    except Exception:
        return datetime.now().strftime("%b %-d, %Y")


def truncate(text: str, length: int = 160) -> str:
    return textwrap.shorten(text, width=length, placeholder="…")


# ══════════════════════════════════════════════════════════
# STEP 1: FETCH RSS
# ══════════════════════════════════════════════════════════

def fetch_feed(feed_cfg: dict) -> list[dict]:
    """Pull items from one RSS feed, return raw story dicts."""
    print(f"  📡  Fetching: {feed_cfg['url'][:70]}…")
    try:
        parsed = feedparser.parse(feed_cfg["url"])
        stories = []
        for entry in parsed.entries[:ITEMS_PER_FEED]:
            desc  = strip_html(getattr(entry, "summary", ""))
            thumb = None

            # Try multiple thumbnail sources
            if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                thumb = entry.media_thumbnail[0].get("url")
            elif hasattr(entry, "media_content") and entry.media_content:
                thumb = entry.media_content[0].get("url")

            stories.append({
                "title":    clean_title(getattr(entry, "title", "")),
                "link":     getattr(entry, "link", "#"),
                "date":     format_date(getattr(entry, "published_parsed", None)),
                "rawDesc":  desc,
                "excerpt":  truncate(desc, 140),  # overwritten by AI if enabled
                "thumbnail":thumb,
                "tag":      feed_cfg["tag"],
                "tagClass": feed_cfg["tagClass"],
                "color":    feed_cfg["color"],
                "source":   getattr(parsed.feed, "title", "")
                                .replace(" - Google News", "").strip(),
            })
        print(f"     ✓  {len(stories)} stories")
        return stories
    except Exception as e:
        print(f"     ✗  Failed: {e}")
        return []


# ══════════════════════════════════════════════════════════
# STEP 2: AI POLISH (optional)
# Sends the top stories to Claude for cleaner excerpts.
# ══════════════════════════════════════════════════════════

def polish_with_claude(stories: list[dict]) -> list[dict]:
    """
    Ask Claude to write a clean 1-2 sentence excerpt for each story.
    Replaces the raw RSS description snippet.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("\n⚠️  ANTHROPIC_API_KEY not set — skipping AI polish.")
        print("   Set it with: export ANTHROPIC_API_KEY='sk-ant-...'\n")
        return stories

    client = anthropic.Anthropic(api_key=api_key)

    # Build a compact prompt with all stories in one API call
    story_list = "\n".join(
        f"{i+1}. TITLE: {s['title']}\n   RAW: {s['rawDesc'][:300]}"
        for i, s in enumerate(stories)
    )

    prompt = f"""You write punchy, editorial excerpts for Culture & Pulse — a Black culture, 
sports, and history media brand. Tone is direct, informed, community-forward. 
Not corporate. Not clickbait.

For each story below, write ONE sentence (max 130 characters) that:
- Captures the core news value
- Speaks to a Black and Brown audience
- Reads like a real editorial caption, not a press release

Return ONLY a JSON array of strings, one excerpt per story, in order.
No preamble, no markdown, no explanation — just the JSON array.

STORIES:
{story_list}"""

    try:
        print("\n🤖  Polishing excerpts with Claude…")
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        # Strip any accidental markdown fences
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        excerpts = json.loads(raw)

        for i, story in enumerate(stories):
            if i < len(excerpts) and excerpts[i]:
                story["excerpt"] = excerpts[i].strip()

        print(f"   ✓  Polished {len(stories)} excerpts")
    except Exception as e:
        print(f"   ✗  AI polish failed ({e}) — using raw excerpts")

    return stories


# ══════════════════════════════════════════════════════════
# STEP 3: REVIEW MODE
# Drew approves or skips each story interactively.
# ══════════════════════════════════════════════════════════

def review_stories(stories: list[dict]) -> list[dict]:
    """Interactive CLI review — approve/skip/edit each story."""
    print("\n" + "═"*60)
    print("  REVIEW MODE — approve stories before they go live")
    print("  Commands:  y=approve  n=skip  e=edit excerpt  q=quit")
    print("═"*60 + "\n")

    approved = []
    for i, s in enumerate(stories):
        print(f"[{i+1}/{len(stories)}]  {s['tag'].upper()} · {s['date']}")
        print(f"  TITLE:   {s['title']}")
        print(f"  EXCERPT: {s['excerpt']}")
        print(f"  LINK:    {s['link'][:80]}")
        print()

        while True:
            cmd = input("  → ").strip().lower()
            if cmd in ("y", ""):
                approved.append(s)
                print("  ✓ Approved\n")
                break
            elif cmd == "n":
                print("  ✗ Skipped\n")
                break
            elif cmd == "e":
                new_excerpt = input("  New excerpt: ").strip()
                if new_excerpt:
                    s["excerpt"] = new_excerpt
                approved.append(s)
                print("  ✓ Approved with edit\n")
                break
            elif cmd == "q":
                print("\n  Stopping review early.")
                return approved
            else:
                print("  Use: y / n / e / q")

    return approved


# ══════════════════════════════════════════════════════════
# STEP 4: BUILD + WRITE stories.json
# ══════════════════════════════════════════════════════════

def build_output(stories: list[dict]) -> dict:
    """
    Assemble the final JSON structure the website reads.
    """
    # Deduplicate by title prefix
    seen, unique = set(), []
    for s in stories:
        key = s["title"][:40].lower()
        if key not in seen and s["title"]:
            seen.add(key)
            unique.append(s)

    ticker_headlines = [s["title"] for s in unique[:TICKER_HEADLINES]]
    grid_stories     = unique[:STORIES_IN_GRID]

    return {
        "generated":  datetime.now(timezone.utc).isoformat(),
        "ticker":     ticker_headlines,
        "stories":    [
            {
                "title":     s["title"],
                "excerpt":   s["excerpt"],
                "link":      s["link"],
                "date":      s["date"],
                "thumbnail": s["thumbnail"],
                "tag":       s["tag"],
                "tagClass":  s["tagClass"],
                "color":     s["color"],
                "source":    s.get("source", ""),
            }
            for s in grid_stories
        ]
    }


def write_output(data: dict, path: Path) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"\n✅  Wrote {path}")
    print(f"    {len(data['ticker'])} ticker headlines")
    print(f"    {len(data['stories'])} grid stories")
    print(f"    Generated: {data['generated']}")


def print_dry_run(data: dict) -> None:
    print("\n── DRY RUN OUTPUT ──────────────────────────────────")
    print("\nTICKER HEADLINES:")
    for h in data["ticker"]:
        print(f"  • {h}")
    print("\nGRID STORIES:")
    for s in data["stories"]:
        print(f"\n  [{s['tag']}]  {s['title']}")
        print(f"  {s['excerpt']}")
        print(f"  {s['link'][:70]}")
    print("\n────────────────────────────────────────────────────")
    print("(Dry run — nothing written)")


# ══════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Culture & Pulse — RSS → stories.json pipeline"
    )
    parser.add_argument("--review",  action="store_true", help="Approve stories interactively")
    parser.add_argument("--no-ai",   action="store_true", help="Skip Claude, use raw RSS excerpts")
    parser.add_argument("--dry-run", action="store_true", help="Print output without writing file")
    args = parser.parse_args()

    use_ai = HAS_ANTHROPIC and not args.no_ai

    print("\n" + "═"*60)
    print("  CULTURE & PULSE — Story Pipeline")
    print(f"  Mode: {'Review' if args.review else 'Auto'}"
          f" | AI: {'On' if use_ai else 'Off'}"
          f" | Dry run: {args.dry_run}")
    print("═"*60)

    # ── Fetch all feeds
    print("\n📰  Fetching RSS feeds…\n")
    all_stories = []
    for feed in FEEDS:
        all_stories.extend(fetch_feed(feed))

    if not all_stories:
        sys.exit("\n❌  No stories fetched. Check your internet connection.")

    print(f"\n  Total raw stories: {len(all_stories)}")

    # ── AI polish
    if use_ai:
        all_stories = polish_with_claude(all_stories[:TICKER_HEADLINES])

    # ── Review
    if args.review:
        all_stories = review_stories(all_stories)
        if not all_stories:
            sys.exit("\n⚠️  No stories approved. Nothing written.")

    # ── Build + write
    output = build_output(all_stories)

    if args.dry_run:
        print_dry_run(output)
    else:
        write_output(output, OUTPUT_FILE)

    print()


if __name__ == "__main__":
    main()
