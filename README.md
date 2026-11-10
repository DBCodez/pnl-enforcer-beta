# PnL Enforcer (Closed Beta) — Schwab & Webull Edition

An external, real-time PnL circuit breaker and discipline enforcer for **Charles Schwab (Thinkorswim)** and **Webull** traders on Windows 10/11.

📸 **[View App Screenshots (HUD & Pre-Flight Rulebook UI)](https://imgur.com/a/REID2kV)**

---

## ⚠️ IMPORTANT BETA DISCLAIMER & ASSUMPTION OF RISK
This software is **experimental beta software** provided strictly **"AS IS"** without warranty of any kind (see [`LICENSE.txt`](LICENSE.txt)). By installing, configuring, or running this software, you agree that you assume **100% sole responsibility** for your trading account, order executions, and risk management, and agree to indemnify and hold harmless the authors from any trading losses or claims.
* **Not Financial Advice & No Guarantee of Loss Prevention:** This tool is a self-directed mechanical utility, not a registered investment advisor or broker-dealer. **It does NOT and CANNOT guarantee that losses will be limited to your configured thresholds.** API outages, network latency, rate limits, rejected orders, illiquid spreads, market gaps, or trading halts can cause actual losses to significantly exceed your configured limits.
* **No Broker Affiliation:** This project is an independent tool and is **not** affiliated with, endorsed by, or sponsored by Charles Schwab, Thinkorswim, or Webull.
* **Test Safely First (`Alarms Only Mode`):** On your first day, check the **`Alarms Only Mode`** master toggle inside **Card 2 (`2. DAILY STOP ACTIONS`)** to verify live PnL tracking and warning sirens passively before testing live Auto-Flatten with **1 share**.
* **Equities vs. Options:**
  * **Equities (Stocks):** Tracked in real-time for HUD display, Alarms, **and** automated Market (`9:30 AM – 4:00 PM ET`) / Extended-Hours (`GTC_EXT`) Limit liquidation.
  * **Options Contracts:** Tracked in real-time (`100x` multiplier via Mark/Last price) for **HUD Display and Warning Sirens ONLY**. Because option bid-ask spreads can widen dramatically, **the script will NEVER submit automated orders on Option contracts.** If a guardrail is breached while you hold open options, the siren will sound continuously and wait for you to manually flatten your options before executing any OS Lock or App Termination.

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

### Option B: If Your Broker is Webull
1. Go to [https://developer.webull.com/apis/docs/authentication/IndividualApplicationAPI](https://developer.webull.com/apis/docs/authentication/IndividualApplicationAPI) (or log into your Webull web portal -> **Account Management -> OpenAPI Management**).
2. Apply for a **Retail Trading API Key** (typically approved in 1–2 business days).
3. Once approved, generate and copy your **App Key** and **App Secret** in the OpenAPI portal.
4. *(Note for Live Quotes)*: Webull's OpenAPI uses account position snapshots by default; if you subscribe to Webull OpenAPI real-time quotes (`webullapp.com/quote`), it will also poll live bid/ask quotes during extended-hours liquidations.

---

## Step 2: Launch the App (Automatic One-Click Setup)
1. Double-click **`Launch_Enforcer.bat`**.
   * *(Windows SmartScreen Note: Because `.bat` scripts downloaded from the internet are unsigned, Windows 10/11 may show a blue **"Windows protected your PC"** prompt the first time you run it. Click **`More info`** -> **`Run anyway`**.)*
2. **Automatic Python & Library Installation:**
   * If Python is not already installed on your PC, `Launch_Enforcer.bat` will automatically install **Python 3.12** via Windows `winget` and configure your system `PATH` (click **Yes** if a Windows permission prompt appears).
   * It will then automatically install all required broker libraries (`schwab-py`, `webull-openapi-python-sdk`, `pillow`, and dependencies) and launch the Pre-Flight Setup Wizard.
3. Accept the **Beta Liability Waiver**, select your broker (**Schwab** or **Webull**), and paste your **App Key** and **App Secret** into the first-time setup prompt (or click **`🔑 API Keys`** at the top of the Pre-Flight screen anytime).
4. **Schwab Browser Login Step (First Time & Every 7 Days):**
   * If using **Schwab**, your web browser will open to the official Charles Schwab login page. Log in with your regular Schwab brokerage credentials and approve account access.
   * After you click approve, your browser will redirect to a blank **"This site can't be reached (`127.0.0.1`)"** page. **This is 100% normal!**
   * Copy the **entire URL** from the top of your browser's address bar (starting with `https://127.0.0.1/?code=...`) — the on-screen **Schwab 7-Day Security Login** popup window will automatically detect it from your clipboard (or click **📋 Paste from Clipboard**), then click **Complete Schwab Login >>**.
   * *(Note: Schwab security tokens last 7 days. You don't need to track this yourself — the app displays your remaining token days in Pre-Flight Settings, **automatically walks you through this renewal early at startup** whenever `< 14 hours` remain so it never expires mid-session, and also lets you renew it manually anytime via **`🔑 API Keys -> 🔄 Renew 7-Day Token Now`**.)*
5. Choose which sub-account you want to monitor from the **`ACCOUNT:`** dropdown at the top-left of the Pre-Flight screen.
6. **⏰ Launch Before Your First Trade of the Day:** Always launch the app **before taking your first trade of the day** (or before **9:30 AM ET** if trading Regular Hours) so it can snapshot your clean starting account equity baseline (`$0.00` Daily PnL). Once captured, **that baseline is automatically saved for the rest of the day**—so if you ever close and reopen the app later in the session, it will seamlessly restore your morning baseline and full daily PnL without resetting to zero.

---

## Step 3: Quick Guide to Pre-Flight Settings & the Live HUD
* **Card 1 — Single-Trade Stop (`Open PnL`):** Flattens open equity shares if a single trade goes against you by your configured dollar limit (with an optional short **Penalty Box OS Lock** cooldown) without ending your trading day.
* **Card 2 — Daily Stop Actions (`Max Loss & Profit Lock`):** Controls what happens when your Net PnL hits your active Daily Stop in Card 4 or Card 5 (Auto-Flatten Equities, Kill Thinkorswim / Webull Desktop once confirmed flat, and Lock Windows OS for your cooldown timer).
  * **💡 `Alarms Only Mode`:** Check **`Alarms Only Mode`** in Card 2 to disable all automated flattening, app kills, and OS locks while keeping all HUD tracking and warning sirens active.
* **Card 3 — Session Baselines & Audio Preview:**
  * **Daily Baseline Persistence:** Your starting baseline is saved per account for the entire trading day (marked `(Preserved)` in Card 3 if you close and relaunch the app mid-day). You can also check **Re-Zero Today's Starting Baseline to Current Equity** if you ever intentionally want to reset your daily PnL to `$0.00` mid-session.
  * **Start Fresh on Rulebook Switch:** Automatically snapshots a fresh starting baseline at **9:30 AM ET** (Regular Hours) and **4:00 PM ET** (After-Hours) if you are flat. Uncheck this if you want Pre-Market PnL to carry into your Regular Hours total.
  * **Audio Tester (`🔊 Test`):** Preview your Warning Siren, Chimes, and Lockout Voice cues at your current speaker volume.
* **Cards 4 & 5 — Extended Hours vs. Regular Hours (`9:30 AM – 4:00 PM ET`) Rulebooks:**
  * All session times and order types (**Market** orders during `9:30 AM – 4:00 PM ET`; marketable **Extended-Hours Limit** orders outside RTH) automatically sync to **US Eastern Time (New York)** regardless of your computer's local timezone.
  * **Card 5 Profit Ratchet Tiers:** As your realized profit climbs through Tiers 2, 3, and 4 during Regular Hours, your Daily Stop automatically ratchets upward to prevent green-to-red round-trips.
* **Positioning & Customizing the HUD:**
  * **Move the HUD:** Left-click and drag anywhere on the HUD bar to place it wherever you want on your monitor (coordinates save automatically).
  * **Customize Columns & Small 3-Col HUD (`📊 HUD Columns`):** Toggle and reorder up to 8 metrics (`REALIZED PnL`, `OPEN PnL`, `NET PnL`, `DAILY STOP`, `$ TO STOP`, `SESSION HIGH`, `FROM HIGH`, and `WIN / LOSS`), or switch in one click between the **Standard 5-Col HUD** (`800x88`) and the compact **Small 3-Col HUD** (`480x88`, featuring a concise `● ARMED` pill with a hover-over configuration tooltip).
  * **Anti-Tamper Lock (`🔒 IN TRADE`):** Whenever you hold an open position, the HUD **`⚙ SETTINGS`** and **`✕`** buttons automatically lock so you cannot disable your stops mid-trade.

---

## Step 4: How to Report a Bug or Share Logs Safely (`🐞 Report Bug`)
* Click **`🐞 Report Bug`** in the top bar of the Pre-Flight window anytime.
* The app automatically generates a privacy-scrubbed copy of your log (`enforcer_log_sanitized.txt`) with **all total account balances (`$[REDACTED]`), Windows usernames, and order IDs redacted** while keeping relative PnL and guardrail events intact.
* It automatically copies the redacted log to your clipboard, highlights the file in Windows Explorer, and opens the **[Private Beta Bug Report Form](https://tally.so/r/Z98y4V)**.

---

If you end up enjoying this tool, feel welcome to buy me a coffee (or beer): [https://buymeacoffee.com/dbcodez](https://buymeacoffee.com/dbcodez)
