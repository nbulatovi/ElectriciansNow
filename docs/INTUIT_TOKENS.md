# Intuit OAuth Token Setup

This guide explains how to generate and maintain Intuit OAuth tokens for the ElectriciansNow app.

## Secret Names

Add these secrets to GitHub Actions:

| Secret Name | Description |
|-------------|-------------|
| `INTUIT_ACCESS_TOKEN` | OAuth access token (expires in ~1 hour, but gets refreshed) |
| `INTUIT_REFRESH_TOKEN` | OAuth refresh token (expires in 100 days) |

## How to Generate Tokens

### Step 1: Go to Intuit Developer Playground
https://developer.intuit.com/app/developer/playground

### Step 2: Configure OAuth
1. Sign in with your Intuit developer account
2. Select your app from the dropdown
3. Switch to **Production** mode (not Sandbox)
4. Under "Scopes", select **Payments** (`com.intuit.quickbooks.payment`)

### Step 3: Get Tokens
1. Click **"Get OAuth 2.0 tokens"**
2. Complete the authorization flow (sign in, grant access)
3. Copy the **Access Token** and **Refresh Token** from the response

### Step 4: Add to GitHub Secrets

**Option A: Using GitHub CLI**
```bash
gh secret set INTUIT_ACCESS_TOKEN
# Paste access token, press Enter, then Ctrl+D

gh secret set INTUIT_REFRESH_TOKEN
# Paste refresh token, press Enter, then Ctrl+D
```

**Option B: GitHub Web UI**
1. Go to: https://github.com/nbulatovi/ElectriciansNow/settings/secrets/actions
2. Click "New repository secret"
3. Add `INTUIT_ACCESS_TOKEN` with your access token
4. Add `INTUIT_REFRESH_TOKEN` with your refresh token

## How to Restart CI

After adding/updating tokens, trigger a new build:

**Option A: Using GitHub CLI**
```bash
# Run the test workflow first
gh workflow run test_tokens.yml

# Or trigger a full build
gh workflow run ios_testflight.yml
```

**Option B: Push a commit**
Any push to `main` triggers the build automatically.

**Option C: GitHub Web UI**
1. Go to: https://github.com/nbulatovi/ElectriciansNow/actions
2. Select "Build and Publish to TestFlight"
3. Click "Run workflow" → "Run workflow"

## Token Refresh Schedule

- **Access tokens** expire in ~1 hour but are automatically refreshed by the app
- **Refresh tokens** expire in **100 days**
- **Recommended**: Update tokens manually every **1-2 months** to be safe

### Automatic Refresh (Optional)
There's a scheduled workflow that can auto-refresh tokens, but it requires a GitHub PAT with secrets access. For now, manual refresh is recommended.

## Troubleshooting

### "INTUIT_ACCESS_TOKEN not set"
The secret is empty or not configured. Re-add it following the steps above.

### "Token refresh failed"
The refresh token has expired (100 days). Generate new tokens from the playground.

### "No sandbox companies found"
You're in Sandbox mode. Switch to **Production** in the OAuth playground.

## Quick Reference

```bash
# Check if secrets are set (won't show values)
gh secret list

# Test token workflow
gh workflow run test_tokens.yml

# Watch workflow progress
gh run watch

# Full build
gh workflow run ios_testflight.yml
```
