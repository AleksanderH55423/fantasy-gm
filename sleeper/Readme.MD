# Weekly Fantasy Football Report

Pulls your Sleeper league, has Claude analyze it with live web search, and
emails you a report every Thursday.

## 1. Get your Sleeper league ID

Open your league in the Sleeper app or at sleeper.com — the ID is the number
in the URL, e.g. `sleeper.com/leagues/987654321`.

## 2. Choose an AI provider and get your API keys

The script supports either OpenAI or Anthropic to generate the report —
pick one and set `LLM_PROVIDER` accordingly in your `.env` file. It defaults
to `openai`.

**If using OpenAI:**
1. Go to platform.openai.com and sign up/log in (separate from a ChatGPT
   subscription).
2. Settings → Billing → add a payment method and some credit ($5-10 minimum
   top-up is typical).
3. Settings → API keys → Create new secret key. Copy it into `.env` as
   `OPENAI_API_KEY`.
4. Optional but recommended: Settings → Limits → set a monthly spend cap so
   a stuck or looping script can't run up unexpected charges.
5. Leave `OPENAI_MODEL` as `gpt-5.6-sol` (a good default), or swap in
   `gpt-5.6-terra`/`gpt-5.6-luna` for a cheaper, faster model.

**If using Anthropic instead:**
1. Go to console.anthropic.com and sign up/log in.
2. Settings → Billing → add a payment method and credit.
3. Settings → API Keys → Create Key. Copy it into `.env` as
   `ANTHROPIC_API_KEY`.
4. Set `LLM_PROVIDER=anthropic` in `.env`.

**Either way, also get:**
- **Resend API key** — sign up free at resend.com (100 emails/day free tier).
  You can send from `onboarding@resend.dev` with no setup, or verify your own
  domain for a custom "from" address.

## 3. Test it locally first

```bash
pip install -r requirements.txt
python sleeper/fantasy_report.py
```

The script automatically loads the root `.env` on startup (via `python-dotenv`), so
you don't need to set anything in your terminal session. `.env` is already
listed in `.gitignore`, so it won't get committed to GitHub by accident —
never commit real API keys.

If it works, the report will print in your terminal. To email a report from a
manual run, add `--send`:

```bash
python sleeper/fantasy_report.py --send
```

## 4. Set up automatic weekly runs (GitHub Actions)

1. Create a new GitHub repo (private is fine) and push these files to it.
2. Move the root `thursday_report.yml` into a folder called `.github/workflows/`.
3. In the repo, go to **Settings → Secrets and variables → Actions** and add
   these as repository secrets:
   - `SLEEPER_LEAGUE_ID`
   - `SLEEPER_USERNAME`
   - `RESEND_API_KEY`
   - `EMAIL_TO`
   - `LLM_PROVIDER` (set to `openai` or `anthropic`)
   - `OPENAI_API_KEY` (if using OpenAI)
   - `ANTHROPIC_API_KEY` (if using Anthropic)
4. Go to the **Actions** tab, find "Fantasy GM Weekly Report", and
   click "Run workflow" to test it manually before waiting for Thursday.

The workflow passes `--send`, so scheduled and GitHub Actions manual runs
email the report.

The workflow is scheduled for 9am ET on Thursdays — edit the cron line in
the YAML if you want a different day/time. GitHub Actions cron runs in UTC.

## Notes & things to tune

- **Username matching**: `SLEEPER_USERNAME` must exactly match your Sleeper
  display name (case-insensitive). If the script errors saying it can't find
  you, double check this against the "Members" tab in your league.
- **Player cache**: the script caches Sleeper's full player list for 3 days
  to avoid re-downloading a large file every run. On GitHub Actions this is
  handled by the `actions/cache` step in the workflow.
- **Improving trade suggestions**: the quality of trade advice depends on
  giving Claude the full league roster context, which the script already
  does. If proposals still feel off, try adding your league's scoring
  settings (PPR/standard/superflex) into the prompt inside
  `generate_report()`.
- **Costs**: each run makes one Claude API call with web search enabled.
  Typical cost is a few cents per report.
