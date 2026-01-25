#!/usr/bin/env python3
"""
Headless OAuth token retrieval for Intuit with extensive debugging.
"""

import os
import sys
import re
import base64
import json
import urllib.parse
import requests

# Configuration
CLIENT_ID = os.environ.get('INTUIT_CLIENT_ID', '')
CLIENT_SECRET = os.environ.get('INTUIT_CLIENT_SECRET', '')
INTUIT_USERNAME = os.environ.get('INTUIT_USERNAME', '')
INTUIT_PASSWORD = os.environ.get('INTUIT_PASSWORD', '')

REDIRECT_URI = 'https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl'
SCOPES = 'com.intuit.quickbooks.payment'

# Intuit URLs
AUTH_URL = 'https://appcenter.intuit.com/connect/oauth2'
TOKEN_URL = 'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer'
LOGIN_URL = 'https://accounts.intuit.com/app/sign-in'

DEBUG = True

def debug(msg):
    if DEBUG:
        print(f"[DEBUG] {msg}")

def debug_response(resp, label="Response"):
    debug(f"{label} status: {resp.status_code}")
    debug(f"{label} URL: {resp.url}")
    debug(f"{label} headers: {dict(resp.headers)}")
    if len(resp.text) < 2000:
        debug(f"{label} body: {resp.text[:1000]}")
    else:
        debug(f"{label} body length: {len(resp.text)} chars")


def get_auth_url():
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
    debug(f"Exchanging code: {code[:20]}...")

    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    auth_header = base64.b64encode(credentials.encode()).decode()

    resp = requests.post(
        TOKEN_URL,
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {auth_header}',
            'Accept': 'application/json'
        },
        data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI
        },
        timeout=30
    )

    debug_response(resp, "Token exchange")

    if resp.status_code != 200:
        print(f"ERROR: Token exchange failed: {resp.status_code}")
        print(resp.text)
        return None

    return resp.json()


def extract_form_data(html, form_id=None):
    """Extract form action and all input fields."""
    forms = {}

    # Find all forms
    form_pattern = r'<form[^>]*>(.*?)</form>'
    for match in re.finditer(form_pattern, html, re.DOTALL | re.I):
        form_html = match.group(0)

        # Get action
        action_match = re.search(r'action=["\']([^"\']+)["\']', form_html, re.I)
        action = action_match.group(1) if action_match else ''

        # Get method
        method_match = re.search(r'method=["\']([^"\']+)["\']', form_html, re.I)
        method = method_match.group(1).upper() if method_match else 'GET'

        # Get all inputs
        inputs = {}
        for inp in re.finditer(r'<input[^>]*>', form_html, re.I):
            inp_html = inp.group(0)
            name_match = re.search(r'name=["\']([^"\']+)["\']', inp_html, re.I)
            value_match = re.search(r'value=["\']([^"\']*)["\']', inp_html, re.I)
            type_match = re.search(r'type=["\']([^"\']+)["\']', inp_html, re.I)

            if name_match:
                name = name_match.group(1)
                value = value_match.group(1) if value_match else ''
                inp_type = type_match.group(1) if type_match else 'text'
                inputs[name] = {'value': value, 'type': inp_type}

        forms[action] = {'action': action, 'method': method, 'inputs': inputs}

    return forms


def find_csrf_token(html):
    """Find CSRF token in various formats."""
    patterns = [
        r'name=["\']csrf["\'][^>]*value=["\']([^"\']+)["\']',
        r'name=["\']_csrf["\'][^>]*value=["\']([^"\']+)["\']',
        r'name=["\']csrfToken["\'][^>]*value=["\']([^"\']+)["\']',
        r'"csrf":\s*"([^"]+)"',
        r'"csrfToken":\s*"([^"]+)"',
        r'data-csrf=["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.I)
        if match:
            return match.group(1)
    return None


def automated_oauth_flow():
    """Attempt automated OAuth with detailed debugging."""

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    })

    # Step 1: Start OAuth flow
    auth_url = get_auth_url()
    debug(f"Step 1: Starting OAuth at {auth_url}")

    resp = session.get(auth_url, allow_redirects=True)
    debug_response(resp, "OAuth start")

    current_url = resp.url
    html = resp.text

    # Check if we already have a code (unlikely but check)
    if 'code=' in current_url:
        parsed = urllib.parse.urlparse(current_url)
        params = urllib.parse.parse_qs(parsed.query)
        if 'code' in params:
            debug("Got auth code immediately!")
            return params['code'][0]

    # Step 2: Analyze the login page
    debug(f"Step 2: Analyzing login page at {current_url}")

    # Look for JSON config embedded in page
    json_config_match = re.search(r'window\.__CONFIG__\s*=\s*({.*?});', html, re.DOTALL)
    if json_config_match:
        try:
            config = json.loads(json_config_match.group(1))
            debug(f"Found page config: {list(config.keys())}")
        except:
            pass

    # Extract forms
    forms = extract_form_data(html)
    debug(f"Found {len(forms)} forms: {list(forms.keys())}")

    # Find CSRF token
    csrf = find_csrf_token(html)
    debug(f"CSRF token: {csrf[:20] if csrf else 'NOT FOUND'}...")

    # Look for specific Intuit login elements
    has_email_field = 'email' in html.lower() or 'username' in html.lower()
    has_password_field = 'password' in html.lower()
    debug(f"Has email field: {has_email_field}, Has password field: {has_password_field}")

    # Check if this is a two-step login (email first, then password)
    # Intuit often uses this pattern

    # Try to find the login API endpoint
    api_endpoints = re.findall(r'["\'](/api/[^"\']+)["\']', html)
    debug(f"Found API endpoints: {api_endpoints}")

    # Step 3: Try different login approaches

    # Approach A: Direct form submission
    debug("Step 3A: Trying direct form submission")

    # Find the most likely login form
    login_form = None
    for action, form in forms.items():
        inputs = form['inputs']
        input_names = [n.lower() for n in inputs.keys()]
        if any(x in input_names for x in ['email', 'username', 'user', 'login']):
            login_form = form
            break

    if login_form:
        debug(f"Found login form: {login_form['action']}")
        debug(f"Form inputs: {list(login_form['inputs'].keys())}")

        # Build form data
        form_data = {}
        for name, info in login_form['inputs'].items():
            if info['type'] == 'hidden':
                form_data[name] = info['value']
            elif name.lower() in ['email', 'username', 'user', 'login']:
                form_data[name] = INTUIT_USERNAME
            elif name.lower() == 'password':
                form_data[name] = INTUIT_PASSWORD

        debug(f"Submitting form with fields: {list(form_data.keys())}")

        form_action = login_form['action']
        if not form_action.startswith('http'):
            form_action = urllib.parse.urljoin(current_url, form_action)

        resp = session.post(form_action, data=form_data, allow_redirects=True)
        debug_response(resp, "Form submission")

        # Check for auth code
        if 'code=' in resp.url:
            parsed = urllib.parse.urlparse(resp.url)
            params = urllib.parse.parse_qs(parsed.query)
            if 'code' in params:
                debug("Got auth code after form submission!")
                return params['code'][0]

    # Approach B: Try Intuit's sign-in API directly
    debug("Step 3B: Trying Intuit sign-in API")

    # First, get the sign-in page to get cookies and tokens
    signin_resp = session.get('https://accounts.intuit.com/app/sign-in', allow_redirects=True)
    debug_response(signin_resp, "Sign-in page")

    signin_html = signin_resp.text
    csrf = find_csrf_token(signin_html)

    # Look for the authentication endpoint
    auth_api = None
    api_match = re.search(r'["\'](https?://[^"\']*auth[^"\']*)["\']', signin_html, re.I)
    if api_match:
        auth_api = api_match.group(1)
        debug(f"Found auth API: {auth_api}")

    # Try JSON-based authentication
    debug("Step 3C: Trying JSON authentication")

    json_headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Origin': 'https://accounts.intuit.com',
        'Referer': 'https://accounts.intuit.com/app/sign-in',
    }
    if csrf:
        json_headers['X-CSRF-Token'] = csrf
        json_headers['csrf-token'] = csrf

    # Try username/email step
    email_payload = {
        'username': INTUIT_USERNAME,
        'email': INTUIT_USERNAME,
    }

    for endpoint in ['/api/v1/sign-in/identifier', '/api/sign-in', '/v1/sign-in']:
        try:
            url = f"https://accounts.intuit.com{endpoint}"
            debug(f"Trying: {url}")
            resp = session.post(url, json=email_payload, headers=json_headers, allow_redirects=False)
            debug_response(resp, f"API {endpoint}")

            if resp.status_code in [200, 201, 302]:
                debug(f"Got response from {endpoint}")

                # If 200, might need password step
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        debug(f"JSON response: {data}")
                    except:
                        pass

                # Try password step
                pwd_payload = {
                    'username': INTUIT_USERNAME,
                    'email': INTUIT_USERNAME,
                    'password': INTUIT_PASSWORD,
                }

                for pwd_endpoint in ['/api/v1/sign-in/password', '/api/sign-in/password', endpoint]:
                    pwd_url = f"https://accounts.intuit.com{pwd_endpoint}"
                    debug(f"Trying password at: {pwd_url}")
                    resp = session.post(pwd_url, json=pwd_payload, headers=json_headers, allow_redirects=True)
                    debug_response(resp, f"Password {pwd_endpoint}")

                    if 'code=' in resp.url:
                        parsed = urllib.parse.urlparse(resp.url)
                        params = urllib.parse.parse_qs(parsed.query)
                        if 'code' in params:
                            return params['code'][0]
        except Exception as e:
            debug(f"Error with {endpoint}: {e}")

    # Step 4: Check if we're now authenticated and can complete OAuth
    debug("Step 4: Retrying OAuth after login attempts")

    resp = session.get(auth_url, allow_redirects=True)
    debug_response(resp, "OAuth retry")

    if 'code=' in resp.url:
        parsed = urllib.parse.urlparse(resp.url)
        params = urllib.parse.parse_qs(parsed.query)
        if 'code' in params:
            debug("Got auth code on OAuth retry!")
            return params['code'][0]

    # Check for consent page
    if 'authorize' in resp.url.lower() or 'consent' in resp.url.lower():
        debug("Found consent page, looking for approve button")
        consent_html = resp.text
        consent_forms = extract_form_data(consent_html)
        debug(f"Consent forms: {list(consent_forms.keys())}")

        # Try to submit consent
        for action, form in consent_forms.items():
            if 'authorize' in action.lower() or 'consent' in action.lower() or 'allow' in action.lower():
                form_data = {n: i['value'] for n, i in form['inputs'].items()}
                form_action = action if action.startswith('http') else urllib.parse.urljoin(resp.url, action)

                debug(f"Submitting consent to: {form_action}")
                resp = session.post(form_action, data=form_data, allow_redirects=True)
                debug_response(resp, "Consent submission")

                if 'code=' in resp.url:
                    parsed = urllib.parse.urlparse(resp.url)
                    params = urllib.parse.parse_qs(parsed.query)
                    if 'code' in params:
                        return params['code'][0]

    debug("All approaches failed")
    return None


def main():
    print("=" * 60)
    print("Intuit OAuth Headless Token Retrieval (DEBUG MODE)")
    print("=" * 60)

    # Check environment
    print(f"\nEnvironment check:")
    print(f"  CLIENT_ID: {'set' if CLIENT_ID else 'NOT SET'} ({len(CLIENT_ID)} chars)")
    print(f"  CLIENT_SECRET: {'set' if CLIENT_SECRET else 'NOT SET'} ({len(CLIENT_SECRET)} chars)")
    print(f"  USERNAME: {'set' if INTUIT_USERNAME else 'NOT SET'} ({len(INTUIT_USERNAME)} chars)")
    print(f"  PASSWORD: {'set' if INTUIT_PASSWORD else 'NOT SET'} ({len(INTUIT_PASSWORD)} chars)")

    if not all([CLIENT_ID, CLIENT_SECRET, INTUIT_USERNAME, INTUIT_PASSWORD]):
        print("\nERROR: Missing required environment variables")
        sys.exit(1)

    print(f"\nUsing redirect URI: {REDIRECT_URI}")
    print(f"Requested scopes: {SCOPES}")

    # Run OAuth flow
    print("\n" + "=" * 60)
    print("Starting OAuth flow...")
    print("=" * 60 + "\n")

    code = automated_oauth_flow()

    if not code:
        print("\n" + "=" * 60)
        print("OAUTH FAILED - Could not obtain authorization code")
        print("=" * 60)
        print("\nPossible reasons:")
        print("  1. Invalid credentials")
        print("  2. 2FA/MFA enabled on Intuit account")
        print("  3. CAPTCHA required")
        print("  4. Account security restrictions")
        print("\nPlease use the Intuit Developer Playground manually:")
        print("  https://developer.intuit.com/app/developer/playground")
        sys.exit(1)

    print(f"\n✓ Got authorization code: {code[:20]}...")

    # Exchange for tokens
    print("\nExchanging code for tokens...")
    tokens = exchange_code_for_tokens(code)

    if not tokens:
        print("ERROR: Failed to exchange code for tokens")
        sys.exit(1)

    access_token = tokens.get('access_token', '')
    refresh_token = tokens.get('refresh_token', '')

    print("\n" + "=" * 60)
    print("SUCCESS!")
    print("=" * 60)
    print(f"\nAccess token: {len(access_token)} chars")
    print(f"Refresh token: {len(refresh_token)} chars")

    # Output for GitHub Actions
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            print(f"::add-mask::{access_token}")
            print(f"::add-mask::{refresh_token}")
            f.write(f"ACCESS_TOKEN={access_token}\n")
            f.write(f"REFRESH_TOKEN={refresh_token}\n")
        print("\nTokens written to GITHUB_OUTPUT")


if __name__ == '__main__':
    main()
