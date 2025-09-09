#!/usr/bin/env python3
"""
Generate secure token for cron job authentication
"""

import secrets

def generate_secure_token():
    """Generate a cryptographically secure token for cron authentication."""
    token = secrets.token_urlsafe(32)
    return token

if __name__ == "__main__":
    token = generate_secure_token()
    print(f"CRON_SECRET_TOKEN={token}")
    print(f"\nGenerated secure token with {len(token)} characters")
    print("Copy the above line to your .env file or environment variables")
