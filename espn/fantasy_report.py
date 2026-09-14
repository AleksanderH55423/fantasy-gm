"""Email a weekly fantasy-football report for an ESPN Fantasy league.

ESPN's fantasy read API is not an official public integration, so its response
shape can change. Private leagues need the ESPN_S2 and ESPN_SWID browser-cookie
values. Keep both in .env or GitHub Actions secrets.
"""

import argparse
import html
import json
import os
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

LEAGUE_ID = os.environ["ESPN_LEAGUE_ID"]
SEASON = os.environ["ESPN_SEASON"]
MY_TEAM_ID = int(os.environ["ESPN_TEAM_ID"])
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
RESEND_API_KEY = os.environ["RESEND_API_KEY"]
EMAIL_TO = os.environ["EMAIL_TO"]
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-sol")

ESPN_BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
POSITION_NAMES = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST"}


def espn_session():
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (compatible; weekly-fantasy-report/1.0)"
    if os.getenv("ESPN_S2"):
        session.cookies.set("espn_s2", os.environ["ESPN_S2"], domain=".espn.com")
    if os.getenv("ESPN_SWID"):
        session.cookies.set("SWID", os.environ["ESPN_SWID"], domain=".espn.com")
    return session


def league_url():
    return f"{ESPN_BASE}/seasons/{SEASON}/segments/0/leagues/{LEAGUE_ID}"


def get_league(session):
    response = session.get(
        league_url(),
        params=[("view", "mSettings"), ("view", "mStatus"), ("view", "mTeam"), ("view", "mRoster")],
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_free_agents(session, limit=30):
    """Return ESPN's available/waiver player pool, or an empty list if unavailable."""
    fantasy_filter = {
        "players": {
            "filterStatus": {"value": ["FREEAGENT", "WAIVERS"]},
            "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
            "limit": limit,
        }
    }
    response = session.get(
        league_url(),
        params={"view": "kona_player_info"},
        headers={"x-fantasy-filter": json.dumps(fantasy_filter)},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("players", [])


def team_name(team):
    return " ".join(part for part in (team.get("location"), team.get("nickname")) if part).strip() or f"Team {team['id']}"


def player_label(entry):
    player = entry.get("playerPoolEntry", {}).get("player", entry.get("player", entry))
    name = player.get("fullName", "Unknown player")
    position = POSITION_NAMES.get(player.get("defaultPositionId"), "FLEX")
    pro_team = player.get("proTeamId")
    injury = player.get("injuryStatus")
    suffix = f"; {injury}" if injury and injury != "ACTIVE" else ""
    return f"{name} ({position}, NFL team {pro_team or 'FA'}{suffix})"


def roster_labels(team):
    entries = team.get("roster", {}).get("entries", [])
    return [player_label(entry) for entry in entries]


def rostered_player_ids(teams):
    return {
        entry.get("playerPoolEntry", {}).get("player", {}).get("id")
        for team in teams
        for entry in team.get("roster", {}).get("entries", [])
    }


def free_agent_labels(raw_players, rostered_ids):
    labels = []
    for item in raw_players:
        player = item.get("player", item.get("playerPoolEntry", {}).get("player", {}))
        if player.get("id") in rostered_ids:
            continue
        labels.append(player_label(item))
    return labels


def league_summary(teams):
    return "\n".join(f"- {team_name(team)}: {', '.join(roster_labels(team))}" for team in teams)


def build_prompt(my_team, teams, settings, free_agents, week):
    scoring = settings.get("scoringSettings", {})
    roster = ", ".join(roster_labels(my_team))
    available = ", ".join(free_agents) if free_agents else "No verified ESPN free-agent list was returned; do not name waiver targets."
    return f"""You are a fantasy-football analyst writing a concise Thursday report for {team_name(my_team)}, ESPN NFL Week {week}.

MY ROSTER:
{roster}

FULL LEAGUE ROSTERS:
{league_summary(teams)}

VERIFIED ESPN FREE AGENTS / WAIVERS:
{available}

LEAGUE SETTINGS (raw ESPN scoring values):
{json.dumps(scoring, separators=(',', ':'))}

Use web search for the newest injury reports, beat-writer news, and matchup context. Only recommend waiver players from the verified ESPN list above. Write Markdown with these sections:
## Injury & News Watch
## Start/Sit Calls
## Waiver Wire Targets
## Trade Opportunities
For trades, name 1-2 realistic proposals using another listed team and its roster construction. Be decisive, specific, and brief.

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


def generate_report(prompt):
    from openai import OpenAI

    response = OpenAI(api_key=OPENAI_API_KEY).responses.create(
        model=OPENAI_MODEL,
        tools=[{"type": "web_search"}],
        input=prompt,
        # This includes hidden reasoning tokens. A web-search report can use
        # more than 2,200 tokens before producing visible text.
        max_output_tokens=5000,
        store=False,
    )
    if response.incomplete_details:
        reason = getattr(response.incomplete_details, "reason", "unknown reason")
        raise RuntimeError(f"AI response was incomplete: {reason}")
    if response.error:
        message = getattr(response.error, "message", str(response.error))
        raise RuntimeError(f"AI response failed: {message}")
    return response.output_text


def report_html(report):
    """Safely preserve model output in a readable email without trusting its HTML."""
    escaped = html.escape(report)
    escaped = escaped.replace("\n", "<br>\n")
    return f"<div style='font-family:Arial,sans-serif;line-height:1.5'>{escaped}</div>"


def send_email(subject, body):
    response = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
        json={"from": EMAIL_FROM, "to": [EMAIL_TO], "subject": subject, "html": body},
        timeout=30,
    )
    response.raise_for_status()


def build_report():
    """Collect ESPN data and return (week, report text) without emailing."""
    session = espn_session()
    league = get_league(session)
    teams = league.get("teams", [])
    my_team = next((team for team in teams if team.get("id") == MY_TEAM_ID), None)
    if not my_team:
        raise ValueError(f"ESPN_TEAM_ID {MY_TEAM_ID} was not found in this league.")

    try:
        free_agents = free_agent_labels(get_free_agents(session), rostered_player_ids(teams))
    except requests.RequestException as exc:
        print(f"Could not load ESPN free agents: {exc}")
        free_agents = []

    week = league.get("status", {}).get("currentMatchupPeriod", "current")
    print(f"Building ESPN report for week {week} at {datetime.now().isoformat(timespec='seconds')}...")
    prompt = build_prompt(my_team, teams, league.get("settings", {}), free_agents, week)
    report = generate_report(prompt)
    if not isinstance(report, str) or not report.strip():
        return week, ""
    return week, report


def main():
    parser = argparse.ArgumentParser(description="Generate an ESPN fantasy-football report.")
    parser.add_argument("--send", action="store_true", help="Email the report through Resend.")
    args = parser.parse_args()

    week, report = build_report()
    if not report:
        print("no output")
        return

    if args.send:
        send_email(f"Your ESPN Week {week} Fantasy Football Report", report_html(report))
        print("Report sent successfully.")
    else:
        print("\n" + report)
        print("\nReport was not emailed. Run with --send to deliver it through Resend.")


if __name__ == "__main__":
    main()
