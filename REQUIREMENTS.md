# Blender Gem Designer — Requirements Document

## Overview

A free, open-source Blender add-on for designing faceted gemstones. Inspired by Gem Cut Studio (commercial) but with Blender's superior rendering (Cycles) and a more modern workflow.

**Core premise:** Gem Cut Studio has great facet-design UX but mediocre rendering. Blender has world-class rendering but no gem-design tools. Bridge the gap.

## Target Users

- **Primary:** The developer/author — a hobbyist-to-semi-pro gem faceter who cuts garnets, aquamarine, spinel, peridot, topaz, sphene, and zircon
- **Secondary:** Other faceters wanting a free alternative to GCS. Must be usable by people who are **not** skilled with computers — easy UI is vital.

## Facet Data Model

A facet diagram consists of **tiers** (groups of facets at the same height and angle). Each tier is defined by:

| Parameter | Description |
|-----------|-------------|
| **Height** | Distance of the facet's center from the girdle plane (mm). Negative = pavilion, positive = crown. |
| **Angle** | Pitch from horizontal. 90° = vertical (table), 0° = flat in the girdle plane. Pavilion angles are typically below the girdle plane but measured from horizontal. |
| **Index** | Rotation around the Z (main) axis, measured in teeth on the index gear. |
| **Index gear** | Number of teeth on the faceting machine's index wheel. Typically **96**. Sometimes 64, 72, 80, or 120. This defines the angular resolution. |
| **Rotational symmetry** | Number of evenly-spaced copies around the Z axis. Must divide evenly into the index gear. |
| **Mirror symmetry** | Pairs of facets mirrored across a radial line. Defined by the number of index teeth between left and right facet of each pair. A value of **1** means mirror symmetry is off (single facet per rotational position). |

### Mirror Symmetry Math

When mirror symmetry > 1 for a tier:

- The total "width" of a pair is `mirror_symmetry` index teeth
- The left facet's index offset from the pair center: `+(mirror_symmetry // 2) - 1` (rounded down)
- The right facet's index offset from the pair center: `-(mirror_symmetry // 2)`
- Each pair is centered at `index_gear / rotational_symmetry` teeth apart

**Example:** Index gear 96, rotational symmetry 6, mirror symmetry 4.
- Pair spacing: `96 / 6 = 16` teeth between pair centers
- Each pair spans 4 teeth total
- Left offset: `+(4 // 2) - 1 = +1`
- Right offset: `-(4 // 2) = -2`
- First pair at center index 0: teeth `1` (left) and `94` (right) — wrapping around modulo 96
- Second pair at center index 16: teeth `17` and `14`
- Full list: 2, 14, 18, 30, 34, 46, 50, 62, 66, 78, 82, 94 (12 facets total)

### Girdle Definition

- The girdle outline is **user-defined**, same as any other tier — explicitly specified by the user
- No automatic girdle generation; the user places girdle facets at height 0 with the desired outline
- This gives full control over shape: round-ish, oval, cushion, emerald, pear, marquise, or freeform
- Girdle tier typically has angle = 90° (vertical), but can vary for different girdle styles

## Must-Have Features (v1)

### 1. Facet Diagram Editor

- Define tiers of facets with height, angle, index, rotational symmetry, and mirror symmetry
- Changing any parameter updates the 3D view in **realtime** — no manual "refresh" step
- Index gear selection (dropdown: 96, 64, 72, 80, 120, or custom)
- Visual overlay in 3D viewport showing:
  - Facet index numbers
  - Angles for each tier
  - Tier outlines/groupings (toggleable)
- No cheater mechanism — it compensates for machine flaws, not an intentional design feature
- **Prefer Geometry Nodes** over pure Python bpy mesh construction where possible:
  - Geometry Nodes run heavily optimized C++ code
  - Enable non-linear/non-destructive workflow (change parameters, mesh updates)
  - Python for UI, data management, and bridging to geometry nodes

### 2. Meetpoint Auto-Lowering

- GCS feature: for a selected tier, auto-lower its height until facets meet the tier below it at a clean meetpoint
- Click repeatedly to step down through successive meetpoints
- Requires nearby tiers to already be defined for the meetpoint calculation to work

### 3. Material System

Two default materials shipped with the add-on:

**Realistic material:**
- Glass/Principled BSDF shader with accurate IOR per gem type
- Dispersion approximation
- For high-quality final renders

**Performance-analysis material:**
- Simplified/fast shader for quick renders
- Used by the automated performance analysis (windowing, brightness graphs)
- Optimized for speed over photorealism

Preset library with real optical data:

| Gem | RI | Dispersion |
|-----|-----|-----------|
| Garnet (Almandine) | 1.77–1.81 | 0.022–0.027 |
| Aquamarine | 1.57–1.58 | 0.014 |
| Spinel | 1.712–1.736 | 0.020 |
| Peridot | 1.65–1.69 | 0.020 |
| Topaz | 1.61–1.64 | 0.014 |
| Sphene (Titanite) | 1.89–2.02 | 0.051 |
| Zircon | 1.92–1.98 | 0.039 |
| Quartz | 1.54–1.55 | 0.013 |
| Sapphire/Ruby | 1.76–1.77 | 0.018 |
| Diamond | 2.417 | 0.044 |
| Cubic Zirconia | 2.15 | 0.060 |
| Moissanite | 2.65–2.69 | 0.104 |
| YAG | 1.83 | 0.028 |
| Glass | 1.50–1.52 | 0.008–0.009 |

### 4. Critical Angle & Windowing Analysis

- Calculate critical angle from RI: `θ_c = arcsin(1 / RI)`
- **Pavilion facets only** (crown facets aren't subject to windowing in the same way)
- Option to turn off the warning if a user intentionally designs below critical angle
- Color-code facets in the viewport overlay:
  - Green: safe (angle > θ_c + 1°)
  - Yellow: borderline (θ_c − 1° ≤ angle ≤ θ_c + 1°)
  - Red: below critical angle (windowing risk)
- Pavilion main angle calculator: `pav_angle = θ_c + safety_margin` (default 2°)

### 5. Crown/Pavilion Scaling & Performance Analysis

Inspired by GCS's scaling grid:

**Scaling grid:**
- Select a range of crown scales and pavilion scales
- Displays a 5×5 grid of results (5 crown steps × 5 pavilion steps)
- All 25 gems rotate simultaneously for visual comparison

**Performance graphs:**
- Horizontal axis: tilt X and tilt Y (centered at 0°, no tilt)
- Vertical axis: percentage of maximum brightness
- Four metrics plotted:
  - **Windowing** — light passes straight through without reflecting back (low is better)
  - **Head shadow** — light reflects too directly back and is blocked by viewer's head (low is better)
  - **ISO brightness** — overall brightness metric
  - **COS brightness** — cosine-weighted brightness (accounts for viewing angle falloff)
- **Dashed-line variants** of all four metrics when only looking through the table (not the crown)
- This lets the user optimize the design for maximum brilliance and minimal dead zones

### 6. Rendering Presets

- One-click Cycles render setup with:
  - Proper IOR glass shader with dispersion approximation
  - HDRI environment lighting
  - Turntable animation preset
  - Macro/inclusion inspection angles
- Real-time viewport preview: user can set viewport to rendered mode (Cycles or Eevee) — this is built into Blender, no special handling needed

### 7. Import/Export

- **Our own format** (JSON-based, `.gemdesign` or similar) — because our features won't perfectly match GemCAD or GCS
- Import/export **GemCAD** and **Gem Cut Studio** formats (stretch goal for import; spec needs documenting)
- STL / OBJ / glTF mesh export: these are built into Blender, no special handling needed
- When **importing** a mesh, stretch goal: automatic facet analysis to recover the facet diagram from a 3D model
- Export design as **PDF** with facet diagram layout (match the style of GemCAD and GCS printouts)
- Size ratio checks, easy way to scale crown or pavilion independently

### 8. UI/UX

- **Easy to use** — many faceters are not computer-savvy
- 3D viewport sidebar panel (consistent with Blender conventions)
- Clear, labeled controls with real-world gem-cutting terminology
- Visual feedback in viewport is immediate and obvious
- Material picker with gem-type dropdown
- Facet tier list with expand/collapse, drag to reorder

## Nice-to-Have (v2+)

- **Curved facets:** facets that curve along a stretch of indices by loosening the index gear resolution for that step. Allows smooth, organic shapes.
- **Fantasy cuts:** freeform designs, concave/convex curved facets, non-traditional layouts
- **Concave faceting:** negative-radius facets (requires different cutting tools — stretch goal)
- **Auto-analyze 3D model:** import any mesh and automatically detect facet groupings, symmetry, and angles
- **Light path visualization:** click gem from a camera angle, spawn ray-traced light paths with cone-arrow indicators in 3D view
- **Yield calculator:** compute rough stone volume needed from design dimensions using Blender's bmesh volume calculation API
- **Rough stone scanner:** photograph a rough stone and estimate usable volume/shape (never 100% accurate — can't detect subsurface flaws — but useful for planning)
- **CAM integration:** generate toolpaths for an automated faceting machine (stretch goal — building a good automated machine is a major engineering challenge)
- **Gem cutting sequence animation:** facet-by-facet reveal (low priority — user doesn't have a PC near the faceting machine)
- **Calibrated gem support:** visual girdle outline designer to precisely hit commercial standard dimensions

## Technical Architecture

### Implementation Approach

**Geometry Nodes are the primary mesh construction method:**
- Heavily optimized (largely C++), much faster than Python mesh building
- Non-destructive: change a parameter, mesh updates instantly
- Python handles: UI panels, data model, bridging parameters to geometry nodes, import/export, material setup

### Add-on Structure

```
blender_gem_designer/
├── __init__.py              # Add-on registration
├── operators/
│   ├── tier_ops.py          # Add/remove/edit facet tiers
│   ├── meetpoint_ops.py     # Auto-lower to meetpoint
│   ├── scaling_ops.py       # Crown/pavilion scaling + 5×5 grid
│   ├── analysis_ops.py      # Performance graph generation
│   └── render_setup.py      # Material + lighting presets
├── panels/
│   ├── gem_designer.py      # Main sidebar panel
│   ├── tier_list.py         # Facet tier list UI
│   ├── material_presets.py  # Gem material selector
│   ├── scaling_grid.py      # 5×5 scaling comparison UI
│   └── performance.py       # Performance graph panel
├── data/
│   ├── materials.py         # Gem optical data, RI tables
│   └── presets/             # Render + material presets
├── geometry_nodes/
│   ├── gem_from_tiers.blend # Main geometry node: tiers → mesh
│   └── facet_overlay.blend  # Index number / angle overlay
├── utils/
│   ├── symmetry.py          # Rotational + mirror symmetry math
│   ├── meetpoint.py         # Meetpoint intersection solver
│   ├── optics.py            # Critical angle, brightness metrics
│   └── format_io.py         # .gemdesign JSON format + GemCAD/GCS parsing
└── tests/
    ├── test_symmetry.py
    ├── test_meetpoint.py
    └── test_optics.py
```

### Key Dependencies

- **Blender 5.x** — target current stable, not 4.3+
- **blender-mcp addon** (ahujasid/blender-mcp) for Hermes integration during development
- **hermes-agent** with `blender-mcp` skill installed
- No external Python packages (uses bpy + stdlib only)
- Test dependencies: pytest (outside Blender, for math/optics unit tests)

### Hermes Integration (via blender-mcp)

- Hermes drives Blender during development: create test scenes, run bpy commands
- Batch rendering: generate multiple designs and render comparison
- Automated facet-analysis testing: set up a gem diagram → apply geometry nodes → run facet analysis → compare detected facets with originals
- AI-assisted facet generation is **low priority** — most LLMs are bad at geometry, and the user enjoys designing manually
- Automated visual testing via screenshots is **unreliable** — vision tools have limited context and miss geometric detail

## Development Phases

### Phase 0: Setup (Current)
- [x] Install hermes-agent blender-mcp skill
- [x] Download blender_mcp_addon.py to Desktop
- [x] Create project repo and REQUIREMENTS.md
- [x] Blender 5.1.2 installed via Steam
- [x] blender-mcp addon installed + server running on port 9876
- [ ] Verify socket connection from Hermes
- [ ] First Hermes → Blender command (e.g., create a sphere, take a screenshot)

### Phase 1: Core Geometry
- [ ] Facet data model: tier list with height/angle/index/symmetry, JSON-serializable
- [ ] Symmetry expansion: rotational + mirror → flat list of facet definitions
- [ ] Geometry node: tiers → 3D mesh (vertices at index positions, faces for each facet)
- [ ] Index gear selection and validation
- [ ] Real-time parameter → mesh update via geometry nodes
- [ ] Unit tests for symmetry math and tier expansion

### Phase 2: UI Foundation
- [ ] Sidebar panel with tier list (add, remove, edit, reorder)
- [ ] Per-tier controls: height, angle, index, rotational symmetry, mirror symmetry
- [ ] Index gear dropdown
- [ ] Realtime update: change any parameter → mesh updates in viewport
- [ ] Visual overlay: index numbers, angles, tier colors (toggleable)

### Phase 3: Materials & Rendering
- [ ] Gem material presets with accurate IOR
- [ ] Realistic Cycles shader
- [ ] Fast performance-analysis shader (simplified)
- [ ] One-click render setup (lighting, environment, turntable)
- [ ] Critical angle coloring overlay (pavilion only, toggleable) + warning toggle

### Phase 4: Analysis & Scaling
- [ ] Meetpoint auto-lowering per tier
- [ ] Crown/pavilion scaling grid (5×5 view)
- [ ] Performance graph: windowing, head shadow, ISO brightness, COS brightness
- [ ] Table-only dashed-line variants on graphs
- [ ] Volume calculator via bmesh

### Phase 5: I/O & Polish
- [ ] `.gemdesign` JSON format (our own)
- [ ] Export design as PDF (facet diagram layout)
- [ ] Import/export GemCAD (`.gem`) and GCS formats (depending on spec availability)
- [ ] Documentation and examples
- [ ] Release on GitHub / Blender Extensions

## References

- Gem Cut Studio: https://gemcutstudio.com/ (commercial reference product)
- GemCAD: http://gemcad.com/ (legacy facet design software)
- Blender Python API: https://docs.blender.org/api/current/
- Blender Geometry Nodes: https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/
- blender-mcp: https://github.com/ahujasid/blender-mcp
- Facet diagram reference (Gemology Project): https://www.gemologyproject.com/
- "Amateur Gemstone Faceting" by Tom Herbst (reference for angle math and meetpoint theory)
- Critical angle formula: `θ_c = arcsin(n_air / n_gem)`
- Pavilion main angle guideline: `pav_angle > θ_c + 2°` (typical safety margin)

## Design Decisions (Resolved)

1. **Facet data model:** ✅ Parametric — height, angle, index, with symmetry ops expanding to explicit facet list. User edits angles, not coordinates.
2. **Mesh construction:** ✅ Geometry Nodes primary, Python for UI and data management.
3. **Rendering:** ✅ Both — viewport can use Eevee or Cycles at user's choice (Blender built-in). One-click Cycles final-render setup included.
4. **UI placement:** ✅ 3D viewport sidebar panel (N-panel).
5. **Girdle:** ✅ User-defined, same as any other tier. No auto-generation.
6. **Cheater mechanism:** ✅ Excluded — not an intentional design feature.
7. **Target Blender version:** ✅ Blender 5.x (currently 5.1.2).
8. **Custom format:** ✅ `.gemdesign` JSON format. Import of GemCAD/GCS formats as stretch goal.
