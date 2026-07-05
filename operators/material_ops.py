"""Operators for applying gem material presets."""

import bpy
from ..data.materials import GEMS


class GEM_OT_apply_material(bpy.types.Operator):
    """Apply a gemstone material preset to the active gem"""
    bl_idname = "gem.apply_material"
    bl_label = "Apply Gem Material"
    bl_options = {'REGISTER', 'UNDO'}

    gem_type: bpy.props.EnumProperty(
        name="Gem Type",
        items=[(k, k, "") for k in GEMS.keys()],
    )

    def execute(self, context):
        obj = context.active_object
        if obj is None:
            self.report({'WARNING'}, "Select a gem object first")
            return {'CANCELLED'}

        gem_data = GEMS.get(self.gem_type)
        if gem_data is None:
            return {'CANCELLED'}

        # Create or get material
        mat_name = f"Gem_{self.gem_type}"
        mat = bpy.data.materials.get(mat_name)
        if mat is None:
            mat = bpy.data.materials.new(name=mat_name)

        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        bsdf = nodes.get("Principled BSDF")

        if bsdf:
            r, g, b = gem_data["color"]
            bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.0
            bsdf.inputs["IOR"].default_value = gem_data["ri"]
            bsdf.inputs["Transmission Weight"].default_value = 1.0

        # Assign to object
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)

        self.report({'INFO'}, f"Applied {self.gem_type} material (RI={gem_data['ri']})")
        return {'FINISHED'}
