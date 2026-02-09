# 00 — Build Manifest

## Project

**Bitcoin Cycle Monitor v2.0** — Transform a manual CLI tool into a self-running personal Bitcoin intelligence system with web dashboard, email digests, and persistent background monitoring.

## Document Index

| # | Document | Path | Purpose |
|---|----------|------|---------|
| 00 | Build Manifest | `specs/00-build-manifest.md` | This file. Master index and execution guide. |
| 01 | Automation (launchd) | `specs/01-automation-launchd.md` | Persistent background scheduling via macOS launchd |
| 02 | macOS Notifications | `specs/02-macos-notifications.md` | Hardened native desktop alerts replacing os.system |
| 03 | Email Digest | `specs/03-email-digest.md` | SMTP weekly digest delivery with embedded charts |
| 04 | Historical Data | `specs/04-historical-data.md` | Full-cycle price backfill (2013–present) via multi-source |
| 05 | Web Dashboard | `specs/05-web-dashboard.md` | Flask app with full + partner views on local network |
| 06 | Interactive Charts | `specs/06-interactive-charts.md` | Plotly migration for web dashboard interactivity |

## Execution Order

Build in this sequence. Each phase can be tested independently before moving to the next.

```
Phase 1 — Foundation (parallel, no dependencies)
├── 04-historical-data.md     Build + test backfill system
└── 02-macos-notifications.md Build + test hardened notifications

Phase 2 — Visualization (depends on Phase 1)
└── 06-interactive-charts.md  Build + test Plotly charts (needs historical data from 04)

Phase 3 — Delivery (parallel, depends on Phase 2)
├── 05-web-dashboard.md       Build + test Flask app (needs charts from 06)
└── 03-email-digest.md        Build + test email sending (independent but benefits from full picture)

Phase 4 — Orchestration (depends on all above)
└── 01-automation-launchd.md  Build + test launchd services (triggers notifications, email, web)
```

### Phase 1: Foundation

| Task | New Files | Modified Files | New Deps |
|------|-----------|---------------|----------|
| Historical data backfill | `monitor/backfill.py`, `monitor/api/yfinance_client.py`, `monitor/api/csv_backfill.py`, `data/seed_prices.csv`, `tests/test_backfill.py` | `monitor/monitor.py`, `monitor/api/coingecko.py`, `models/database.py`, `alerts/engine.py`, `main.py`, `requirements.txt` | `yfinance>=0.2.30` |
| macOS notifications | `tests/test_notifications.py` | `alerts/channels.py`, `config/default_config.yaml`, `main.py` | None |

**Verification:** Run `python main.py monitor backfill --full` and confirm 4,000+ price records. Trigger a CRITICAL alert and confirm macOS notification appears with sound.

### Phase 2: Visualization

| Task | New Files | Modified Files | New Deps |
|------|-----------|---------------|----------|
| Interactive charts | `web/__init__.py`, `web/charts.py`, `web/chart_data.py`, `tests/test_web_charts.py` | `dca/charts.py`, `requirements.txt` | `plotly>=5.18.0` |

**Verification:** Import `web.charts`, call `scenario_fan()` with test data, confirm valid Plotly figure JSON output.

### Phase 3: Delivery

| Task | New Files | Modified Files | New Deps |
|------|-----------|---------------|----------|
| Web dashboard | `web/app.py`, `web/templates/base.html`, `web/templates/dashboard.html`, `web/templates/partner.html`, `web/static/style.css`, `tests/test_web.py` | `main.py`, `requirements.txt` | `flask>=3.0.0` |
| Email digest | `notifications/email_sender.py`, `tests/test_email.py` | `alerts/channels.py`, `main.py`, `config/default_config.yaml`, `dca/charts.py` | None (stdlib) |

**Verification:** Run `python main.py web`, visit `http://localhost:5000` and `http://localhost:5000/partner`. Run `python main.py email test` and confirm email arrives.

### Phase 4: Orchestration

| Task | New Files | Modified Files | New Deps |
|------|-----------|---------------|----------|
| launchd automation | `service/__init__.py`, `service/launchd.py`, `tests/test_service.py` | `main.py`, `config/default_config.yaml` | None |

**Verification:** Run `python main.py service install`, wait 15 minutes, check `python main.py service logs`. Confirm fetch ran automatically.

## Tech Stack Decisions

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Background scheduling** | macOS launchd | Native, survives reboots, handles sleep/wake, manages processes |
| **Desktop notifications** | osascript via subprocess | Zero dependencies, works on all macOS versions |
| **Email delivery** | Python stdlib smtplib | Zero dependencies, SMTP is simple, TLS built in |
| **Historical data (2014+)** | yfinance library | Free, no API key, reliable, goes back to Sep 2014 |
| **Historical data (2013)** | Bundled CSV | Fills gap before Yahoo Finance data, ~15 KB |
| **Web framework** | Flask 3.0 | Simple, Jinja2 templates, no build step, mature |
| **Interactive charts** | Plotly.js (CDN) + plotly Python | Python API for data prep, JS for rendering, zero build step |
| **Static charts (email)** | Matplotlib (existing) | Email can't run JS, PNGs embedded as base64 |
| **Frontend styling** | Single CSS file (CSS Grid) | No framework, no build step, responsive, ~200 lines |
| **Frontend JS** | Vanilla JavaScript | Fetch API for auto-refresh, Plotly.js for charts, no npm |

## New Dependencies Summary

| Package | Version | Purpose | Size |
|---------|---------|---------|------|
| `yfinance` | >=0.2.30 | Historical BTC/USD prices from Yahoo Finance | ~1 MB installed |
| `plotly` | >=5.18.0 | Interactive chart generation (Python API) | ~30 MB installed |
| `flask` | >=3.0.0 | Web dashboard server | ~2 MB installed |

Total new install footprint: ~33 MB. All pure Python, no system dependencies.

Updated `requirements.txt`:
```
requests>=2.31.0
click>=8.1.0
pyyaml>=6.0
rich>=13.0.0
matplotlib>=3.7.0
schedule>=1.2.0
pytest>=7.4.0
yfinance>=0.2.30
plotly>=5.18.0
flask>=3.0.0
```

## Complete New File Inventory

| File | Spec Doc | Lines (est.) |
|------|----------|-------------|
| `monitor/backfill.py` | 04 | ~150 |
| `monitor/api/yfinance_client.py` | 04 | ~60 |
| `monitor/api/csv_backfill.py` | 04 | ~30 |
| `data/seed_prices.csv` | 04 | ~620 rows |
| `web/__init__.py` | 05/06 | ~5 |
| `web/app.py` | 05 | ~200 |
| `web/charts.py` | 06 | ~350 |
| `web/chart_data.py` | 06 | ~150 |
| `web/templates/base.html` | 05 | ~80 |
| `web/templates/dashboard.html` | 05 | ~150 |
| `web/templates/partner.html` | 05 | ~100 |
| `web/static/style.css` | 05 | ~200 |
| `notifications/email_sender.py` | 03 | ~200 |
| `service/__init__.py` | 01 | ~5 |
| `service/launchd.py` | 01 | ~250 |
| `tests/test_backfill.py` | 04 | ~80 |
| `tests/test_notifications.py` | 02 | ~60 |
| `tests/test_web_charts.py` | 06 | ~80 |
| `tests/test_web.py` | 05 | ~80 |
| `tests/test_email.py` | 03 | ~80 |
| `tests/test_service.py` | 01 | ~60 |
| **Total new** | | **~2,990 lines** |

## Complete Modified File Inventory

| File | Changed By Specs | Nature of Change |
|------|-----------------|------------------|
| `main.py` | 01, 02, 03, 04, 05 | Add `service`, `email`, `web` command groups; update `backfill`; update channel registration |
| `alerts/channels.py` | 02, 03 | Replace DesktopChannel; add EmailChannel |
| `config/default_config.yaml` | 01, 02, 03 | Add `service:`, `notifications:`, `email:` sections |
| `monitor/monitor.py` | 04 | Update `backfill_history()` for `--full` mode |
| `monitor/api/coingecko.py` | 04 | Update `get_full_history()` docstring |
| `models/database.py` | 04 | Add `get_price_gaps()`, `get_nearest_snapshot()` |
| `alerts/engine.py` | 04 | Add `_compute_btc_gold_change_30d()` |
| `dca/charts.py` | 03, 06 | Update `_save()` for buffer support; extract data prep to shared module |
| `requirements.txt` | 04, 05, 06 | Add `yfinance`, `flask`, `plotly` |

## Open Questions

None. All architectural decisions have been made and documented:

- Notification method: macOS osascript (hardened) — decided
- Email delivery: stdlib smtplib — decided
- Historical data: yfinance + bundled CSV — decided
- Web framework: Flask + Jinja2 — decided
- Chart library: Plotly (web) + Matplotlib (email) — decided
- Scheduling: launchd — decided
- Frontend: Vanilla JS + Plotly.js CDN — decided

## Regression Safety

Every spec document includes the requirement: **"All 165 existing tests still pass."**

Each phase adds new test files without modifying existing tests. The only modified production files are additive changes (new methods, new channels, new CLI commands) — no existing behavior is altered.

Recommended test sequence after each phase:
```bash
source venv/bin/activate
python -m pytest tests/ -q --tb=short
```

---

All specification documents are complete. The system is fully described and ready to build. Use these documents as your source of truth for implementation.
