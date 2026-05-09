"""
Whop payment integration for ElectriciansNow app.
Creates checkout sessions for service payments.
Apple Pay is supported through Whop's checkout UI.

Every API call is logged to the diagnostic log so payment failures can
be triaged from inside the app without server access.
"""

import os
import uuid

from app_logger import log, log_exception

WHOP_API_KEY = os.environ.get('WHOP_API_KEY', '')
WHOP_COMPANY_ID = os.environ.get('WHOP_COMPANY_ID', 'biz_zJoSxeeg1Jai0e')
WHOP_ENVIRONMENT = os.environ.get('WHOP_ENVIRONMENT', 'production')

_API_URLS = {
    "sandbox": "https://sandbox-api.whop.com/api/v1",
    "production": "https://api.whop.com/api/v1",
}
_CHECKOUT_URLS = {
    "sandbox": "https://sandbox.whop.com",
    "production": "https://whop.com",
}
WHOP_BASE_URL = _API_URLS.get(WHOP_ENVIRONMENT, _API_URLS["production"])
WHOP_CHECKOUT_BASE = _CHECKOUT_URLS.get(WHOP_ENVIRONMENT, _CHECKOUT_URLS["production"])

PAYMENT_SUCCESS_REDIRECT = "https://whop.com/joined/nikola-s-electric/?payment=success"


def _headers():
    return {
        "Authorization": f"Bearer {WHOP_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _redact(s):
    if not s:
        return ""
    return s[:12] + "...REDACTED"


def create_checkout(amount_dollars, description, metadata=None):
    """Create a Whop checkout configuration for a one-time service payment."""
    import requests

    log("whop", "create_checkout called", amount=amount_dollars, description=description,
        env=WHOP_ENVIRONMENT, base_url=WHOP_BASE_URL,
        api_key_present=bool(WHOP_API_KEY), api_key_prefix=_redact(WHOP_API_KEY),
        company_id=WHOP_COMPANY_ID)

    if amount_dollars < 1.00:
        log("whop", "rejected: amount below minimum", amount=amount_dollars)
        return {"status": "failed", "error": "Minimum charge amount is $1.00"}

    if not WHOP_API_KEY:
        log("whop", "rejected: WHOP_API_KEY missing in environment")
        return {"status": "failed",
                "error": "Payment configuration missing. WHOP_API_KEY not set."}

    plan_title = description[:30] if len(description) > 30 else description

    payload = {
        "mode": "payment",
        "redirect_url": PAYMENT_SUCCESS_REDIRECT,
        "plan": {
            "company_id": WHOP_COMPANY_ID,
            "currency": "usd",
            "plan_type": "one_time",
            "initial_price": amount_dollars,
            "title": plan_title,
            "product": {
                "title": "Electrician Service",
                "external_identifier": str(uuid.uuid4()),
            }
        },
        "metadata": metadata or {},
    }

    url = f"{WHOP_BASE_URL}/checkout_configurations"
    log("whop", "POST checkout_configurations", url=url, payload=payload)

    try:
        response = requests.post(url, headers=_headers(), json=payload, timeout=30)
    except Exception as e:
        log_exception("whop", "request raised", e)
        return {"status": "failed", "error": f"Network error: {e}"}

    body_text = response.text[:2000]
    log("whop", "response received", status_code=response.status_code,
        body=body_text, headers=dict(response.headers))

    try:
        result = response.json()
    except Exception as e:
        log_exception("whop", "response not JSON", e)
        return {"status": "failed",
                "error": f"Whop returned non-JSON ({response.status_code}): {body_text[:200]}"}

    if response.status_code == 200:
        purchase_url = result.get("purchase_url", "")
        if purchase_url and not purchase_url.startswith("http"):
            purchase_url = f"{WHOP_CHECKOUT_BASE}{purchase_url}"
        log("whop", "checkout created", checkout_id=result.get("id"),
            purchase_url=purchase_url)
        return {
            "status": "created",
            "checkout_id": result.get("id"),
            "purchase_url": purchase_url,
        }

    error = result.get("error", {})
    if isinstance(error, dict):
        msg = error.get("message") or error.get("detail") or str(error)
    else:
        msg = str(error)
    log("whop", "checkout failed", error=msg, full_response=result)
    return {"status": "failed",
            "error": f"Whop error ({response.status_code}): {msg}"}


def get_payment(payment_id):
    import requests
    log("whop", "get_payment", payment_id=payment_id)
    try:
        response = requests.get(
            f"{WHOP_BASE_URL}/payments/{payment_id}",
            headers=_headers(),
            timeout=30,
        )
        log("whop", "get_payment response", status_code=response.status_code,
            body=response.text[:1000])
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        log_exception("whop", "get_payment raised", e)
    return None


def refund_payment(payment_id, partial_amount=None):
    import requests

    payload = {}
    if partial_amount is not None:
        payload["partial_amount"] = partial_amount

    log("whop", "refund_payment", payment_id=payment_id, partial_amount=partial_amount)

    try:
        response = requests.post(
            f"{WHOP_BASE_URL}/payments/{payment_id}/refund",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        log("whop", "refund response", status_code=response.status_code,
            body=response.text[:1000])
        if response.status_code == 200:
            return {"status": "refunded", "payment_id": payment_id}
        result = response.json()
        return {"error": result.get("message", "Refund failed")}
    except Exception as e:
        log_exception("whop", "refund raised", e)
        return {"error": f"Refund failed: {e}"}
