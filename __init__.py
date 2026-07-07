"""
Blender Gem Designer — Open-source gemstone facet design add-on for Blender.

Lets faceters define gem designs as a stack of facet tiers with rotational
and mirror symmetry, using Geometry Nodes for fast real-time preview.
"""

from __future__ import annotations

from typing import Any

import bpy

bl_info: dict[str, Any] = {
    "name": "Gem Designer",
    "author": "Dekker + Hermes",
    "version": (0, 1, 1),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > Gem",
    "description": "Design faceted gemstones with parametric facet tiers",
    "category": "3D View",
}


_classes: list[type] = []


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def register() -> None:
    global _classes

    from .utils.properties import GemTierProperty, GemTierList, push_and_sync, maybe_pull_on_active_change
    from .utils import properties as props_mod
    from .operators.gem_setup import GEM_OT_setup_gem, GEM_OT_refresh_modifiers, GEM_OT_set_index_gear
    from .operators.tier_ops import (
        GEM_OT_add_tier, GEM_OT_remove_tier,
        GEM_OT_move_tier_up, GEM_OT_move_tier_down,
        GEM_OT_set_active_tier, GEM_OT_toggle_tier,
        GEM_OT_move_tier_side, GEM_OT_bake_tiers,
    )
    from .operators.material_ops import GEM_OT_apply_material
    from .operators.gcs_import import GEM_OT_import_gcs
    from .operators.gemcad_import import GEM_OT_import_asc, GEM_OT_import_gem
    from .panels.tier_panel import GEM_PT_main_panel, GEM_PT_material_panel

    _classes = [
        GemTierProperty,
        GemTierList,
        GEM_OT_setup_gem,
        GEM_OT_refresh_modifiers,
        GEM_OT_set_index_gear,
        GEM_OT_add_tier,
        GEM_OT_remove_tier,
        GEM_OT_move_tier_up,
        GEM_OT_move_tier_down,
        GEM_OT_set_active_tier,
        GEM_OT_toggle_tier,
        GEM_OT_move_tier_side,
        GEM_OT_bake_tiers,
        GEM_OT_apply_material,
        GEM_OT_import_gcs,
        GEM_OT_import_asc,
        GEM_OT_import_gem,
        GEM_PT_main_panel,
        GEM_PT_material_panel,
    ]

    for cls in _classes:
        bpy.utils.register_class(cls)

    # Register any module-level hooks (menus, handlers, etc.)
    from .operators import gcs_import, gemcad_import
    gcs_import.register()
    gemcad_import.register()

    bpy.types.Scene.gem_tier_list = bpy.props.PointerProperty(type=GemTierList)

    # Wire the update callback so property changes auto-sync to modifiers
    props_mod._sync_callback = push_and_sync

    # Only pull from object JSON when the active object actually changes
    bpy.app.handlers.depsgraph_update_post.append(maybe_pull_on_active_change)


def unregister() -> None:
    global _classes

    from .utils import properties as props_mod
    from .utils.properties import maybe_pull_on_active_change

    if maybe_pull_on_active_change in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(maybe_pull_on_active_change)

    props_mod._sync_callback = None

    if hasattr(bpy.types.Scene, "gem_tier_list"):
        del bpy.types.Scene.gem_tier_list

    # Unregister module-level hooks
    from .operators import gcs_import, gemcad_import
    gcs_import.unregister()
    gemcad_import.unregister()

    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
    _classes = []
