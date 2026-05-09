# Telemetry Worker — 5-min setup

Receives HMAC-signed events from the iOS app and stores them in Cloudflare
KV. Read endpoint requires a bearer token. Free tier: 100k requests/day.

## One-time setup (browser only)

1. Sign up at [dash.cloudflare.com](https://dash.cloudflare.com) (free).
2. **Workers & Pages** → **Create application** → **Create Worker**.
3. Name it `electricians-telemetry`. Click **Deploy**.
4. After it deploys, click **Edit code**. Replace the boilerplate with the
   contents of `index.js` from this directory. Click **Save and deploy**.
5. **Settings** → **Variables and Secrets** → add two encrypted variables:
   - `HMAC_KEY` — random 32 chars (any letters/digits, no spaces)
   - `READ_TOKEN` — random 32 chars (any letters/digits, no spaces)
6. **Settings** → **Bindings** → **Add binding** → **KV Namespace**:
   - Variable name: `TELEMETRY_KV`
   - Click **Create new namespace** → name it `electricians-kv`.
7. Copy the worker URL (looks like `https://electricians-telemetry.<acct>.workers.dev`).

## Add to GitHub secrets

In `nbulatovi/ElectriciansNow` → Settings → Secrets and variables → Actions,
add three repository secrets:

- `TELEMETRY_URL` — the worker URL from step 7
- `TELEMETRY_HMAC_KEY` — same 32 chars as `HMAC_KEY` in step 5
- `TELEMETRY_READ_TOKEN` — same 32 chars as `READ_TOKEN` in step 5
  (only used by Claude in future debug sessions; doesn't ship in the IPA)

## Verifying

Health check:
```bash
curl https://electricians-telemetry.<acct>.workers.dev/health
# -> ok
```

Read events:
```bash
curl -H "Authorization: Bearer $TELEMETRY_READ_TOKEN" \
  "https://electricians-telemetry.<acct>.workers.dev/events?since=2026-05-09T00:00:00Z" | jq
```
