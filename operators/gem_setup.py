"""Operators for initializing a new gem design and global settings."""

from __future__ import annotations

from typing import Any, Optional

import bpy
from bpy.types import Context

from ..utils.node_utils import load_node_group, sync_modifiers
from ..utils.properties import (
    GemTierList,
    scene_tiers_from_object,
    scene_tiers_to_object,
)
from ..utils.tier_data import get_tiers, add_tier, DEFAULT_TIER


class GEM_OT_setup_gem(bpy.types.Operator):
    """Create a new gem design: adds a cube with the tier-cutter node group"""
    bl_idname = "gem.setup_gem"
    bl_label = "Setup New Gem"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context) -> set[str]:
        ng = load_node_group()

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0))
        obj: bpy.types.Object = context.active_object
        obj.name = "Gem"
        obj["gem_designer"] = True

        # Default tier with index 0 (any position works, it's symmetrical)
        tier = dict(DEFAULT_TIER)
        add_tier(obj, tier)

        tiers = get_tiers(obj)
        gear: int = obj.get("gem_index_gear", 96)
        sync_modifiers(obj, tiers, gear, active_tier_idx=0)

        tier_list: GemTierList = context.scene.gem_tier_list
        scene_tiers_from_object(obj, tier_list)
        tier_list.active_tier_index = 0
        tier_list.index_gear = gear

        obj.select_set(True)
        context.view_layer.objects.active = obj

        self.report({'INFO'}, f"Created gem '{obj.name}' with {gear}-tooth gear")
        return {'FINISHED'}


class GEM_OT_refresh_modifiers(bpy.types.Operator):
    """Rebuild the modifier stack from the tier list"""
    bl_idname = "gem.refresh_modifiers"
    bl_label = "Refresh Modifiers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context) -> set[str]:
        obj = context.active_object
        if obj is None or not obj.get("gem_designer"):
            self.report({'WARNING'}, "Select a gem object first")
            return {'CANCELLED'}

        tier_list: GemTierList = context.scene.gem_tier_list
        scene_tiers_to_object(obj, tier_list)

        tiers = get_tiers(obj)
        gear: int = tier_list.index_gear
        sync_modifiers(obj, tiers, gear, active_tier_idx=tier_list.active_tier_index)

        n_enabled = len([t for t in tiers if t.get("enabled", True)])
        self.report({'INFO'}, f"Synced {n_enabled} tier(s)")
        return {'FINISHED'}


class GEM_OT_set_index_gear(bpy.types.Operator):
    """Change the index gear size — affects all tier index calculations"""
    bl_idname = "gem.set_index_gear"
    bl_label = "Change Index Gear"
    bl_options = {'REGISTER', 'UNDO'}

    new_gear: bpy.props.IntProperty(  # type: ignore[valid-type]
        name="New Gear Size",
        description="Number of teeth on the index wheel",
        default=96, min=12, max=120,
    )

    @classmethod
    def poll(cls, context: Context) -> bool:
        obj = context.active_object
        return obj is not None and obj.get("gem_designer")

    def invoke(self, context: Context, event: Any) -> set[str]:
        tier_list: GemTierList = context.scene.gem_tier_list
        self.new_gear = tier_list.index_gear
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context: Context) -> None:
        layout = self.layout
        layout.label(text="Changing the index gear recalculates all tier positions.", icon='INFO')
        layout.label(text="Index values will keep their current tooth number.")
        layout.label(text="The angular position of each facet will change.")
        layout.separator()
        layout.prop(self, "new_gear")

    def execute(self, context: Context) -> set[str]:
        obj = context.active_object
        if obj is None:
            return {'CANCELLED'}

        tier_list: GemTierList = context.scene.gem_tier_list
        old_gear: int = tier_list.index_gear
        tier_list.index_gear = self.new_gear
        obj["gem_index_gear"] = self.new_gear

        # Clamp existing tier values to new gear range
        for tier in tier_list.tiers:
            tier.base_index = max(0, min(tier.base_index, self.new_gear - 1))
            tier.mirror_symmetry = max(0, min(tier.mirror_symmetry, self.new_gear // 2))

        # Sync
        scene_tiers_to_object(obj, tier_list)
        tiers = get_tiers(obj)
        sync_modifiers(obj, tiers, self.new_gear, active_tier_idx=tier_list.active_tier_index)

        self.report({'INFO'}, f"Index gear changed: {old_gear} → {self.new_gear}")
        return {'FINISHED'}
