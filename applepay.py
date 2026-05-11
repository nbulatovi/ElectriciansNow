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

OBJC_AVAILABLE = False
SFSafariViewController = None
NSURL = None
UIApplication = None
ObjCClass = None

if IS_IOS:
    # kivy-ios ships pyobjus, NOT pyobjc. Previous version of this module
    # imported `objc` (pyobjc, Mac-only) which always failed on device,
    # silently routing payments to the desktop fallback that doesn't open
    # anything. That bug looked like "no error, no Whop window" -- which is
    # exactly the symptom the user reported.
    try:
        from pyobjus import autoclass as _autoclass
        ObjCClass = _autoclass
        SFSafariViewController = ObjCClass('SFSafariViewController')
        NSURL = ObjCClass('NSURL')
        UIApplication = ObjCClass('UIApplication')
        OBJC_AVAILABLE = True
        log("applepay", "pyobjus bridge loaded")
    except Exception as e:
        log_exception("applepay", "pyobjus bridge unavailable", e)


def _resolve_top_view_controller():
    """Find the current topmost view controller, handling iOS 13+ scenes.

    UIApplication.keyWindow is deprecated since iOS 13 and may return nil
    on iOS 15+ when the app uses scenes. We walk the connected scenes to
    find the foreground active one and grab its key window, then descend
    through any presented controllers to find the actual top.
    """
    UIApplication = ObjCClass('UIApplication')
    app = UIApplication.sharedApplication()
    log("applepay", "resolving top view controller")

    key_window = None

    # Path 1: iOS 13+ connected scenes
    try:
        scenes = app.connectedScenes()
        n = scenes.count() if scenes else 0
        log("applepay", "connectedScenes count", n=n)
        # NSSet -> need allObjects to iterate by index
        scenes_array = scenes.allObjects() if scenes else None
        narr = scenes_array.count() if scenes_array else 0
        for i in range(narr):
            scene = scenes_array.objectAtIndex_(i)
            state = scene.activationState() if scene else None
            log("applepay", "scene", index=i, activationState=state)
            # 0 = UISceneActivationStateForegroundActive
            if state == 0:
                # Try scene.keyWindow first (iOS 15+)
                try:
                    kw = scene.keyWindow()
                    if kw:
                        key_window = kw
                        log("applepay", "got keyWindow from scene.keyWindow")
                        break
                except Exception as e:
                    log("applepay", "scene.keyWindow raised", err=str(e))
                # Fall back to scene.windows[0]
                try:
                    windows = scene.windows()
                    if windows and windows.count() > 0:
                        for j in range(windows.count()):
                            w = windows.objectAtIndex_(j)
                            if w.isKeyWindow():
                                key_window = w
                                log("applepay", "got keyWindow from scene.windows[isKey]")
                                break
                        if not key_window and windows.count() > 0:
                            key_window = windows.objectAtIndex_(0)
                            log("applepay", "fell back to first scene window")
                        break
                except Exception as e:
                    log("applepay", "scene.windows raised", err=str(e))
    except Exception as e:
        log_exception("applepay", "connectedScenes path raised", e)

    # Path 2: deprecated keyWindow
    if not key_window:
        try:
            kw = app.keyWindow
            if kw:
                key_window = kw
                log("applepay", "got deprecated UIApplication.keyWindow")
        except Exception as e:
            log("applepay", "deprecated keyWindow raised", err=str(e))

    # Path 3: scan app.windows
    if not key_window:
        try:
            ws = app.windows
            n = ws.count() if ws else 0
            log("applepay", "app.windows count", n=n)
            for i in range(n):
                w = ws.objectAtIndex_(i)
                if w.isKeyWindow():
                    key_window = w
                    log("applepay", "got keyWindow from app.windows scan")
                    break
            if not key_window and n > 0:
                key_window = ws.objectAtIndex_(0)
                log("applepay", "fell back to first app.windows")
        except Exception as e:
            log_exception("applepay", "app.windows path raised", e)

    if not key_window:
        log("applepay", "FAIL: could not find any window")
        return None

    try:
        vc = key_window.rootViewController()
        if not vc:
            log("applepay", "FAIL: rootViewController is nil")
            return None
        # Descend through presented controllers
        depth = 0
        while True:
            presented = None
            try:
                presented = vc.presentedViewController
            except Exception:
                pass
            if not presented:
                break
            vc = presented
            depth += 1
            if depth > 10:
                break
        log("applepay", "resolved top VC", depth=depth)
        return vc
    except Exception as e:
        log_exception("applepay", "rootVC resolution raised", e)
        return None


def _open_checkout_ios(purchase_url, on_complete=None):
    """Open Whop checkout in SFSafariViewController on iOS."""
    log("applepay", "_open_checkout_ios called", purchase_url=purchase_url)
    try:
        url = NSURL.URLWithString_(purchase_url)
        if not url:
            log("applepay", "FAIL: NSURL.URLWithString_ returned nil",
                purchase_url=purchase_url)
            return {"error": "Invalid checkout URL"}

        safari_vc = SFSafariViewController.alloc().initWithURL_(url)
        if not safari_vc:
            log("applepay", "FAIL: SFSafariViewController init returned nil")
            return {"error": "Could not construct Safari view"}

        top_vc = _resolve_top_view_controller()
        if not top_vc:
            return {"error": "Could not find a window to present from. Reopen the app and try again."}

        top_vc.presentViewController_animated_completion_(safari_vc, True, None)
        log("applepay", "SFSafariViewController present call returned")
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
    plan_id = checkout.get("plan_id")
    log("applepay", "checkout created, opening",
        purchase_url=purchase_url, plan_id=plan_id)

    if not IS_IOS or not OBJC_AVAILABLE:
        result = _open_checkout_desktop(purchase_url, on_complete)
    else:
        result = _open_checkout_ios(purchase_url, on_complete)

    # Surface plan_id so the caller can poll for actual payment completion.
    result["plan_id"] = plan_id
    result["checkout_id"] = checkout.get("checkout_id")
    result["purchase_url"] = purchase_url
    return result


def can_make_payments():
    return True
