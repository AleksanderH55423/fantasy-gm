"""Build one combined weekly report for the configured Sleeper and ESPN leagues."""

import argparse
import html
import os
import re
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
    sleeper_body = sleeper_report.split("\n\n", 1)[-1]
    opening = next((line.strip() for line in sleeper_body.splitlines() if line.strip()), "Fantasy GM in the Group Chat 🏈")
    if " in the " not in opening:
        opening = "Fantasy GM in the Group Chat 🏈"
    # The opening joke is promoted above the title, so remove that first copy
    # from the embedded Sleeper section.
    sleeper_report = sleeper_report.replace(opening, "", 1)
    return opening + "\n\n" + title + "\n\n" + sleeper_report + "\n\n---\n\n" + espn_report


def markdown_to_email_html(report):
    """Render the report's small Markdown subset as email-friendly HTML."""
    # Keep the report conversational: retain Markdown link labels, but never
    # expose source URLs or web-search citation tokens in the email.
    report = re.sub(r"\[([^\]]+)\]\((?:https?://|www\.)[^)]+\)", r"\1", report)
    report = re.sub(r"<?(?:https?://|www\.)[^\s)>]+>?", "", report)
    report = re.sub(r"cite[^]+", "", report)
    parts = []
    paragraph = []
    list_items = []

    def inline(text):
        escaped = html.escape(text)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
        return escaped

    def flush_paragraph():
        if paragraph:
            parts.append(
                "<p style='margin:0 0 14px;'>" + "<br>".join(inline(line) for line in paragraph) + "</p>"
            )
            paragraph.clear()

    def flush_list():
        if list_items:
            items = "".join(f"<li style='margin:0 0 6px;'>{inline(item)}</li>" for item in list_items)
            parts.append(f"<ul style='margin:0 0 14px;padding-left:22px;'>{items}</ul>")
            list_items.clear()

    for line in report.splitlines():
        heading = re.fullmatch(r"\s*(#{1,6})\s+(.+?)\s*#*\s*", line)
        bullet = re.fullmatch(r"\s*[-*]\s+(.+)", line)
        if heading:
            flush_paragraph()
            flush_list()
            level = "h1" if len(heading.group(1)) == 1 else "h2"
            style = (
                "margin:24px 0 10px;font-size:24px;line-height:1.2;color:#16213e;"
                if level == "h1"
                else "margin:22px 0 9px;font-size:18px;line-height:1.3;color:#2563eb;"
            )
            parts.append(f"<{level} style='{style}'>{inline(heading.group(2))}</{level}>")
        elif re.fullmatch(r"\s*---+\s*", line):
            flush_paragraph()
            flush_list()
            parts.append("<hr style='border:0;border-top:1px solid #dbe3ef;margin:28px 0;'>")
        elif bullet:
            flush_paragraph()
            list_items.append(bullet.group(1))
        elif line.strip():
            flush_list()
            paragraph.append(line.strip())
        else:
            flush_paragraph()
            flush_list()

    flush_paragraph()
    flush_list()
    return "<div style='font-family:Arial,sans-serif;line-height:1.55;color:#1f2937;'>" + "".join(parts) + "</div>"


def send_email(subject, report):
    response = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
        json={
            "from": os.getenv("EMAIL_FROM", "onboarding@resend.dev"),
            "to": [os.environ["EMAIL_TO"]],
            "subject": subject,
            "html": markdown_to_email_html(report),
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
