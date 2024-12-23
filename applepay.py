import platform
import requests

# Constants
MERCHANT_ID = "merchant.com.snslocation.electricians-now"  # Replace with your Apple Pay Merchant ID
SQUARE_TOKEN = "EAAAlqyI_bF8mfhp426lVLd8-aXwBmS25f3tKkJzczH0q_orx8e4DLbpRBhmaswd"  # Replace with your Square API access token
SQUARE_LOCATION = "SNS Location"  # Replace with your Square location ID

# Check if running on iOS/macOS
IS_IOS = platform.system() == "Darwin"
if IS_IOS:
    import objc
    from objc import ObjCClass

    # Objective-C classes for Apple Pay
    PKPaymentRequest = ObjCClass('PKPaymentRequest')
    PKPaymentAuthorizationViewController = ObjCClass('PKPaymentAuthorizationViewController')
    PKPaymentSummaryItem = ObjCClass('PKPaymentSummaryItem')
    NSDecimalNumber = ObjCClass('NSDecimalNumber')
    UIApplication = ObjCClass('UIApplication')


def setup_apple_pay_request(amount_cents, description):
    """
    Configures the Apple Pay payment request.

    Returns:
    - PKPaymentRequest: Configured Apple Pay request.
    """
    try:
        req = PKPaymentRequest.alloc().init()
        req.merchantIdentifier, req.countryCode, req.currencyCode = MERCHANT_ID, "US", "USD"
        req.supportedNetworks, req.merchantCapabilities = ["visa", "masterCard", "amex"], 1 << 0
        req.paymentSummaryItems = [
            PKPaymentSummaryItem.summaryItemWithLabelAmount(
                description,
                NSDecimalNumber.decimalNumberWithString_(str(amount_cents / 100))
            )
        ]
        print("Apple Pay payment request configured.")
        return req
    except Exception as e:
        print(f"Error configuring Apple Pay request: {e}")
        return None


def send_to_square(amount_cents, token):
    """
    Sends the payment token to Square for preauthorization.

    Returns:
    - dict: Square API response.
    """
    try:
        response = requests.post(
            "https://connect.squareup.com/v2/payments",
            headers={"Authorization": f"Bearer {SQUARE_TOKEN}", "Content-Type": "application/json"},
            json={
                "idempotency_key": "unique_key_here",
                "amount_money": {"amount": amount_cents, "currency": "USD"},
                "autocomplete": False,  # Preauthorization mode
                "source_id": token,
                "location_id": SQUARE_LOCATION,
            },
        )
        print("Square API response received.")
        return response.json()
    except Exception as e:
        print(f"Error sending token to Square: {e}")
        return {"error": "Failed to send token to Square"}


def present_apple_pay_controller(amount_cents, description):
    """
    Presents the Apple Pay sheet and retrieves the payment token.

    Parameters:
    - amount_cents: Amount to be authorized in cents.
    - description: Description of the transaction.

    Returns:
    - dict: Square API response or error details.
    """
    def did_authorize_payment(_, payment, completion):
        """
        Called when the user authorizes the payment.
        Processes the token and sends it to Square.
        """
        try:
            token = payment.token.paymentData
            completion(0)  # Notify Apple Pay of success
            print("Apple Pay token retrieved. Sending to Square...")
            response = send_to_square(amount_cents, token)
            print("Preauthorization complete:", response)
        except Exception as e:
            completion(1)  # Notify Apple Pay of failure
            print(f"Error retrieving or processing Apple Pay token: {e}")

    def did_finish(controller):
        """
        Called when the Apple Pay sheet is dismissed.
        """
        print("Apple Pay sheet dismissed.")
        controller.dismissViewControllerAnimated_completion_(True, None)

    try:
        request = setup_apple_pay_request(amount_cents, description)
        if not request:
            print("Failed to configure Apple Pay request.")
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
        print("Apple Pay authorization view presented.")
    except Exception as e:
        print(f"Error presenting Apple Pay controller: {e}")
        return {"error": "Failed to present Apple Pay controller"}


def preauthorize(amount_cents, description):
    """
    Full preauthorization workflow: configure Apple Pay, get token, and preauthorize with Square.

    Returns:
    - dict: Final response from Square API or error details.
    """
    print(f"Starting preauthorization for {description} (${amount_cents / 100:.2f}).")

    if not IS_IOS:
        print("Running on a non-iOS platform. Returning a mock response.")
        return {"mock_response": True, "amount_cents": amount_cents, "description": description}

    return present_apple_pay_controller(amount_cents, description)
