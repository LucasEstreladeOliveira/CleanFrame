"""One-time Spotify sign-in for the Gallery now-playing widget (run on your Mac).

Uses the Authorization Code flow with PKCE, so no client secret is needed. The refresh token is stored in
.local/spotify.json (ignored by git, mode 600) and added to your own TV package by scripts/package.py and the
local preview. It is never part of app/ and never part of the public export.

Before running it, create an app at https://developer.spotify.com/dashboard and add this exact Redirect URI:
    http://127.0.0.1:8888/callback
"""
import argparse
import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import subprocess
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / '.local/spotify.json'
SCOPES = 'user-read-playback-state user-modify-playback-state'
TOKEN_URL = 'https://accounts.spotify.com/api/token'
AUTH_URL = 'https://accounts.spotify.com/authorize'


def pkce_pair():
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    return verifier, challenge


def authorize_url(client_id, redirect, challenge, state):
    return AUTH_URL + '?' + urllib.parse.urlencode({
        'client_id': client_id, 'response_type': 'code', 'redirect_uri': redirect,
        'code_challenge_method': 'S256', 'code_challenge': challenge, 'state': state, 'scope': SCOPES})


def exchange(client_id, redirect, code, verifier, token_url=TOKEN_URL):
    body = urllib.parse.urlencode({'grant_type': 'authorization_code', 'code': code, 'redirect_uri': redirect,
                                   'client_id': client_id, 'code_verifier': verifier}).encode()
    request = urllib.request.Request(token_url, body, {'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise SystemExit('Spotify refused the sign-in (' + str(error.code) + '): ' + error.read().decode(errors='replace')[:300])


def save(client_id, refresh_token, target=TARGET):
    if not re.fullmatch(r'[A-Za-z0-9]{16,64}', client_id):
        raise SystemExit('The client ID should be 16 to 64 letters and digits.')
    if not re.fullmatch(r'[A-Za-z0-9_.\-]{20,512}', refresh_token):
        raise SystemExit('Spotify returned a refresh token in an unexpected format.')
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as handle:
        json.dump({'clientId': client_id, 'refreshToken': refresh_token}, handle)
    os.chmod(target, 0o600)


APP_FILE = ROOT / 'app/assets/spotify-local.js'


def write_app_file(source=TARGET, target=APP_FILE):
    """For builds made from app/ directly (for example the VS Code Tizen extension).

    Writes your sign-in into the tracked app/assets/spotify-local.js and tells git to ignore local changes to it,
    so it cannot be committed by accident. Undo with --clear-app.
    """
    settings = json.loads(source.read_text())
    save(settings['clientId'], settings['refreshToken'], source)  # re-validates the stored values
    target.write_text('window.CleanFrameSpotify = ' + json.dumps({
        'enabled': True, 'clientId': settings['clientId'], 'refreshToken': settings['refreshToken']}) + ';\n')
    subprocess.run(['git', 'update-index', '--skip-worktree', str(target.relative_to(ROOT))], cwd=ROOT, check=False)


def clear_app_file(target=APP_FILE):
    rel = str(target.relative_to(ROOT))
    subprocess.run(['git', 'update-index', '--no-skip-worktree', rel], cwd=ROOT, check=False)
    subprocess.run(['git', 'checkout', '--', rel], cwd=ROOT, check=False)


def wait_for_code(port, state):
    result = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            if urllib.parse.urlsplit(self.path).path != '/callback':
                self.send_error(404)
                return
            if query.get('state', [''])[0] != state:
                result['error'] = 'State mismatch'
            elif 'error' in query:
                result['error'] = query['error'][0]
            else:
                result['code'] = query.get('code', [''])[0]
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(b'CleanFrame is connected to Spotify. You can close this tab.' if 'code' in result else b'Spotify sign-in failed. Return to the terminal.')
            done.set()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(('127.0.0.1', port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, result, done


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--client-id', help='Client ID of your Spotify developer app (not needed with --apply-only or --clear-app)')
    parser.add_argument('--into-app', action='store_true', help='After signing in, also write app/assets/spotify-local.js for builds made straight from app/')
    parser.add_argument('--apply-only', action='store_true', help='Do not sign in again; write app/assets/spotify-local.js from the saved .local/spotify.json')
    parser.add_argument('--clear-app', action='store_true', help='Restore the disabled app/assets/spotify-local.js')
    parser.add_argument('--port', type=int, default=8888)
    args = parser.parse_args()
    if args.clear_app:
        clear_app_file()
        print('Restored the disabled ' + str(APP_FILE.relative_to(ROOT)) + '.')
        return
    if args.apply_only:
        if not TARGET.is_file():
            raise SystemExit('No saved sign-in. Run this script with --client-id first.')
        write_app_file()
        print('Wrote ' + str(APP_FILE.relative_to(ROOT)) + ' (git will not list or commit changes to it). Rebuild and reinstall.')
        return
    if not args.client_id:
        raise SystemExit('--client-id is required for a new sign-in.')
    args.client_id = args.client_id.strip().strip('\'"<>')
    if not re.fullmatch(r'[0-9a-f]{32}', args.client_id):
        raise SystemExit('That is not a Spotify Client ID. It is exactly 32 letters and digits (0-9, a-f), shown as "Client ID" on your app page at '
                         'https://developer.spotify.com/dashboard. Do not use the app name, the Client Secret or the placeholder text from the instructions.')
    redirect = 'http://127.0.0.1:%d/callback' % args.port
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(16)
    server, result, done = wait_for_code(args.port, state)
    url = authorize_url(args.client_id, redirect, challenge, state)
    print('Open this address if your browser does not open by itself:\n' + url + '\n')
    webbrowser.open(url)
    if not done.wait(300):
        raise SystemExit('Timed out waiting for the Spotify sign-in.')
    server.shutdown()
    if not result.get('code'):
        raise SystemExit('Spotify sign-in failed: ' + result.get('error', 'no code returned'))
    tokens = exchange(args.client_id, redirect, result['code'], verifier)
    if not tokens.get('refresh_token'):
        raise SystemExit('Spotify did not return a refresh token.')
    save(args.client_id, tokens['refresh_token'])
    if args.into_app:
        write_app_file()
    print('Saved ' + str(TARGET) + '. Rebuild and reinstall CleanFrame to use it on the TV.')


if __name__ == '__main__':
    main()
