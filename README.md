# Fantasy GM

One weekly report for a Sleeper league and an ESPN Fantasy league. The root
command gathers both reports, combines them, and either prints or emails it.

1. If you do not already have one, copy `.env.example` to `.env` and fill in
   both leagues' configuration. Existing users should keep their current `.env`.
2. Run `pip install -r requirements.txt`.
3. Run `python fantasy_gm.py` to print the merged report locally.
4. Run `python fantasy_gm.py --send` to email it through Resend.

Individual commands remain in `sleeper/fantasy_report.py` and
`espn/fantasy_report.py`; both load the shared root `.env` and print by default.

For weekly delivery, the workflow is already located at
`.github/workflows/thursday_report.yml`. Add the variables from `.env.example`
as GitHub Actions secrets after the repository is pushed to GitHub. It sends one
combined email every Thursday at 14:00 UTC.
