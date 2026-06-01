# Copyright 2026 Valentin Richter

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import http.server
import json
import os
import socketserver
import ssl
import threading
import webbrowser
import urllib.parse
import time
from typing import Any, Dict, Optional

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AUTH_DIR = os.path.join(SCRIPT_DIR, "auth")
CERT_FILE = os.path.join(AUTH_DIR, "cert.pem")
KEY_FILE = os.path.join(AUTH_DIR, "key.pem")
TOKEN_FILE = os.path.join(AUTH_DIR, "token.json")
CLIENT_CONFIG_FILE = os.path.join(AUTH_DIR, "client.json")

# === CONFIG ===
REDIRECT_URL = "https://127.0.0.1:6767"

AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"

# === GLOBALS ===
auth_code: Optional[str] = None
httpd: Optional[socketserver.TCPServer] = None


def ensure_auth_dir() -> None:
    os.makedirs(AUTH_DIR, exist_ok=True)


def load_client_config() -> tuple[str, str]:
    ensure_auth_dir()
    if os.path.exists(CLIENT_CONFIG_FILE):
        with open(CLIENT_CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)

        try:
            return config["client_id"], config["client_secret"]
        except KeyError as exc:
            raise ValueError(
                f"{CLIENT_CONFIG_FILE} must contain client_id and client_secret"
            ) from exc

    print("No auth/client.json found. Paste your Schwab Developer Portal credentials.")
    client_id = input("Client ID: ").strip()
    client_secret = input("Client Secret: ").strip()

    if not client_id or not client_secret:
        raise ValueError("Client ID and Client Secret cannot be empty.")

    with open(CLIENT_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"client_id": client_id, "client_secret": client_secret}, f, indent=2)

    print(f"Saved Schwab credentials to {CLIENT_CONFIG_FILE}")
    return client_id, client_secret


def generate_cert_files(cert_file: str = CERT_FILE, key_file: str = KEY_FILE) -> None:
    ensure_auth_dir()

    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from datetime import datetime, timedelta
    import ipaddress

    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    with open(key_file, "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, u"127.0.0.1"),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    with open(cert_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))


def ensure_certs() -> None:
    ensure_auth_dir()
    if not (os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE)):
        generate_cert_files()


class OAuthHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        global auth_code

        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        auth_code = params.get("code", [None])[0]

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Authentication complete. You may close this window.")

        # Shut down server after responding
        assert httpd is not None
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    def log_message(self, format, *args):
        return


def get_auth_code(client_id: str) -> str:
    global httpd, auth_code
    auth_code = None

    ensure_certs()

    httpd = socketserver.TCPServer(("127.0.0.1", 6767), OAuthHandler)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

    assert httpd is not None
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URL,
        "response_type": "code",
        "scope": "read marketdata",
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)

    print("Opening browser for Schwab login…")
    webbrowser.open(url)

    while auth_code is None:
        time.sleep(0.1)

    return auth_code


def exchange_code_for_tokens(code: str, client_id: str, client_secret: str) -> str:
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("utf-8")
    headers = {
        "Authorization": f"Basic {basic}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URL,
        "client_id": client_id,
        "scope": "read marketdata",
    }

    resp = requests.post(TOKEN_URL, headers=headers, data=data)
    resp.raise_for_status()
    return resp.text


def load_tokens(token_file: str = TOKEN_FILE) -> Optional[Dict[str, Any]]:
    try:
        with open(token_file, "r", encoding="utf-8") as f:
            return json.loads(f.read())
    except FileNotFoundError:
        return None


def save_tokens(raw_json: str, token_file: str = TOKEN_FILE) -> None:
    ensure_auth_dir()
    tokens = json.loads(raw_json)
    # Add timestamp of when token was created
    tokens["created_at"] = time.time()
    with open(token_file, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)


def perform_initial_handshake(token_file: str = TOKEN_FILE) -> Dict[str, Any]:
    client_id, client_secret = load_client_config()

    print("Waiting for Schwab login…")
    code = get_auth_code(client_id)

    raw_tokens = exchange_code_for_tokens(code, client_id, client_secret)
    save_tokens(raw_tokens, token_file)
    return json.loads(raw_tokens)


def is_token_expired(tokens: Dict[str, Any]) -> bool:
    """Check if the access token has expired."""
    if "created_at" not in tokens or "expires_in" not in tokens:
        return True
    
    elapsed_time = time.time() - tokens["created_at"]
    return elapsed_time >= tokens["expires_in"]


def refresh_access_token(tokens: Dict[str, Any], token_file: str = TOKEN_FILE) -> Dict[str, Any]:
    """Refresh the access token using the refresh token."""
    client_id, client_secret = load_client_config()
    
    if "refresh_token" not in tokens:
        raise ValueError("No refresh_token found. Need to perform initial authentication.")
    
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("utf-8")
    headers = {
        "Authorization": f"Basic {basic}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    
    data = {
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "client_id": client_id,
        "scope": "read marketdata",
    }
    
    print("Refreshing access token...")
    resp = requests.post(TOKEN_URL, headers=headers, data=data)
    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        print(f"Refresh token request failed ({resp.status_code}): {resp.text}")
        raise

    new_tokens = resp.json()
    # Preserve refresh_token if not included in response
    if "refresh_token" not in new_tokens and "refresh_token" in tokens:
        new_tokens["refresh_token"] = tokens["refresh_token"]
    
    # Save updated tokens
    save_tokens(json.dumps(new_tokens), token_file)
    print("Access token refreshed successfully.")
    return new_tokens


def get_or_create_tokens(token_file: str = TOKEN_FILE) -> Dict[str, Any]:
    tokens = load_tokens(token_file)
    if tokens is None:
        tokens = perform_initial_handshake(token_file)
    return tokens


if __name__ == "__main__":
    ensure_auth_dir()
    ensure_certs()
    perform_initial_handshake()
    print(f"Token response saved to {TOKEN_FILE}.")
