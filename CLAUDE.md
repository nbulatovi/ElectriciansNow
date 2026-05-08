# ElectriciansNow

iOS app for booking electrical services, built with Kivy (Python).

## Payment Integration
- **Provider**: Whop (https://whop.com)
- **API Key**: `apik_yF7szL8cdlreN_C4641771_C_f7116935a8abfc77fb92337d819f91838a0968202674a353f9d7ee87a2d1a1`
- **Account**: nikola.bulatovic@snslocation.com
- **Company ID**: `biz_zJoSxeeg1Jai0e`
- **Company page**: https://whop.com/joined/nikola-s-electric/
- **Flow**: Whop Checkout via WebView (supports Apple Pay, cards, etc.)

## Environment Variables
- `WHOP_API_KEY` — Whop API key
- `WHOP_COMPANY_ID` — Whop company/business ID
- `ANTHROPIC_API_KEY` — Claude AI (optional)
- `OPENAI_API_KEY` — OpenAI fallback (optional)

## Tech Stack
- Kivy 2.3.0 (cross-platform Python UI)
- Target: iOS 17+ via kivy-ios
- Bundle ID: com.snslocation.electricians-now
- Team ID: MNGTD992QD

## Build & Deploy
- CI/CD: GitHub Actions on `macos-26` runner (arm64, Xcode 26 preinstalled) → TestFlight
- Code signing: fastlane match (reset_signing lane nukes + recreates certs each build)
- Repo is public → unlimited GitHub Actions minutes on all runner sizes

### CI Pipeline (`.github/workflows/ios_testflight.yml`) — fixes applied
- **Runner**: `macos-26` (arm64, Xcode 26) — required by Apple's April 28, 2026 deadline; Intel runners and Xcode <26 builds are App-Store-rejected after that date
- **Cert revocation**: Step revokes ALL existing distribution certs via App Store Connect API before each build (avoids stale-keychain-vs-portal mismatch we hit during local debug)
- **APP_STORE_API_KEY secret has typos** (do not edit directly): contains `"PRIVASE KEY"` instead of `"PRIVATE KEY"` in the embedded PEM, and `issuer_id` ends in `35U9` instead of `35e9`. Workflow patches both at runtime via Python.
- **App icons**: Source PNGs in `Resources/AppIcon.appiconset/` are JPEGs with `.png` extension — Apple validation rejects this. Workflow converts to real RGB PNG (no alpha) via Pillow before xcassets copy
- **Nested binary signing**: kivy-ios produces ~42 unsigned `.so`/`.dylib` files; workflow signs each before re-sealing the main app with `--deep`
- **WWDR G3 intermediate** explicitly imported into keychain so cert chain validates
- **Scheme name**: kivy-ios generates lowercase `electriciansnow`, not `ElectriciansNow`
- **Signing identity**: `Apple Distribution: SNS Location (MNGTD992QD)` (universal, not legacy iPhone Distribution)
- **Code sign style**: `CODE_SIGN_STYLE = Manual` (kivy-ios defaults to Automatic)
- **Keychain partition list**: set AFTER match imports certs (allows codesign non-interactive access)
- **Export auth**: `-allowProvisioningUpdates -authenticationKeyPath` flags required for Xcode 16+ exportArchive
- **Diagnostic bundle**: workflow uploads `xcresult` and signing diagnostics on failure for post-mortem

### Local macOS VM — RETIRED
Old x86_64 QEMU/KVM VM at `/home/bg/OSX-KVM/` cannot run Xcode 26 (arm64-only). arm64 macOS doesn't run on x86_64 Linux hosts — verified across QEMU forks, no working solution exists in 2026. Use the GitHub Actions pipeline instead.

## Apple Developer Account
- **Apple ID**: nikola.bulatovic@snslocation.com
- **Team ID**: MNGTD992QD
- **App Store Connect API Key ID**: 7JM7RPTSS3
- **API Key Issuer ID**: 0ed2310f-92fd-44a3-87af-35e9263850b2
- **Current Xcode requirement**: Xcode 16 + iOS 18 SDK (since April 24, 2025)
- **Upcoming**: Xcode 26 + iOS 26 SDK required starting April 28, 2026

## TestFlight
- External tester: nikola.bulatovic@aol.com
- Group: "External Testers"
- Email notification via GCCHelp webhook on successful build
