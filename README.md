# SCOPAY for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Validate HACS](https://github.com/robbrad/ha-scopay/actions/workflows/hacs_validation.yml/badge.svg)](https://github.com/robbrad/ha-scopay/actions/workflows/hacs_validation.yml)
[![Tests](https://github.com/robbrad/ha-scopay/actions/workflows/tests.yml/badge.svg)](https://github.com/robbrad/ha-scopay/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Bring your child's **SCOPAY** (Tucasi) school payment account into Home
Assistant: cashless catering balance, money owed for trips and clubs, the
latest transaction, and spend trends you can actually budget against.

> Unofficial. Not affiliated with, endorsed by, or supported by Tucasi Ltd.

## Sensors

| Sensor | Description |
| --- | --- |
| Cashless catering balance | Current dinner-money balance. Lists every product as an attribute. |
| Amount owed | Total outstanding across all trips, clubs and items. |
| Last transaction | Amount of the most recent completed payment, with its date and description. |
| Alerts | Number of unread SCOPAY alerts. |
| Catering spend (7 days) | Money spent on catering in the last 7 days. |
| Catering spend (30 days) | Money spent on catering in the last 30 days, with the recent rows as an attribute. |
| Catering avg per school day | Mean spend across days your child actually spent — weekends and holidays do not drag it down. |
| Catering projected monthly | The average above, extrapolated over a typical 19-school-day month. |

Only negative rows count as spend, so top-ups never inflate the totals.

## Installation

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories**
2. Add `https://github.com/robbrad/ha-scopay`, category **Integration**
3. Install **SCOPAY**, then restart Home Assistant
4. **Settings → Devices & Services → Add Integration → SCOPAY**

### Manual

Copy `custom_components/scopay` into your Home Assistant `config/custom_components`
directory and restart.

## Configuration

Everything is set up in the UI.

| Field | Notes |
| --- | --- |
| Email address | Your SCOPAY parent login |
| Password | Stored in Home Assistant's encrypted config entry storage |
| Pupil account ID | **Leave blank unless you have more than one child.** See below. |
| Update interval | Minutes between polls. 15–1440, default 60. |

### More than one child

Add the integration once per child. To find a pupil's account ID, sign in to
SCOPAY, select that child, and read the number from the address bar:

```
https://www.scopay.com/account/AccountHistory/1234/56789/-1
                                               ^^^^  ^^^^^
                                             site ID  pupil account ID
```

Use the second number. Each entry gets its own device, its own login session
and its own set of sensors.

### Changing the poll interval

**Settings → Devices & Services → SCOPAY → Configure.** SCOPAY updates a few
times a day at most, so the hourly default is plenty — please do not poll
aggressively.

## Example automation

Warn when dinner money is running low, at most once a day:

```yaml
automation:
  - alias: "Low school dinner balance"
    triggers:
      - trigger: numeric_state
        entity_id: sensor.scopay_alex_cashless_catering_balance
        below: 5
        for: "00:30:00"
    actions:
      - action: notify.mobile_app_phone
        data:
          title: "School dinner money low"
          message: >-
            {{ states('sensor.scopay_alex_cashless_catering_balance') }} left —
            about {{ (states('sensor.scopay_alex_catering_avg_per_school_day')
            | float(0)) | round(2) }} a day.
```

## How it works

SCOPAY has no public API — no JSON endpoints, no tokens, no HTTP Basic Auth.
This integration performs the same form login a browser does, keeps the
resulting `SESSION` cookie in a dedicated `aiohttp` session per pupil, and
parses the server-rendered HTML.

That means **page changes on SCOPAY's side can break it**. All parsing lives in
[`parse.py`](custom_components/scopay/parse.py) as pure functions with no
Home Assistant or network imports, so a breakage can be reproduced and fixed
against a saved HTML fixture without a live account.

## Privacy

Your credentials go to `www.scopay.com` and nowhere else. There is no
telemetry, and no third-party service is involved. Credentials live in Home
Assistant's config entry storage; the integration prompts you to re-enter your
password if SCOPAY ever rejects it.

**When reporting a bug, redact your email, password and your child's name from
any logs you attach.**

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-test.txt
pytest
ruff check . && ruff format --check .
```

Commits follow [Conventional Commits](https://www.conventionalcommits.org) —
the release version is derived from them by Commitizen, so `feat:` and `fix:`
prefixes matter. `pre-commit install` sets up the same checks CI runs.

## Contributing

Issues and PRs welcome. Please never paste real credentials or a child's
personal data into an issue, a test fixture or a log.

## Licence

[MIT](LICENSE)
