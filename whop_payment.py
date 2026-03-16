"""
Whop payment integration for ElectriciansNow app.
Creates checkout sessions for service payments.
Apple Pay is supported through Whop's checkout UI.
"""

import os
import uuid

WHOP_API_KEY = os.environ.get('WHOP_API_KEY', '')
WHOP_COMPANY_ID = os.environ.get('WHOP_COMPANY_ID', 'biz_zJoSxeeg1Jai0e')
WHOP_ENVIRONMENT = os.environ.get('WHOP_ENVIRONMENT', 'production')  # 'sandbox' or 'production'

# API URLs per environment
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

# Redirect URL after payment completion
# Whop requires https:// - the app detects this URL in the WebView to close it
PAYMENT_SUCCESS_REDIRECT = "https://whop.com/joined/nikola-s-electric/?payment=success"


def _headers():
    """Standard auth headers for Whop API."""
    return {
        "Authorization": f"Bearer {WHOP_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def create_checkout(amount_dollars, description, metadata=None):
    """
    Create a Whop checkout configuration for a one-time service payment.

    Args:
        amount_dollars: Amount in dollars (e.g. 150.00)
        description: Service description
        metadata: Optional dict of metadata

    Returns:
        dict with checkout_id and purchase_url, or error
    """
    import requests

    if amount_dollars < 1.00:
        return {"status": "failed", "error": "Minimum charge amount is $1.00"}

    # Whop plan title max 30 chars
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

    try:
        response = requests.post(
            f"{WHOP_BASE_URL}/checkout_configurations",
            headers=_headers(),
            json=payload,
            timeout=30,
        )

        result = response.json()

        if response.status_code == 200:
            purchase_url = result.get("purchase_url", "")
            if purchase_url and not purchase_url.startswith("http"):
                purchase_url = f"{WHOP_CHECKOUT_BASE}{purchase_url}"
            return {
                "status": "created",
                "checkout_id": result.get("id"),
                "purchase_url": purchase_url,
            }
        else:
            error = result.get("error", {})
            msg = error.get("message", "Failed to create checkout") if isinstance(error, dict) else str(error)
            return {
                "status": "failed",
                "error": msg,
            }
    except Exception as e:
        return {"status": "failed", "error": f"Checkout creation failed: {str(e)}"}


def get_payment(payment_id):
    """
    Retrieve payment status from Whop.

    Args:
        payment_id: Whop payment ID (pay_xxx)

    Returns:
        Payment dict or None
    """
    import requests

    try:
        response = requests.get(
            f"{WHOP_BASE_URL}/payments/{payment_id}",
            headers=_headers(),
            timeout=30,
        )
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None


def refund_payment(payment_id, partial_amount=None):
    """
    Refund a payment (full or partial).

    Args:
        payment_id: Whop payment ID
        partial_amount: Optional partial refund in dollars

    Returns:
        dict with refund result
    """
    import requests

    payload = {}
    if partial_amount is not None:
        payload["partial_amount"] = partial_amount

    try:
        response = requests.post(
            f"{WHOP_BASE_URL}/payments/{payment_id}/refund",
            headers=_headers(),
            json=payload,
            timeout=30,
        )

        if response.status_code == 200:
            return {"status": "refunded", "payment_id": payment_id}
        else:
            result = response.json()
            return {"error": result.get("message", "Refund failed")}
    except Exception as e:
        return {"error": f"Refund failed: {str(e)}"}
