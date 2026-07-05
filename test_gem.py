import bpy

# Clear default scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Clean up orphan data
for block in bpy.data.meshes:
    if block.users == 0:
        bpy.data.meshes.remove(block)

# Create a rough gem shape using joined cones
bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=1.5, depth=2.5, location=(0, 0, 0))
cone = bpy.context.active_object
cone.name = 'GemPavilion'

bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=1.5, depth=1.2, location=(0, 0, 1.45))
crown = bpy.context.active_object
crown.name = 'GemCrown'

# Join them into one object
bpy.ops.object.select_all(action='SELECT')
bpy.context.view_layer.objects.active = bpy.context.selected_objects[0]
bpy.ops.object.join()
gem = bpy.context.active_object
gem.name = 'TestGem'

# Subdivision for smoothness
mod = gem.modifiers.new(name='Subdivision', type='SUBSURF')
mod.levels = 1

# Glass material
mat = bpy.data.materials.new(name='GemGlass')
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get('Principled BSDF')
bsdf.inputs['Base Color'].default_value = (0.3, 0.7, 1.0, 1.0)
bsdf.inputs['Roughness'].default_value = 0.05
bsdf.inputs['Transmission Weight'].default_value = 0.95
bsdf.inputs['IOR'].default_value = 1.76
gem.data.materials.append(mat)

# Add camera and light (defaults were deleted)
bpy.ops.object.camera_add(location=(3.5, -3.5, 2.8))
cam = bpy.context.active_object
bpy.context.scene.camera = cam

bpy.ops.object.light_add(type='SUN', location=(5, -5, 8))
sun = bpy.context.active_object
sun.data.energy = 3

# Point camera at gem
direction = gem.location - cam.location
cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

print('Created TestGem with glass material, camera, and light')
