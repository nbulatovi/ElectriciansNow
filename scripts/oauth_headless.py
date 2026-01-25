#!/usr/bin/env python3
"""
Headless OAuth token retrieval for Intuit.
Uses requests to automate the OAuth flow without a browser.

Required environment variables:
- INTUIT_CLIENT_ID: App client ID
- INTUIT_CLIENT_SECRET: App client secret
- INTUIT_USERNAME: Intuit account email
- INTUIT_PASSWORD: Intuit account password

Note: This may not work if Intuit requires CAPTCHA or 2FA.
In that case, use the developer playground manually.
"""

import os
import sys
import re
import base64
import json
import urllib.parse
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import time

# Configuration
CLIENT_ID = os.environ.get('INTUIT_CLIENT_ID', '')
CLIENT_SECRET = os.environ.get('INTUIT_CLIENT_SECRET', '')
INTUIT_USERNAME = os.environ.get('INTUIT_USERNAME', '')
INTUIT_PASSWORD = os.environ.get('INTUIT_PASSWORD', '')

REDIRECT_URI = 'http://localhost:9876/callback'
SCOPES = 'com.intuit.quickbooks.payment'

# Intuit URLs
AUTH_URL = 'https://appcenter.intuit.com/connect/oauth2'
TOKEN_URL = 'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer'

# Global to capture auth code
auth_code = None
server_ready = threading.Event()


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if 'code' in params:
            auth_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<h1>Success! You can close this window.</h1>')
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            error = params.get('error', ['unknown'])[0]
            self.wfile.write(f'<h1>Error: {error}</h1>'.encode())

    def log_message(self, format, *args):
        pass


def start_callback_server():
    """Start local server to receive OAuth callback."""
    server = HTTPServer(('localhost', 9876), CallbackHandler)
    server.timeout = 5
    server_ready.set()

    # Handle requests until we get the code or timeout
    start = time.time()
    while auth_code is None and (time.time() - start) < 120:
        server.handle_request()

    server.server_close()


def get_auth_url():
    """Generate OAuth authorization URL."""
    params = {
        'client_id': CLIENT_ID,
        'scope': SCOPES,
        'redirect_uri': REDIRECT_URI,
        'response_type': 'code',
        'state': 'automation'
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens(code):
    """Exchange authorization code for tokens."""
    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    auth_header = base64.b64encode(credentials.encode()).decode()

    response = requests.post(
        TOKEN_URL,
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {auth_header}'
        },
        data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI
        },
        timeout=30
    )

    if response.status_code != 200:
        print(f"Token exchange failed: {response.status_code}")
        print(response.text)
        return None

    return response.json()


def automated_oauth_flow():
    """
    Attempt automated OAuth using requests.
    This simulates browser login flow.
    """
    global auth_code

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    })

    # Step 1: Get authorization page
    auth_url = get_auth_url()
    print(f"Starting OAuth flow...")

    response = session.get(auth_url, allow_redirects=True)

    if response.status_code != 200:
        print(f"Failed to get auth page: {response.status_code}")
        return None

    # Check if we got redirected to login
    current_url = response.url
    print(f"Redirected to: {current_url}")

    # Try to find login form and CSRF token
    html = response.text

    # Look for form action and hidden fields
    # Intuit's login page structure varies, so we try multiple patterns

    # Extract any hidden inputs
    hidden_inputs = {}
    for match in re.finditer(r'<input[^>]+type=["\']hidden["\'][^>]*>', html, re.I):
        input_tag = match.group(0)
        name_match = re.search(r'name=["\']([^"\']+)["\']', input_tag)
        value_match = re.search(r'value=["\']([^"\']*)["\']', input_tag)
        if name_match:
            hidden_inputs[name_match.group(1)] = value_match.group(1) if value_match else ''

    print(f"Found hidden inputs: {list(hidden_inputs.keys())}")

    # Try to find the login form action
    form_action = None
    form_match = re.search(r'<form[^>]+action=["\']([^"\']+)["\']', html, re.I)
    if form_match:
        form_action = form_match.group(1)
        if not form_action.startswith('http'):
            # Relative URL
            from urllib.parse import urljoin
            form_action = urljoin(current_url, form_action)

    if not form_action:
        # Try common Intuit login endpoints
        form_action = 'https://accounts.intuit.com/app/sign-in'

    print(f"Login form action: {form_action}")

    # Step 2: Submit login credentials
    login_data = {
        **hidden_inputs,
        'Email': INTUIT_USERNAME,
        'Password': INTUIT_PASSWORD,
        'username': INTUIT_USERNAME,
        'password': INTUIT_PASSWORD,
    }

    print("Submitting login...")
    login_response = session.post(
        form_action,
        data=login_data,
        allow_redirects=True
    )

    print(f"Login response: {login_response.status_code}, URL: {login_response.url}")

    # Check if we need to handle authorization consent
    if 'oauth' in login_response.url.lower() or 'authorize' in login_response.url.lower():
        print("Looking for authorization consent...")

        # Look for authorize button/form
        consent_html = login_response.text

        # Try to find and submit consent form
        consent_action = None
        consent_match = re.search(r'<form[^>]+action=["\']([^"\']+)["\'][^>]*>', consent_html, re.I)
        if consent_match:
            consent_action = consent_match.group(1)
            if not consent_action.startswith('http'):
                from urllib.parse import urljoin
                consent_action = urljoin(login_response.url, consent_action)

        if consent_action:
            print(f"Submitting consent to: {consent_action}")
            consent_response = session.post(consent_action, allow_redirects=True)
            print(f"Consent response URL: {consent_response.url}")

            # Check for callback with code
            if 'code=' in consent_response.url:
                parsed = urllib.parse.urlparse(consent_response.url)
                params = urllib.parse.parse_qs(parsed.query)
                if 'code' in params:
                    auth_code = params['code'][0]

    # Check final URL for auth code
    if auth_code is None and 'code=' in login_response.url:
        parsed = urllib.parse.urlparse(login_response.url)
        params = urllib.parse.parse_qs(parsed.query)
        if 'code' in params:
            auth_code = params['code'][0]

    return auth_code


def main():
    # Validate environment
    missing = []
    if not CLIENT_ID:
        missing.append('INTUIT_CLIENT_ID')
    if not CLIENT_SECRET:
        missing.append('INTUIT_CLIENT_SECRET')
    if not INTUIT_USERNAME:
        missing.append('INTUIT_USERNAME')
    if not INTUIT_PASSWORD:
        missing.append('INTUIT_PASSWORD')

    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    print("=" * 60)
    print("Intuit OAuth Headless Token Retrieval")
    print("=" * 60)

    # Try automated flow
    code = automated_oauth_flow()

    if not code:
        print("\nAutomated login failed.")
        print("This usually happens due to:")
        print("  - CAPTCHA required")
        print("  - 2FA/MFA enabled")
        print("  - Changed login page structure")
        print("\nPlease use Intuit Developer Playground instead:")
        print("  https://developer.intuit.com/app/developer/playground")
        sys.exit(1)

    print(f"\nAuthorization code obtained!")

    # Exchange for tokens
    print("Exchanging code for tokens...")
    tokens = exchange_code_for_tokens(code)

    if not tokens:
        print("Failed to exchange code for tokens")
        sys.exit(1)

    access_token = tokens.get('access_token', '')
    refresh_token = tokens.get('refresh_token', '')

    print("\n" + "=" * 60)
    print("SUCCESS!")
    print("=" * 60)

    # Output for GitHub Actions
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            # Mask the tokens
            print(f"::add-mask::{access_token}")
            print(f"::add-mask::{refresh_token}")
            f.write(f"INTUIT_ACCESS_TOKEN={access_token}\n")
            f.write(f"INTUIT_REFRESH_TOKEN={refresh_token}\n")
        print("Tokens written to GITHUB_OUTPUT")
    else:
        print(f"\nINTUIT_ACCESS_TOKEN={access_token[:50]}...")
        print(f"INTUIT_REFRESH_TOKEN={refresh_token[:50]}...")

    print("\nTokens retrieved successfully!")


if __name__ == '__main__':
    main()
