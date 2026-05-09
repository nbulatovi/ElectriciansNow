"""
Payment integration for ElectriciansNow app.
Uses Whop checkout which supports Apple Pay, cards, and other methods.
On iOS, opens checkout in SFSafariViewController.
On desktop, opens in browser (mock for testing).
"""

import platform
import os

from whop_payment import create_checkout
from app_logger import log, log_exception

IS_IOS = platform.system() == "Darwin"

if IS_IOS:
    try:
        import objc
        from objc import ObjCClass

        SFSafariViewController = ObjCClass('SFSafariViewController')
        NSURL = ObjCClass('NSURL')
        UIApplication = ObjCClass('UIApplication')
        OBJC_AVAILABLE = True
        log("applepay", "objc bridge loaded")
    except Exception as e:
        OBJC_AVAILABLE = False
        log_exception("applepay", "objc bridge unavailable", e)
else:
    OBJC_AVAILABLE = False


def _open_checkout_ios(purchase_url, on_complete=None):
    """Open Whop checkout in SFSafariViewController on iOS."""
    log("applepay", "_open_checkout_ios called", purchase_url=purchase_url)
    try:
        url = NSURL.URLWithString_(purchase_url)
        safari_vc = SFSafariViewController.alloc().initWithURL_(url)

        root_vc = UIApplication.sharedApplication().keyWindow.rootViewController
        root_vc.presentViewController_animated_completion_(safari_vc, True, None)

        log("applepay", "SFSafariViewController presented")
        return {"status": "presented", "purchase_url": purchase_url}
    except Exception as e:
        log_exception("applepay", "failed to present SafariVC", e)
        return {"error": f"Failed to open checkout: {e}"}


def _open_checkout_desktop(purchase_url, on_complete=None):
    """Open checkout in browser for desktop testing."""
    import webbrowser
    log("applepay", "_open_checkout_desktop", purchase_url=purchase_url)
    webbrowser.open(purchase_url)

    result = {
        "status": "authorized",
        "mock_response": True,
        "purchase_url": purchase_url,
    }
    if on_complete:
        on_complete(result)
    return result


def preauthorize(amount_cents, description, on_complete=None):
    """Create a Whop checkout session and open it for payment."""
    amount_dollars = amount_cents / 100.0

    log("applepay", "preauthorize start", amount_cents=amount_cents,
        amount_dollars=amount_dollars, description=description,
        is_ios=IS_IOS, objc_available=OBJC_AVAILABLE)

    checkout = create_checkout(
        amount_dollars=amount_dollars,
        description=description,
        metadata={"source": "electriciansnow_ios"},
    )

    if checkout.get("status") != "created":
        error = checkout.get("error", "Failed to create checkout")
        log("applepay", "checkout creation failed", error=error)
        return {"status": "failed", "error": error}

    purchase_url = checkout["purchase_url"]
    log("applepay", "checkout created, opening", purchase_url=purchase_url)

    if not IS_IOS or not OBJC_AVAILABLE:
        return _open_checkout_desktop(purchase_url, on_complete)

    return _open_checkout_ios(purchase_url, on_complete)


def can_make_payments():
    return True
