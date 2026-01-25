#!/usr/bin/env python3
"""
Build-time script to create encrypted initial token bundle.

This script is run during CI/CD to embed OAuth tokens into the app bundle.
The tokens are encrypted with Fernet (AES-128-CBC) to prevent extraction.

Required environment variables:
- INTUIT_ACCESS_TOKEN: Current access token
- INTUIT_REFRESH_TOKEN: Current refresh token
- TOKEN_ENCRYPTION_KEY: Fernet key for encryption

Usage:
    python scripts/embed_tokens.py
"""

import os
import sys
import json
import time


def generate_encryption_key():
    """Generate a new Fernet key (for initial setup)."""
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


def create_token_bundle():
    """Create encrypted token bundle from environment variables."""
    from cryptography.fernet import Fernet

    access_token = os.environ.get('INTUIT_ACCESS_TOKEN')
    refresh_token = os.environ.get('INTUIT_REFRESH_TOKEN')
    encryption_key = os.environ.get('TOKEN_ENCRYPTION_KEY')

    if not access_token:
        print("Error: INTUIT_ACCESS_TOKEN not set")
        sys.exit(1)
    if not refresh_token:
        print("Error: INTUIT_REFRESH_TOKEN not set")
        sys.exit(1)
    if not encryption_key:
        print("Error: TOKEN_ENCRYPTION_KEY not set")
        sys.exit(1)

    # Token data with timestamps
    now = time.time()
    tokens = {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'created_at': now,
        # Access tokens expire in ~1 hour, we'll refresh anyway
        'expires_at': now + 3600,
        # Refresh tokens expire in 100 days
        'refresh_expires_at': now + (100 * 24 * 60 * 60)
    }

    # Encrypt the token data
    key = encryption_key.encode() if isinstance(encryption_key, str) else encryption_key
    fernet = Fernet(key)
    encrypted = fernet.encrypt(json.dumps(tokens).encode())

    # Ensure Resources directory exists
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Resources')
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, 'initial_tokens.enc')
    with open(output_path, 'wb') as f:
        f.write(encrypted)

    print(f"Token bundle created: {output_path}")
    print(f"Bundle size: {len(encrypted)} bytes")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--generate-key':
        # Helper to generate a new encryption key
        print("New encryption key (save as TOKEN_ENCRYPTION_KEY secret):")
        print(generate_encryption_key())
    else:
        create_token_bundle()


if __name__ == '__main__':
    main()
