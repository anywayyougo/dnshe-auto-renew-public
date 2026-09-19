# DNSHE Domain Auto-Renewal Assistant (Feishu Notification Edition)

Automatically renews free [DNSHE](https://www.dnshe.com/) domains via GitHub Actions, pushing results through a **Feishu group bot**. Supports multiple accounts, pre-flight checks, automatic retries, and failure fallback alerts.

> **How to use this template**: Fork this repository → configure your own GitHub Secrets following the steps below → trigger a manual run from the Actions tab. Keys live only in your own repository Secrets and are never exposed.

## Features

- **Fully automatic renewal**: Runs automatically on the 1st and 15th of each month at 09:12 Beijing time; can also be triggered manually from GitHub.
- **Multi-account support**: Up to 10 DNSHE accounts (`DNSHE_API_KEY_1` / `DNSHE_API_SECRET_1` and onward).
- **Smart renewal**: Only renews domains with fewer than 180 days remaining; `never expires` domains are skipped.
- **Pre-flight checks**: Verifies account authentication, domain list retrieval, and expiry date field parsing; if any check fails, it notifies and exits without renewing.
- **Request retry**: Exponential backoff retry (3 attempts) on timeout / connection errors / HTTP 5xx.
- **Last renewal tracking**: Root-level `last_renew.json` records each domain's last renewal time, shown in notifications as "last renewed X days ago".
- **Failure fallback alert**: Even if the script crashes, a failed GitHub Actions job triggers a separate `if: failure()` alert.
- **Privacy & security**: Keys are injected via GitHub Secrets or a local `.env`; `.env` is gitignored.

## Quick Start

### Step 1: Create a Feishu group bot

1. Register a Feishu account (free, personal) and sign in.
2. Create a group (may contain only yourself). Inside the group, click **... → Settings → Group Bots → Add Bot → Custom Bot** in the top-right corner. **The "Custom Bot" option is only available on the desktop client, not on mobile.**
3. Name it and add it. Copy the **Webhook URL** (format: `https://open.feishu.cn/open-apis/bot/v2/hook/xxxx`).
4. It is recommended to enable **signature verification** under security settings (click the bot to open its config page) and copy the signing secret.
   - With signing enabled, notification requests must include `timestamp + sign`; this script already supports it — just set `FEISHU_SIGN_SECRET`.
   - **Do NOT use the IP whitelist**: GitHub Actions runner IPs change dynamically and will block notifications.
   - Using no security settings at all also works (with the risk that a leaked webhook could be used to spam the group).
5. Fill the webhook (and optional signing secret) into the Secrets in the next step.

### Step 2: Configure GitHub Secrets (IMPORTANT!)

In your repository, go to **Settings → Security and quality → Secrets and variables → Actions**, click **New repository secret** to add the following:

| Variable Name | Required | Example | Description |
|---|---|---|---|
| `DNSHE_API_KEY_1` | Yes | `cfsd_8f3a91c2b4d5e607` | API Key of account 1 |
| `DNSHE_API_SECRET_1` | Yes | `a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6` | API Secret of account 1 |
| `DNSHE_API_KEY_2` ~ `DNSHE_API_KEY_10` | No | `cfsd_1a2b3c4d5e6f7890` | Other accounts, add as needed |
| `DNSHE_API_SECRET_2` ~ `DNSHE_API_SECRET_10` | No | `z9y8x7w6v5u4t3s2r1q0` | Other accounts |
| `FEISHU_WEBHOOK_URL` | Yes | `https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxxxxxxxxxxxxxxxxxx` | Feishu bot webhook |
| `FEISHU_SIGN_SECRET` | No | `Gi7pQw9rT2yL5nV8bCk4m` | Feishu signing secret (only if signature verification is enabled) |

> The values in the "Example" column are **fabricated placeholders — do not copy them**. Use your own real values.
> Get your DNSHE API Key: sign in to [DNSHE](https://my.dnshe.com/) → Free Domains → API Management → Create API Key.

### Step 3: Manually trigger once

Go to **Actions → DNSHE Domain Auto Renew → Run workflow** to verify the configuration. On a manual trigger, the script sends a confirmation message to Feishu: `ℹ️ Manual run: DNSHE pre-flight passed (N accounts, M domains), Feishu notification channel is working.` Receiving it means the whole chain (GitHub Secrets, webhook, signing, script) is working. If the first run log mentions missing keys, that is expected — reconfigure and re-run.
For per-domain details, see the `Run renew script` step output in the corresponding action run.

## Local Run & Testing (optional)

```bash
# 1. Install dependencies (a dedicated conda environment is recommended)
pip install -r requirements.txt

# 2. Copy the template and fill in real values
copy .env.example .env

# 3. Run locally (performs a real pre-flight against the read-only DNSHE API)
python renew_domains.py
```

Configuration priority: **environment variables > `.env` file**. GitHub Actions injects values via Secrets, so `.env` is not needed there. `.env` and `.gitignore` form the privacy layer: keys live only in the local `.env` and never enter the repository.

## Notification Behavior

| Scenario | Notify? |
|---|---|
| Renewal succeeded | ✅ One message per domain (days remaining, new expiry, points spent, last renewal) |
| Renewal failed | ❌ Notified immediately, including error details |
| Pre-flight failed / no account configured / script exception | ❌ Notify and exit |
| Manual run | ℹ️ Always sends a "channel OK" confirmation message (whether or not anything renewed) |
| All domains have enough days remaining | No notification, only written to the Actions log |
| Job failure caused by a script crash | ❌ Separate `if: failure()` fallback alert |

## Schedule & Logs

- **cron**: `12 1 1,15 * *` (UTC) = 09:12 Beijing time on the 1st and 15th of each month, avoiding round/on-the-hour times to lower Feishu rate-limit risk.
- **Manual trigger**: `workflow_dispatch`, run anytime; manual runs always send a confirmation message, while scheduled runs notify only when needed.
- **Log retention**: GitHub retains logs for 90 days by default. To change to 14 days, modify **Settings → Actions → General → Workflow job retention** (there is no such option in the workflow YAML).
- **Concurrency**: A `concurrency` guard prevents scheduled and manual runs from overlapping.

## Notes & Caveats

- Renewal request retries only happen on timeout / connection errors / 5xx; if the first request actually succeeded but the response was lost, a retry may charge points twice (low probability).
- `last_renew.json` is automatically committed back by the workflow; no manual maintenance needed. Stale entries no longer in the domain list are pruned automatically.
- Times are stored and computed in UTC to avoid timezone confusion.
- Never commit keys to the repository; it is recommended to rotate keys regularly via `regenerate` in the DNSHE console.

## Acknowledgments

- [DNSHE](https://www.dnshe.com/)
- [DeepSeek](https://platform.deepseek.com/)
- [OpenCode](https://opencode.ai/)
- [Elsht666](https://github.com/Elsht666/DNSHE-Auto-COMPAT)
- [Feishu](https://www.feishu.cn/)
