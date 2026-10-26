# PnL Enforcer (Closed Beta) — Schwab & Webull Edition

An external, real-time PnL circuit breaker and discipline enforcer for **Charles Schwab (Thinkorswim)** and **Webull** traders on Windows 10/11.

---

## ⚠️ IMPORTANT BETA DISCLAIMER
This software is **experimental beta software** provided strictly "AS IS." By installing and running this software, you agree that you are 100% solely responsible for your trading account, order executions, and risk management.
* **Test First:** Always test in **Alarm-Only Mode** (all enforcement switches unchecked) or with **1 share** before enabling live Auto-Flatten.
* **Equities vs. Options:**
  * **Equities (Stocks):** Tracked in real-time for HUD display, Alarms, **and** automated Market / Extended-Hours (`GTC_EXT`) Limit liquidation.
  * **Options Contracts:** Tracked in real-time (`100x` multiplier via Mark/Last price) for **HUD Display and Warning Sirens ONLY**. Because option bid-ask spreads can widen dramatically, **the script will NEVER submit automated orders on Option contracts.** If a guardrail is breached while you hold open options, the siren will sound continuously and wait for you to manually flatten your options before executing any OS Lock or App Termination.

---

## Step 1: Get Your Broker API Keys (Schwab OR Webull)
Your API keys stay 100% local on your computer inside `C:\Users\<YourUsername>\enforcer_config.json`. Never share your App Key or App Secret with anyone.

### Option A: If Your Broker is Charles Schwab (Thinkorswim)
1. Go to [developer.schwab.com](https://developer.schwab.com/) and register a free Individual Developer account.
2. Go to **Dashboard -> Apps -> Create App**:
   * **API Product:** Select `Accounts and Trading Production`
   * **App Name:** `PnL Enforcer` (or any name)
   * **Callback URL:** `https://127.0.0.1` *(Must match this exact URL)*
3. Wait for your app status to change from *Approved - Pending* to **`Ready for Use`** (typically takes 2–5 business days).
4. Once `Ready for Use`, copy your **App Key** and **Secret**.

### Option B: If Your Broker is Webull
1. Go to [developer.webull.com](https://developer.webull.com/) (or log into your Webull web portal -> **Account Management -> OpenAPI Management**).
2. Apply for a **Retail Trading API Key** (typically approved in 1–2 business days).
3. Once approved, generate your **App Key** and **App Secret** in the OpenAPI portal.
4. *(Note for Live Quotes)*: Webull's OpenAPI uses account position snapshots by default; if you subscribe to Webull OpenAPI real-time quotes (`webullapp.com/quote`), it will also poll live bid/ask quotes during extended-hours liquidations.

---

## Step 2: Launch the App (Automatic One-Click Setup)
1. Double-click **`Launch_Enforcer.bat`**.
2. **Automatic Python & Library Installation:**
   * If Python is not already installed on your PC, `Launch_Enforcer.bat` will automatically install **Python 3.12** via Windows `winget` and configure your system `PATH` (click **Yes** if a Windows permission prompt appears).
   * It will then automatically install all required broker libraries (`schwab-py`, `webull-openapi-python-sdk`, and dependencies) and launch the Pre-Flight Setup Wizard.
3. Accept the **Beta Liability Waiver**, select your broker (**Schwab** or **Webull**), and paste your **App Key** and **App Secret** into the first-time setup prompt.
4. **Schwab Browser Login Step (First Time & Every 7 Days):**
   * If using **Schwab**, your web browser will open to the official Charles Schwab login page. Log in and approve account access.
   * After you click approve, your browser will redirect to a blank **"This site can't be reached (`127.0.0.1`)"** page. **This is 100% normal!**
   * Copy the **entire URL** from the top of your browser's address bar (starting with `https://127.0.0.1/?code=...`), paste it into the black terminal window, and press **Enter**.
   * *(Note: Schwab security tokens last 7 days, so you will only need to repeat this quick copy-paste login once a week when your token expires.)*
5. Choose which account you want to monitor from the **Account Dropdown** at the top of the Pre-Flight screen.
