"""Fase 0: captura UNA vez el refresh token del dueño del canal (scope
youtube.channel-memberships.creator). Solo stdlib. Uso:

  set GOOGLE_CLIENT_ID=...  &  set GOOGLE_CLIENT_SECRET=...
  python scripts/capture_youtube_refresh_token.py

Requiere que http://localhost:8765/ este en las URIs de redireccion
autorizadas del cliente OAuth. Inicia sesion con la cuenta DUEÑA del canal.
Imprime el refresh token; pegalo en el admin de Django ->
GoogleOAuthCredential (provider = youtube_creator). No lo subas a git."""

import json
import os
import sys
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
PORT = 8765
REDIRECT = f"http://localhost:{PORT}/"
# readonly solo sirve para que este script pueda mostrar QUE canal quedo
# autorizado; el sync diario usa unicamente el scope de membresias.
SCOPE = (
    "https://www.googleapis.com/auth/youtube.channel-memberships.creator "
    "https://www.googleapis.com/auth/youtube.readonly"
)

if not CLIENT_ID or not CLIENT_SECRET:
    sys.exit("Define GOOGLE_CLIENT_ID y GOOGLE_CLIENT_SECRET en el entorno.")

result = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        result["code"] = q.get("code", [""])[0]
        result["error"] = q.get("error", [""])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Listo, puedes cerrar esta pestaña y volver a la terminal.".encode())

    def log_message(self, *a):
        pass


url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
    "client_id": CLIENT_ID, "redirect_uri": REDIRECT, "response_type": "code",
    "scope": SCOPE, "access_type": "offline", "prompt": "consent",
})
print("Abriendo el navegador. Si no abre, visita:\n", url)
webbrowser.open(url)
HTTPServer(("localhost", PORT), Handler).handle_request()

if not result.get("code"):
    sys.exit(f"Google no devolvió code: {result.get('error')}")

data = urllib.parse.urlencode({
    "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "code": result["code"],
    "grant_type": "authorization_code", "redirect_uri": REDIRECT,
}).encode()
with urllib.request.urlopen("https://oauth2.googleapis.com/token", data) as r:
    tok = json.load(r)

if not tok.get("refresh_token"):
    sys.exit("No vino refresh_token. Revoca el acceso en myaccount.google.com/permissions y repite.")
req = urllib.request.Request(
    "https://youtube.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
    headers={"Authorization": "Bearer " + tok["access_token"]},
)
try:
    with urllib.request.urlopen(req) as r:
        items = json.load(r).get("items", [])
except Exception as e:
    items = None
    print("\nNo se pudo consultar el canal:", e)
if items:
    print("\nCANAL AUTORIZADO:", items[0]["snippet"]["title"], "(" + items[0]["id"] + ")")
    print("Si ese NO es el canal de Hardcore Games, repite y elige el canal correcto en el selector de Google.")
elif items is not None:
    print("\nOJO: esta cuenta no tiene ningun canal asociado. Repite eligiendo el canal de Hardcore Games.")
print("\nREFRESH TOKEN (guárdalo en el admin, no lo compartas):\n" + tok["refresh_token"])
