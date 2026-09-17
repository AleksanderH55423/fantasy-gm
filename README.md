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

## Interactive advisor

Ask one-off trade, waiver, or start/sit questions without generating the weekly
email:

```bash
python advisor_chat
```

Choose Sleeper or ESPN when prompted. It uses the same root `.env` configuration
as the reports. The advisor loads your starters and bench, an available-player
list, and compact league roster summaries; mention another team by name when
you want its full roster considered for a trade. It uses live web search only
for questions that need current news, such as injuries, weather, or start/sit
calls. Enter `exit` or `quit` to finish.

For weekly delivery, the workflow is already located at
`.github/workflows/thursday_report.yml`. Add the variables from `.env.example`
as GitHub Actions secrets after the repository is pushed to GitHub. It sends one
combined email every Thursday at 14:00 UTC.
