"""Build one combined weekly report for the configured Sleeper and ESPN leagues."""

import argparse
import html
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

from espn import fantasy_report as espn  # noqa: E402
from sleeper import fantasy_report as sleeper  # noqa: E402


def collect_report(label, builder):
    try:
        week, report = builder()
    except Exception as exc:
        return None, f"## {label}\n\nUnable to generate this league's report: `{exc}`"
    if not report:
        return week, f"## {label}\n\nno output"
    return week, f"## {label} — Week {week}\n\n{report}"


def build_combined_report():
    sleeper_week, sleeper_report = collect_report("Sleeper League", sleeper.build_report)
    espn_week, espn_report = collect_report("ESPN League", espn.build_report)
    weeks = [str(week) for week in (sleeper_week, espn_week) if week is not None]
    title = f"# Fantasy GM Weekly Report{' — Week ' + ' / '.join(weeks) if weeks else ''}"
    return title + "\n\n" + sleeper_report + "\n\n---\n\n" + espn_report


def send_email(subject, report):
    safe_html = html.escape(report).replace("\n", "<br>\n")
    response = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
        json={
            "from": os.getenv("EMAIL_FROM", "onboarding@resend.dev"),
            "to": [os.environ["EMAIL_TO"]],
            "subject": subject,
            "html": f"<div style='font-family:Arial,sans-serif;line-height:1.5'>{safe_html}</div>",
        },
        timeout=30,
    )
    response.raise_for_status()


def main():
    parser = argparse.ArgumentParser(description="Generate a combined Sleeper and ESPN fantasy report.")
    parser.add_argument("--send", action="store_true", help="Email the combined report through Resend.")
    args = parser.parse_args()
    report = build_combined_report()
    if args.send:
        send_email("Your Fantasy GM Weekly Report", report)
        print("Combined report sent successfully.")
    else:
        print("\n" + report)
        print("\nReport was not emailed. Run with --send to deliver it through Resend.")


if __name__ == "__main__":
    main()
