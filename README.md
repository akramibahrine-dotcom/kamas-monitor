# Kamas Price Monitor — Multi-server

Hourly check of multiple Dofus servers on
[leskamas.com](https://www.leskamas.com/en-gb/sell-kamas.html).
Sends a Gmail alert when any monitored server's Morocco (Dhs/M) price
enters its configured target range.

Current targets:
- **Imagiro**: 6.0 – 7.0 Dhs/M
- **TalKasha**: 6.0 – 7.0 Dhs/M
- **Dakal**: 11.0 – 13.0 Dhs/M

When several servers enter their ranges at the same time, you get **one combined email**, not separate ones.

Runs entirely on GitHub Actions free tier — no server, no cost.

## Files

```
kamas-monitor/
├── monitor.py                       # the scraper + emailer
├── requirements.txt                 # Python dependencies
├── README.md                        # this file
└── .github/
    └── workflows/
        └── monitor.yml              # GitHub Actions schedule
```

## Setup (~10 minutes, one time)

### 1. Create a GitHub repo

1. Go to https://github.com/new
2. Create a **private** repo named e.g. `kamas-monitor` (private so your state file isn't public).
3. Upload all the files above, **keeping the folder structure** (`.github/workflows/monitor.yml` must be in that exact path).
   - Easiest way: drag-and-drop the whole `kamas-monitor` folder contents into the GitHub web upload page. GitHub will preserve subfolders.

### 2. Create a Gmail App Password

Gmail SMTP needs an App Password, not your normal Gmail password.

1. Make sure 2-Step Verification is on: https://myaccount.google.com/security
2. Go to https://myaccount.google.com/apppasswords
3. Create a new app password (name it "Kamas Monitor")
4. Copy the 16-character password (ignore the spaces)

### 3. Add repo secrets

In your repo: **Settings → Secrets and variables → Actions → New repository secret**

Add three secrets:

| Name                  | Value                                  |
|-----------------------|----------------------------------------|
| `GMAIL_USER`          | `akramibahrine@gmail.com`              |
| `GMAIL_APP_PASSWORD`  | the 16-character app password           |
| `GMAIL_RECIPIENT`     | `akramibahrine@gmail.com`              |

Sender and recipient are the same — you're emailing yourself.

### 4. Test the workflow

Go to the **Actions** tab → **Kamas Price Monitor** → **Run workflow** button.
It runs immediately. Open the run and check the logs. Expected log line:

```
[2026-05-11T...] Imagiro: 5.371 Dhs/M (threshold 6.0) -> below
No alert needed.
```

If price is below 6 you correctly get no email. To verify the email path works, see "Testing email delivery" below.

## How it works

- **Hourly schedule** (~720 runs/month, ~30 seconds each, well inside the 2000-minute free tier).
- Scrapes the page, parses the Imagiro row, reads the **Morocco(Dhs)** column.
- Tracks state in `state.json`, which GitHub Actions commits back to the repo after each run.
- Sends an email when the price **crosses** from below → above 6 Dhs/M.
- Sends a daily reminder while still above (configurable: `REMINDER_HOURS` in `monitor.py`).
- If the price drops back below 6, no more emails until it crosses again.

## Testing email delivery

To confirm the email part works without waiting for the price to actually rise:

1. Edit `monitor.py`, change `THRESHOLD_DHS = 6.0` to `THRESHOLD_DHS = 0.0`
2. Commit and push
3. Run the workflow manually from the Actions tab
4. You should receive an email
5. **Change it back to 6.0** and commit again

## Customizing

Edit the `TARGETS` list at the top of `monitor.py`. Add, remove, or change entries:

```python
TARGETS = [
    {"server": "Imagiro",  "min": 6.0,  "max": 7.0},
    {"server": "TalKasha", "min": 6.0,  "max": 7.0},
    {"server": "Dakal",    "min": 11.0, "max": 13.0},
    # Add more, e.g.:
    # {"server": "Salar",   "min": 6.0,  "max": 8.0},
]
```

Server names must match the leskamas.com table exactly (capitalization counts: `TalKasha`, not `talkasha`).
Set `max` to a large number like `999` to remove the upper bound.

`REMINDER_HOURS = 24` controls how often you get re-pinged while a server stays in range.

To check more frequently, edit the cron in `.github/workflows/monitor.yml`:
- Every 30 min: `'*/30 * * * *'`
- Every 15 min: `'*/15 * * * *'` (still free, ~120 minutes/month)

## Troubleshooting

| Problem | Fix |
|---|---|
| No email arriving | Check spam folder. Check Actions logs for SMTP errors. |
| `Username and Password not accepted` | Wrong App Password, or 2-Step Verification not enabled on the Gmail account. |
| `Imagiro row not found` | The site's HTML structure changed. Open an issue or re-run this conversation. |
| Cron seems late | GitHub Actions cron can lag 10–30 min during peak traffic. Normal. |
| Workflow showing red X | Open the failed run, read the error in the logs. |

## Notes

- The `state.json` file is auto-created on first run and committed back by the workflow. Don't edit it manually.
- If you delete `state.json`, the next run treats the price as a new "unknown → above" transition and will email you immediately if above threshold.
