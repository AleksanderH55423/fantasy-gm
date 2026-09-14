# ESPN Weekly Fantasy Football Report

This companion tool gathers your ESPN Fantasy Football league, asks OpenAI for
a current weekly analysis, and emails it through Resend. It is separate from
`../sleeper`. Configuration, dependencies, and the weekly workflow now live at
the repository root.

## Setup

1. Copy `../.env.example` to `../.env` and fill in the required values.
2. Set `ESPN_LEAGUE_ID` from your ESPN league URL, `ESPN_SEASON` to the league
   season, and `ESPN_TEAM_ID` to your numerical team ID. The team ID is visible
   in ESPN league URLs and API responses.
3. For a private league, set `ESPN_S2` and `ESPN_SWID` to the values of those
   cookies from an authenticated ESPN browser session. Treat both as secrets.
   Public leagues do not normally need them.
4. Install and test:

   ```bash
   pip install -r requirements.txt
   python espn/fantasy_report.py
   ```

The script fetches league settings, all team rosters, and ESPN's available/
waiver player list. It never asks the model to invent waiver availability.
Local runs print the report and do not email it. Add `--send` when you want a
manual run to deliver an email:

```bash
python espn/fantasy_report.py --send
```

## GitHub Actions

Use the root `thursday_report.yml`, which runs both leagues and sends one
combined weekly email. Add the root `.env.example` variables as GitHub Actions
secrets.

## Notes

ESPN's fantasy read endpoint is an unsupported web API, so ESPN can change its
fields or cookie requirements. If ESPN changes it, the error will occur before
any report is emailed. Update the ESPN credentials when their session expires.
