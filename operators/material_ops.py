"""Operators for applying gem material presets using the Gem (Birefringent) shader."""

from __future__ import annotations

import bpy
from bpy.types import Context

from ..data.materials import GEMS
from ..utils.node_utils import create_gem_material


class GEM_OT_apply_material(bpy.types.Operator):
    """Apply a realistic gemstone material preset to the active gem"""
    bl_idname = "gem.apply_material"
    bl_label = "Apply Gem Material"
    bl_options = {'REGISTER', 'UNDO'}

    gem_type: bpy.props.EnumProperty(  # type: ignore[valid-type]
        name="Gem Type",
        items=[(k, k, "") for k in GEMS.keys()],
    )

    def execute(self, context: Context) -> set[str]:
        obj = context.active_object
        if obj is None:
            self.report({'WARNING'}, "Select a gem object first")
            return {'CANCELLED'}

        gem_data = GEMS.get(self.gem_type)
        if gem_data is None:
            return {'CANCELLED'}

        try:
            mat = create_gem_material(
                gem_name=self.gem_type,
                main_ior=gem_data["main_ior"],
                birefringence_ior=gem_data["birefringence_ior"],
                dispersion=gem_data["dispersion"],
                color=gem_data["color"],
                color_density=gem_data.get("color_density", 5.0),
                has_birefringence=gem_data.get("has_birefringence", "No birefringence"),
            )
        except Exception as e:
            self.report({'ERROR'}, f"Failed to create material: {e}")
            return {'CANCELLED'}

        # Assign to object
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)

        self.report({'INFO'}, f"Applied {self.gem_type} (RI={gem_data['main_ior']:.3f})")
        return {'FINISHED'}
