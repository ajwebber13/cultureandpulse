#!/usr/bin/env python3
"""
Culture & Pulse — monitor.py
═════════════════════════════════════════════════════════════
Pulls RSS feeds + Black history events for today's date.
Writes stories.json for the website to consume.

USAGE
─────
  python monitor.py               # auto mode
  python monitor.py --review      # approve stories before saving
  python monitor.py --no-ai       # skip Claude (free mode)
  python monitor.py --dry-run     # print without writing

SETUP
─────
  pip install feedparser requests
"""

import json, sys, os, re, argparse, textwrap, requests
from datetime import datetime, timezone
from pathlib import Path
from html import unescape

try:
    import feedparser
except ImportError:
    sys.exit("❌  pip install feedparser")

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

# ══════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════

OUTPUT_FILE      = Path(__file__).parent / "stories.json"
STORIES_IN_GRID  = 4
TICKER_HEADLINES = 20
ITEMS_PER_FEED   = 5

FEEDS = [
    {"url": "https://news.google.com/rss/search?q=HBCU+news&hl=en-US&gl=US&ceid=US:en",
     "tag": "Sports",   "tagClass": "tag-sports",    "color": "ev-ph1"},
    {"url": "https://news.google.com/rss/search?q=Black+community+news&hl=en-US&gl=US&ceid=US:en",
     "tag": "Community","tagClass": "tag-community", "color": "ev-ph2"},
    {"url": "https://news.google.com/rss/search?q=WNBA+2025&hl=en-US&gl=US&ceid=US:en",
     "tag": "Sports",   "tagClass": "tag-sports",    "color": "ev-ph3"},
    {"url": "https://news.google.com/rss/search?q=Black+culture+music&hl=en-US&gl=US&ceid=US:en",
     "tag": "Culture",  "tagClass": "tag-culture",   "color": "ev-ph4"},
    {"url": "https://news.google.com/rss/search?q=Black+business+entrepreneurs&hl=en-US&gl=US&ceid=US:en",
     "tag": "Business", "tagClass": "tag-news",      "color": "ev-ph1"},
    {"url": "https://news.google.com/rss/search?q=Black+athletes+sports&hl=en-US&gl=US&ceid=US:en",
     "tag": "Sports",   "tagClass": "tag-sports",    "color": "ev-ph2"},
]

# ── Keywords that signal Black history relevance ──────────
BLACK_HISTORY_KEYWORDS = [
    "african american", "black american", "black history",
    "slavery", "enslaved", "abolitionist", "emancipation",
    "civil rights", "segregation", "desegregation", "jim crow",
    "naacp", "hbcu", "historically black",
    "juneteenth", "reconstruction", "freedmen",
    "harlem renaissance", "black power", "black panther",
    # Notable figures
    "martin luther king", "rosa parks", "malcolm x",
    "harriet tubman", "frederick douglass", "booker t washington",
    "w.e.b. du bois", "thurgood marshall", "medgar evers",
    "john lewis", "fannie lou hamer", "shirley chisholm",
    "jesse owens", "jackie robinson", "muhammad ali",
    "jack johnson", "joe louis", "arthur ashe",
    "sojourner truth", "nat turner", "denmark vesey",
    "marcus garvey", "ida b wells", "mary mcleod bethune",
    "charles drew", "george washington carver", "garrett morgan",
    "lewis howard latimer", "granville woods", "jan matzeliger",
    "mae jemison", "katherine johnson", "charles richard drew",
    "tuskegee", "selma", "montgomery", "little rock",
    "woolworth", "freedom riders", "march on washington",
    "voting rights", "civil rights act",
]

# ── Curated fallback events keyed by MM-DD ───────────────
# Used when Wikipedia doesn't return enough relevant results.
FALLBACK_EVENTS = {
    "01-01": [
        {"year": "1863", "title": "Emancipation Proclamation Takes Effect",
         "text": "President Lincoln's Emancipation Proclamation officially took effect, declaring enslaved people in Confederate states to be free — a turning point that reshaped the Civil War into a war for liberation.",
         "person": "President Abraham Lincoln"},
        {"year": "1804", "title": "Haiti Declares Independence",
         "text": "Haiti became the first Black republic in the world after a successful slave revolt led by formerly enslaved people, establishing the first nation born from a slave revolution in history.",
         "person": "Jean-Jacques Dessalines"},
    ],
    "01-15": [
        {"year": "1929", "title": "Martin Luther King Jr. Is Born",
         "text": "Michael King Jr. — later known as Martin Luther King Jr. — was born in Atlanta, Georgia. He would become the defining voice of the American civil rights movement.",
         "person": "Martin Luther King Jr."},
    ],
    "02-01": [
        {"year": "1960", "title": "Greensboro Sit-Ins Begin",
         "text": "Four Black college students sat down at a segregated Woolworth's lunch counter in Greensboro, NC and refused to leave. The sit-in sparked a nationwide wave of nonviolent protest.",
         "person": "The Greensboro Four"},
    ],
    "02-03": [
        {"year": "1870", "title": "15th Amendment Ratified",
         "text": "The 15th Amendment to the U.S. Constitution was ratified, prohibiting the denial of the right to vote based on race, color, or previous condition of servitude.",
         "person": "Congress of the United States"},
    ],
    "02-12": [
        {"year": "1909", "title": "NAACP Founded",
         "text": "The National Association for the Advancement of Colored People was founded in New York City, becoming one of the most powerful civil rights organizations in American history.",
         "person": "W.E.B. Du Bois & Co-Founders"},
    ],
    "02-25": [
        {"year": "1964", "title": "Cassius Clay Becomes World Heavyweight Champion",
         "text": "Cassius Clay — soon to rename himself Muhammad Ali — defeated Sonny Liston to become the World Heavyweight Champion, announcing a new era in both boxing and Black American pride.",
         "person": "Muhammad Ali"},
    ],
    "03-07": [
        {"year": "1965", "title": "Bloody Sunday on the Edmund Pettus Bridge",
         "text": "Six hundred marchers were brutally attacked by state troopers at the Edmund Pettus Bridge in Selma, Alabama, in a moment that galvanized the nation and led directly to the Voting Rights Act.",
         "person": "John Lewis & Hosea Williams"},
    ],
    "04-04": [
        {"year": "1968", "title": "Dr. Martin Luther King Jr. Assassinated",
         "text": "Dr. Martin Luther King Jr. was assassinated on the balcony of the Lorraine Motel in Memphis, Tennessee. His death sent shockwaves across the nation and the world.",
         "person": "Dr. Martin Luther King Jr."},
    ],
    "04-09": [
        {"year": "1865", "title": "Civil War Ends — Confederate Surrender",
         "text": "General Robert E. Lee surrendered to Ulysses S. Grant at Appomattox Court House, effectively ending the Civil War and paving the way for the abolition of slavery.",
         "person": "General Ulysses S. Grant"},
    ],
    "04-15": [
        {"year": "1947", "title": "Jackie Robinson Breaks Baseball's Color Line",
         "text": "Jackie Robinson took the field for the Brooklyn Dodgers, becoming the first Black player in Major League Baseball's modern era and permanently changing American sports.",
         "person": "Jackie Robinson"},
    ],
    "05-17": [
        {"year": "1954", "title": "Brown v. Board of Education Decided",
         "text": "The Supreme Court unanimously ruled that racial segregation in public schools was unconstitutional, overturning Plessy v. Ferguson and reshaping American education forever.",
         "person": "Thurgood Marshall"},
    ],
    "05-19": [
        {"year": "1925", "title": "Malcolm X Is Born",
         "text": "Malcolm Little — later known as Malcolm X — was born in Omaha, Nebraska. He became one of the most influential and powerful voices for Black self-determination and dignity in the 20th century.",
         "person": "Malcolm X"},
    ],
    "05-22": [
        {"year": "1967", "title": "Thurgood Marshall Nominated to Supreme Court",
         "text": "President Lyndon B. Johnson nominated Thurgood Marshall to the U.S. Supreme Court, making him the first African American Justice in the nation's history.",
         "person": "Thurgood Marshall"},
        {"year": "1856", "title": "Preston Brooks Attacks Charles Sumner on Senate Floor",
         "text": "South Carolina congressman Preston Brooks savagely beat anti-slavery Senator Charles Sumner with a cane on the Senate floor — a moment that crystallized the brutal reality of pro-slavery politics.",
         "person": "Senator Charles Sumner"},
    ],
    "06-19": [
        {"year": "1865", "title": "Juneteenth — The Last Enslaved People Are Freed",
         "text": "Union soldiers arrived in Galveston, Texas and announced that all enslaved people were free — two and a half years after the Emancipation Proclamation. June 19th became Juneteenth.",
         "person": "General Gordon Granger"},
    ],
    "07-04": [
        {"year": "1827", "title": "New York State Abolishes Slavery",
         "text": "New York State's Emancipation Act took full effect on July 4, 1827, freeing all enslaved people in the state — including Sojourner Truth, who had been freed a year earlier.",
         "person": "Sojourner Truth"},
    ],
    "08-06": [
        {"year": "1965", "title": "Voting Rights Act Signed Into Law",
         "text": "President Lyndon B. Johnson signed the Voting Rights Act of 1965, outlawing discriminatory voting practices that had disenfranchised Black Americans across the South for generations.",
         "person": "President Lyndon B. Johnson"},
    ],
    "08-28": [
        {"year": "1963", "title": "March on Washington — 'I Have a Dream'",
         "text": "Over 250,000 people gathered at the Lincoln Memorial for the March on Washington, where Dr. Martin Luther King Jr. delivered his historic 'I Have a Dream' speech.",
         "person": "Dr. Martin Luther King Jr."},
        {"year": "1955", "title": "Emmett Till Murdered in Mississippi",
         "text": "14-year-old Emmett Till was abducted and murdered in Money, Mississippi. His mother's decision to hold an open-casket funeral exposed the horror of racial violence and helped ignite the civil rights movement.",
         "person": "Emmett Till"},
    ],
    "09-09": [
        {"year": "1739", "title": "Stono Rebellion — Largest Slave Revolt in Colonial America",
         "text": "Enslaved Africans in South Carolina launched the Stono Rebellion, the largest slave revolt in colonial American history, marching toward Spanish Florida in a bid for freedom.",
         "person": "Jemmy (Cato)"},
    ],
    "10-01": [
        {"year": "1962", "title": "James Meredith Enrolls at Ole Miss",
         "text": "James Meredith became the first Black student to enroll at the University of Mississippi, escorted by federal marshals amid violent riots — a landmark moment in the integration of higher education.",
         "person": "James Meredith"},
    ],
    "10-16": [
        {"year": "1995", "title": "Million Man March",
         "text": "Hundreds of thousands of Black men gathered on the National Mall in Washington D.C. for the Million Man March, one of the largest demonstrations in American history.",
         "person": "Minister Louis Farrakhan"},
        {"year": "1968", "title": "Tommie Smith & John Carlos Black Power Salute",
         "text": "At the 1968 Mexico City Olympics, sprinters Tommie Smith and John Carlos raised their fists in a Black Power salute on the medal podium — an image that defined an era.",
         "person": "Tommie Smith & John Carlos"},
    ],
    "11-02": [
        {"year": "1983", "title": "MLK Holiday Signed Into Law",
         "text": "President Ronald Reagan signed legislation establishing Martin Luther King Jr. Day as a federal holiday, to be observed on the third Monday of January each year.",
         "person": "President Ronald Reagan"},
    ],
    "12-01": [
        {"year": "1955", "title": "Rosa Parks Refuses to Give Up Her Seat",
         "text": "Rosa Parks was arrested in Montgomery, Alabama after refusing to give up her bus seat to a white passenger. Her act of defiance launched the Montgomery Bus Boycott and changed history.",
         "person": "Rosa Parks"},
    ],
    "12-06": [
        {"year": "1865", "title": "13th Amendment Abolishes Slavery",
         "text": "The 13th Amendment to the U.S. Constitution was ratified, formally abolishing slavery throughout the United States and ending over 250 years of legalized bondage.",
         "person": "Congress of the United States"},
    ],
}


# ══════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════

def strip_html(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()

def clean_title(title):
    if not title: return ""
    return re.sub(r"\s+-\s+[^-]+$", "", title).strip()

def format_date(struct_time):
    try:
        dt = datetime(*struct_time[:6], tzinfo=timezone.utc)
        return dt.strftime("%b %-d, %Y")
    except:
        return datetime.now().strftime("%b %-d, %Y")

def truncate(text, length=160):
    return textwrap.shorten(text, width=length, placeholder="…")

def is_black_history(text):
    t = text.lower()
    return any(kw in t for kw in BLACK_HISTORY_KEYWORDS)


# ══════════════════════════════════════════════════════════
# DID YOU KNOW — Wikipedia On This Day
# ══════════════════════════════════════════════════════════

def fetch_did_you_know() -> list[dict]:
    """
    Pull 3 Black history events that happened on today's date.
    Source: Wikipedia On This Day API (free, no key needed).
    Falls back to curated dataset if Wikipedia comes up short.
    """
    today     = datetime.now()
    month     = today.month
    day       = today.day
    month_str = str(month)
    day_str   = str(day)
    date_key  = f"{month:02d}-{day:02d}"

    print(f"\n📅  Fetching Did You Know for {today.strftime('%B %-d')}…")

    wiki_events = []
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{month_str}/{day_str}"
        res = requests.get(url, timeout=10,
                           headers={"User-Agent": "CultureAndPulse/1.0"})
        if res.status_code == 200:
            data   = res.json()
            events = data.get("events", [])

            for ev in events:
                text = ev.get("text", "")
                year = str(ev.get("year", ""))
                if not is_black_history(text):
                    continue

                # Try to extract a person name from linked pages
                person = ""
                pages  = ev.get("pages", [])
                if pages:
                    person = pages[0].get("titles", {}).get("normalized", "")

                # Build a clean title from first sentence
                first_sentence = text.split(".")[0].strip()
                title = first_sentence[:80] + ("…" if len(first_sentence) > 80 else "")

                wiki_events.append({
                    "year":   year,
                    "title":  title,
                    "text":   text,
                    "person": person,
                })

                if len(wiki_events) >= 3:
                    break

        print(f"   ✓  Wikipedia: {len(wiki_events)} relevant events found")

    except Exception as e:
        print(f"   ✗  Wikipedia fetch failed: {e}")

    # ── Fill remaining slots from curated fallback ────────
    fallback = FALLBACK_EVENTS.get(date_key, [])

    # Also check nearby dates if current date has no fallback
    if not fallback:
        for offset in [1, -1, 2, -2]:
            from datetime import timedelta
            alt = today + timedelta(days=offset)
            alt_key = f"{alt.month:02d}-{alt.day:02d}"
            if alt_key in FALLBACK_EVENTS:
                fallback = FALLBACK_EVENTS[alt_key]
                break

    combined = wiki_events[:]
    seen_years = {e["year"] for e in combined}

    for fb in fallback:
        if len(combined) >= 3:
            break
        if fb["year"] not in seen_years:
            combined.append(fb)
            seen_years.add(fb["year"])

    # Final fallback — use static content if everything failed
    if not combined:
        combined = [
            {"year": "1947", "title": "Jackie Robinson Breaks Baseball's Color Line",
             "text": "Jackie Robinson took the field for the Brooklyn Dodgers, becoming the first Black player in Major League Baseball's modern era.",
             "person": "Jackie Robinson"},
            {"year": "1963", "title": "March on Washington",
             "text": "Over 250,000 people gathered at the Lincoln Memorial where Dr. Martin Luther King Jr. delivered his 'I Have a Dream' speech.",
             "person": "Dr. Martin Luther King Jr."},
            {"year": "1955", "title": "Rosa Parks Refuses to Give Up Her Seat",
             "text": "Rosa Parks was arrested in Montgomery, Alabama after refusing to give up her bus seat, launching the Montgomery Bus Boycott.",
             "person": "Rosa Parks"},
        ]

    result = combined[:3]
    print(f"   ✓  Did You Know: {len(result)} events ready")
    return result


# ══════════════════════════════════════════════════════════
# RSS FETCH
# ══════════════════════════════════════════════════════════

def fetch_feed(feed_cfg):
    print(f"  📡  Fetching: {feed_cfg['url'][:70]}…")
    try:
        parsed = feedparser.parse(feed_cfg["url"])
        stories = []
        for entry in parsed.entries[:ITEMS_PER_FEED]:
            desc  = strip_html(getattr(entry, "summary", ""))
            thumb = None
            if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                thumb = entry.media_thumbnail[0].get("url")
            elif hasattr(entry, "media_content") and entry.media_content:
                thumb = entry.media_content[0].get("url")
            stories.append({
                "title":    clean_title(getattr(entry, "title", "")),
                "link":     getattr(entry, "link", "#"),
                "date":     format_date(getattr(entry, "published_parsed", None)),
                "rawDesc":  desc,
                "excerpt":  truncate(desc, 140),
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
# AI POLISH (optional)
# ══════════════════════════════════════════════════════════

def polish_with_claude(stories):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("\n⚠️  No ANTHROPIC_API_KEY — skipping AI polish.")
        return stories
    client = anthropic.Anthropic(api_key=api_key)
    story_list = "\n".join(
        f"{i+1}. TITLE: {s['title']}\n   RAW: {s['rawDesc'][:300]}"
        for i, s in enumerate(stories)
    )
    prompt = f"""You write punchy editorial excerpts for Culture & Pulse — a Black culture,
sports, and history media brand. Tone: direct, informed, community-forward.

For each story, write ONE sentence (max 130 chars) that captures the news value
and speaks to a Black and Brown audience.

Return ONLY a JSON array of strings. No markdown, no preamble.

STORIES:
{story_list}"""
    try:
        print("\n🤖  Polishing with Claude…")
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = re.sub(r"^```[a-z]*\n?|\n?```$", "", msg.content[0].text.strip())
        excerpts = json.loads(raw)
        for i, s in enumerate(stories):
            if i < len(excerpts) and excerpts[i]:
                s["excerpt"] = excerpts[i].strip()
        print(f"   ✓  Polished {len(stories)} excerpts")
    except Exception as e:
        print(f"   ✗  AI polish failed ({e})")
    return stories


# ══════════════════════════════════════════════════════════
# REVIEW MODE
# ══════════════════════════════════════════════════════════

def review_stories(stories):
    print("\n" + "═"*60)
    print("  REVIEW MODE  —  y=approve  n=skip  e=edit  q=quit")
    print("═"*60 + "\n")
    approved = []
    for i, s in enumerate(stories):
        print(f"[{i+1}/{len(stories)}]  {s['tag'].upper()} · {s['date']}")
        print(f"  TITLE:   {s['title']}")
        print(f"  EXCERPT: {s['excerpt']}")
        print(f"  LINK:    {s['link'][:80]}\n")
        while True:
            cmd = input("  → ").strip().lower()
            if cmd in ("y", ""):
                approved.append(s); print("  ✓ Approved\n"); break
            elif cmd == "n":
                print("  ✗ Skipped\n"); break
            elif cmd == "e":
                new = input("  New excerpt: ").strip()
                if new: s["excerpt"] = new
                approved.append(s); print("  ✓ Approved\n"); break
            elif cmd == "q":
                return approved
            else:
                print("  y / n / e / q")
    return approved


# ══════════════════════════════════════════════════════════
# BUILD + WRITE stories.json
# ══════════════════════════════════════════════════════════

def build_output(stories, did_you_know):
    seen, unique = set(), []
    for s in stories:
        key = s["title"][:40].lower()
        if key not in seen and s["title"]:
            seen.add(key); unique.append(s)

    return {
        "generated":    datetime.now(timezone.utc).isoformat(),
        "ticker":       [s["title"] for s in unique[:TICKER_HEADLINES]],
        "stories":      [
            {k: s[k] for k in
             ("title","excerpt","link","date","thumbnail","tag","tagClass","color","source")}
            for s in unique[:STORIES_IN_GRID]
        ],
        "did_you_know": did_you_know,   # ← new key
    }


def write_output(data, path):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"\n✅  Wrote {path}")
    print(f"    {len(data['ticker'])} ticker headlines")
    print(f"    {len(data['stories'])} grid stories")
    print(f"    {len(data['did_you_know'])} Did You Know events")


def print_dry_run(data):
    print("\n── DRY RUN ──────────────────────────────────────────")
    print("\nDID YOU KNOW:")
    for e in data["did_you_know"]:
        print(f"  [{e['year']}] {e['title']}")
        print(f"  {e['text'][:100]}…")
    print("\nGRID STORIES:")
    for s in data["stories"]:
        print(f"\n  [{s['tag']}] {s['title']}")
        print(f"  {s['excerpt']}")
    print("\n─────────────────────────────────────────────────────")
    print("(Dry run — nothing written)")


# ══════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Culture & Pulse pipeline")
    parser.add_argument("--review",  action="store_true")
    parser.add_argument("--no-ai",   action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args   = parser.parse_args()
    use_ai = HAS_ANTHROPIC and not args.no_ai

    print("\n" + "═"*60)
    print("  CULTURE & PULSE — Story Pipeline")
    print(f"  Mode: {'Review' if args.review else 'Auto'} | AI: {'On' if use_ai else 'Off'}")
    print("═"*60)

    # ── RSS
    print("\n📰  Fetching RSS feeds…\n")
    all_stories = []
    for feed in FEEDS:
        all_stories.extend(fetch_feed(feed))
    if not all_stories:
        sys.exit("\n❌  No stories fetched.")
    print(f"\n  Total: {len(all_stories)} raw stories")

    if use_ai:
        all_stories = polish_with_claude(all_stories[:TICKER_HEADLINES])

    if args.review:
        all_stories = review_stories(all_stories)
        if not all_stories:
            sys.exit("\n⚠️  Nothing approved.")

    # ── Did You Know
    did_you_know = fetch_did_you_know()

    # ── Build + write
    output = build_output(all_stories, did_you_know)

    if args.dry_run:
        print_dry_run(output)
    else:
        write_output(output, OUTPUT_FILE)
    print()


if __name__ == "__main__":
    main()
