#!/usr/bin/env python3
"""
One-time script to get Intuit OAuth tokens.
Run this locally to obtain access_token and refresh_token.

Usage:
    export INTUIT_CLIENT_ID="your_client_id"
    export INTUIT_CLIENT_SECRET="your_client_secret"
    python scripts/get_intuit_tokens.py
"""

import os
import sys
import base64
import webbrowser
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

# Configuration
CLIENT_ID = os.environ.get('INTUIT_CLIENT_ID', '')
CLIENT_SECRET = os.environ.get('INTUIT_CLIENT_SECRET', '')
REDIRECT_URI = 'http://localhost:8765/callback'
SCOPES = 'com.intuit.quickbooks.payment'

# Intuit OAuth URLs
AUTH_URL = 'https://appcenter.intuit.com/connect/oauth2'
TOKEN_URL = 'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer'

# Store the authorization code
auth_code = None


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handle OAuth callback from Intuit."""

    def do_GET(self):
        global auth_code

        # Parse the callback URL
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if 'code' in params:
            auth_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'''
                <html>
                <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                    <h1>Authorization Successful!</h1>
                    <p>You can close this window and return to the terminal.</p>
                </body>
                </html>
            ''')
        elif 'error' in params:
            error = params.get('error', ['Unknown'])[0]
            error_desc = params.get('error_description', [''])[0]
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(f'''
                <html>
                <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                    <h1>Authorization Failed</h1>
                    <p>Error: {error}</p>
                    <p>{error_desc}</p>
                </body>
                </html>
            '''.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress logging


def get_authorization_url():
    """Generate Intuit OAuth authorization URL."""
    params = {
        'client_id': CLIENT_ID,
        'scope': SCOPES,
        'redirect_uri': REDIRECT_URI,
        'response_type': 'code',
        'state': 'security_token'
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens(code):
    """Exchange authorization code for access and refresh tokens."""
    # Create Basic auth header
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
        }
    )

    if response.status_code != 200:
        print(f"Error: {response.status_code}")
        print(response.text)
        return None

    return response.json()


def main():
    global auth_code

    if not CLIENT_ID or not CLIENT_SECRET:
        print("Error: Set INTUIT_CLIENT_ID and INTUIT_CLIENT_SECRET environment variables")
        print("")
        print("Example:")
        print('  export INTUIT_CLIENT_ID="ABc123..."')
        print('  export INTUIT_CLIENT_SECRET="XYz789..."')
        print("  python scripts/get_intuit_tokens.py")
        sys.exit(1)

    print("=" * 60)
    print("Intuit OAuth Token Generator")
    print("=" * 60)
    print("")
    print("This will open your browser to authorize with Intuit.")
    print("After authorization, tokens will be displayed here.")
    print("")

    # Generate auth URL
    auth_url = get_authorization_url()

    # Start local server
    server = HTTPServer(('localhost', 8765), OAuthCallbackHandler)
    server.timeout = 120  # 2 minute timeout

    print("Opening browser for Intuit authorization...")
    print(f"If browser doesn't open, go to:\n{auth_url}\n")

    # Open browser
    webbrowser.open(auth_url)

    print("Waiting for authorization callback...")

    # Wait for callback
    while auth_code is None:
        server.handle_request()

    server.server_close()

    print("\nAuthorization code received. Exchanging for tokens...")

    # Exchange code for tokens
    tokens = exchange_code_for_tokens(auth_code)

    if not tokens:
        print("Failed to get tokens")
        sys.exit(1)

    access_token = tokens.get('access_token', '')
    refresh_token = tokens.get('refresh_token', '')
    expires_in = tokens.get('expires_in', 0)
    refresh_expires = tokens.get('x_refresh_token_expires_in', 0)

    print("")
    print("=" * 60)
    print("SUCCESS! Add these as GitHub Secrets:")
    print("=" * 60)
    print("")
    print(f"INTUIT_ACCESS_TOKEN:")
    print(f"{access_token}")
    print("")
    print(f"INTUIT_REFRESH_TOKEN:")
    print(f"{refresh_token}")
    print("")
    print(f"Access token expires in: {expires_in // 60} minutes")
    print(f"Refresh token expires in: {refresh_expires // 86400} days")
    print("")
    print("=" * 60)


if __name__ == '__main__':
    main()
