"""Local HTTP backend for the SkinTokens Blender add-on.

Runs on the machine that has the GPU. Loads the TokenRig model once and keeps
it resident, then rigs any mesh POSTed to it and returns the rigged GLB.

Security
--------
* Binds to 127.0.0.1 only by default (loopback) -- nothing is exposed on the
  network, so no other machine can reach it.
* Every /rig request must carry a matching X-Auth-Token header. The token is
  read from the SKINTOKENS_TOKEN env var, or auto-generated into a local
  `.addon_token` file (git-ignored) on first run.

Usage
-----
    .venv\\Scripts\\python.exe addon_server.py

Then copy the printed Server URL + Token into the Blender add-on preferences.

Environment overrides:
    SKINTOKENS_ADDON_HOST   default 127.0.0.1   (do NOT set to 0.0.0.0 unless
                                                 you really want LAN access)
    SKINTOKENS_ADDON_PORT   default 8787
    SKINTOKENS_TOKEN        explicit auth token (otherwise auto-generated)
"""

import json
import os
import secrets
import tempfile
import traceback
from pathlib import Path

# Config file the Blender add-on reads so you never have to copy the token.
ADDON_CONFIG_FILE = Path.home() / ".skintokens_addon.json"

os.environ["XFORMERS_IGNORE_FLASH_VERSION_CHECK"] = "1"

import bottle
from bottle import request, response

# Reuse the inference machinery from demo.py (model load + run_rig + bpy server).
from demo import (
    MODEL_CKPTS,
    load_model,
    run_rig,
    start_bpy_server,
    wait_for_bpy_server,
)

HOST = os.environ.get("SKINTOKENS_ADDON_HOST", "127.0.0.1")
PORT = int(os.environ.get("SKINTOKENS_ADDON_PORT", "8787"))

PROJECT_DIR = Path(__file__).resolve().parent
TOKEN_FILE = PROJECT_DIR / ".addon_token"

SUPPORTED_EXT = {".obj", ".fbx", ".glb"}


def _load_or_create_token() -> str:
    tok = os.environ.get("SKINTOKENS_TOKEN")
    if tok:
        return tok.strip()
    if TOKEN_FILE.exists():
        existing = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    tok = secrets.token_hex(16)
    TOKEN_FILE.write_text(tok, encoding="utf-8")
    return tok


TOKEN = _load_or_create_token()

DEFAULT_PARAMS = dict(
    top_k=5,
    top_p=0.95,
    temperature=1.0,
    repetition_penalty=2.0,
    num_beams=10,
    use_skeleton=False,
    use_transfer=False,
    use_postprocess=False,
)


def _authorized() -> bool:
    return request.headers.get("X-Auth-Token", "") == TOKEN


def build_app() -> bottle.Bottle:
    app = bottle.Bottle()

    @app.route("/ping", method="GET")
    def ping():
        # No auth: lets the add-on check connectivity without leaking anything.
        return "ok"

    @app.route("/rig", method="POST")
    def rig():
        if not _authorized():
            response.status = 401
            return "unauthorized: bad or missing X-Auth-Token"

        try:
            params = dict(DEFAULT_PARAMS)
            raw_params = request.headers.get("X-Params")
            if raw_params:
                params.update(json.loads(raw_params))

            suffix = request.headers.get("X-Filename-Ext", ".glb").lower()
            if suffix not in SUPPORTED_EXT:
                suffix = ".glb"

            data = request.body.read()
            if not data:
                response.status = 400
                return "empty request body (no mesh data)"

            tmp_dir = Path(tempfile.mkdtemp(prefix="skintokens_addon_"))
            in_path = tmp_dir / f"input{suffix}"
            out_path = tmp_dir / "rigged.glb"
            in_path.write_bytes(data)

            run_rig(
                [in_path],
                params["top_k"],
                params["top_p"],
                params["temperature"],
                params["repetition_penalty"],
                params["num_beams"],
                bool(params["use_skeleton"]),
                bool(params["use_transfer"]),
                bool(params["use_postprocess"]),
                [out_path],
                MODEL_CKPTS[0] if MODEL_CKPTS else "",
                None,
            )

            if not out_path.exists():
                response.status = 500
                return "rigging finished but no output was produced"

            response.content_type = "application/octet-stream"
            return out_path.read_bytes()
        except Exception as e:  # noqa: BLE001 - report any failure back to Blender
            tb = traceback.format_exc()
            print(tb)
            response.status = 500
            return f"{type(e).__name__}: {e}\n{tb}"

    return app


def _port_in_use(host: str, port: int) -> bool:
    import socket

    probe_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex((probe_host, port)) == 0


def main():
    # Refuse to start a second backend on the same port -- running duplicates
    # leaves a broken one (no bpy_server child) that the add-on may hit.
    if _port_in_use(HOST, PORT):
        print("=" * 64)
        print(f"  A backend already appears to be running on port {PORT}.")
        print("  Do NOT start a second one -- close the other window first,")
        print("  or just use the one that is already running.")
        print("=" * 64)
        return

    print("[addon_server] starting bpy_server ...")
    start_bpy_server()
    wait_for_bpy_server()

    print("[addon_server] loading model (this can take a minute) ...")
    load_model(MODEL_CKPTS[0] if MODEL_CKPTS else "", None)
    print("[addon_server] model loaded.")

    url = f"http://{HOST}:{PORT}"

    # Write connection info where the add-on can auto-load it (no copy-paste).
    try:
        ADDON_CONFIG_FILE.write_text(
            json.dumps({"url": url, "token": TOKEN}), encoding="utf-8"
        )
    except OSError as e:
        print(f"[addon_server] warning: could not write {ADDON_CONFIG_FILE}: {e}")

    print("=" * 64)
    print("  SkinTokens add-on backend is ready.")
    print(f"  Server URL : {url}")
    print(f"  Auth token : {TOKEN}")
    print("  The Blender add-on auto-detects these -- no copy-paste needed.")
    if HOST not in ("127.0.0.1", "localhost"):
        print("  WARNING: host is not loopback -- this is reachable from the")
        print("           network. Only do this on a trusted LAN.")
    print("=" * 64)

    bottle.run(build_app(), host=HOST, port=PORT, server="tornado")


if __name__ == "__main__":
    main()
