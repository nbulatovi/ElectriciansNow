"""
Apple Pay + Intuit GoPayment integration for ElectriciansNow app.
Apple Pay handles the payment UI, Intuit processes the transaction.
"""

import platform
import os

# Configuration from environment variables
MERCHANT_ID = os.environ.get('APPLE_PAY_MERCHANT_ID', 'merchant.com.snslocation.electricians-now')
INTUIT_CLIENT_ID = os.environ.get('INTUIT_CLIENT_ID', '')
INTUIT_CLIENT_SECRET = os.environ.get('INTUIT_CLIENT_SECRET', '')
INTUIT_ACCESS_TOKEN = os.environ.get('INTUIT_ACCESS_TOKEN', '')
INTUIT_ENVIRONMENT = os.environ.get('INTUIT_ENVIRONMENT', 'sandbox')  # 'sandbox' or 'production'

# Intuit API endpoints
INTUIT_SANDBOX_URL = "https://sandbox.api.intuit.com/quickbooks/v4/payments"
INTUIT_PRODUCTION_URL = "https://api.intuit.com/quickbooks/v4/payments"

IS_IOS = platform.system() == "Darwin"

if IS_IOS:
    try:
        import objc
        from objc import ObjCClass

        PKPaymentRequest = ObjCClass('PKPaymentRequest')
        PKPaymentAuthorizationViewController = ObjCClass('PKPaymentAuthorizationViewController')
        PKPaymentSummaryItem = ObjCClass('PKPaymentSummaryItem')
        NSDecimalNumber = ObjCClass('NSDecimalNumber')
        UIApplication = ObjCClass('UIApplication')
        OBJC_AVAILABLE = True
    except ImportError:
        OBJC_AVAILABLE = False
else:
    OBJC_AVAILABLE = False


def get_intuit_base_url():
    """Get the appropriate Intuit API URL based on environment."""
    if INTUIT_ENVIRONMENT == 'production':
        return INTUIT_PRODUCTION_URL
    return INTUIT_SANDBOX_URL


def process_payment_with_intuit(amount_cents, apple_pay_token, description):
    """
    Process payment through Intuit GoPayment API.

    Args:
        amount_cents: Amount in cents
        apple_pay_token: Token from Apple Pay authorization
        description: Payment description

    Returns:
        dict with payment result
    """
    if not INTUIT_ACCESS_TOKEN:
        return {"error": "Intuit GoPayment not configured", "mock": True}

    try:
        import requests
        import uuid
        import json

        base_url = get_intuit_base_url()

        # Convert Apple Pay token to base64 string if needed
        token_data = apple_pay_token
        if hasattr(apple_pay_token, 'bytes'):
            import base64
            token_data = base64.b64encode(apple_pay_token.bytes()).decode('utf-8')

        payload = {
            "amount": str(amount_cents / 100),
            "currency": "USD",
            "context": {
                "mobile": "false",
                "isEcommerce": "true"
            },
            "token": token_data,
            "description": description,
            "capture": False  # Preauthorization - capture later when service is complete
        }

        headers = {
            "Authorization": f"Bearer {INTUIT_ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Request-Id": str(uuid.uuid4())
        }

        response = requests.post(
            f"{base_url}/charges",
            headers=headers,
            json=payload,
            timeout=30
        )

        result = response.json()

        if response.status_code in [200, 201]:
            return {
                "status": "authorized",
                "charge_id": result.get("id"),
                "amount": amount_cents,
                "description": description
            }
        else:
            return {
                "error": result.get("errors", [{"message": "Payment failed"}])[0].get("message"),
                "status": "failed"
            }

    except Exception as e:
        return {"error": f"Payment processing failed: {str(e)}", "status": "failed"}


def capture_payment(charge_id, amount_cents=None):
    """
    Capture a previously authorized payment.
    Call this when the electrician completes the service.

    Args:
        charge_id: The charge ID from preauthorization
        amount_cents: Optional amount to capture (can be less than authorized)

    Returns:
        dict with capture result
    """
    if not INTUIT_ACCESS_TOKEN:
        return {"error": "Intuit GoPayment not configured"}

    try:
        import requests
        import uuid

        base_url = get_intuit_base_url()

        payload = {}
        if amount_cents:
            payload["amount"] = str(amount_cents / 100)

        headers = {
            "Authorization": f"Bearer {INTUIT_ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Request-Id": str(uuid.uuid4())
        }

        response = requests.post(
            f"{base_url}/charges/{charge_id}/capture",
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code in [200, 201]:
            return {"status": "captured", "charge_id": charge_id}
        else:
            result = response.json()
            return {"error": result.get("errors", [{"message": "Capture failed"}])[0].get("message")}

    except Exception as e:
        return {"error": f"Capture failed: {str(e)}"}


def refund_payment(charge_id, amount_cents=None):
    """
    Refund a captured payment.

    Args:
        charge_id: The charge ID to refund
        amount_cents: Optional partial refund amount

    Returns:
        dict with refund result
    """
    if not INTUIT_ACCESS_TOKEN:
        return {"error": "Intuit GoPayment not configured"}

    try:
        import requests
        import uuid

        base_url = get_intuit_base_url()

        payload = {}
        if amount_cents:
            payload["amount"] = str(amount_cents / 100)

        headers = {
            "Authorization": f"Bearer {INTUIT_ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Request-Id": str(uuid.uuid4())
        }

        response = requests.post(
            f"{base_url}/charges/{charge_id}/refunds",
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code in [200, 201]:
            return {"status": "refunded", "charge_id": charge_id}
        else:
            result = response.json()
            return {"error": result.get("errors", [{"message": "Refund failed"}])[0].get("message")}

    except Exception as e:
        return {"error": f"Refund failed: {str(e)}"}


def setup_apple_pay_request(amount_cents, description):
    """Configure Apple Pay payment request."""
    if not OBJC_AVAILABLE:
        return None

    try:
        req = PKPaymentRequest.alloc().init()
        req.merchantIdentifier = MERCHANT_ID
        req.countryCode = "US"
        req.currencyCode = "USD"
        req.supportedNetworks = ["visa", "masterCard", "amex", "discover"]
        req.merchantCapabilities = 1 << 0  # PKMerchantCapability3DS

        amount_dollars = amount_cents / 100.0
        req.paymentSummaryItems = [
            PKPaymentSummaryItem.summaryItemWithLabelAmount(
                description,
                NSDecimalNumber.decimalNumberWithString_(str(amount_dollars))
            )
        ]
        return req
    except Exception as e:
        print(f"Error configuring Apple Pay request: {e}")
        return None


def present_apple_pay_controller(amount_cents, description, on_complete=None):
    """Present Apple Pay sheet and process payment through Intuit."""
    if not OBJC_AVAILABLE:
        return {"error": "Apple Pay not available on this platform"}

    payment_result = {"status": "pending"}

    def did_authorize_payment(_, payment, completion):
        try:
            # Get the Apple Pay token and process through Intuit
            token = payment.token.paymentData
            result = process_payment_with_intuit(amount_cents, token, description)

            if result.get("status") == "authorized" or result.get("mock"):
                payment_result.update(result)
                completion(0)  # Success
            else:
                payment_result["status"] = "failed"
                payment_result["error"] = result.get("error", "Payment failed")
                completion(1)  # Failure

            if on_complete:
                on_complete(payment_result)

        except Exception as e:
            completion(1)
            payment_result["status"] = "failed"
            payment_result["error"] = str(e)
            if on_complete:
                on_complete(payment_result)

    def did_finish(controller):
        controller.dismissViewControllerAnimated_completion_(True, None)

    try:
        import objc

        request = setup_apple_pay_request(amount_cents, description)
        if not request:
            return {"error": "Failed to configure Apple Pay request"}

        delegate_methods = {
            "paymentAuthorizationViewController_didAuthorizePayment_completion_": did_authorize_payment,
            "paymentAuthorizationViewControllerDidFinish_": did_finish,
        }
        DelegateClass = type(
            "ApplePayDelegate",
            (objc.protocolNamed("PKPaymentAuthorizationViewControllerDelegate"),),
            delegate_methods,
        )
        delegate = DelegateClass.alloc().init()
        controller = PKPaymentAuthorizationViewController.alloc().initWithPaymentRequest_(request)
        controller.setDelegate_(delegate)
        UIApplication.sharedApplication().keyWindow.rootViewController.presentViewController_animated_completion_(
            controller, True, None
        )
        return {"status": "presented"}
    except Exception as e:
        return {"error": f"Failed to present Apple Pay: {str(e)}"}


def preauthorize(amount_cents, description, on_complete=None):
    """
    Preauthorize payment: Apple Pay UI + Intuit GoPayment processing.

    Args:
        amount_cents: Amount in cents
        description: Payment description
        on_complete: Callback when payment completes

    Returns:
        dict with status
    """
    if not IS_IOS or not OBJC_AVAILABLE:
        # Mock response for testing on non-iOS
        result = {
            "mock_response": True,
            "status": "authorized",
            "charge_id": "mock_charge_123",
            "amount_cents": amount_cents,
            "description": description
        }
        if on_complete:
            on_complete(result)
        return result

    return present_apple_pay_controller(amount_cents, description, on_complete)


def can_make_payments():
    """Check if Apple Pay is available."""
    if not OBJC_AVAILABLE:
        return False
    try:
        return PKPaymentAuthorizationViewController.canMakePayments()
    except Exception:
        return False
