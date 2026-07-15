"""GemCAD .asc importer for Cinema 4D 2024+ (Script Manager script).

Reduced-scope C4D equivalent of the "Gem Designer" Blender add-on's ASC
importer.  Import-only, geometry-only:

    Script Manager  ->  Run  ->  file dialog  ->  pick a gem-asc/*.asc  ->
    a single hard-edged PolygonObject is built at the origin, table up (+Y),
    scaled so the girdle diameter is ~2 cm, with undo support.

Unlike the Blender add-on (where Geometry Nodes does the boolean cutting and
no mesh is ever constructed here), this script builds the convex polyhedron
itself by clipping a seed cube against each facet plane.  The .asc parser is
pure Python and is ported near-verbatim from the add-on.

The geometry core (parser + plane math + clipper + mesh build) has no C4D
dependency.  Run this file as plain Python with a path argument to exercise
that core and print closure statistics, e.g.:

    python import_gemcad_asc.py ../gem-asc/pc23002.asc
    python import_gemcad_asc.py ../gem-asc          # all *.asc in a folder

Format reference: https://github.com/mbparker/gemcad-file-reader
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

try:
    import c4d
    from c4d import storage
    HAVE_C4D = True
except ImportError:
    HAVE_C4D = False


# ============================================================================
# 1. Constants
# ============================================================================

GIRDLE_DIAMETER = 2.0      # target girdle diameter in cm (C4D default units)
EPS = 1e-8                 # signed-distance classification tolerance
                           # (loose enough to fuse designed "meet" facets;
                           #  a sweep over the 19 samples fails at 1e-9 and 1e-6)
WELD_EPS = 1e-7            # vertex-weld / duplicate-plane distance tolerance
BOUND = 10.0               # seed-cube half-size in file units (samples: 0.3-0.9)
ROW_GAP = 3.0              # spacing between batch-imported gems along X, in cm


# ============================================================================
# 2. ASC parser  (port of Blender add-on gemcad_import.load_asc; already bpy-free)
# ============================================================================

def _parse_float_safe(value: str) -> float:
    """Parse a string to float, returning 0.0 on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def load_asc(filepath: str) -> dict[str, Any]:
    """Parse a GemCAD .asc file and return structured data.

    Returns a dict with:
        info:  {title, headers: [str], footnotes: [str]}
        render: {refractive_index}
        index: {gear, gear_location_angle, symmetry_folds, symmetry_mirror}
        tiers: [{angle, distance, cutting_instructions,
                 facets: [{index, name}]}]

    Two verified quirks are preserved:
      * ``n <name>`` names the PREVIOUSLY read tooth index.
      * The first non-numeric, non-``n`` token ends the index list and
        becomes the tier's cutting instructions.
    """
    with open(filepath, "r", encoding="ascii", errors="replace") as fh:
        lines = [line.strip() for line in fh if line.strip()]

    # Files in gem-asc/ are v4.41 / 4.51 / 5.0 -> all start with "GemCad ".
    if not lines or not lines[0].startswith("GemCad "):
        raise ValueError(f"Not a valid GemCAD ASC file: {filepath}")

    data: dict[str, Any] = {
        "info": {"title": "", "headers": [], "footnotes": []},
        "render": {"refractive_index": 1.54},
        "index": {
            "gear": 96,
            "gear_location_angle": 0.0,
            "symmetry_folds": 1,
            "symmetry_mirror": False,
        },
        "tiers": [],
    }

    for line in lines[1:]:  # skip the "GemCad <ver>" header line
        parts = line.split()
        if not parts:
            continue

        directive = parts[0]

        if directive == "g" and len(parts) >= 3:
            data["index"]["gear"] = abs(int(parts[1]))
            data["index"]["gear_location_angle"] = _parse_float_safe(parts[2])

        elif directive == "y" and len(parts) >= 3:
            data["index"]["symmetry_folds"] = int(parts[1])
            data["index"]["symmetry_mirror"] = parts[2].lower() == "y"

        elif directive == "I" and len(parts) >= 2:
            data["render"]["refractive_index"] = _parse_float_safe(parts[1])

        elif directive == "H" and len(parts) >= 2:
            header_text = " ".join(parts[1:])
            data["info"]["headers"].append(header_text)
            if not data["info"]["title"]:
                data["info"]["title"] = header_text

        elif directive == "F" and len(parts) >= 2:
            data["info"]["footnotes"].append(" ".join(parts[1:]))

        elif directive == "a" and len(parts) >= 4:
            # a <angle> <distance> <idx1> [<idx2> ...] [n <name> ...] [instructions]
            angle = _parse_float_safe(parts[1])
            distance = _parse_float_safe(parts[2])

            facets: list[dict[str, Any]] = []
            cutting_instructions = ""
            current_index: float | None = None
            i = 3

            while i < len(parts):
                token = parts[i]

                if token == "n" and i + 1 < len(parts):
                    # The name applies to the PREVIOUSLY read index.
                    if current_index is not None:
                        facets.append({"index": current_index, "name": parts[i + 1]})
                        current_index = None
                    i += 2
                else:
                    try:
                        idx = float(token)
                        if current_index is not None:
                            facets.append({"index": current_index, "name": ""})
                        current_index = idx
                        i += 1
                    except ValueError:
                        # First non-numeric, non-"n" token -> cutting instructions.
                        if current_index is not None:
                            facets.append({"index": current_index, "name": ""})
                            current_index = None
                        cutting_instructions = " ".join(parts[i:])
                        break

            if current_index is not None:
                facets.append({"index": current_index, "name": ""})

            data["tiers"].append({
                "angle": angle,
                "distance": distance,
                "cutting_instructions": cutting_instructions,
                "facets": facets,
            })

    return data


# ============================================================================
# 3. Tier -> facet planes
# ============================================================================

def tiers_to_planes(data: dict[str, Any]) -> list[tuple[tuple[float, float, float], float]]:
    """Convert parsed tiers into a deduplicated list of ``(unit_normal, d)``
    half-space planes.  The kept half-space is ``n . x <= d``.

    GemCad coordinates: Z is the optical axis, the table normal is +Z.
    Math is the inverse of the add-on's normal -> (angle, distance, index)
    computation (gemcad_import.py:393-461):

      step = 360 / gear                         (degrees per tooth)
      az   = 90 - (index + gear_location)*step  (azimuth in XY plane)
      elev = 90 - |angle|                       (normal elevation off horizontal)
      sgn  = +1 if angle >= 0 (crown/table) else -1 (pavilion)
      n    = (cos elev cos az, cos elev sin az, sgn sin elev)
      d    = tier distance (perpendicular distance from origin along n)

    |angle| == 90 -> girdle: elev == 0 -> horizontal normal (sgn irrelevant).
    """
    gear = max(int(data["index"]["gear"]), 1)
    gear_location = float(data["index"]["gear_location_angle"])
    step = 360.0 / gear

    planes: list[tuple[tuple[float, float, float], float]] = []

    for tier in data["tiers"]:
        angle = float(tier["angle"])
        distance = float(tier["distance"])
        sgn = 1.0 if angle >= 0.0 else -1.0
        elev = math.radians(90.0 - abs(angle))
        ce = math.cos(elev)
        se = math.sin(elev)

        for facet in tier["facets"]:
            index = float(facet["index"])
            az = math.radians(90.0 - (index + gear_location) * step)
            n = (ce * math.cos(az), ce * math.sin(az), sgn * se)
            _add_plane(planes, n, distance)

    return planes


def _split_planes_for_mirror(planes):
    """Split planes into (girdle, crown/table, pavilion) by outward-normal Z sign.

    Girdle tiers (``|angle| == 90``) always convert to ``nz == 0`` (a vertical
    rim wall); this is a more reliable way to find the rim than facet names,
    which are inconsistent across designs (unnamed, numbered, or lettered).
    """
    girdle, crown, pavilion = [], [], []
    for (n, d) in planes:
        if abs(n[2]) <= EPS:
            girdle.append((n, d))
        elif n[2] > 0:
            crown.append((n, d))
        else:
            pavilion.append((n, d))
    return girdle, crown, pavilion


def _mirror_axis_height(girdle, crown, pavilion):
    """Full-clip the untouched (girdle+crown+pavilion) design and return the
    raw-frame Z height at the midpoint of its girdle band.

    Mirroring the crown about this height (rather than about Z=0) reproduces
    the *original* rim thickness: Z=0 is just the file's arbitrary origin, not
    necessarily where the crown and pavilion actually meet the girdle wall.
    """
    verts, faces = make_cube(BOUND)
    for (n, d) in girdle + crown + pavilion:
        result = clip_polyhedron(verts, faces, n, d)
        if result is None:
            continue
        verts, faces = result

    referenced = {idx for face in faces for idx in face}
    rim_verts = [verts[i] for i in referenced]
    max_r = max(math.hypot(v[0], v[1]) for v in rim_verts)
    # Radius comparison needs a looser tolerance than vertex-weld distance.
    band_zs = [v[2] for v in rim_verts if math.hypot(v[0], v[1]) >= max_r - 1e-6]
    return (min(band_zs) + max(band_zs)) / 2.0


def _mirror_top_polyhedron(girdle, crown, pavilion):
    """Discard the pavilion and build the bottom half as a mesh-level mirror
    of the crown, glued at the midpoint of the design's own girdle band.

    Gluing at the girdle band's own midpoint (rather than at Z=0) reproduces
    the *original* rim thickness -- Z=0 is just the file's arbitrary origin,
    not necessarily where the crown and pavilion actually meet the girdle
    wall.  The crown+girdle solid is clipped by one extra flat cut at that
    midpoint height, then the resulting cap ring is reflected onto itself
    (not re-derived through a second independent clip) so the two halves
    glue with zero seam error -- re-clipping with reflected *planes* instead
    computes the seam twice via different plane pairs, which is numerically
    fragile: on some designs the two computations of "the same" point land
    fractions of a WELD_EPS apart, on either side of the vertex-weld grid's
    rounding boundary, leaving a non-manifold seam.
    """
    z0 = _mirror_axis_height(girdle, crown, pavilion)

    verts, faces = make_cube(BOUND)
    for (n, d) in girdle + crown + [((0.0, 0.0, -1.0), -z0)]:
        result = clip_polyhedron(verts, faces, n, d)
        if result is None:
            continue
        verts, faces = result

    cap_face = None
    for face in faces:
        if all(abs(verts[i][2] - z0) < WELD_EPS for i in face):
            cap_face = face
            break
    cap_ring = set(cap_face) if cap_face is not None else set()

    referenced = {idx for face in faces for idx in face}
    combined_verts = list(verts)
    remap: dict[int, int] = {}
    for i in referenced:
        if i in cap_ring:
            remap[i] = i  # seam vertex: exactly on the mirror plane, maps to itself
        else:
            v = verts[i]
            remap[i] = len(combined_verts)
            combined_verts.append((v[0], v[1], 2.0 * z0 - v[2]))

    combined_faces = [face for face in faces if face is not cap_face]
    for face in faces:
        if face is cap_face:
            continue
        combined_faces.append([remap[i] for i in reversed(face)])

    return combined_verts, combined_faces


def _add_plane(planes: list[tuple[tuple[float, float, float], float]],
               n: tuple[float, float, float], d: float) -> None:
    """Append plane (n, d) unless an exact duplicate is already present.

    Duplicate == same direction (n1.n2 > 1 - 1e-9) AND same offset
    (|d1 - d2| < WELD_EPS).  Girdle tiers that share an angle but differ in
    distance (e.g. pc23002.asc's two -90 tiers) are BOTH kept.
    """
    for (pn, pd) in planes:
        dot = pn[0] * n[0] + pn[1] * n[1] + pn[2] * n[2]
        if dot > 1.0 - 1e-9 and abs(pd - d) < WELD_EPS:
            return
    planes.append((n, d))


# ============================================================================
# 4. Convex clipping  (dependency-free)
#
# Polyhedron = verts: list[(x,y,z)] + faces: list[list[int]], CCW from outside.
# ============================================================================

def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _normalize(a):
    m = math.sqrt(_dot(a, a))
    if m < 1e-30:
        return (0.0, 0.0, 0.0)
    return (a[0] / m, a[1] / m, a[2] / m)


def make_cube(half: float) -> tuple[list[tuple[float, float, float]], list[list[int]]]:
    """Axis-aligned seed cube of the given half-size.  Faces CCW from outside."""
    h = half
    verts = [
        (-h, -h, -h), (h, -h, -h), (h, h, -h), (-h, h, -h),  # 0..3  z = -h
        (-h, -h, h), (h, -h, h), (h, h, h), (-h, h, h),      # 4..7  z = +h
    ]
    faces = [
        [0, 3, 2, 1],  # -Z
        [4, 5, 6, 7],  # +Z
        [0, 1, 5, 4],  # -Y
        [2, 3, 7, 6],  # +Y
        [1, 2, 6, 5],  # +X
        [0, 4, 7, 3],  # -X
    ]
    return verts, faces


def clip_polyhedron(verts, faces, n, d):
    """Clip a convex polyhedron by the half-space ``n . x <= d``.

    Returns ``(new_verts, new_faces)`` or ``None`` if the plane removes the
    whole solid (degenerate design).  Sutherland-Hodgman per face, plus one
    cap face built from the on-plane cut ring.
    """
    nx, ny, nz = n
    s = [nx * x + ny * y + nz * z - d for (x, y, z) in verts]

    if max(s) <= EPS:
        return verts, faces           # everything inside/on -> no cut
    if min(s) >= -EPS:
        return None                   # nothing inside -> solid removed

    new_verts = list(verts)
    icache: dict[tuple[int, int], int] = {}

    def intersect(a: int, b: int) -> int:
        key = (a, b) if a < b else (b, a)
        cached = icache.get(key)
        if cached is not None:
            return cached
        sa, sb = s[a], s[b]
        t = sa / (sa - sb)
        va, vb = verts[a], verts[b]
        p = (va[0] + t * (vb[0] - va[0]),
             va[1] + t * (vb[1] - va[1]),
             va[2] + t * (vb[2] - va[2]))
        idx = len(new_verts)
        new_verts.append(p)
        icache[key] = idx
        return idx

    # Cap-ring membership is tracked exactly (on-plane kept verts + every new
    # intersection), never re-derived from a distance tolerance -- that keeps
    # nearly-tangent planes from wrongly absorbing interior corners.
    cap_members: set[int] = set()

    new_faces: list[list[int]] = []
    for face in faces:
        out_poly: list[int] = []
        m = len(face)
        for k in range(m):
            a = face[k]
            b = face[(k + 1) % m]
            sa, sb = s[a], s[b]
            if sa <= EPS:                 # a is inside or on -> keep it
                out_poly.append(a)
                if sa >= -EPS:            # a lies on the cut plane
                    cap_members.add(a)
            if (sa < -EPS and sb > EPS) or (sa > EPS and sb < -EPS):
                cap_members.add(intersect(a, b))
                out_poly.append(icache[(a, b) if a < b else (b, a)])

        cleaned: list[int] = []
        for idx in out_poly:
            if not cleaned or cleaned[-1] != idx:
                cleaned.append(idx)
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1]:
            cleaned.pop()
        if len(cleaned) >= 3:
            new_faces.append(cleaned)

    # --- Cap face: the on-plane cut ring welded into one convex polygon. ---
    used = {i for f in new_faces for i in f}
    cap: list[tuple[int, tuple[float, float, float]]] = []
    seen_keys: set[tuple[int, int, int]] = set()
    for i in cap_members:
        if i not in used:
            continue
        v = new_verts[i]
        key = (round(v[0] / WELD_EPS), round(v[1] / WELD_EPS), round(v[2] / WELD_EPS))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        cap.append((i, v))

    if len(cap) >= 3:
        new_faces.append(_order_cap(cap, n))

    return new_verts, new_faces


def _order_cap(cap, n):
    """Order cap ring vertices CCW-from-outside (outward normal = +n)."""
    cx = sum(v[0] for _, v in cap) / len(cap)
    cy = sum(v[1] for _, v in cap) / len(cap)
    cz = sum(v[2] for _, v in cap) / len(cap)
    centroid = (cx, cy, cz)

    # Plane basis: u perpendicular to n, v = n x u.
    an = (abs(n[0]), abs(n[1]), abs(n[2]))
    if an[0] <= an[1] and an[0] <= an[2]:
        seed = (1.0, 0.0, 0.0)
    elif an[1] <= an[2]:
        seed = (0.0, 1.0, 0.0)
    else:
        seed = (0.0, 0.0, 1.0)
    u = _normalize(_cross(n, seed))
    w = _cross(n, u)

    def angle(item):
        rel = _sub(item[1], centroid)
        return math.atan2(_dot(rel, w), _dot(rel, u))

    ordered = sorted(cap, key=angle)
    ring = [i for i, _ in ordered]

    # Orient so the geometric (Newell) normal agrees with +n.
    gn = _newell([new for _, new in ordered])
    if _dot(gn, n) < 0.0:
        ring.reverse()
    return ring


def _newell(points):
    """Newell's method polygon normal (not normalized)."""
    nx = ny = nz = 0.0
    m = len(points)
    for i in range(m):
        a = points[i]
        b = points[(i + 1) % m]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return (nx, ny, nz)


# ============================================================================
# 5. Mesh build  (weld -> axis swap -> scale -> winding fix -> triangulate)
# ============================================================================

def build_geometry(verts, faces):
    """Turn the clipped polyhedron into a triangle mesh in C4D coordinates.

    Returns ``(points, tris, stats)`` where ``points`` are (x, y, z) C4D
    coordinates, ``tris`` are (a, b, c) index triples, and ``stats`` is a
    dict of verification metrics.  No C4D dependency.
    """
    # --- Global weld: grid-hash + union-find near-coincident vertices.  Only
    # vertices referenced by a surviving face are kept; clipped-away seed
    # corners are orphaned in the clipper's vertex list and must be dropped
    # here.
    #
    # A single rounded key isn't enough: independently-computed intersection
    # points can be < WELD_EPS apart yet straddle a rounding boundary and
    # round to *adjacent* cells.  Worse, at a facet "star" where several
    # planes meet at one theoretical point, the clipper can produce a whole
    # cluster of near-duplicates whose pairwise gaps chain past WELD_EPS
    # end-to-end even though each adjacent pair is within tolerance.  Union-
    # find merges such chains transitively; a 3x3x3 grid-cell lookup (cell
    # size == WELD_EPS) is enough to find every pair within WELD_EPS, since
    # such a pair can never be more than one cell apart in any axis. ---
    referenced = sorted({idx for face in faces for idx in face})
    parent = list(range(len(referenced)))

    def _find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(x: int, y: int) -> None:
        rx, ry = _find(x), _find(y)
        if rx != ry:
            parent[rx] = ry

    grid: dict[tuple[int, int, int], list[int]] = {}
    for k, idx in enumerate(referenced):
        v = verts[idx]
        cx = round(v[0] / WELD_EPS)
        cy = round(v[1] / WELD_EPS)
        cz = round(v[2] / WELD_EPS)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for other_k in grid.get((cx + dx, cy + dy, cz + dz), ()):
                        ov = verts[referenced[other_k]]
                        if (abs(ov[0] - v[0]) < WELD_EPS
                                and abs(ov[1] - v[1]) < WELD_EPS
                                and abs(ov[2] - v[2]) < WELD_EPS):
                            _union(k, other_k)
        grid.setdefault((cx, cy, cz), []).append(k)

    clusters: dict[int, list[int]] = {}
    for k in range(len(referenced)):
        clusters.setdefault(_find(k), []).append(k)

    remap: dict[int, int] = {}
    welded: list[tuple[float, float, float]] = []
    for members in clusters.values():
        pts_in_cluster = [verts[referenced[m]] for m in members]
        centroid = (
            sum(p[0] for p in pts_in_cluster) / len(pts_in_cluster),
            sum(p[1] for p in pts_in_cluster) / len(pts_in_cluster),
            sum(p[2] for p in pts_in_cluster) / len(pts_in_cluster),
        )
        j = len(welded)
        welded.append(centroid)
        for m in members:
            remap[referenced[m]] = j

    # Reindex faces, drop consecutive duplicates and degenerate faces.
    clean_faces: list[list[int]] = []
    for face in faces:
        f: list[int] = []
        for idx in face:
            r = remap[idx]
            if not f or f[-1] != r:
                f.append(r)
        if len(f) >= 2 and f[0] == f[-1]:
            f.pop()
        if len(f) >= 3:
            clean_faces.append(f)

    # --- Seed-cube survivor check (in file units, before scaling). ---
    seed_survivors = sum(
        1 for v in welded
        if max(abs(v[0]), abs(v[1]), abs(v[2])) >= BOUND - 1e-4
    )

    # --- Axis conversion: GemCad Z-up right-handed -> C4D Y-up left-handed.
    # (x, y, z) -> (x, z, y): a single-axis swap flips handedness; table -> +Y.
    pts = [(v[0], v[2], v[1]) for v in welded]

    # --- Scale so girdle diameter == GIRDLE_DIAMETER.  Convex gem is widest
    # at the girdle; in C4D coords the axis is Y so girdle radius = sqrt(x^2+z^2).
    diameter = 0.0
    for p in pts:
        r = 2.0 * math.sqrt(p[0] * p[0] + p[2] * p[2])
        if r > diameter:
            diameter = r
    scale = GIRDLE_DIAMETER / diameter if diameter > 1e-12 else 1.0
    pts = [(p[0] * scale, p[1] * scale, p[2] * scale) for p in pts]

    # --- Winding fix (per polygon, from geometry): outward = away from centroid.
    gx = sum(p[0] for p in pts) / len(pts)
    gy = sum(p[1] for p in pts) / len(pts)
    gz = sum(p[2] for p in pts) / len(pts)
    center = (gx, gy, gz)

    tris: list[tuple[int, int, int]] = []
    has_table = False
    for face in clean_faces:
        poly = [pts[i] for i in face]
        gn = _newell(poly)
        fc = (sum(p[0] for p in poly) / len(poly),
              sum(p[1] for p in poly) / len(poly),
              sum(p[2] for p in poly) / len(poly))
        if _dot(gn, _sub(fc, center)) < 0.0:
            face = list(reversed(face))
            gn = (-gn[0], -gn[1], -gn[2])

        un = _normalize(gn)                # outward normal after winding fix
        if un[1] > 0.999:                 # near +Y -> table facet
            has_table = True

        # Fan-triangulate from vertex 0 (facets are convex).
        for k in range(1, len(face) - 1):
            tris.append((face[0], face[k], face[k + 1]))

    # --- Verification stats. ---
    edges: dict[tuple[int, int], int] = {}
    for (a, b, c) in tris:
        for (p, q) in ((a, b), (b, c), (c, a)):
            e = (p, q) if p < q else (q, p)
            edges[e] = edges.get(e, 0) + 1
    non_manifold = sum(1 for cnt in edges.values() if cnt != 2)

    V = len(pts)
    E = len(edges)
    F = len(tris)
    stats = {
        "V": V, "E": E, "F": F,
        "euler": V - E + F,
        "closed": non_manifold == 0,
        "non_manifold_edges": non_manifold,
        "seed_survivors": seed_survivors,
        "girdle_diameter_raw": diameter,
        "has_table_facet": has_table,
    }
    return pts, tris, stats


# ============================================================================
# 6. C4D object build + main()
# ============================================================================

def _center_points(pts):
    """Recenter ``pts`` on their bounding-box middle ("center axis").

    Returns (centered_pts, size) where ``size`` is the (dx, dy, dz)
    bounding-box extent, used to space batch-imported gems along X.
    """
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    center = ((min(xs) + max(xs)) / 2.0,
              (min(ys) + max(ys)) / 2.0,
              (min(zs) + max(zs)) / 2.0)
    centered = [(p[0] - center[0], p[1] - center[1], p[2] - center[2]) for p in pts]
    size = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    return centered, size


def build_polygon_object(pts, tris, name):
    """Create a hard-edged c4d.PolygonObject (no Phong tag)."""
    op = c4d.PolygonObject(pcnt=len(pts), vcnt=len(tris))
    for i, p in enumerate(pts):
        op.SetPoint(i, c4d.Vector(p[0], p[1], p[2]))
    for i, (a, b, c) in enumerate(tris):
        op.SetPolygon(i, c4d.CPolygon(a, b, c, c))  # triangle: 4th == 3rd
    op.SetName(name)
    op.Message(c4d.MSG_UPDATE)
    # No Phong tag is added -> fresh PolygonObjects render with hard edges.
    return op


def _build_mesh(filepath: str, mirror_top: bool = False):
    """Parse -> planes -> clip -> mesh.  Returns (pts, tris, stats, name)."""
    data = load_asc(filepath)
    planes = tiers_to_planes(data)

    if mirror_top:
        girdle, crown, pavilion = _split_planes_for_mirror(planes)
        verts, faces = _mirror_top_polyhedron(girdle, crown, pavilion)
    else:
        verts, faces = make_cube(BOUND)
        for (n, d) in planes:
            result = clip_polyhedron(verts, faces, n, d)
            if result is None:
                print(f"[GemCAD] WARNING: plane n={n} d={d} removed the whole "
                      f"solid (degenerate design); skipping.")
                continue
            verts, faces = result

    pts, tris, stats = build_geometry(verts, faces)
    name = data["info"]["title"] or Path(filepath).stem
    if mirror_top:
        name += " (mirrored top)"
    return pts, tris, stats, name


if HAVE_C4D:
    class _ImportSettingsDialog(c4d.gui.GeDialog):
        """Pre-import options dialog: a "Settings" group with the "Mirror top"
        checkbox, and two buttons -- "Single import" (one file, via
        ``ID_SINGLE_IMPORT``) and "Batch import" (every .asc in a folder, via
        ``ID_BATCH_IMPORT``) -- read back by ``main()`` as ``self.mode``."""

        ID_GROUP = 1000
        ID_MIRROR_TOP = 1001
        ID_SINGLE_IMPORT = 1002
        ID_BATCH_IMPORT = 1003

        def __init__(self):
            self.mirror_top = True
            self.mode = None  # "single" or "batch"
            self.confirmed = False

        def CreateLayout(self):
            self.SetTitle("Import GemCAD .asc design(s)")
            self.GroupBegin(0, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 1, 0)
            self.GroupBorderSpace(12, 12, 12, 12)
            self.GroupBegin(self.ID_GROUP, c4d.BFH_SCALEFIT, 1, 0, "Settings")
            self.GroupBorder(c4d.BORDER_GROUP_IN)
            self.GroupBorderSpace(10, 8, 10, 8)
            self.AddCheckbox(self.ID_MIRROR_TOP, c4d.BFH_LEFT, 0, 0, "Mirror top")
            self.GroupEnd()
            self.GroupBegin(0, c4d.BFH_SCALEFIT, 2, 0)
            self.GroupSpace(8, 0)
            self.AddButton(self.ID_SINGLE_IMPORT, c4d.BFH_SCALEFIT, name="Single import")
            self.AddButton(self.ID_BATCH_IMPORT, c4d.BFH_SCALEFIT, name="Batch import")
            self.GroupEnd()
            self.GroupEnd()
            return True

        def InitValues(self):
            self.SetBool(self.ID_MIRROR_TOP, True)
            return True

        def Command(self, id, msg):
            if id in (self.ID_SINGLE_IMPORT, self.ID_BATCH_IMPORT):
                self.mirror_top = self.GetBool(self.ID_MIRROR_TOP)
                self.mode = "single" if id == self.ID_SINGLE_IMPORT else "batch"
                self.confirmed = True
                self.Close()
            return True


def _import_files(filepaths, mirror_top, doc):
    """Build each file in ``filepaths`` and insert it into ``doc``, laid out
    along X (ROW_GAP spacing) with its axis centered on its own geometry.

    Shared between single-file and folder-batch import; a one-element list
    behaves like a plain single import.
    """
    doc.StartUndo()

    x_cursor = 0.0
    last_op = None
    for filepath in filepaths:
        try:
            pts, tris, stats, name = _build_mesh(filepath, mirror_top=mirror_top)
        except Exception as exc:  # noqa: BLE001 - surface any parse/build failure
            c4d.gui.MessageDialog(
                f"Failed to import '{os.path.basename(filepath)}':\n{exc}")
            continue

        if not stats["closed"]:
            print(f"[GemCAD] WARNING: '{name}' mesh is not closed "
                  f"({stats['non_manifold_edges']} non-manifold edges).")
        if stats["seed_survivors"]:
            print(f"[GemCAD] WARNING: '{name}' has {stats['seed_survivors']} "
                  f"seed-cube vertices remaining (design may be unbounded).")
        print(f"[GemCAD] '{name}': V={stats['V']} E={stats['E']} F={stats['F']} "
              f"Euler={stats['euler']} closed={stats['closed']}")

        pts, size = _center_points(pts)
        op = build_polygon_object(pts, tris, name)

        half_width = size[0] / 2.0
        x_pos = x_cursor + half_width
        op.SetRelPos(c4d.Vector(x_pos, 0, 0))
        x_cursor = x_pos + half_width + ROW_GAP

        doc.InsertObject(op)
        doc.AddUndo(c4d.UNDOTYPE_NEW, op)
        last_op = op

    if last_op is not None:
        doc.SetActiveObject(last_op)
    doc.EndUndo()
    c4d.EventAdd()


def main():
    """Script Manager entry point: settings dialog (Single import / Batch
    import) -> file or folder dialog -> build -> insert with undo.

    Single import: one file dialog, one object.
    Batch import: a folder dialog; every *.asc found directly in it
    (non-recursive) is imported and laid out along X with ROW_GAP spacing.
    The classic c4d.storage.LoadDialog has no multi-file-select mode, so
    batch import is folder-based rather than a multi-select file picker.
    """
    dlg = _ImportSettingsDialog()
    dlg.Open(c4d.DLG_TYPE_MODAL, defaultw=260, defaulth=110)
    if not dlg.confirmed:
        return
    mirror_top = dlg.mirror_top

    if dlg.mode == "single":
        filepath = storage.LoadDialog(
            title="Import GemCAD .asc design",
            flags=c4d.FILESELECT_LOAD,
            force_suffix="asc",
        )
        if not filepath:
            return
        filepaths = [filepath]
    else:
        directory = storage.LoadDialog(
            title="Select folder of GemCAD .asc designs",
            flags=c4d.FILESELECT_DIRECTORY,
        )
        if not directory:
            return
        filepaths = sorted(str(p) for p in Path(directory).glob("*.asc"))
        if not filepaths:
            c4d.gui.MessageDialog(f"No .asc files found in:\n{directory}")
            return

    doc = c4d.documents.GetActiveDocument()
    _import_files(filepaths, mirror_top, doc)


# ============================================================================
# Offline verification harness (plain Python, no C4D)
# ============================================================================

def _verify_file(filepath: str) -> bool:
    data = load_asc(filepath)
    has_table_tier = any(abs(float(t["angle"])) < 1e-6 for t in data["tiers"])
    pts, tris, stats, name = _build_mesh(filepath)

    ok = (stats["closed"]
          and stats["euler"] == 2
          and stats["seed_survivors"] == 0
          and (stats["has_table_facet"] or not has_table_tier))

    flags = []
    if not stats["closed"]:
        flags.append(f"NOT-CLOSED({stats['non_manifold_edges']})")
    if stats["euler"] != 2:
        flags.append(f"EULER={stats['euler']}")
    if stats["seed_survivors"]:
        flags.append(f"SEED={stats['seed_survivors']}")
    if has_table_tier and not stats["has_table_facet"]:
        flags.append("NO-TABLE-FACET")

    status = "OK " if ok else "FAIL"
    print(f"[{status}] {os.path.basename(filepath):16s} "
          f"V={stats['V']:3d} E={stats['E']:3d} F={stats['F']:3d} "
          f"Euler={stats['euler']:2d}  '{name}'"
          + (("  <- " + " ".join(flags)) if flags else ""))
    return ok


def _run_offline(target: str) -> int:
    if os.path.isdir(target):
        files = sorted(str(p) for p in Path(target).glob("*.asc"))
    else:
        files = [target]
    if not files:
        print(f"No .asc files found at: {target}")
        return 1
    all_ok = True
    for f in files:
        try:
            all_ok &= _verify_file(f)
        except Exception as exc:  # noqa: BLE001
            all_ok = False
            print(f"[FAIL] {os.path.basename(f):16s} -> {exc}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    if HAVE_C4D:
        main()
    else:
        import sys
        if len(sys.argv) < 2:
            print("Offline usage: python import_gemcad_asc.py <file.asc | dir>")
            sys.exit(2)
        sys.exit(_run_offline(sys.argv[1]))
