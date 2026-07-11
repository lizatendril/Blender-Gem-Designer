# Blender Gem Designer

A Blender add-on for designing faceted gemstones. Define your gem as a stack of
tiers with rotational and mirror symmetry, get real-time previews through
Geometry Nodes, and render with realistic materials (birefringence, dispersion,
volume absorption rather than coloured glass, and a slight fingerprint-smudge
texture on the roughness channel).

I built this because most faceting design software doesn't give you a realistic
preview of how light behaves inside the stone. GCS has a decent preview but
it's not very realistic, it's hard to tell exactly how it would look IRL.
GemRAY's renders are about the same, I think? But less convenient?

Fair warning: most of the code was vibe-coded — an AI wrote it, I steered. If
something seems oddly structured or over-commented, that's why. It does work,
though, and it's pretty well-tested. Probably helps that I have some
programming experience, myself.

## What it does

Define facet tiers by angle, tooth index, and symmetry. The Geometry Nodes
stack cuts your gem in real time with boolean operations in node groups.
It's slightly optimized compared to the most naive possible implementation,
but it's still slow. Does make for a good visualization, though!

Import your existing designs from Gem Cut Studio (.gcs) or GemCAD (.asc and
.gem). The importer figures out the tier layout and sets up the modifiers. If
the file names the gem material, or if the gem material itself is named (in
.gcs only), you get the right shader without touching anything.

The material presets aren't just coloured glass. They model absorption (deeper
colour along longer light paths), dispersion (the red-blue split in diamonds),
and birefringence where the stone calls for it. There's even a fingerprint
smudge texture on the roughness, because a perfectly clean gem looks fake.

The Scene Setup panel knocks out the boring render config in a few clicks:
noise threshold, light bounces, camera with depth of field, and a world
background that puts an HDRI on reflections but keeps the camera background
black.

It takes just a few clicks to import a .gem, .asc or .gcs file and set up a
pretty good rendering scene, and the materials can also easily be simplified
for faster renders.

## Installation

1. Download the .zip from the [latest release](https://github.com/dekker3d/blender-gem-designer/releases)
2. In Blender: Edit → Preferences → Add-ons → Install
3. Pick the .zip file, enable the add-on
4. Find the "Gem" tab in the 3D View sidebar (press N if you don't see a sidebar)

## Quick start

### From scratch

Hit "Setup New Gem" in the Gem panel. That gives you a cube with a default
tier. Add more tiers in the Crown and Pavilion sections, tweak the angles, and
the preview updates live.

### From an existing design

Use "Import GCS Design" or Blender's File → Import menu for GemCAD files.
The importer sets up the tiers for you. If the file names the gem material
("Ruby", "Peridot", etc.), it applies the matching shader automatically.

### Materials

The Material panel lists presets for common gemstones — Ruby, Sapphire,
Diamond, Moissanite, Sphene, and ten others. Click one to apply it.

Each material uses a custom shader that handles:

- **Absorption colour** — colour builds up along longer light paths, like a
  real gem
- **Dispersion** — red and blue wavelengths split at different angles
- **Birefringence** — for doubly-refractive stones like Zircon and Sphene
- **Fingerprint smudges** — because real gems aren't perfectly clean

The shader has a "Render Dispersion" dropdown. Leave it on "Full Dispersion"
for final renders. Switch to "First-Bounce" or "No Dispersion" while you're
working — the viewport preview updates faster.

### Scene Setup

Four buttons under Scene Setup to get you rendering fast:

- **Preview Render Settings** — noise threshold 0.01, 1024 samples, denoise on
- **Full GI Light Paths** — max bounces bumped up to catch all the internal
  reflections
- **Camera from View + DoF** — grabs your current view, creates a camera there,
  focuses it on the gem, sets depth of field to f/0.5
- **Studio World Background** — black for the camera, an HDRI for everything
  else (so reflections look right but the background stays clean). Currently
  uses a workshop scene, turn the gem to the top-right (press R twice to do
  that easily) for a good bright spot (big garage door).

## Requirements

- Blender 5.1 or later
- Cycles renderer (the materials rely on Cycles shader nodes)

## License

GPL v3. See `LICENSE.txt`. Third-party asset credits in `CREDITS.md`.
