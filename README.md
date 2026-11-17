# PnL Enforcer (Closed Beta) — Schwab & Webull Edition

An external, real-time PnL circuit breaker and discipline enforcer for **Charles Schwab (Thinkorswim)** and **Webull** traders on Windows 10/11.

*Built by a trader who needed it. PnL Enforcer runs outside your trading platform and holds you to the limits you set with a clear head — especially on the days you'd rather it didn't.*

📸 **[View App Screenshots (HUD & Pre-Flight Rulebook UI)](https://imgur.com/a/REID2kV)**

---

## 🧪 Try It in 10 Seconds (No API Keys Needed Yet)
Waiting on Schwab or Webull API key approval, or want to see how every guardrail behaves before connecting a live account?
1. Double-click **`Launch_Enforcer.bat`** to open the Pre-Flight Rulebook.
2. Click **`BROKER:`** in the top-left bar and select **`🧪 DEMO (SIMULATOR)`**.
3. Click **`🧪 Launch & Pad`** (or **`LAUNCH DEMO SIMULATOR >>`**) to open the live HUD alongside the interactive **`$25,000` Paper Simulator Controls** — where you can open simulated positions (`+100 NVDA`, `-100 TSLA`, `+2 SPY Calls`), nudge PnL, and rehearse Single-Trade Stops, Daily Stops, Profit Ratchets, Tilt Streaks, and LULD Halts with **zero real orders** and **Windows OS locks disabled** (`100%` isolated from your live account baselines).

---

## ⚠️ IMPORTANT BETA DISCLAIMER & ASSUMPTION OF RISK
This software is **experimental beta software** provided strictly **"AS IS"** without warranty of any kind (see [`LICENSE.txt`](LICENSE.txt)). By installing, configuring, or running this software, you agree that you assume **100% sole responsibility** for your trading account, order executions, and risk management, and agree to indemnify and hold harmless the authors from any trading losses or claims.
* **Not Financial Advice & No Guarantee of Loss Prevention:** This tool is a self-directed client-side mechanical utility, not a registered investment advisor, broker-dealer, or broker-side account block. **It does NOT and CANNOT guarantee that losses will be limited to your configured thresholds.** API outages, network latency, rate limits, rejected orders, illiquid spreads, market gaps, or trading halts can cause actual losses to significantly exceed your configured limits.
* **No Broker Affiliation:** This project is an independent tool and is **not** affiliated with, endorsed by, or sponsored by Charles Schwab, Thinkorswim, or Webull.
* **Test Safely First (`Alarms Only Mode`):** On your first live day, toggle **`🔔 Alarms Only: OFF / ON`** in the bottom launch bar next to **`🚀 SAVE & LAUNCH ENFORCER >>`** to verify live PnL tracking and warning sirens passively before testing live Auto-Flatten with **1 share**.
* **Equities vs. Options:**
  * **Equities (Stocks):** Tracked in real-time for HUD display, warning sirens, **and** automated Market (`9:30 AM – 4:00 PM ET`) / Extended-Hours (`GTC_EXT`) Limit liquidation across stops, Post-Breach Force-Flatten, `Done Today`, and `HOLD 2s: FLATTEN`.
  * **Options Contracts (Siren-Only by Default; Optional Experimental BETA Auto-Flatten):** Tracked in real-time (`100x` multiplier via Mark/Last price) for **HUD Display and Warning Sirens by default** (`Include Options in Auto-Flatten (BETA)` is **OFF** by default).
    * **Default Mode (Siren-Only):** By default, Enforcer never submits orders on Option contracts. If a stop, `Done Today`, or `HOLD 2s: FLATTEN` fires while you hold open options, equities flatten first while an explicit manual-options warning/siren alerts you to close your options manually (and defers any OS Lock or App Kill until flat).
    * **Opt-In `Include Options in Auto-Flatten (BETA — RTH Market Orders)` Toggle (Card 2):** Traders who want automated option liquidation during Regular Trading Hours (`9:30 AM – 4:00 PM ET`) can check **`└─ Include Options in Auto-Flatten (BETA — RTH Market Orders)`** inside Card 2 and accept the mandatory **BETA Options Auto-Flatten Risk Waiver** (recorded in `enforcer_log.txt` and `enforcer_config.json` with a SHA-256 audit hash). When armed during RTH (`9:30 AM – 4:00 PM ET`), Enforcer cancels working orders and submits single-leg RTH **MARKET** orders (`BUY_TO_CLOSE` on short legs first to prevent naked-short margin rejections, followed by `SELL_TO_CLOSE` on long legs). **⚠️ EXTREME SLIPPAGE & SPREAD WARNING:** Option Market orders have no price protection and fill at whatever Bid/Ask liquidity exists at that millisecond; wide bid-ask spreads, illiquid strikes, or fast gamma moves can cause actual realized losses to **substantially exceed** your configured stop threshold. Multi-leg spreads/condors are liquidated leg-by-leg as individual Market orders. Options cannot be auto-flattened outside `9:30 AM – 4:00 PM ET` (the manual siren sounds instead).

---

## Step 1: Get Your Broker API Keys (Schwab OR Webull)
Your API keys stay 100% local on your computer inside `C:\Users\<YourUsername>\enforcer_config.json`. Never share your App Key or App Secret with anyone.

### Option A: If Your Broker is Charles Schwab (Thinkorswim)
1. Go to [developer.schwab.com](https://developer.schwab.com/) and register a free **Individual Developer** account.
   * *(Note: Your regular Schwab/Thinkorswim brokerage login does not log into the Developer Portal—click **Register** on `developer.schwab.com` to create a separate free developer login first. You will link your brokerage accounts later during the browser login step.)*
2. Once logged into the Developer Portal, go to **Dashboard -> Apps -> Create App**:
   * **API Product:** Select `Accounts and Trading Production`
   * **Order Limit:** Enter `120` *(the maximum calls per minute allowed for Individual Developers)*
   * **App Name:** `PnL Enforcer` (or any name)
   * **Callback URL:** `https://127.0.0.1` *(Must match this exact URL—use `https` and do **not** add a trailing `/` slash at the end)*
3. Wait for your app status to change from *Approved - Pending* to **`Ready for Use`** (typically takes 2–5 business days).
4. Once `Ready for Use`, click **View Details** on your app and copy your **App Key** and **Secret**.

### Option B: If Your Broker is Webull (Webull US)
1. Go to [https://developer.webull.com/apis/docs/authentication/IndividualApplicationAPI](https://developer.webull.com/apis/docs/authentication/IndividualApplicationAPI) (or log into your Webull web portal -> **Account Management -> OpenAPI Management**).
2. Apply for a **Retail Trading API Key** (typically approved in 1–2 business days).
3. Once approved, generate and copy your **App Key** and **App Secret** in the OpenAPI portal.
4. *(Note for Live Quotes)*: Webull's OpenAPI uses account position snapshots by default; if you subscribe to Webull OpenAPI real-time quotes (`webullapp.com/quote`), it will also poll live bid/ask quotes during extended-hours liquidations.
5. *(Note for Webull Canada Users)*: Direct self-serve Retail OpenAPI keys (`App Key` / `App Secret`) are currently only offered by **Webull US** (*Webull Financial LLC*). **Webull Canada** (*Webull Securities (Canada) Limited*) does not currently issue direct individual OpenAPI keys and only supports third-party OAuth aggregators (such as SnapTrade), which are not natively supported out of the box due to aggregator refresh/caching latency.

---

## Step 2: Launch the App (Automatic One-Click Setup)
1. Double-click **`Launch_Enforcer.bat`**.
   * *(Windows SmartScreen Note: Because `.bat` scripts downloaded from the internet are unsigned, Windows 10/11 may show a blue **"Windows protected your PC"** prompt the first time you run it. Click **`More info`** -> **`Run anyway`**.)*
2. **Automatic Python & Library Installation:**
   * If Python is not already installed on your PC, `Launch_Enforcer.bat` will automatically install **Python 3.12** via Windows `winget` and configure your system `PATH` (click **Yes** if a Windows permission prompt appears).
   * It will then automatically install all required broker libraries (`schwab-py`, `webull-openapi-python-sdk`, `pillow`, and dependencies) and launch the Pre-Flight Setup Wizard.
3. Accept the **Beta Liability Waiver**, select your broker (**Schwab**, **Webull**, or **Demo Simulator**), and paste your **App Key** and **App Secret** into the first-time setup prompt (or click the **`BROKER:`** dropdown at the top of Pre-Flight anytime and choose **`🔑 API Keys & Renew 7-Day Token...`** / **`🔑 Configure Webull API Keys...`**).
4. **Schwab Browser Login Step (First Time & Every 7 Days):**
   * If using **Schwab**, your web browser will open to the official Charles Schwab login page. Log in with your regular Schwab brokerage credentials and approve account access.
   * After you click approve, your browser will redirect to a blank **"This site can't be reached (`127.0.0.1`)"** page. **This is 100% normal!**
   * Copy the **entire URL** from the top of your browser's address bar (starting with `https://127.0.0.1/?code=...`) — the on-screen **Schwab 7-Day Security Login** popup window will automatically detect it from your clipboard (or click **📋 Paste from Clipboard**), then click **Complete Schwab Login >>**.
   * *(Note: Schwab security tokens last 7 days. You don't need to track this yourself — the app displays your remaining token days in Card 3, **automatically walks you through this renewal early at startup** whenever `< 14 hours` remain so it never expires mid-session, and also lets you renew it manually anytime by clicking **`Token: X.Xd ↻`** in Card 3 or **`BROKER:`** -> **`🔑 API Keys & Renew 7-Day Token...`**.)*
5. Choose which sub-account you want to monitor from the **`ACCOUNT:`** dropdown at the top-left of the Pre-Flight screen.
6. **⏰ Launch Before Your First Trade of the Day:** Always launch the app **before taking your first trade of the day** (or before **9:30 AM ET** if trading Regular Hours) so it can snapshot your clean starting account equity baseline (`$0.00` Daily PnL). Once captured, **that baseline is automatically saved for the rest of the day**—so if you ever close and reopen the app later in the session, it seamlessly restores your morning baseline and full daily PnL without resetting to zero.

---

## Step 3: Quick Guide to Pre-Flight Settings & the Live HUD
* **Card 1 — Trade & Tilt Stops (`Intraday Penalty Box`):**
  * **Single-Trade Stop (`Open PnL`):** Flattens open tracked equity shares (and RTH option contracts if **BETA Options Auto-Flatten** in Card 2 is armed) if a single trade goes against you by your configured dollar limit—cutting a bad trade before it becomes a red day.
  * **Consecutive Loss Cooldown (`Tilt Streak Stop`):** If you close **`X` consecutive losing trades** (each at or beyond your **`Min Loss ($)`** filter in **`⚙ Filter`**, e.g. `-$25`) within **`Y` minutes**, Enforcer cancels working orders, confirms flat, and triggers the **Penalty Box OS Lock Cooldown** so you step away from the mouse instead of revenge-trading. While an active streak is underway (`1/X` or higher), cooldown settings automatically lock (`🔒 LOCKED`) until the rolling window expires or you close a qualifying win (`>= +Win Reset $`).
* **Card 2 — Daily Stop Actions (`Max Loss & Profit Lock`):**
  * Controls what happens when Net PnL hits your active Daily Stop in Card 4 or Card 5: **Auto-Flatten Equities**, optional **`└─ Include Options in Auto-Flatten (BETA — RTH Market Orders)`**, **Kill Thinkorswim / Webull Desktop** (only after the Triple / 15-Second Flat Check confirms `0` open tracked positions), and **Lock Windows OS** (preceded by a multi-monitor Penalty Box briefing card showing exact status).
  * **Post-Breach Force-Flatten:** After a Daily Stop breach (when Auto-Flatten is ON and Alarms Only is OFF), the HUD enters crimson **`🚨 DAILY STOP BREACHED — NEW POSITIONS WILL BE FORCE-FLATTENED`** mode so impulse revenge trades opened later that day are closed automatically until Midnight ET (or until you intentionally adjust your stop / Re-Zero).
  * **Smart LULD Trading Halt Handling:** If a stock enters a trading halt with **no** risk rule breached, Enforcer posts a calm status notice with `0` orders sent. If a stop breaches *during* a halt, Enforcer keeps your exit order queued at the broker (preserving time priority) and pauses App Kill / Windows OS Lock until `100%` flat is triple-confirmed.
* **Card 3 — Today's Session, Discipline Locks & Baseline:**
  * **`🔒 Done Today` (Walk Away Green):** Voluntarily lock in a green session (or call a choppy morning early). Cancels working daytrade orders, flattens open tracked equities right now (even if `Alarms Only` is ON; options only if Options Auto-Flatten is armed during `9:30–4:00 ET`), and auto-flattens impulse re-entries until `00:00 Midnight ET` (with a 5-second cooling-off check if you try to unlock early).
  * **`🔒 Commit Today` (Freeze Your Rulebook):** Optional one-way commitment until `00:00 Midnight ET`—locks your stops, ratchets, presets, `Alarms Only`, `Re-Zero`, and broker/account switching on disk (even across restarts) so mid-session tilt can't move the goalposts. Pair with **`🔒 Done Today`** when you want zero option to unlock early.
  * **`Trade API` Permission Check:** 1-click point-in-time check in Card 3 (`✓ Verified`, `✗ Blocked`, or `Unconfirmed` during broker rate-limits/timeouts) to confirm your API key has live order-routing permission before the bell.
  * **`🛡️ Positions (N)` Swing Filter & `↺ Re-Zero Baseline`:** Pre-existing swing/long-term holdings are automatically marked **`🛡️ Ignored`** on launch (`$0.00` daytrade PnL impact and never touched by flatten sweeps). Use **`↺ Re-Zero Baseline`** after a cash transfer or for a planned fresh afternoon anchor (tamper-locked during open trades, active tilt streaks, or committed sessions).
  * **`⚙ Preferences & Audio...` & Silent Mode (`🔇`):** Configure 9:30 AM / 4:00 PM ratchet resets, **`Mute All Sounds & Voice Callouts`** (highlighted subtly in warm amber as **`🔇 MUTED ·`** and **`🔇 SETTINGS`** so you always know audio is muted), voice callouts, **`🔊 Test`** previews, poll interval, and **`✦ Quick Tour`** (`Spotlight New Controls`).
* **Cards 4 & 5 — Extended Hours vs. Regular Hours (`9:30 AM – 4:00 PM ET`) Rulebooks:**
  * Syncs automatically to **US Eastern Time (New York)** regardless of your PC's local timezone (Market orders in RTH `9:30–4:00 ET`; marketable `GTC_EXT` Limit orders in Pre-Market / After-Hours), ratcheting your Daily Stop upward through Tiers 2, 3, and 4 as realized profit grows.
* **Live HUD Controls & Multi-Monitor Ergonomics:**
  * **`🚨 HOLD 2s: FLATTEN` (Manual 2-Second Bailout):** Press and hold for 2.0 full seconds on the HUD anytime to cancel working daytrade orders and flatten tracked equities immediately (plus RTH options if armed; alerts you if unarmed options remain open)—even if `Alarms Only` is ON. Releasing early cancels cleanly.
  * **10 Customizable Metrics (`📊 HUD Columns`):** Toggle and reorder `REALIZED PnL`, `OPEN PnL`, `NET PnL`, `DAILY STOP`, `$ TO STOP`, `SESSION HIGH`, `SESSION LOW`, `FROM HIGH`, `TRADES (W/L)`, and `LOSS STREAK` (or switch between **Standard 5-Col** and **Compact 3-Col** layouts).
  * **Multi-Monitor Memory & Non-Modal Settings:** Drag both the **HUD** and the **Pre-Flight / Settings** window anywhere across your monitors—both remember their positions across restarts, and the HUD stays draggable and interactive even while Settings is open.

---

## Step 4: Report Bugs, Share Safe Logs & Roll Back Updates (`🐞 Report Bug` & `📜 Logs ▾`)
Real session logs from fellow traders are what make edge-case fixes fast and rock-solid:
* **Built-In Bug Report (`🐞 Report Bug`) & Safe Logs (`📜 Logs ▾`):** Submit a bug report in one click or enable **`Auto-Share Daily Safe Logs`**. Every shared log is automatically scrubbed (`$[REDACTED]` account balances, `~` home paths, masked order IDs, and anonymous 6-char Tester ID) while preserving relative PnL ticks and guardrail events—with a **`🔍 Preview Safe Log`** button so you can inspect every line first.
* **1-Click Version Rollback (`📜 Logs ▾ -> ↺ Revert to Previous Version...`):** Every update automatically backs up your prior working `enforcer.py` and `CHANGELOG.md` as `.prev`. If a new build ever acts up, click **`↺ Revert to Previous Version...`** (available when flat with no active session lock/streak; restores code files while keeping your `~/enforcer_config.json` settings, tokens, and session baselines intact).

---

If you end up enjoying this tool, feel welcome to buy me a coffee (or beer): [https://buymeacoffee.com/dbcodez](https://buymeacoffee.com/dbcodez)
