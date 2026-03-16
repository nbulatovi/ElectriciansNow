# ElectriciansNow

iOS app for booking electrical services, built with Kivy (Python).

## Payment Integration
- **Provider**: Whop (https://whop.com)
- **API Key**: `apik_yF7szL8cdlreN_C4641771_C_f7116935a8abfc77fb92337d819f91838a0968202674a353f9d7ee87a2d1a1`
- **Account**: nikola.bulatovic@snslocation.com
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
- CI/CD: GitHub Actions → TestFlight
- Code signing: fastlane match
