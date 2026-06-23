# SkinTokens Blender Add-on

Auto-rig a mesh directly inside Blender. The add-on is a thin client: the model
runs on your GPU machine via a small local backend (`addon_server.py`), and
Blender only sends the mesh and imports the rigged result back.

```
Blender (add-on)  --HTTP 127.0.0.1 + token-->  addon_server.py  -->  TokenRig (GPU)
        ^                                                                  |
        +------------------- rigged GLB imported back --------------------+
```

## Quick reference

1. Set up the environment once: run **`../setup_windows.ps1`** (see `../WINDOWS_SETUP.md`).
2. Start the backend: double-click **`../run_addon_server.bat`** and wait for `... backend is ready` (leave it open).
3. Install this add-on in Blender: Edit → Preferences → Add-ons → **Install from Disk** → pick `blender_addon.zip` → enable **SkinTokens Auto-Rig**.
4. Select a mesh → **SkinTokens** tab in the N-panel → **Generate Rig**.

## Full documentation

See **[USAGE_GUIDE.md](USAGE_GUIDE.md)** for the complete guide: hardware/software
requirements, supported Blender versions, the server-status indicator and
Check-Environment button, multi-object auto-join, troubleshooting, security, and
design rationale.
