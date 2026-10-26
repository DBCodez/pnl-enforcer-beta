# PnL Enforcer Beta — Agent Rules & Architecture

## Project Overview
- **Single-file Python app (`enforcer.py`)** + Windows launcher (`Launch_Enforcer.bat`).
- **UI:** `tkinter` (800x85 5-column HUD + widescreen Pre-Flight settings window).
- **Brokers:** Charles Schwab (`schwab-py`) and Webull (`webull-openapi-python-sdk`) via `SchwabAdapter` and `WebullAdapter`.

## Strict Guardrail Invariants (NEVER VIOLATE)
1. **No Hardcoded Keys or Repo Tokens:** All user tokens/configs (`schwab_token.json`, `enforcer_config.json`, `enforcer_log.txt`, and Webull `conf/token.txt`) MUST resolve to `os.path.expanduser("~")` (`USER_HOME`). Never store credentials inside the project directory.
2. **Equities vs. Options:**
   - **Equities:** Tracked for HUD PnL, warning sirens, AND automated flatten orders (RTH Market orders `9:30–16:00 ET`; Extended-Hours marketable `GTC_EXT` / `ALL` limit orders outside RTH).
   - **Options:** Tracked for HUD PnL and warning sirens ONLY (100x multiplier). NEVER auto-flatten option contracts.
3. **Per-Account Session Separation:** Daily baselines (`start_equity`, `max_equity`, `daily_max_equity`, `last_flat_equity`) are stored per broker + account ID inside `config["account_sessions"]`. Switching brokers must never cross-contaminate baselines.
4. **Surgical Edits Only:** Do not delete existing RTH/Pre-Market tier rules, smart dimming callbacks (`refresh_smart_dimming`), or `[FLATTEN]` / `[GUARDRAIL]` audit log statements when making targeted edits.