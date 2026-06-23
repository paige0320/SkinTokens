"""SkinTokens / TokenRig Blender add-on.

A thin client: it exports the selected mesh, sends it to a local SkinTokens
backend (addon_server.py) running on the GPU machine, and imports the rigged
result back into the scene.

The model itself never runs inside Blender -- Blender only talks HTTP to the
backend on 127.0.0.1, authenticated with a token. See WINDOWS_SETUP.md /
blender_addon/README.md for setup.
"""

import json
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import bpy

# The backend (addon_server.py) writes connection info here on startup, so the
# add-on can auto-detect the URL + token without any copy-paste.
ADDON_CONFIG_FILE = Path.home() / ".skintokens_addon.json"
from bpy.props import (
    BoolProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import AddonPreferences, Operator, Panel, PropertyGroup

bl_info = {
    "name": "SkinTokens Auto-Rig",
    "author": "SkinTokens (local fork)",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > SkinTokens",
    "description": "Auto-rig the selected mesh via a local SkinTokens backend",
    "category": "Rigging",
}


# --------------------------------------------------------------------------- #
# Preferences: where the backend is and the auth token.
# --------------------------------------------------------------------------- #
class SkinTokensPreferences(AddonPreferences):
    bl_idname = __name__

    server_url: StringProperty(
        name="Server URL",
        description="Address of the local SkinTokens backend (addon_server.py)",
        default="http://127.0.0.1:8787",
    )
    token: StringProperty(
        name="Auth Token",
        description="Token printed by addon_server.py on startup",
        default="",
        subtype="PASSWORD",
    )

    def draw(self, context):
        layout = self.layout
        cfg = _auto_config()
        if cfg.get("token"):
            layout.label(text="Backend detected automatically — nothing to fill in.", icon="CHECKMARK")
        else:
            layout.label(text="Start addon_server.py; it shares the token automatically.", icon="INFO")
        layout.prop(self, "server_url")
        layout.prop(self, "token")
        layout.label(text="Leave both blank to auto-detect a running backend.")


# --------------------------------------------------------------------------- #
# Per-scene generation parameters.
# --------------------------------------------------------------------------- #
class SkinTokensSettings(PropertyGroup):
    top_k: IntProperty(name="top_k", default=5, min=1, max=200)
    top_p: FloatProperty(name="top_p", default=0.95, min=0.1, max=1.0)
    temperature: FloatProperty(name="temperature", default=1.0, min=0.1, max=2.0)
    repetition_penalty: FloatProperty(
        name="repetition_penalty", default=2.0, min=0.5, max=3.0
    )
    num_beams: IntProperty(name="num_beams", default=10, min=1, max=20)
    use_skeleton: BoolProperty(
        name="Use existing skeleton",
        description="Only generate skin weights, keep the input skeleton",
        default=False,
    )
    use_transfer: BoolProperty(
        name="Preserve texture/scale",
        description="Transfer the original texture and scale onto the result",
        default=True,
    )
    use_postprocess: BoolProperty(
        name="Voxel skin postprocess",
        description="Apply voxel-based skin postprocessing",
        default=False,
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _prefs(context):
    return context.preferences.addons[__name__].preferences


def _auto_config() -> dict:
    """Read the URL + token the running backend wrote to the home dir."""
    try:
        if ADDON_CONFIG_FILE.exists():
            return json.loads(ADDON_CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {}


def _resolve_connection(prefs):
    """Use the add-on preferences if filled, else fall back to the backend's
    auto-written config. Returns (url, token)."""
    cfg = _auto_config()
    url = (prefs.server_url.strip() or cfg.get("url", "")).rstrip("/")
    token = prefs.token.strip() or cfg.get("token", "")
    return url, token


def _params_from_settings(s) -> dict:
    return {
        "top_k": s.top_k,
        "top_p": s.top_p,
        "temperature": s.temperature,
        "repetition_penalty": s.repetition_penalty,
        "num_beams": s.num_beams,
        "use_skeleton": s.use_skeleton,
        "use_transfer": s.use_transfer,
        "use_postprocess": s.use_postprocess,
    }


def _remove_gltf_not_exported():
    """Blender's glTF importer dumps non-exported helper nodes (a marker
    'Icosphere', etc.) into a 'glTF_not_exported' collection. Remove that whole
    collection and everything inside it, plus any legacy stray empty by name."""
    for coll in list(bpy.data.collections):
        if coll.name.startswith("glTF_not_exported"):
            for obj in list(coll.objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.collections.remove(coll)
    # Older Blender added it as a plain empty object instead of a collection.
    for obj in list(bpy.data.objects):
        if obj.name.startswith("glTF_not_exported"):
            bpy.data.objects.remove(obj, do_unlink=True)


# --------------------------------------------------------------------------- #
# Operator
# --------------------------------------------------------------------------- #
class SKINTOKENS_OT_rig(Operator):
    bl_idname = "skintokens.rig_selected"
    bl_label = "Rig Selected Mesh"
    bl_description = "Send the selected mesh to the SkinTokens backend and import the rigged result"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(o.type == "MESH" for o in context.selected_objects)

    def _export_for_rig(self, context, mesh_objs, filepath):
        """Export the selected mesh(es) to GLB for rigging.

        A single mesh is exported directly. Multiple meshes are JOINED into one
        first (on a throwaway duplicate, so the user's scene is untouched): the
        backend's texture-transfer step crashes on multi-object inputs, and a
        single combined mesh is what the rig is generated for anyway.
        """
        if len(mesh_objs) <= 1:
            bpy.ops.export_scene.gltf(
                filepath=filepath, use_selection=True, export_format="GLB"
            )
            return

        # Remember the original selection/active so we can restore it.
        prev_selected = list(context.selected_objects)
        prev_active = context.view_layer.objects.active

        bpy.ops.object.select_all(action="DESELECT")
        for o in mesh_objs:
            o.select_set(True)
        context.view_layer.objects.active = mesh_objs[0]
        bpy.ops.object.duplicate()          # duplicates become the new selection
        bpy.ops.object.join()               # join copies into the active duplicate
        joined = context.view_layer.objects.active
        try:
            bpy.ops.object.select_all(action="DESELECT")
            joined.select_set(True)
            context.view_layer.objects.active = joined
            bpy.ops.export_scene.gltf(
                filepath=filepath, use_selection=True, export_format="GLB"
            )
        finally:
            bpy.ops.object.select_all(action="DESELECT")
            joined.select_set(True)
            context.view_layer.objects.active = joined
            bpy.ops.object.delete()
            # Restore the user's original selection.
            for o in prev_selected:
                try:
                    o.select_set(True)
                except ReferenceError:
                    pass
            if prev_active is not None:
                try:
                    context.view_layer.objects.active = prev_active
                except ReferenceError:
                    pass

    def execute(self, context):
        prefs = _prefs(context)
        settings = context.scene.skintokens
        url, token = _resolve_connection(prefs)

        if not url:
            self.report({"ERROR"}, "No server URL. Start addon_server.py, or set it in preferences.")
            return {"CANCELLED"}
        if not token:
            self.report(
                {"ERROR"},
                "No auth token found. Start addon_server.py (it auto-shares the token), "
                "or paste one in the add-on preferences.",
            )
            return {"CANCELLED"}

        mesh_objs = [o for o in context.selected_objects if o.type == "MESH"]
        if not mesh_objs:
            self.report({"ERROR"}, "Select at least one mesh object.")
            return {"CANCELLED"}

        tmp_dir = tempfile.mkdtemp(prefix="skintokens_blender_")
        in_path = os.path.join(tmp_dir, "input.glb")
        out_path = os.path.join(tmp_dir, "rigged.glb")

        # Export the selection as GLB (joining multiple objects -- see helper).
        try:
            self._export_for_rig(context, mesh_objs, in_path)
        except Exception as e:  # noqa: BLE001
            self.report({"ERROR"}, f"GLB export failed: {e}")
            return {"CANCELLED"}

        with open(in_path, "rb") as f:
            payload = f.read()

        # POST to the backend. Inference can take a while -> generous timeout.
        req = urllib.request.Request(
            f"{url}/rig",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/octet-stream",
                "X-Auth-Token": token,
                "X-Params": json.dumps(_params_from_settings(settings)),
                "X-Filename-Ext": ".glb",
            },
        )
        self.report({"INFO"}, "Rigging... Blender will be unresponsive until it finishes.")
        # The backend is local/LAN, so bypass any system HTTP proxy -- otherwise a
        # corporate proxy (e.g. Squid) hijacks the 127.0.0.1 request and returns 503.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=900) as resp:
                result = resp.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            self.report({"ERROR"}, f"Backend error {e.code}: {detail[:300]}")
            return {"CANCELLED"}
        except urllib.error.URLError as e:
            self.report(
                {"ERROR"},
                f"Cannot reach backend at {url}. Is addon_server.py running? ({e.reason})",
            )
            return {"CANCELLED"}

        with open(out_path, "wb") as f:
            f.write(result)

        before = set(bpy.data.objects)
        try:
            bpy.ops.import_scene.gltf(filepath=out_path)
        except Exception as e:  # noqa: BLE001
            self.report({"ERROR"}, f"Import of rigged result failed: {e}")
            return {"CANCELLED"}

        _remove_gltf_not_exported()

        imported = [o for o in bpy.data.objects if o not in before]
        n_arm = sum(1 for o in imported if o.type == "ARMATURE")
        self.report(
            {"INFO"},
            f"Done. Imported {len(imported)} object(s), {n_arm} armature(s).",
        )
        return {"FINISHED"}


# --------------------------------------------------------------------------- #
# Panel
# --------------------------------------------------------------------------- #
class SKINTOKENS_PT_panel(Panel):
    bl_label = "SkinTokens Auto-Rig"
    bl_idname = "SKINTOKENS_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SkinTokens"

    def draw(self, context):
        layout = self.layout
        s = context.scene.skintokens

        col = layout.column(align=True)
        col.prop(s, "use_transfer")
        col.prop(s, "use_skeleton")
        col.prop(s, "use_postprocess")

        box = layout.box()
        box.label(text="Sampling")
        box.prop(s, "top_k")
        box.prop(s, "top_p")
        box.prop(s, "temperature")
        box.prop(s, "repetition_penalty")
        box.prop(s, "num_beams")

        layout.separator()
        layout.operator(SKINTOKENS_OT_rig.bl_idname, icon="ARMATURE_DATA")


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #
_classes = (
    SkinTokensPreferences,
    SkinTokensSettings,
    SKINTOKENS_OT_rig,
    SKINTOKENS_PT_panel,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.skintokens = bpy.props.PointerProperty(type=SkinTokensSettings)


def unregister():
    del bpy.types.Scene.skintokens
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
