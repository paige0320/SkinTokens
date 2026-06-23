# SkinTokens Blender Add-on

Auto-rig a mesh directly inside Blender. The add-on is a thin client: the model
runs on your GPU machine via a small local backend, and Blender only sends the
mesh and imports the rigged result back.

```
Blender (add-on)  --HTTP 127.0.0.1 + token-->  addon_server.py  -->  TokenRig (GPU)
        ^                                                                  |
        +------------------- rigged GLB imported back --------------------+
```

## Why this design is safe

* The backend (`addon_server.py`) binds to **127.0.0.1 only** — nothing is
  exposed on your network, so no other machine can connect.
* Every request needs a matching **auth token** (auto-generated on first run,
  stored in the git-ignored `.addon_token`).
* The add-on code being public on GitHub does **not** let anyone reach your
  computer — only a running, network-exposed server could, and this one is
  loopback + token-gated.

## Setup (same machine as the GPU / SkinTokens install)

1. **Start the backend** — double-click `run_addon_server.ps1`
   (or run `.\.venv\Scripts\python.exe addon_server.py` from the project root).

   Leave this window open — it keeps the model loaded in VRAM. It also writes the
   connection token to `~/.skintokens_addon.json`, so the add-on auto-detects it.

2. **Install the add-on in Blender** (one time):
   - Zip the `blender_addon` folder (or use the provided `blender_addon.zip`).
   - Edit → Preferences → Add-ons → Install… → pick the zip.
   - Enable **"SkinTokens Auto-Rig"**. That's it — leave the preferences blank;
     the add-on auto-detects the running backend. (You only need to fill in the
     URL/token manually if the backend runs on a non-default port or another host.)

3. **Use it**:
   - In the 3D Viewport, select a mesh object.
   - Open the **SkinTokens** tab in the right sidebar (press `N` if hidden).
   - Adjust options if needed, then click **Rig Selected Mesh**.
   - Blender freezes while the GPU works, then imports the rigged armature + skin.

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| Preserve texture/scale | on | Transfer the original texture and scale (`--use_transfer`) |
| Use existing skeleton | off | Only generate skin weights, keep the input skeleton |
| Voxel skin postprocess | off | Voxel-based skin cleanup (`--use_postprocess`) |
| top_k / top_p / temperature / repetition_penalty / num_beams | 5 / 0.95 / 1.0 / 2.0 / 10 | Sampling parameters |

## Notes

* Supported export formats from Blender: GLB (the add-on always exports GLB).
* If you see **"Cannot reach backend"**, the `addon_server.py` window isn't
  running, or the URL/token in preferences don't match what it printed.
* The `glTF_not_exported` helper empty that Blender's glTF importer adds is
  removed automatically after import.
