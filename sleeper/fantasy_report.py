"""
Weekly Fantasy Football Report Generator
-----------------------------------------
Pulls your Sleeper league data, asks an AI model to analyze it (with live
web search for injury/news context), and emails you a Thursday report.
Supports either OpenAI or Anthropic as the analysis provider.

Required environment variables:
  SLEEPER_LEAGUE_ID   - your league's ID from the Sleeper app URL
  SLEEPER_USERNAME    - your Sleeper display name (exactly as shown in-app)
  RESEND_API_KEY      - your Resend API key (resend.com, free tier is fine)
  EMAIL_TO            - where to send the report
  EMAIL_FROM          - (optional) verified sender address, defaults below
  LLM_PROVIDER        - "openai" (default) or "anthropic"
  OPENAI_API_KEY      - required if LLM_PROVIDER=openai
  ANTHROPIC_API_KEY   - required if LLM_PROVIDER=anthropic
"""

import argparse
import os
import re
import json
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

SLEEPER_BASE = "https://api.sleeper.app/v1"

LEAGUE_ID = os.environ["SLEEPER_LEAGUE_ID"]
USERNAME = os.environ["SLEEPER_USERNAME"]
RESEND_API_KEY = os.environ["RESEND_API_KEY"]
EMAIL_TO = os.environ["EMAIL_TO"]
EMAIL_FROM = os.environ.get("EMAIL_FROM", "fantasy-bot@resend.dev")

# Which AI provider to use: "openai" or "anthropic". Defaults to openai.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai").lower()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-sol")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

PLAYERS_CACHE_PATH = Path(__file__).with_name("players_cache.json")
PLAYERS_CACHE_MAX_AGE_SECONDS = 60 * 60 * 24 * 3  # 3 days


def get_json(url):
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()


def get_current_week():
    state = get_json("https://api.sleeper.app/v1/state/nfl")
    return state["week"]


def get_league_data():
    rosters = get_json(f"{SLEEPER_BASE}/league/{LEAGUE_ID}/rosters")
    users = get_json(f"{SLEEPER_BASE}/league/{LEAGUE_ID}/users")
    return rosters, users


def get_players_map():
    """The /players/nfl endpoint is ~5MB and rarely changes, so cache it."""
    if os.path.exists(PLAYERS_CACHE_PATH):
        age = datetime.now().timestamp() - os.path.getmtime(PLAYERS_CACHE_PATH)
        if age < PLAYERS_CACHE_MAX_AGE_SECONDS:
            with open(PLAYERS_CACHE_PATH) as f:
                return json.load(f)
    players = get_json(f"{SLEEPER_BASE}/players/nfl")
    with open(PLAYERS_CACHE_PATH, "w") as f:
        json.dump(players, f)
    return players


def find_user_and_roster(rosters, users, username):
    user = next(
        (u for u in users if u.get("display_name", "").lower() == username.lower()),
        None,
    )
    if not user:
        raise ValueError(
            f"Could not find Sleeper user '{username}' in this league. "
            "Check SLEEPER_USERNAME matches your display name exactly."
        )
    roster = next((r for r in rosters if r["owner_id"] == user["user_id"]), None)
    if not roster:
        raise ValueError(f"Found user '{username}' but no matching roster.")
    return user, roster


def player_label(player_id, players_map):
    p = players_map.get(player_id)
    if not p:
        return player_id
    name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
    pos = p.get("position", "?")
    team = p.get("team") or "FA"
    return f"{name} ({pos}, {team})"


def roster_player_labels(roster, players_map):
    return [player_label(pid, players_map) for pid in (roster.get("players") or [])]


def build_league_summary(rosters, users, players_map):
    user_by_id = {u["user_id"]: u.get("display_name", "Unknown") for u in users}
    lines = []
    for r in rosters:
        owner = user_by_id.get(r["owner_id"], "Unknown")
        labels = roster_player_labels(r, players_map)
        lines.append(f"- {owner}: {', '.join(labels)}")
    return "\n".join(lines)


def get_trending_adds(players_map, hours=24, limit=15):
    trending = get_json(
        f"{SLEEPER_BASE}/players/nfl/trending/add?lookback_hours={hours}&limit={limit}"
    )
    out = []
    for t in trending:
        p = players_map.get(t["player_id"])
        if p:
            label = player_label(t["player_id"], players_map)
            out.append(f"{label} - {t['count']} adds in last {hours}h")
    return out


def build_prompt(my_name, my_roster_labels, league_summary, trending_adds, week):
    return f"""You are a fantasy football analyst writing a Thursday report for {my_name}, NFL Week {week}.

MY ROSTER:
{', '.join(my_roster_labels)}

FULL LEAGUE ROSTERS (use this to spot trade mismatches - a team with surplus
at a position I need, or a team that needs what I have surplus of):
{league_summary}

TRENDING WAIVER ADDS LEAGUE-WIDE (last 24 hours):
{', '.join(trending_adds) if trending_adds else 'No significant trends.'}

Use web search to check current injury reports, beat writer news, and
matchup difficulty for players on my roster and any waiver targets you
mention. Prioritize the most recent news.

Write the report with these sections, using markdown headers:
## Injury & News Watch
Anything affecting my roster this week.

## Start/Sit Calls
Any close calls on my roster, with brief reasoning.

## Waiver Wire Targets
2-3 available or trending players worth adding, with reasoning.

## Trade Opportunities
1-2 realistic trade proposals naming specific other teams/owners in this
league, based on roster mismatches you identified above.

Keep it concise and skimmable. Do not pad with generic disclaimers.
Do not include source citations, URLs, or links in the report.

STYLE RULES:
- Sound like a funny, high-energy frat bro giving real fantasy advice: casual,
  confident, and playful, but never hostile or mean-spirited.
- Your very first line must be a standalone joke in the form "[Player] in the
  [funny place]" followed by one fitting emoji. Base it on a player who balled
  out, flopped, or affected a manager's fantasy week. Example: "Puka in the
  worst" or  "Alec Pierce in being constantly injured" or even "The Panthers
   in getting dogwalked by Caleb Williams". Do not put a markdown header before this line. This should be a 
  roast of a player or a shout-out for a player who had a great week.
- Use 1-2 fitting emojis per section. Keep the actual recommendations specific
  and useful beneath the jokes."""


def generate_report_openai(my_name, my_roster_labels, league_summary, trending_adds, week):
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = build_prompt(my_name, my_roster_labels, league_summary, trending_adds, week)

    response = client.responses.create(
        model=OPENAI_MODEL,
        tools=[{"type": "web_search"}],
        input=prompt,
    )
    return response.output_text


def generate_report_anthropic(my_name, my_roster_labels, league_summary, trending_adds, week):
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = build_prompt(my_name, my_roster_labels, league_summary, trending_adds, week)

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=2000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )
    text_parts = [block.text for block in response.content if block.type == "text"]
    return "\n\n".join(text_parts)


def generate_report(my_name, my_roster_labels, league_summary, trending_adds, week):
    if LLM_PROVIDER == "anthropic":
        if not ANTHROPIC_API_KEY:
            raise ValueError("LLM_PROVIDER is 'anthropic' but ANTHROPIC_API_KEY is not set.")
        return generate_report_anthropic(my_name, my_roster_labels, league_summary, trending_adds, week)
    elif LLM_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise ValueError("LLM_PROVIDER is 'openai' but OPENAI_API_KEY is not set.")
        return generate_report_openai(my_name, my_roster_labels, league_summary, trending_adds, week)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER '{LLM_PROVIDER}'. Use 'openai' or 'anthropic'.")


def markdown_to_html(text):
    """Minimal markdown -> HTML conversion, good enough for an email body."""
    html = text
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    html = html.replace("\n\n", "<br><br>")
    return f"<div style='font-family: sans-serif; line-height: 1.5;'>{html}</div>"


def send_email(subject, html_body):
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
        json={
            "from": EMAIL_FROM,
            "to": [EMAIL_TO],
            "subject": subject,
            "html": html_body,
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def build_report():
    """Collect Sleeper data and return (week, report text) without emailing."""
    week = get_current_week()
    print(f"Building report for NFL week {week}...")

    rosters, users = get_league_data()
    players_map = get_players_map()
    _, my_roster = find_user_and_roster(rosters, users, USERNAME)

    my_labels = roster_player_labels(my_roster, players_map)
    league_summary = build_league_summary(rosters, users, players_map)
    trending_adds = get_trending_adds(players_map)

    print(f"Generating report with {LLM_PROVIDER}...")
    report_text = generate_report(USERNAME, my_labels, league_summary, trending_adds, week)
    if not isinstance(report_text, str) or not report_text.strip():
        return week, ""
    return week, report_text


def main():
    parser = argparse.ArgumentParser(description="Generate a Sleeper fantasy-football report.")
    parser.add_argument("--send", action="store_true", help="Email the report through Resend.")
    args = parser.parse_args()

    week, report_text = build_report()
    if not report_text:
        print("no output")
        return

    if args.send:
        html = markdown_to_html(report_text)
        send_email(f"Your Week {week} Fantasy Football Report", html)
        print("Report sent successfully.")
    else:
        print("\n" + report_text)
        print("\nReport was not emailed. Run with --send to deliver it through Resend.")


if __name__ == "__main__":
    main()
