# Development Notes — Blender MCP on Windows

Hard-won knowledge from getting Hermes → Blender working. Update as new issues surface.

## Environment

- **Blender:** 5.1.2 (Steam install: `C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe`)
- **MCP addon:** [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp), downloaded to Desktop
- **Skill:** `hermes skills install official/creative/blender-mcp`
- **Port:** 9876 (default)
- **OS:** Windows 10, bash via git-bash/MSYS

## Path Handling

| What | Works? | Notes |
|------|--------|-------|
| `C:/Users/...` | ✅ | Use forward-slash Windows paths |
| `/c/Users/...` (MSYS) | ❌ | Blender is native Windows, treats leading `/` as drive root → becomes `C:\c\Users\...` |
| `~/Desktop/...` | ❌ | Same issue, Blender doesn't expand `~` |

**Rule:** Always pass `C:/Users/dekke/...` style paths in MCP `filepath` params.

## MCP Commands — What Works

### ✅ Reliable

| Command | Notes |
|---------|-------|
| `get_scene_info` | Lists all objects with name, type, location |
| `execute_code` | Runs arbitrary bpy code. Multi-line works. |
| `get_viewport_screenshot` | Needs `filepath` + optional `max_size`. Captures current viewport (not camera). |

### ✅ bpy Operations (inside execute_code)

| Category | Notes |
|----------|-------|
| `bpy.ops.mesh.primitive_*_add()` | All primitives work |
| `bpy.ops.object.select_all()`, `delete()`, `join()` | Object ops work |
| `bpy.data.materials.new()`, `node_tree.nodes` | Material creation + shader editing |
| `bpy.context.active_object`, `bpy.context.scene` | Context access works |
| `obj.modifiers.new()` | Modifiers work |
| `obj.hide_viewport = True` | Hide helpers from viewport — **do this before screenshots** |

### ❌ Broken (exec sandbox context issues)

`execute_code` runs inside `exec(code, {"bpy": bpy})` — no proper 3D view region context.

| What fails | Error | Workaround |
|------------|-------|------------|
| `bpy.ops.view3d.view_all()` | `1-2 args execution context is supported` | Use `region_3d` directly |
| `bpy.ops.view3d.view_camera()` | poll() failed, context incorrect | Use `region_3d` directly |
| `bpy.ops.view3d.view_selected()` | Expected a view3d region | Use `region_3d` directly |

### ✅ Viewport Control (workaround)

Instead of operators, manipulate `space.region_3d` directly:

```python
import bpy
from mathutils import Vector

for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        space = area.spaces.active
        r3d = space.region_3d

        # Set shading mode
        space.shading.type = 'MATERIAL'  # or 'SOLID', 'WIREFRAME', 'RENDERED'

        # Point view at target
        target = Vector((0, 0, 0.5))    # what to look at
        loc = Vector((3.5, -3.5, 3.0))  # camera position
        r3d.view_location = target
        direction = target - loc
        r3d.view_rotation = direction.to_track_quat('-Z', 'Y')
        r3d.view_distance = direction.length
        break
```

### Protocol

Plain JSON over TCP, no length prefix:

```
Send:     {"type": "<command>", "params": {<kwargs>}}
Receive:  {"status": "success", "result": <value>}
          {"status": "error",   "message": "<reason>"}
```

Can hit it from Python, `nc`, whatever:

```bash
# Quick test
python -c "import socket,json; s=socket.create_connection(('localhost',9876),timeout=3); s.close(); print('OPEN')"

# One-liner execute
python -c "import socket,json; s=socket.create_connection(('localhost',9876)); s.sendall(json.dumps({'type':'execute_code','params':{'code':'import bpy; print(len(bpy.data.objects))'}}).encode()); print(s.recv(4096).decode())"
```

## Screenshot Checklist

Before taking a viewport screenshot for visual verification:

1. ✅ Hide camera/light helpers: `obj.hide_viewport = True`
2. ✅ Set viewport angle via `region_3d` (see above)
3. ✅ Set shading: `space.shading.type = 'MATERIAL'` (or `'RENDERED'` for Cycles)
4. ✅ Use Windows path: `C:/Users/dekke/workspace/.../filename.png`
5. ❌ Don't use `/c/Users/...` paths
6. ❌ Don't rely on `view3d.*` operators

## Test Script Conventions

Test scripts for `execute_code` should be self-contained:
- Create their own camera and light (defaults get deleted with scene clear)
- Hide helpers after setup (`obj.hide_viewport = True`)
- Use `print()` for status — output is captured and returned
- Avoid `view3d.*` operators entirely
- Avoid `bpy.ops.view3d.*` — use `region_3d` instead
