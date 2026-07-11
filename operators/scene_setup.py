"""Operators for one-click scene setup: render settings, camera, world."""

from __future__ import annotations

import bpy
from bpy.types import Context, Area, Region


# ============================================================================
# 1. Preview Render Settings
# ============================================================================

class GEM_OT_render_preview(bpy.types.Operator):
    """Set render settings for high-quality preview:
    noise threshold 0.01, max samples 1024, denoise enabled"""
    bl_idname = "gem.render_preview"
    bl_label = "Preview Render Settings"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context) -> set[str]:
        scene = context.scene
        cycles = scene.cycles

        cycles.preview_adaptive_threshold = 0.01
        cycles.preview_samples = 1024
        cycles.use_preview_denoising = True

        self.report(
            {'INFO'},
            "Preview render: noise=0.01, samples=1024, denoise=ON",
        )
        return {'FINISHED'}


# ============================================================================
# 2. Full Global Illumination Light Paths
# ============================================================================

class GEM_OT_render_full_gi(bpy.types.Operator):
    """Set light path max bounces to the Full Global Illumination preset"""
    bl_idname = "gem.render_full_gi"
    bl_label = "Full GI Light Paths"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context) -> set[str]:
        cycles = context.scene.cycles

        # Full Global Illumination preset values
        cycles.max_bounces = 128
        cycles.diffuse_bounces = 24
        cycles.glossy_bounces = 24
        cycles.transmission_bounces = 24
        cycles.volume_bounces = 24
        cycles.transparent_max_bounces = 24

        self.report(
            {'INFO'},
            "Light paths: Full GI (total=128, diffuse/glossy/transmission=24)",
        )
        return {'FINISHED'}


# ============================================================================
# 3. Camera Setup (largest 3D viewport → camera, DoF, focus on gem)
# ============================================================================

def _find_largest_3d_view(context: Context) -> tuple[Area | None, Region | None]:
    """Find the 3D view area + region with the largest pixel area."""
    best_area: Area | None = None
    best_region: Region | None = None
    best_size = 0

    for area in context.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        for region in area.regions:
            if region.type != 'WINDOW':
                continue
            size = region.width * region.height
            if size > best_size:
                best_size = size
                best_area = area
                best_region = region

    return best_area, best_region


def _ensure_camera(context: Context) -> bpy.types.Object:
    """Return the active scene camera, creating one if needed."""
    scene = context.scene
    cam = scene.camera
    if cam is None:
        bpy.ops.object.camera_add(location=(0, -5, 0))
        cam = context.active_object
        scene.camera = cam
    return cam


class GEM_OT_camera_setup(bpy.types.Operator):
    """Move camera to the largest 3D viewport, enable DoF, focus on gem"""
    bl_idname = "gem.camera_setup"
    bl_label = "Camera from View + DoF"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: Context) -> bool:
        obj = context.active_object
        return obj is not None and obj.get("gem_designer")  # type: ignore[return-value]

    def execute(self, context: Context) -> set[str]:
        gem = context.active_object

        area, region = _find_largest_3d_view(context)
        if area is None:
            self.report({'ERROR'}, "No 3D viewport found")
            return {'CANCELLED'}

        cam = _ensure_camera(context)

        # Move camera to match the largest 3D viewport
        override = {'area': area, 'region': region}
        with context.temp_override(**override):
            bpy.ops.view3d.camera_to_view()

        # Depth of field
        cam_data: bpy.types.Camera = cam.data  # type: ignore[assignment]
        cam_data.dof.use_dof = True
        cam_data.dof.focus_object = gem
        cam_data.dof.aperture_fstop = 0.5
        cam_data.dof.aperture_blades = 6

        self.report(
            {'INFO'},
            f"Camera set from view, DoF on '{gem.name}', f/0.5",
        )
        return {'FINISHED'}


# ============================================================================
# 4. World Background
# ============================================================================

class GEM_OT_world_background(bpy.types.Operator):
    """Import the world shader from gem_tier_cutter.blend
    (black for camera rays, HDRI for everything else)"""
    bl_idname = "gem.world_background"
    bl_label = "Studio World Background"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context) -> set[str]:
        from ..utils.node_utils import load_world_asset

        try:
            world = load_world_asset()
            self.report(
                {'INFO'},
                f"World '{world.name}' loaded (camera=black, other=HDRI)",
            )
        except Exception as e:
            self.report({'ERROR'}, f"Failed to load world: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}
