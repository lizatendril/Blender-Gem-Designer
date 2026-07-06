"""N-panel UI — Crown and Pavilion sections with tier lists."""

import bpy


def _get_gem_object(context):
    obj = context.active_object
    if obj and obj.get("gem_designer"):
        return obj
    return None


def _draw_tier_list(layout, context, tiers, tier_indices, active_index):
    """Draw a single tier list section. tier_indices maps display order → flat index."""
    gem = _get_gem_object(context)
    if gem is None:
        return

    for display_i, flat_i in enumerate(tier_indices):
        tier = tiers[flat_i]
        is_active = (flat_i == active_index)

        box = layout.box()
        row = box.row()

        # Active toggle
        icon = 'RADIOBUT_ON' if is_active else 'RADIOBUT_OFF'
        op = row.operator("gem.set_active_tier", text="", icon=icon, emboss=False)
        op.tier_index = flat_i

        # Name
        row.prop(tier, "name", text="")

        # Move up/down within flat list
        sub = row.row(align=True)
        op = sub.operator("gem.move_tier_up", text="", icon='TRIA_UP')
        op.tier_index = flat_i
        op = sub.operator("gem.move_tier_down", text="", icon='TRIA_DOWN')
        op.tier_index = flat_i

        # Move to other side
        other = 'Pavilion' if tier.side == 'CROWN' else 'Crown'
        op = sub.operator("gem.move_tier_side", text="", icon='ARROW_LEFTRIGHT')
        op.tier_index = flat_i

        # Remove
        op = sub.operator("gem.remove_tier", text="", icon='X')
        op.tier_index = flat_i

        # Parameters for active tier
        if is_active:
            col = box.column(align=True)
            col.prop(tier, "base_index")
            col.prop(tier, "rotational_symmetry")
            col.prop(tier, "mirror_symmetry")
            col.prop(tier, "angle")
            col.prop(tier, "height")


class GEM_PT_main_panel(bpy.types.Panel):
    bl_label = "Gem Designer"
    bl_idname = "GEM_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Gem"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        all_tiers = context.scene.gem_tier_list

        if obj is None or not obj.get("gem_designer"):
            col = layout.column(align=True)
            col.operator("gem.setup_gem", text="Setup New Gem", icon='OUTLINER_OB_MESH')
            col.operator("gem.import_gcs", text="Import GCS Design", icon='IMPORT')
            return

        # Header
        row = layout.row()
        row.label(text=f"Gem: {obj.name}", icon='OUTLINER_OB_MESH')
        row.operator("gem.import_gcs", text="", icon='IMPORT')
        row.operator("gem.bake_tiers", text="", icon='RENDER_STILL')
        row.operator("gem.refresh_modifiers", text="", icon='FILE_REFRESH')

        # Index gear
        gear_row = layout.row(align=True)
        gear_row.label(text=f"Index Gear: {all_tiers.index_gear}")
        gear_row.operator("gem.set_index_gear", text="", icon='SETTINGS')

        # Split tiers into crown / pavilion
        crown_indices = [i for i, t in enumerate(all_tiers.tiers) if t.side == 'CROWN']
        pavilion_indices = [i for i, t in enumerate(all_tiers.tiers) if t.side == 'PAVILION']
        active = all_tiers.active_tier_index

        # -- Crown --
        layout.separator()
        row = layout.row()
        row.label(text=f"Crown / Table ({len(crown_indices)})", icon='TRIA_UP')
        op = row.operator("gem.add_tier", text="", icon='ADD')
        op.side = 'CROWN'

        if crown_indices:
            _draw_tier_list(layout, context, all_tiers.tiers, crown_indices, active)
        else:
            layout.label(text="  No crown tiers yet", icon='BLANK1')

        # -- Pavilion --
        layout.separator()
        row = layout.row()
        row.label(text=f"Pavilion / Culet ({len(pavilion_indices)})", icon='TRIA_DOWN')
        op = row.operator("gem.add_tier", text="", icon='ADD')
        op.side = 'PAVILION'

        if pavilion_indices:
            _draw_tier_list(layout, context, all_tiers.tiers, pavilion_indices, active)
        else:
            layout.label(text="  No pavilion tiers yet", icon='BLANK1')


class GEM_PT_material_panel(bpy.types.Panel):
    bl_label = "Material"
    bl_idname = "GEM_PT_material_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Gem"
    bl_parent_id = "GEM_PT_main_panel"

    def draw(self, context):
        layout = self.layout
        obj = _get_gem_object(context)
        if obj is None:
            return

        from ..data.materials import GEM_NAMES
        layout.label(text="Gem Material Preset")
        col = layout.column(align=True)
        for name, _ in GEM_NAMES:
            op = col.operator("gem.apply_material", text=name)
            op.gem_type = name
