# PnL Enforcer (Closed Beta) — Schwab & Webull Edition

An external, real-time PnL circuit breaker and discipline enforcer for **Charles Schwab (Thinkorswim)** and **Webull** traders on Windows 10/11.

📸 **[View App Screenshots (HUD & Pre-Flight Rulebook UI)](https://imgur.com/a/REID2kV)**

---

## ⚠️ IMPORTANT BETA DISCLAIMER & ASSUMPTION OF RISK
This software is **experimental beta software** provided strictly **"AS IS"** without warranty of any kind (see [`LICENSE.txt`](LICENSE.txt)). By installing, configuring, or running this software, you agree that you assume **100% sole responsibility** for your trading account, order executions, and risk management, and agree to indemnify and hold harmless the authors from any trading losses or claims.
* **Not Financial Advice & No Guarantee of Loss Prevention:** This tool is a self-directed mechanical utility, not a registered investment advisor or broker-dealer. **It does NOT and CANNOT guarantee that losses will be limited to your configured thresholds.** API outages, network latency, rate limits, rejected orders, illiquid spreads, market gaps, or trading halts can cause actual losses to significantly exceed your configured limits.
* **No Broker Affiliation:** This project is an independent tool and is **not** affiliated with, endorsed by, or sponsored by Charles Schwab, Thinkorswim, or Webull.
* **Test Safely First (`Alarms Only Mode`):** On your first day, toggle the global **`🔔 Alarms Only: OFF / ON`** pill in the bottom launch bar next to **`🚀 SAVE & LAUNCH ENFORCER >>`** to verify live PnL tracking and warning sirens passively before testing live Auto-Flatten with **1 share**.
* **Equities vs. Options:**
  * **Equities (Stocks):** Tracked in real-time for HUD display, Alarms, **and** automated Market (`9:30 AM – 4:00 PM ET`) / Extended-Hours (`GTC_EXT`) Limit liquidation.
  * **Options Contracts (Siren-Only by Default; Optional Experimental BETA Auto-Flatten):** Tracked in real-time (`100x` multiplier via Mark/Last price) for **HUD Display and Warning Sirens by default** (`Include Options in Auto-Flatten (BETA)` is **OFF** by default).
    * **Default Mode (Siren-Only):** By default, the script does not submit orders on Option contracts. If a guardrail is breached while you hold open options, the siren sounds continuously and waits for you to manually flatten your options before executing any OS Lock or App Termination.
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
3. Accept the **Beta Liability Waiver**, select your broker (**Schwab** or **Webull**), and paste your **App Key** and **App Secret** into the first-time setup prompt (or click the **`BROKER:`** dropdown at the top of Pre-Flight anytime and choose **`🔑 API Keys & Renew 7-Day Token...`** / **`🔑 Configure Webull API Keys...`**).
4. **Schwab Browser Login Step (First Time & Every 7 Days):**
   * If using **Schwab**, your web browser will open to the official Charles Schwab login page. Log in with your regular Schwab brokerage credentials and approve account access.
   * After you click approve, your browser will redirect to a blank **"This site can't be reached (`127.0.0.1`)"** page. **This is 100% normal!**
   * Copy the **entire URL** from the top of your browser's address bar (starting with `https://127.0.0.1/?code=...`) — the on-screen **Schwab 7-Day Security Login** popup window will automatically detect it from your clipboard (or click **📋 Paste from Clipboard**), then click **Complete Schwab Login >>**.
   * *(Note: Schwab security tokens last 7 days. You don't need to track this yourself — the app displays your remaining token days in Card 3, **automatically walks you through this renewal early at startup** whenever `< 14 hours` remain so it never expires mid-session, and also lets you renew it manually anytime by clicking **`Token: X.Xd ↻`** in Card 3 or **`BROKER:`** -> **`🔑 API Keys & Renew 7-Day Token...`**.)*
5. Choose which sub-account you want to monitor from the **`ACCOUNT:`** dropdown at the top-left of the Pre-Flight screen.
6. **⏰ Launch Before Your First Trade of the Day:** Always launch the app **before taking your first trade of the day** (or before **9:30 AM ET** if trading Regular Hours) so it can snapshot your clean starting account equity baseline (`$0.00` Daily PnL). Once captured, **that baseline is automatically saved for the rest of the day**—so if you ever close and reopen the app later in the session, it will seamlessly restore your morning baseline and full daily PnL without resetting to zero.

---

## Step 3: Quick Guide to Pre-Flight Settings & the Live HUD
* **Card 1 — Trade & Tilt Stops (`Intraday Penalty Box`):**
  * **Single-Trade Stop (`Open PnL`):** Flattens open equity shares (and RTH option contracts if the **BETA Options Auto-Flatten** toggle in Card 2 is enabled) if a single trade goes against you by your configured dollar limit, without ending your trading day.
  * **Consecutive Loss Cooldown (`Tilt Streak Stop`):** If you close **`X` consecutive losing trades** (each at or beyond your **`Min Loss ($)`** micro-scratch threshold configured in **`⚙ Filter`**, e.g. `-$25`) within **`Y` minutes** (`In (Mins)`), Enforcer cancels working orders, confirms flat, and triggers the **Penalty Box OS Lock Cooldown** so you can reset mentally before revenge-trading. While an active streak is underway (`1/X` or higher), your cooldown settings automatically switch to **`🔒 LOCKED`** so they cannot be weakened mid-streak. Closing a qualifying winning trade (`>= +Win Reset $`, e.g. `+$10`) or letting the rolling window expire automatically resets your streak to `0`.
* **Card 2 — Daily Stop Actions (`Max Loss & Profit Lock`):** Controls what happens when your Net PnL hits your active Daily Stop in Card 4 or Card 5 (Auto-Flatten Equities, optional **`└─ Include Options in Auto-Flatten (BETA — RTH Market Orders)`**, Kill Thinkorswim / Webull Desktop once confirmed 100% flat, and Lock Windows OS for your cooldown timer). When a Daily Stop lockout finishes, Pre-Flight Settings opens automatically with a **`DAILY STOP BREACHED — REVIEW OR ADJUST YOUR LIMITS`** notice so you can raise your Daily Stop or Re-Zero your baseline. If you keep your settings as-is while Auto-Flatten is enabled, the HUD enters **`🚨 DAILY STOP BREACHED — NEW POSITIONS WILL BE AUTO-FLATTENED`** mode (`POST-BREACH FORCE-FLATTEN`) and immediately flattens any new tracked position opened until you raise your limit or Re-Zero (or holds in `DAY STOP: BREACHED (DISARMED)` mode if Auto-Flatten is OFF).
  * **💡 Global `🔔 Alarms Only` Mode:** Toggle **`🔔 Alarms Only: OFF / ON`** in the bottom launch bar next to **`🚀 SAVE & LAUNCH ENFORCER >>`** (which turns caution amber **`🔔 SAVE & LAUNCH (ALARMS ONLY) >>`**) to disable all automated flattening (both Equities and Options), app kills, and OS locks across Cards 1 & 2 while keeping HUD tracking and warning sirens active.
* **Card 3 — Today's Session & Baseline (`⚙ Preferences & Audio...`):**
  * **Daily Baseline Persistence & `↺ Re-Zero Baseline` Pill:** Your starting baseline is saved per account for the entire trading day (marked `(Preserved)` in Card 3 if you close and relaunch the app mid-day). Click the **`↺ Re-Zero Baseline`** pill button in the top-right of Card 3 (changing to **`✓ Re-Zero Armed`**) if you ever intentionally want to reset your daily PnL and W/L counter to `$0.00` mid-session.
  * **Ignore Pre-Existing Positions on Launch (`🛡️ Ignored` / `⚡ Tracked` Filter):** Configured inside **`⚙ Preferences & Audio...`** (and enabled by default) so swing or long-term holdings already in your account when you launch PnL Enforcer never lock enforcement settings or HUD `✕` Close as `🔒 IN TRADE`, have `$0.00` impact on your daytrade `Realized PnL`, `Open PnL`, `Net PnL`, and `Daily Stop` (even if you add to, trim, or close them later in the day), and are never auto-flattened or canceled. Click **`🛡️ Positions (N)`** in Card 3 anytime to review or toggle Ignored vs. Tracked holdings. If you close the app briefly mid-day, open a new intraday trade, and re-open the app, Enforcer automatically prompts **`⚡ NEW POSITION(S) FOUND TODAY — DAYTRADE OR SWING?`** with the new trade defaulting to **`⚡ TRACK AS DAYTRADE`** while your earlier swing holdings stay **`🛡️ IGNORED`**.
  * **Session Behavior, Silent Mode & Audio / Poll Settings (`⚙ Preferences & Audio...`):** Configure `Reset Profit Ratchets at 9:30 AM & 4:00 PM Session Switch (Start at Base Tier 1)`, `Mute All Sounds & Voice Callouts (Silent Mode — Work Calls / Quiet Room)`, `Verbal Lockout Voice Cues`, `Upside Tier Chime & Glow`, **`🔊 Test`** previews (Warning Siren, Connection Lost Tone, Chimes, Voice Cues, and 10s Dry-Run Lockout), `API Poll Interval (s)`, `Check for Updates on Startup`, and `Auto-Share Daily Safe Logs`. You can also click **`✦ Quick Tour`** in the bottom-right footer anytime to view the *Overview*, *Where Controls Live* layout map (with **`✦ Highlight Controls`**), and *60-Second Checklist*, or toggle **`👁 Privacy: OFF / ON`** in the top bar to mask account numbers and dollar balances for screenshots.
* **Cards 4 & 5 — Extended Hours vs. Regular Hours (`9:30 AM – 4:00 PM ET`) Rulebooks:**
  * All session times and order types (**Market** orders during `9:30 AM – 4:00 PM ET`; marketable **Extended-Hours Limit** orders outside RTH) automatically sync to **US Eastern Time (New York)** regardless of your computer's local timezone.
  * **Card 5 Profit Ratchet Tiers:** As your realized profit climbs through Tiers 2, 3, and 4 during Regular Hours, your Daily Stop automatically ratchets upward to prevent green-to-red round-trips.
* **Positioning & Customizing the HUD:**
  * **Move the HUD:** Left-click and drag anywhere on the HUD bar to place it wherever you want on your monitor (coordinates save automatically).
  * **Customize Columns & Small 3-Col HUD (`📊 HUD Columns`):** Toggle and reorder up to 9 metrics (`REALIZED PnL`, `OPEN PnL`, `NET PnL`, `DAILY STOP`, `$ TO STOP`, `SESSION HIGH`, `FROM HIGH`, `TRADES (W/L)`, and `LOSS STREAK` showing e.g. `3 / 5` + live `RST 06:42` countdown), or switch in one click between the **Standard 5-Col HUD** (`800x88`) and the compact **Small 3-Col HUD** (`480x88`, featuring a concise `● ARMED` pill with a hover-over configuration tooltip). Clicking the bottom-left HUD capsule also cycles through `W/L -> STREAK -> FLAT -> BASE`.
  * **In-Trade Anti-Tamper Lock (`🔒 IN TRADE ⚙` & `🔒`):** Whenever you hold an active daytrade position, the HUD **`✕`** Close button locks (`🔒`) so you cannot exit the app mid-trade, while the HUD Settings button switches to **`🔒 IN TRADE ⚙`** — allowing you to open Pre-Flight Settings to adjust **HUD Columns**, **Audio/Voice**, or export **Logs** while locking all enforcement and rulebook settings across **Cards 1, 2, 4, and 5** until the trade is closed.

---

## Step 4: How to Report a Bug or Share Logs Safely (`🐞 Report Bug` & `📜 Logs ▾`)
* **1-Click Direct Safe Log Upload (`📜 Logs ▾ -> 📤 Send Today's Safe Log Now`):** Uploads today's balance-redacted session log directly to the beta diagnostic drive tagged only with an anonymous 6-character Tester ID (`$[REDACTED]` balances, `~` user paths, and masked order IDs). You can also enable **`Auto-Share Daily Safe Logs`** in `📜 Logs ▾` or Card 3's **`⚙ Preferences & Audio...`** modal to automatically share yesterday's redacted log in the background on startup (with a one-click **`Preview Safe Log`** button before enabling).
* **Built-In Bug Report Dialog (`🐞 Report Bug`):** Click **`🐞 Report Bug`** in the top bar of the Pre-Flight window (or inside `📜 Logs ▾`) anytime to submit an issue directly inside the app:
  * Optionally include your **Reddit username, Discord, or email** (saved locally so you don't have to re-type it), describe what happened, and click **`🚀 Submit Bug Report`**.
  * Today's balance-redacted Safe Log (`$[REDACTED]` balances, `~` user paths, and masked order IDs) is **automatically attached** — with a **`🔍 Preview Safe Log`** button and an optional checkbox to include your most recent prior-day Safe Log.
  * Includes an **`Open Tally Web Form ↗`** fallback link (and saves a local redacted copy + clipboard backup automatically if offline).

---

If you end up enjoying this tool, feel welcome to buy me a coffee (or beer): [https://buymeacoffee.com/dbcodez](https://buymeacoffee.com/dbcodez)
