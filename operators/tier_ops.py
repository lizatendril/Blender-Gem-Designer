"""Operators for managing gem tiers — uses scene property groups."""

import bpy
from ..utils.properties import (
    GemTierList, GemTierProperty,
    scene_tiers_from_object, scene_tiers_to_object,
)
from ..utils.node_utils import sync_modifiers
from ..utils.tier_data import get_tiers, set_tiers


def _get_scene_tiers(context) -> GemTierList:
    return context.scene.gem_tier_list


def _get_gem_object(context):
    obj = context.active_object
    if obj and obj.get("gem_designer"):
        return obj
    return None


def _save_and_sync(obj, tiers: GemTierList):
    scene_tiers_to_object(obj, tiers)
    raw = get_tiers(obj)
    gear = tiers.index_gear
    active_idx = tiers.active_tier_index
    sync_modifiers(obj, raw, gear, active_tier_idx=active_idx)


# ---------------------------------------------------------------------------
class GEM_OT_add_tier(bpy.types.Operator):
    bl_idname = "gem.add_tier"
    bl_label = "Add Tier"
    bl_options = {'REGISTER', 'UNDO'}

    side: bpy.props.EnumProperty(
        name="Side",
        items=[('CROWN', 'Crown', ''), ('PAVILION', 'Pavilion', '')],
        default='CROWN',
    )

    def execute(self, context):
        obj = _get_gem_object(context)
        if obj is None:
            self.report({'WARNING'}, "Select a gem object first")
            return {'CANCELLED'}

        tiers = _get_scene_tiers(context)
        item = tiers.tiers.add()
        item.name = f"Tier {len(tiers.tiers)}"
        item.side = self.side

        tiers.active_tier_index = len(tiers.tiers) - 1
        _save_and_sync(obj, tiers)
        self.report({'INFO'}, f"Added '{item.name}' ({self.side})")
        return {'FINISHED'}


class GEM_OT_remove_tier(bpy.types.Operator):
    bl_idname = "gem.remove_tier"
    bl_label = "Remove Tier"
    bl_options = {'REGISTER', 'UNDO'}

    tier_index: bpy.props.IntProperty(name="Tier Index")

    def execute(self, context):
        obj = _get_gem_object(context)
        if obj is None:
            return {'CANCELLED'}

        tiers = _get_scene_tiers(context)
        if 0 <= self.tier_index < len(tiers.tiers):
            name = tiers.tiers[self.tier_index].name
            tiers.tiers.remove(self.tier_index)
            if tiers.active_tier_index >= len(tiers.tiers):
                tiers.active_tier_index = len(tiers.tiers) - 1
            _save_and_sync(obj, tiers)
            self.report({'INFO'}, f"Removed '{name}'")
        return {'FINISHED'}


class GEM_OT_move_tier_up(bpy.types.Operator):
    bl_idname = "gem.move_tier_up"
    bl_label = "Move Up"
    bl_options = {'REGISTER', 'UNDO'}

    tier_index: bpy.props.IntProperty()

    def execute(self, context):
        obj = _get_gem_object(context)
        if obj is None or self.tier_index <= 0:
            return {'CANCELLED'}

        tiers = _get_scene_tiers(context)
        tiers.tiers.move(self.tier_index, self.tier_index - 1)
        if tiers.active_tier_index == self.tier_index:
            tiers.active_tier_index -= 1
        elif tiers.active_tier_index == self.tier_index - 1:
            tiers.active_tier_index += 1
        _save_and_sync(obj, tiers)
        return {'FINISHED'}


class GEM_OT_move_tier_down(bpy.types.Operator):
    bl_idname = "gem.move_tier_down"
    bl_label = "Move Down"
    bl_options = {'REGISTER', 'UNDO'}

    tier_index: bpy.props.IntProperty()

    def execute(self, context):
        obj = _get_gem_object(context)
        tiers = _get_scene_tiers(context)
        if obj is None or self.tier_index >= len(tiers.tiers) - 1:
            return {'CANCELLED'}

        tiers.tiers.move(self.tier_index, self.tier_index + 1)
        if tiers.active_tier_index == self.tier_index:
            tiers.active_tier_index += 1
        elif tiers.active_tier_index == self.tier_index + 1:
            tiers.active_tier_index -= 1
        _save_and_sync(obj, tiers)
        return {'FINISHED'}


class GEM_OT_set_active_tier(bpy.types.Operator):
    bl_idname = "gem.set_active_tier"
    bl_label = "Edit Tier"
    bl_options = {'REGISTER', 'UNDO'}

    tier_index: bpy.props.IntProperty()

    def execute(self, context):
        obj = _get_gem_object(context)
        if obj is None:
            return {'CANCELLED'}

        tiers = _get_scene_tiers(context)
        tiers.active_tier_index = self.tier_index
        _save_and_sync(obj, tiers)

        # Bake all tiers except the selected one (keeps it live for editing)
        from ..utils.node_utils import bake_all_except
        bake_all_except(obj, self.tier_index)

        return {'FINISHED'}


class GEM_OT_toggle_tier(bpy.types.Operator):
    bl_idname = "gem.toggle_tier"
    bl_label = "Toggle Tier"
    bl_options = {'REGISTER', 'UNDO'}

    tier_index: bpy.props.IntProperty()

    def execute(self, context):
        obj = _get_gem_object(context)
        if obj is None:
            return {'CANCELLED'}

        tiers = _get_scene_tiers(context)
        if 0 <= self.tier_index < len(tiers.tiers):
            tiers.tiers[self.tier_index].enabled = not tiers.tiers[self.tier_index].enabled
        _save_and_sync(obj, tiers)
        return {'FINISHED'}


class GEM_OT_move_tier_side(bpy.types.Operator):
    """Move tier to the opposite side (crown ↔ pavilion)"""
    bl_idname = "gem.move_tier_side"
    bl_label = "Move to Other Side"
    bl_options = {'REGISTER', 'UNDO'}

    tier_index: bpy.props.IntProperty()

    def execute(self, context):
        obj = _get_gem_object(context)
        if obj is None:
            return {'CANCELLED'}

        tiers = _get_scene_tiers(context)
        if 0 <= self.tier_index < len(tiers.tiers):
            tier = tiers.tiers[self.tier_index]
            old_side = tier.side
            tier.side = 'PAVILION' if old_side == 'CROWN' else 'CROWN'
            target = 'Pavilion' if old_side == 'CROWN' else 'Crown'
            self.report({'INFO'}, f"Moved '{tier.name}' to {target}")
        _save_and_sync(obj, tiers)
        return {'FINISHED'}


class GEM_OT_bake_tiers(bpy.types.Operator):
    """Bake cached geometry for all tier modifiers (speeds up recomputation)"""
    bl_idname = "gem.bake_tiers"
    bl_label = "Bake All Tiers"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.get("gem_designer")

    def execute(self, context):
        obj = context.active_object
        from ..utils.node_utils import bake_all_tiers
        baked = bake_all_tiers(obj)
        if baked:
            self.report({'INFO'}, f"Baked {baked} tier(s)")
        else:
            self.report({'WARNING'}, "No Bake nodes found in tier modifiers")
        return {'FINISHED'}
