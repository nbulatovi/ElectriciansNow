---
name: Whop payment integration
description: ElectriciansNow uses Whop API for payments - company ID biz_zJoSxeeg1Jai0e, replaced Intuit GoPayment on 2026-03-16
type: project
---

Payment backend switched from Intuit GoPayment/QuickBooks to Whop on 2026-03-16.

**Why:** User requested removal of Forwardly/Intuit integration in favor of Whop for Apple Pay + card processing.

**How to apply:**
- Whop company ID: `biz_zJoSxeeg1Jai0e`
- Account: nikola.bulatovic@snslocation.com (username: beadyscale)
- API base: `https://api.whop.com/api/v1` (production), `https://sandbox-api.whop.com/api/v1` (sandbox)
- Checkout creates a plan + product per transaction, returns a `purchase_url` on whop.com
- Whop constraints: min $1 charge, plan title max 30 chars, redirect URL must be https://
- Test cards: 4242 4242 4242 4242 (success), 4000 0000 0000 0002 (decline)
- Payment methods available: Card, Cash App, Crypto, Bank transfer (+ Apple Pay on iOS Safari)
