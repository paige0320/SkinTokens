# SkinTokens Blender Add-on — Usage Guide & Requirements

Auto-rig a mesh inside Blender. The add-on is a **thin client**: it sends the
selected mesh to a small local backend (`addon_server.py`) that runs the model
on your GPU, then imports the rigged result (armature + skin weights) back.

```
Blender (add-on)  --HTTP 127.0.0.1 + token-->  addon_server.py  -->  TokenRig (GPU)
        ^                                                                  |
        +------------------- rigged GLB imported back --------------------+
```

Handing someone only the add-on `.zip` is **not enough** — they also need the
full SkinTokens install, the model weights, and an NVIDIA CUDA GPU. The add-on
alone cannot rig anything.

---

## 1. Hardware requirements

| Component | Minimum | Notes |
| --- | --- | --- |
| GPU | **NVIDIA, ≥ 14 GB VRAM, CUDA-capable** | Tested on RTX 3090 (24 GB, Ampere sm_86). No NVIDIA GPU → the backend cannot run. Apple/AMD/Intel GPUs are **not** supported. |
| System RAM | 16 GB+ | |
| Disk | ~10 GB free | Model checkpoints ≈ 1.5 GB, Python env (`.venv`) ≈ 7.5 GB |
| OS | Windows 10/11 (tested) | macOS can only be a *client* to a remote backend, never run the model. |

> Ampere cards (RTX 30-series) need the flash-attn → PyTorch SDPA fix this fork
> ships. See `../WINDOWS_SETUP.md`.

## 2. Software requirements

| Software | Version | Notes |
| --- | --- | --- |
| Blender | **3.6 – 5.1** | Same add-on code verified on 4.2 / 4.4 / 5.0 / 5.1 — no per-version shims. 3.6 is the declared minimum. |
| Python | 3.11 | Backend `.venv` (separate from Blender's bundled Python). |
| CUDA driver | 12.1+ | Match the PyTorch build in `requirements`. |

---

## 3. The whole flow (what you actually do)

1. **Download / unzip the whole package** and set it up once
   (`../WINDOWS_SETUP.md`): create `.venv`, then `python download.py --model`.
2. **Start the backend first.** Double-click `../run_addon_server.bat`
   (or `.venv\Scripts\python.exe addon_server.py`). Wait until you see:
   ```
   ================================================================
     SkinTokens add-on backend is ready.
     Server URL : http://127.0.0.1:8787
   ================================================================
   ```
   **Leave this window open** — it keeps the model in VRAM. Only run ONE backend
   (it refuses to start a second one on the same port).
3. **Install the add-on in Blender** (once per Blender version):
   Edit → Preferences → Add-ons → **Install from Disk…** → pick
   `blender_addon.zip` → tick **"SkinTokens Auto-Rig"**. Leave its preferences
   blank — it auto-detects the running backend.
4. **Rig:** select your mesh in the viewport (selection outline visible) →
   open the **SkinTokens** tab in the N-panel → click **Rig Selected Mesh**.

## 4. What success looks like

- **Backend window**: prints `... backend is ready` and stays open. During a
  rig it prints a progress bar and `200 POST /rig`.
- **Blender**: freezes ~40–60 s (the GPU is working), then a new **Armature**
  plus the skinned mesh appear in the scene. Status bar shows
  `Done. Imported N object(s), 1 armature(s).`
- Enter **Pose Mode** and rotate a bone — only the nearby geometry should
  deform. That means the skin weights are good.

## 5. Behaviour notes

- **Multiple selected objects are auto-joined.** If you select several parts
  (e.g. body + head + arms), the add-on joins a *throwaway duplicate* and rigs
  that, so the result is one skinned mesh + armature. **Your original objects
  are left untouched** in the scene.
- **Cleanup is automatic.** Blender's glTF importer creates a marker
  `Icosphere` inside a `glTF_not_exported` collection on every import; the
  add-on deletes that object and the collection for you.
- **Options** (N-panel): *Preserve texture/scale* (on by default), *Use existing
  skeleton*, *Voxel skin postprocess*, plus sampling params (top_k, top_p,
  temperature, repetition_penalty, num_beams).

## 6. Supported scope (what rigs well)

- ✅ Single characters with a clear skeleton — humanoids, animals, monsters,
  robots — best in a natural T/A-pose.
- ⚠️ Extreme proportions, many limbs/heads, non-natural poses, multiple glued
  characters, or broken meshes → lower quality.
- ❌ Buildings, furniture, plants, props, whole scenes → not meaningful.
- Input: `.obj` / `.fbx` / `.glb` (`.gltf`).

## 7. How to check the add-on version

- **In the file**: `blender_addon/__init__.py` → `bl_info["version"]`
  (currently **1.0.0**).
- **In Blender**: Preferences → Add-ons → expand "SkinTokens Auto-Rig".

## 8. Security

- The backend binds to **127.0.0.1 only** — nothing is exposed on the network.
  Do not set `SKINTOKENS_ADDON_HOST=0.0.0.0` or port-forward it.
- Requests are gated by a token auto-written to `~/.skintokens_addon.json`.
  Treat it (and `.addon_token`) as secret; never commit them.
- The add-on bypasses any system/corporate HTTP proxy for its local calls, so it
  works behind a proxy without exposing anything.

## 9. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Button greyed out | No mesh selected | Click a mesh so it shows a selection outline |
| `Cannot reach backend` | Backend not running / wrong URL | Start `run_addon_server.bat`; leave it open |
| `Backend error 503` (Squid HTML) | Proxy hijacked the request | Already fixed in this fork (proxy bypass) |
| `500 ... invalid load key '<'` | Proxy hijacked an internal call | Already fixed in this fork |
| `500 ConnectionReset (10054)` | bpy_server crashed (e.g. a bad model) and does not auto-restart | Close the backend window and re-run `run_addon_server.bat` |
| Duplicate/broken backend | Two backends started | Close all backend windows, start exactly one |

## 10. Design rationale (FAQ)

**Why a separate backend — why can't the add-on do everything itself?**
The model is a multi-GB PyTorch/CUDA model that needs a specific Python
environment (torch, transformers, the ~7.5 GB `.venv`) and an NVIDIA GPU.
Blender ships its *own* bundled Python with none of that, and bundling a full
CUDA ML stack into an add-on is impractical (size, per-version Python/ABI
matching, GPU/driver matching). Running the model in a resident backend process
also means it loads **once** and stays in VRAM, instead of reloading on every
rig and freezing Blender. The add-on is a thin HTTP client to that backend —
the standard pattern for heavy-ML Blender tools.

**Why can cloud tools (e.g. Tripo) ship a one-click add-on?**
Those add-ons are *also* thin clients — they send your mesh to the vendor's
**cloud GPUs** and download the result. The heavy compute still runs on a
server, just theirs instead of yours. Trade-off: no local GPU needed and easy
install, but your assets are uploaded, it costs credits, and it needs internet.
This tool keeps everything local (private, offline, free) at the cost of needing
your own GPU and a running backend. Many template-based riggers also make you
manually align a generic skeleton to your character; SkinTokens generates the
skeleton from the mesh directly, so there is no manual alignment step.

## 11. What this fork changed (vs. upstream)

- Added **Windows support** and the **flash-attn → PyTorch SDPA** fix for Ampere
  GPUs (so RTX 30-series can run inference).
- Added the **Blender add-on** + local **`addon_server.py`** backend.
- **Proxy-proofed** every local HTTP call (add-on → backend, and backend →
  `bpy_server`) so it works behind a corporate proxy (Squid etc.).
- **Auto-join** multiple selected objects (the texture-transfer step used to
  crash on multi-object inputs).
- **Auto-remove** the `Icosphere` marker and the `glTF_not_exported` collection
  after import.
- **Single-backend guard** to prevent broken duplicate backends.
