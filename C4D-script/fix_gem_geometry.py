"""Geometry inspector + fixer for Cinema 4D 2024+ (Script Manager script).

Dumps as much geometry information as possible about the selected object(s)
so bad geometry can be diagnosed at a glance, then REPAIRS it:

    Script Manager  ->  select an object  ->  Run

The report is printed to the Python console (Extensions -> Console) and, on
C4D, copied to the clipboard so it can be pasted into a bug note.  See the
sibling ``bad-geo-pointers.md`` for the running list of parameters worth
dumping -- this script is the executable version of that checklist.

What it reports, per selected object:
    * identity / type / editability
    * transform: global & local matrix, position/scale/rotation, matrix
      determinant sign (negative == mirrored), non-uniform / negative scale
    * counts: points, polygons (tris vs quads), unique edges
    * bounding box (local & world), dimensions, centroid
    * topology health: Euler characteristic, boundary edges, non-manifold
      edges, isolated (unused) points, duplicate/coincident points,
      zero-length edges, degenerate (zero-area) polygons, watertight check
    * quality checks (polygon analogs of Autodesk Alias' "Check Model"):
      inconsistent normals / flipped faces, non-planar polygons, bad corners
      (near-0/180 deg slivers), short edges, duplicate polygons
    * per-polygon normals: zero-area count, average normal
    * tags: Phong (angle), UVW, Normal, point/poly/edge selections, materials
    * UV health: out-of-[0,1] islands, zero-area UV polys, flipped UV polys

What it FIXES, per selected object (see section 4):
    1. welds the split meet points the clipper left behind, at a tolerance
       derived per-object from that object's own weld window
    2. dissolves the flat triangulation diagonals so each facet becomes a
       single n-gon
    3. rebuilds the "Gem Edges" selection from the dihedral angle, which
       drops the false gem edges (selected but coplanar) as a side effect

Each fix is only attempted when the dump found something for it to do, and
the whole pass runs inside a single undo step.  The three steps are ordered
by dependency: welding renumbers points, dissolving renumbers polygons, and
the edge selection is addressed by polygon index -- so the selection is
rebuilt last, from the final mesh, rather than carried through and remapped.

The Alias checks that are NURBS-only (rationals, multi-knots, spans, degree,
minimum radius of curvature, G1/G2 continuity, waviness) have no meaning on a
polygon mesh and are intentionally not emulated; the checks above are their
mesh-topology equivalents.

Objects that are not already editable PolygonObjects (generators, splines,
primitives) are polygonized via Current-State-to-Object into a throwaway
copy so their evaluated cache can still be inspected; the original is never
modified -- and, because the fix has nothing persistent to write to, such
objects are reported but not repaired.

The inspection core is C4D-only; run outside C4D and it just prints a note.
"""

from __future__ import annotations

import math

try:
    import c4d
    from c4d import utils
    HAVE_C4D = True
except ImportError:
    HAVE_C4D = False


# ============================================================================
# 1. Config
# ============================================================================

MAX_LIST = 24              # cap on individual items listed per problem section
                           # (full counts are always reported; this only caps
                           #  the enumerated indices/coords that follow)
DUMP_ALL_POINTS = False    # True -> list every point coordinate (can be huge)
WELD_EPS = 1e-6            # coincident-point / zero-length-edge tolerance, cm
DEGENERATE_RATIO = 1e-4   # a polygon is a degenerate sliver when
                          # area / longest_edge^2 drops below this.  Scale-
                          # invariant (~0.43 for an equilateral triangle, -> 0
                          # as it collapses to a line), so it means the same
                          # thing on a 2 cm gem as on a 2 m one -- an absolute
                          # area threshold does not.
SHORT_EDGE = 1e-3         # edges shorter than this (but non-zero) are flagged, cm
PLANARITY_EPS = 1e-4      # max corner-off-plane distance for a "planar" poly, cm
BAD_CORNER_DEG = 1.0      # interior corner angle within this of 0/180 = bad/sliver
TINY_POLY_FRAC = 1e-4     # a polygon is "tiny" when its area falls below
                          # (TINY_POLY_FRAC * bbox_diagonal)^2.  Complements
                          # DEGENERATE_RATIO: that one is scale-invariant and
                          # so is blind to a *correctly shaped* but microscopic
                          # facet (3 planes missing a common point leave a near-
                          # equilateral speck, ratio ~0.43).  Needles need the
                          # shape test; specks need this one.
NEAR_MEET_EPS = 5e-4      # cm; points closer than this are a designed meet
                          # point the clipper resolved into separate vertices.
                          # Deliberately ~500x looser than WELD_EPS -- the real
                          # near-meets sit at 1e-6..2e-4, far above a weld eps.
CONVEX_TOL = 1e-4         # cm a point may sit outside a facet plane before the
                          # solid is reported non-convex
TARGET_GIRDLE_DIAMETER = 2.0  # cm; mirrors import_gemcad_asc's GIRDLE_DIAMETER
GEM_EDGE_TAG = "Gem Edges"  # edge-selection tag holding the gem's real edges
GEM_EDGE_MIN_DIHEDRAL = 0.01  # degrees; mirrors import_gemcad_asc's
                              # FACET_EDGE_MIN_DIHEDRAL -- below this, two
                              # adjacent facets count as coplanar
COPY_TO_CLIPBOARD = True   # copy the full report to the clipboard on finish

# --- fix pass ---------------------------------------------------------------
FIX_WELD = True            # weld the split meet points
FIX_DISSOLVE = True        # dissolve flat diagonals -> one n-gon per facet
FIX_GEM_EDGES = True       # rebuild "Gem Edges" from the dihedral angle
VERIFY_AFTER_FIX = True    # re-run the whole dump on the repaired mesh
MIN_WELD_GAP = 3.0         # the weld window must be at least this wide before
                           # a weld tolerance is trusted.  Below it there is no
                           # value that separates defects from real edges, so
                           # the fix refuses rather than guessing -- same
                           # threshold the dump's "narrow gap" warning uses.


# ============================================================================
# 2. Small geometry helpers (C4D-vector based)
# ============================================================================

def _v(p):
    """(x, y, z) tuple from a c4d.Vector, for hashing / printing."""
    return (p.x, p.y, p.z)


def _tri_area(a, b, c):
    """Area of triangle a-b-c given three c4d.Vectors."""
    return 0.5 * (b - a).Cross(c - a).GetLength()


def _poly_is_tri(poly):
    """A C4D CPolygon encodes a triangle as d == c (4th index repeats 3rd)."""
    return poly.c == poly.d


def _poly_indices(poly):
    """Ordered corner indices of a polygon: 3 for a triangle, 4 for a quad."""
    if _poly_is_tri(poly):
        return (poly.a, poly.b, poly.c)
    return (poly.a, poly.b, poly.c, poly.d)


def _poly_area(pts, poly):
    """Area of a tri or quad (quad split on the a-c diagonal)."""
    a, b, c = pts[poly.a], pts[poly.b], pts[poly.c]
    if _poly_is_tri(poly):
        return _tri_area(a, b, c)
    d = pts[poly.d]
    return _tri_area(a, b, c) + _tri_area(a, c, d)


def _poly_normal(pts, poly):
    """Newell normal of a polygon; zero vector for a degenerate face."""
    idx = _poly_indices(poly)
    n = c4d.Vector(0.0)
    m = len(idx)
    for i in range(m):
        cur = pts[idx[i]]
        nxt = pts[idx[(i + 1) % m]]
        n.x += (cur.y - nxt.y) * (cur.z + nxt.z)
        n.y += (cur.z - nxt.z) * (cur.x + nxt.x)
        n.z += (cur.x - nxt.x) * (cur.y + nxt.y)
    return n


def _poly_thinness(pts, poly):
    """Scale-invariant degeneracy ratio: area / longest_edge^2.

    ~0.43 for an equilateral triangle and -> 0 as the polygon collapses onto
    a line, so it measures *shape*, not size.  This is what an absolute area
    threshold gets wrong: a needle triangle 0.5 cm long and 3e-6 cm wide has
    an area of ~7e-7 -- large in absolute terms, utterly degenerate in shape.
    """
    idx = _poly_indices(poly)
    m = len(idx)
    longest = max((pts[idx[i]] - pts[idx[(i + 1) % m]]).GetLength()
                  for i in range(m))
    if longest < 1e-30:
        return 0.0
    return _poly_area(pts, poly) / (longest * longest)


def _edges_of_poly(poly):
    """Undirected edges of a polygon as sorted (lo, hi) index tuples."""
    idx = _poly_indices(poly)
    m = len(idx)
    out = []
    for i in range(m):
        a, b = idx[i], idx[(i + 1) % m]
        out.append((a, b) if a < b else (b, a))
    return out


def _unique_edges(polys):
    """{(lo, hi): [polygon indices touching it]} over the whole mesh."""
    edge_polys = {}
    for i, poly in enumerate(polys):
        for e in _edges_of_poly(poly):
            edge_polys.setdefault(e, []).append(i)
    return edge_polys


def _weld_window(pts, polys):
    """The gap between the longest defect edge and the shortest real one.

    Returns (worst, next, suggested) or None when there are no short edges.
    Everything below ``worst`` is a clipper artifact, everything at or above
    ``next`` is geometry the design asked for; the geometric mean of the two
    is the tolerance furthest (in ratio terms) from both mistakes.  Shared by
    the dump and the fix so the number the report suggests is exactly the
    number the fix uses -- a fix that welds at a tolerance the report never
    printed is a fix nobody can check.
    """
    lengths = [(pts[a] - pts[b]).GetLength() for (a, b) in _unique_edges(polys)]
    short = [d for d in lengths if WELD_EPS <= d < SHORT_EDGE]
    legit = [d for d in lengths if d >= SHORT_EDGE]
    if not short or not legit:
        return None
    worst = max(short)
    nxt = min(legit)
    return (worst, nxt, math.sqrt(worst * nxt))


# ============================================================================
# 3. Per-object analysis
# ============================================================================

def _as_polygon_object(op, doc):
    """Return (polyobj, was_converted).

    If ``op`` is already an editable PolygonObject it is returned as-is.
    Otherwise its evaluated state is baked to a throwaway PolygonObject via
    Current-State-to-Object so generators/primitives/splines can still be
    inspected.  The original object is never modified.
    """
    if op.IsInstanceOf(c4d.Opolygon):
        return op, False
    result = utils.SendModelingCommand(
        command=c4d.MCOMMAND_CURRENTSTATETOOBJECT,
        list=[op],
        mode=c4d.MODELINGCOMMANDMODE_ALL,
        doc=doc,
    )
    if result and isinstance(result, list):
        cand = result[0]
        # CSTO on a hierarchy may hand back a Null wrapping the real mesh.
        if not cand.IsInstanceOf(c4d.Opolygon):
            child = cand.GetDown()
            if child and child.IsInstanceOf(c4d.Opolygon):
                cand = child
        if cand.IsInstanceOf(c4d.Opolygon):
            return cand, True
    return None, False


def _matrix_report(op, out):
    """Transform block: position/scale/rotation + mirror & non-uniform flags."""
    mg = op.GetMg()
    ml = op.GetMl()
    out.append("  Transform")
    out.append(f"    global pos : {_fmt_vec(mg.off)}")
    out.append(f"    local  pos : {_fmt_vec(ml.off)}")

    # Column scales (lengths of the basis vectors) and handedness.
    sx = mg.v1.GetLength()
    sy = mg.v2.GetLength()
    sz = mg.v3.GetLength()
    out.append(f"    scale      : ({sx:.6g}, {sy:.6g}, {sz:.6g})")

    det = mg.v1.Cross(mg.v2).Dot(mg.v3)
    if det < 0:
        out.append("    !! negative matrix determinant -> MIRRORED transform "
                    "(normals appear inverted)")
    smin, smax = min(sx, sy, sz), max(sx, sy, sz)
    if smax > 0 and (smax - smin) / smax > 1e-4:
        out.append("    !! non-uniform scale -> bakes anisotropy into geometry "
                   "on 'make editable'")
    if smin < 1e-6:
        out.append("    !! near-zero scale on an axis -> collapsed geometry")

    rot = utils.MatrixToHPB(mg)
    out.append(f"    rotation HPB (deg): ({math.degrees(rot.x):.3f}, "
               f"{math.degrees(rot.y):.3f}, {math.degrees(rot.z):.3f})")


def _fmt_vec(v):
    return f"({v.x:.6g}, {v.y:.6g}, {v.z:.6g})"


def _counts_and_bbox(op, pts, polys, out):
    """Counts, triangle/quad split, bounding boxes, centroid."""
    tris = sum(1 for p in polys if _poly_is_tri(p))
    quads = len(polys) - tris
    out.append("  Counts")
    out.append(f"    points   : {len(pts)}")
    out.append(f"    polygons : {len(polys)}  (tris={tris}, quads={quads})")

    # Local bounding box straight from C4D, plus a manual world-space box.
    rad = op.GetRad()
    mp = op.GetMp()
    out.append("  Bounding box")
    out.append(f"    local center : {_fmt_vec(mp)}")
    out.append(f"    local size   : ({2*rad.x:.6g}, {2*rad.y:.6g}, "
               f"{2*rad.z:.6g})")

    if pts:
        mg = op.GetMg()
        wpts = [mg * p for p in pts]
        xs = [p.x for p in wpts]
        ys = [p.y for p in wpts]
        zs = [p.z for p in wpts]
        out.append(f"    world min    : ({min(xs):.6g}, {min(ys):.6g}, "
                   f"{min(zs):.6g})")
        out.append(f"    world max    : ({max(xs):.6g}, {max(ys):.6g}, "
                   f"{max(zs):.6g})")
        cx = sum(p.x for p in pts) / len(pts)
        cy = sum(p.y for p in pts) / len(pts)
        cz = sum(p.z for p in pts) / len(pts)
        out.append(f"    centroid(loc): ({cx:.6g}, {cy:.6g}, {cz:.6g})")


def _topology_report(pts, polys, out):
    """Euler, edges, boundary/non-manifold, isolated pts, dups, degenerates."""
    # --- edge incidence -----------------------------------------------------
    edge_count = {}
    zero_len_edges = []
    for poly in polys:
        for (a, b) in _edges_of_poly(poly):
            edge_count[(a, b)] = edge_count.get((a, b), 0) + 1
    for (a, b) in edge_count:
        if (pts[a] - pts[b]).GetLength() < WELD_EPS:
            zero_len_edges.append((a, b))

    E = len(edge_count)
    V = len(pts)
    F = len(polys)
    euler = V - E + F
    boundary = [e for e, n in edge_count.items() if n == 1]
    nonmanifold = [e for e, n in edge_count.items() if n > 2]

    out.append("  Topology")
    out.append(f"    unique edges : {E}")
    out.append(f"    Euler V-E+F  : {V} - {E} + {F} = {euler}"
               + ("  (closed genus-0 == 2)" if euler == 2 else "  (!= 2)"))
    watertight = (not boundary and not nonmanifold)
    out.append(f"    watertight   : {'YES' if watertight else 'NO'}")

    _report_group(out, "boundary edges (open, used by 1 poly)", boundary,
                  fmt=lambda e: f"{e[0]}-{e[1]}")
    _report_group(out, "NON-MANIFOLD edges (used by >2 polys)", nonmanifold,
                  fmt=lambda e: f"{e[0]}-{e[1]} (x{edge_count[e]})")
    _report_group(out, "zero-length edges", zero_len_edges,
                  fmt=lambda e: f"{e[0]}-{e[1]}")

    # --- isolated (unreferenced) points ------------------------------------
    used = set()
    for poly in polys:
        used.update(_poly_indices(poly))
    isolated = [i for i in range(V) if i not in used]
    _report_group(out, "isolated points (unused by any polygon)", isolated,
                  fmt=str)

    # --- coincident points --------------------------------------------------
    quant = 1.0 / WELD_EPS
    buckets = {}
    for i, p in enumerate(pts):
        key = (round(p.x * quant), round(p.y * quant), round(p.z * quant))
        buckets.setdefault(key, []).append(i)
    dup_groups = [g for g in buckets.values() if len(g) > 1]
    dup_total = sum(len(g) for g in dup_groups)
    if dup_groups:
        out.append(f"    !! coincident points: {dup_total} points in "
                   f"{len(dup_groups)} clusters (weld eps={WELD_EPS})")
        for g in dup_groups[:MAX_LIST]:
            out.append(f"       {g}")
        if len(dup_groups) > MAX_LIST:
            out.append(f"       ... (+{len(dup_groups) - MAX_LIST} more)")
    else:
        out.append("    coincident points: none")

    # --- degenerate polygons + normals -------------------------------------
    # Two independent failure modes, needing two independent tests:
    #   * needles  -> bad SHAPE, caught by the scale-invariant thinness ratio
    #   * specks   -> fine shape, absurd SIZE, caught by the area test below
    # A near-equilateral speck scores ~0.43 on the ratio and would otherwise
    # pass as healthy.
    diag = _mesh_diagonal(pts)
    tiny_area = (TINY_POLY_FRAC * diag) ** 2
    degenerate = []
    tiny = []
    zero_normal = 0
    min_ratio = 1.0
    min_area = float("inf")
    for i, poly in enumerate(polys):
        ratio = _poly_thinness(pts, poly)
        min_ratio = min(min_ratio, ratio)
        if ratio < DEGENERATE_RATIO:
            degenerate.append((i, ratio))
        area = _poly_area(pts, poly)
        min_area = min(min_area, area)
        if area < tiny_area:
            tiny.append((i, area))
        if _poly_normal(pts, poly).GetLength() < 1e-12:
            zero_normal += 1
    _report_group(out,
                  f"degenerate sliver polygons (area/edge^2 < "
                  f"{DEGENERATE_RATIO})", degenerate,
                  fmt=lambda x: f"{x[0]}(r={x[1]:.2g})")
    out.append(f"    thinnest polygon ratio: {min_ratio:.3g}  "
               f"(equilateral = 0.433)")
    _report_group(out, f"tiny polygons (area < {tiny_area:.3g} cm^2)", tiny,
                  fmt=lambda x: f"{x[0]}(a={x[1]:.2g})")
    # Slivers and specks overlap; the interesting number is what only the
    # size test found, since that is exactly the shape test's blind spot.
    only_tiny = [i for (i, _) in tiny
                 if i not in {j for (j, _) in degenerate}]
    if only_tiny:
        out.append(f"       {len(only_tiny)} of these are well-shaped specks "
                   f"the thinness test cannot see: {only_tiny[:MAX_LIST]}")
    out.append(f"    smallest polygon area : {min_area:.3g} cm^2")
    out.append(f"    zero-normal polygons  : {zero_normal}")


def _quality_report(pts, polys, gem, out):
    """Polygon analogs of Autodesk Alias' "Check Model" mesh-relevant checks:
    inconsistent normals / flipped faces, non-planar polygons, bad corners,
    short edges, duplicate polygons.

    ``gem`` is the shared gem-edge set from _gem_edge_pairs (or None).
    """
    out.append("  Quality (Alias-style checks)")

    # --- normal consistency / flipped faces --------------------------------
    # A manifold edge shared by two faces is consistently wound iff the two
    # faces traverse it in OPPOSITE directions.  Same direction => one face
    # is flipped relative to its neighbour.
    directed = {}
    for i, poly in enumerate(polys):
        idx = _poly_indices(poly)
        m = len(idx)
        for k in range(m):
            a, b = idx[k], idx[(k + 1) % m]
            key = (a, b) if a < b else (b, a)
            directed.setdefault(key, []).append((a, b, i))
    inconsistent = []
    for key, uses in directed.items():
        if len(uses) == 2:
            (a0, b0, _), (a1, b1, _) = uses
            if (a0, b0) == (a1, b1):           # same direction, not reversed
                inconsistent.append(key)
    _report_group(out, "inconsistent-normal edges (flipped adjacent face)",
                  inconsistent, fmt=lambda e: f"{e[0]}-{e[1]}")

    # --- short (but non-zero) edges ----------------------------------------
    # Cross-referenced against the gem-edge selection, because the two cases
    # need different fixes: a short edge that is a triangulation diagonal
    # disappears when facets are dissolved to n-gons, while a short edge that
    # is a real gem edge survives the dissolve and can only be removed by a
    # weld / edge-collapse at a tolerance above its length.
    short = []
    for key in directed:
        d = (pts[key[0]] - pts[key[1]]).GetLength()
        if WELD_EPS <= d < SHORT_EDGE:
            short.append((key, d))
    short.sort(key=lambda x: x[1])
    if not short:
        out.append(f"    short edges (< {SHORT_EDGE} cm): 0")
    else:
        if gem is None:
            out.append(f"    !! short edges (< {SHORT_EDGE} cm): {len(short)}"
                       f"  (no '{GEM_EDGE_TAG}' tag -> cannot classify)")
        else:
            n_gem = sum(1 for (e, _) in short if e in gem["pairs"])
            n_diag = len(short) - n_gem
            out.append(f"    !! short edges (< {SHORT_EDGE} cm): {len(short)}"
                       f"  [gem={n_gem}, diagonal={n_diag}]")
        for (e, d) in short[:MAX_LIST]:
            kind = ""
            if gem is not None:
                kind = "  [gem]" if e in gem["pairs"] else "  [diagonal]"
            out.append(f"       {e[0]}-{e[1]}  len={d:.3g}{kind}")
        if len(short) > MAX_LIST:
            out.append(f"       ... (+{len(short) - MAX_LIST} more)")
        if gem is not None:
            if n_gem:
                # The weld tolerance has to clear the longest offender.
                longest_gem = max(d for (e, d) in short if e in gem["pairs"])
                out.append(f"       -> {n_gem} are gem edges: they SURVIVE the "
                           f"n-gon dissolve; only a weld/collapse above "
                           f"{longest_gem:.3g} cm removes them")
            if n_diag:
                out.append(f"       -> {n_diag} are triangulation diagonals: "
                           f"dissolving facets to n-gons removes them")

        # The weld window: everything below is a defect, everything above is
        # real geometry.  Measuring the gap turns the choice of weld tolerance
        # into evidence instead of a guess -- and a NARROW gap is the warning
        # that no safe tolerance exists.
        window = _weld_window(pts, polys)
        if window:
            worst, nxt, suggest = window
            out.append(f"       weld window: {worst:.3g} .. {nxt:.3g} cm "
                       f"({nxt / worst:.1f}x gap) -> suggest "
                       f"{suggest:.3g} cm (geometric mean)")
            if nxt / worst < MIN_WELD_GAP:
                out.append("       !! narrow gap: no clearly safe weld "
                           "tolerance -- welding may destroy real edges")

    # --- non-planar polygons + bad corners (near-0/180 deg) ----------------
    nonplanar = []
    max_dev = 0.0
    bad_corners = []
    min_angle = 180.0
    for i, poly in enumerate(polys):
        idx = _poly_indices(poly)
        m = len(idx)

        # planarity: distance of each corner from the plane of the first 3
        if m == 4:
            n = _poly_normal(pts, poly)
            if n.GetLength() > 1e-12:
                nh = n.GetNormalized()
                origin = pts[idx[0]]
                dev = max(abs((pts[j] - origin).Dot(nh)) for j in idx)
                max_dev = max(max_dev, dev)
                if dev > PLANARITY_EPS:
                    nonplanar.append((i, dev))

        # bad corner: interior angle at each vertex near 0 or 180 deg
        for k in range(m):
            prev = pts[idx[(k - 1) % m]]
            cur = pts[idx[k]]
            nxt = pts[idx[(k + 1) % m]]
            e0, e1 = prev - cur, nxt - cur
            l0, l1 = e0.GetLength(), e1.GetLength()
            if l0 < WELD_EPS or l1 < WELD_EPS:
                continue
            cosang = max(-1.0, min(1.0, e0.Dot(e1) / (l0 * l1)))
            ang = math.degrees(math.acos(cosang))
            min_angle = min(min_angle, ang)
            if ang < BAD_CORNER_DEG or ang > 180.0 - BAD_CORNER_DEG:
                bad_corners.append((i, k, ang))

    if nonplanar:
        out.append(f"    !! non-planar polygons (> {PLANARITY_EPS} cm off "
                   f"plane): {len(nonplanar)}  (max dev={max_dev:.3g})")
        for (i, dev) in nonplanar[:MAX_LIST]:
            out.append(f"       poly {i}  dev={dev:.3g}")
        if len(nonplanar) > MAX_LIST:
            out.append(f"       ... (+{len(nonplanar) - MAX_LIST} more)")
    else:
        out.append(f"    non-planar polygons: 0  (max quad dev={max_dev:.3g})")

    if bad_corners:
        out.append(f"    !! bad corners (angle < {BAD_CORNER_DEG} or > "
                   f"{180 - BAD_CORNER_DEG} deg): {len(bad_corners)}  "
                   f"(min angle={min_angle:.3g})")
        for (i, k, ang) in bad_corners[:MAX_LIST]:
            out.append(f"       poly {i} corner {k}  angle={ang:.3g}")
        if len(bad_corners) > MAX_LIST:
            out.append(f"       ... (+{len(bad_corners) - MAX_LIST} more)")
    else:
        out.append(f"    bad corners: 0  (min corner angle={min_angle:.3g})")

    # --- duplicate polygons (same vertex set = Alias "Copies") -------------
    seen = {}
    dup_polys = []
    for i, poly in enumerate(polys):
        key = frozenset(_poly_indices(poly))
        if key in seen:
            dup_polys.append((seen[key], i))
        else:
            seen[key] = i
    _report_group(out, "duplicate polygons (same vertex set)", dup_polys,
                  fmt=lambda pr: f"{pr[0]}=={pr[1]}")


def _mesh_diagonal(pts):
    """Bounding-box diagonal length -- the reference for "how big is this mesh"."""
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    return math.sqrt((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2
                     + (max(zs) - min(zs)) ** 2)


def _cluster_points(pts, eps):
    """Union-find clustering of points lying within ``eps`` of each other.

    Returns {root_index: [member indices]}.  Bucketed on a grid of cell size
    eps, so every point within eps of p is in the 3x3x3 neighbourhood of p's
    own cell -- the same argument import_gemcad_asc's weld uses, and the
    reason a plain round()-to-bucket scheme (which misses pairs straddling a
    cell boundary) is not good enough here.
    """
    parent = list(range(len(pts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]      # path compression
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    grid = {}
    for i, p in enumerate(pts):
        cell = (int(math.floor(p.x / eps)), int(math.floor(p.y / eps)),
                int(math.floor(p.z / eps)))
        grid.setdefault(cell, []).append(i)

    for cell, members in grid.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    nbrs = grid.get((cell[0] + dx, cell[1] + dy, cell[2] + dz))
                    if not nbrs:
                        continue
                    for i in members:
                        for j in nbrs:
                            if i < j and (pts[i] - pts[j]).GetLength() < eps:
                                union(i, j)

    clusters = {}
    for i in range(len(pts)):
        clusters.setdefault(find(i), []).append(i)
    return clusters


def _near_meet_report(pts, polys, out):
    """Find designed meet-points that the clipper split into separate vertices,
    and predict exactly what welding them would produce.

    A gem design's meet points are the whole craft: 3+ facets are meant to
    converge on ONE vertex.  Plane-clipping in floating point resolves each
    into a cluster of near-coincident vertices joined by micro-edges.  This
    counts them at a *design* tolerance (NEAR_MEET_EPS), not a numerical one,
    then re-runs Euler on the hypothetical welded mesh so the fix can be
    validated before it is written.
    """
    clusters = _cluster_points(pts, NEAR_MEET_EPS)
    multi = {r: m for r, m in clusters.items() if len(m) > 1}

    out.append(f"  Near-meet points (cluster eps={NEAR_MEET_EPS} cm)")
    if not multi:
        out.append("    none: every vertex is already a clean meet point")
        return

    involved = sum(len(m) for m in multi.values())
    pct = 100.0 * involved / len(pts) if pts else 0.0
    sizes = {}
    for m in multi.values():
        sizes[len(m)] = sizes.get(len(m), 0) + 1
    size_txt = ", ".join(f"{n}x{k}-vert" for k, n in sorted(sizes.items()))
    out.append(f"    !! {len(multi)} split meet points, {involved} vertices "
               f"({pct:.1f}% of mesh)  [{size_txt}]")

    # --- predict the welded mesh and check it with Euler ------------------
    root = {}
    for r, members in clusters.items():
        for i in members:
            root[i] = r
    v_after = len(clusters)
    edges_after = set()
    for poly in polys:
        for (a, b) in _edges_of_poly(poly):
            ra, rb = root[a], root[b]
            if ra != rb:
                edges_after.add((ra, rb) if ra < rb else (rb, ra))
    f_after = sum(1 for poly in polys
                  if len({root[i] for i in _poly_indices(poly)}) >= 3)
    euler = v_after - len(edges_after) + f_after
    verdict = "valid closed solid" if euler == 2 else "!! BROKEN (expected 2)"
    out.append(f"    if welded at {NEAR_MEET_EPS} cm -> V={v_after} "
               f"E={len(edges_after)} F={f_after}, Euler={euler} ({verdict})")
    out.append(f"       ({len(pts) - v_after} points merged, "
               f"{len(polys) - f_after} degenerate polys removed)")


def _convexity_report(pts, polys, out):
    """A gem built by clipping a solid against facet planes MUST be convex.
    Any point outside any facet's plane means the clipper produced something
    the design does not describe.

    Sliver polygons are skipped as plane sources: their normals are numerical
    garbage (that is what makes them slivers), so trusting them here would
    manufacture false violations.
    """
    worst = 0.0
    worst_at = None
    planes = 0
    for i, poly in enumerate(polys):
        if _poly_thinness(pts, poly) < DEGENERATE_RATIO:
            continue                       # unreliable normal -- skip
        n = _poly_normal(pts, poly)
        if n.GetLength() < 1e-12:
            continue
        nh = n.GetNormalized()
        origin = pts[poly.a]
        planes += 1
        for j, p in enumerate(pts):
            d = (p - origin).Dot(nh)       # >0 == outside (normals point out)
            if d > worst:
                worst, worst_at = d, (i, j)
    out.append("  Convexity (must hold for a plane-clipped gem)")
    if planes == 0:
        out.append("    no reliable planes to test against")
    elif worst <= CONVEX_TOL:
        out.append(f"    convex: max point-outside-plane = {worst:.3g} cm "
                   f"(tol {CONVEX_TOL}, {planes} planes tested)")
    else:
        out.append(f"    !! NON-CONVEX: point {worst_at[1]} sits {worst:.3g} cm "
                   f"outside the plane of poly {worst_at[0]} (tol {CONVEX_TOL})")


def _gem_metrics_report(pts, polys, out):
    """Check the mesh against the importer's own stated targets: girdle
    diameter scaled to GIRDLE_DIAMETER, and a table facet pointing at +Y."""
    out.append("  Gem metrics (vs importer targets)")

    # Girdle diameter, defined exactly as import_gemcad_asc:620-625 does it --
    # 2 x max radial distance from the Y axis, NOT the bbox width.
    dia = 0.0
    for p in pts:
        dia = max(dia, 2.0 * math.sqrt(p.x * p.x + p.z * p.z))
    delta = dia - TARGET_GIRDLE_DIAMETER
    flag = "" if abs(delta) < 1e-6 else "  !! off target"
    out.append(f"    girdle diameter : {dia:.6f} cm "
               f"(target {TARGET_GIRDLE_DIAMETER}, delta {delta:+.2g}){flag}")

    # Table facet: import_gemcad_asc:649 calls a facet the table when its
    # outward normal.y > 0.999 (~2.6 deg of +Y).  Always report the flattest
    # up-facing normal alongside the verdict: a bare "none found" cannot tell
    # a design with genuinely no table (a mirrored top is a mirrored pavilion,
    # which ends in a culet) from a table tilted just past the cutoff.  Slivers
    # are skipped -- their normals are garbage and could fake a table.
    # Report the LADDER of up-facing facets, not a yes/no.  Whether the
    # flattest facet is a table or merely the shallowest ring of a shallow
    # design cannot be decided by any single cutoff -- but it is obvious from
    # the gap between the first row and the second.  A verdict here would just
    # be a hardcoded threshold pretending to know the design's intent.
    rings = {}
    for poly in polys:
        if _poly_thinness(pts, poly) < DEGENERATE_RATIO:
            continue                      # sliver normals are garbage
        n = _poly_normal(pts, poly)
        if n.GetLength() < 1e-12:
            continue
        ny = n.GetNormalized().y
        if ny <= 0.5:
            continue                      # not meaningfully up-facing
        key = round(ny, 6)                # symmetric rings share a normal
        cnt, area = rings.get(key, (0, 0.0))
        rings[key] = (cnt + 1, area + _poly_area(pts, poly))

    if not rings:
        out.append("    up-facing facets: none above 30 deg from horizontal")
        return
    ladder = sorted(rings.items(), key=lambda kv: -kv[0])
    out.append("    up-facing facets (flattest first; a table shows as one "
               "flat row clear of the next):")
    for ny, (cnt, area) in ladder[:5]:
        tilt = math.degrees(math.acos(max(-1.0, min(1.0, ny))))
        out.append(f"       normal.y={ny:.6f}  {tilt:5.2f} deg off +Y  "
                   f"{cnt:3d} polys  area={area:.4g} cm^2")
    if len(ladder) > 5:
        out.append(f"       ... (+{len(ladder) - 5} more rings)")
    qualifies = sum(c for ny, (c, _) in ladder if ny > 0.999)
    out.append(f"    importer's table rule (normal.y > 0.999): "
               f"{qualifies} polys qualify"
               + ("" if qualifies else "  -> no 'table' facet flagged"))


def _global_edge_to_pair(polys, gidx):
    """Map a C4D global edge index back to an undirected (lo, hi) point pair.

    Matches import_gemcad_asc's convention exactly: global index = 4*poly +
    local, with local 0=a-b, 1=b-c, 2=c-d, 3=d-a.  Triangles (d == c) only
    ever use locals 0, 1 and 3 -- local 2 would be the degenerate c-c side.
    Returns None for an out-of-range or degenerate side.
    """
    t, local = divmod(gidx, 4)
    if t >= len(polys):
        return None
    poly = polys[t]
    corners = (poly.a, poly.b, poly.c, poly.d)
    p, q = corners[local], corners[(local + 1) % 4]
    if p == q:                      # degenerate side of a triangle
        return None
    return (p, q) if p < q else (q, p)


def _pair_to_global_edges(polys, pair):
    """Every global edge index that addresses the point pair ``pair``.

    The inverse of _global_edge_to_pair, and necessarily one-to-many: an
    interior edge is named once per polygon that owns it, and C4D's edge
    selections carry every one of those sides.  Selecting only one side leaves
    the tag half-set, which is how an edge selection ends up looking correct
    in the tag and wrong in the viewport.
    """
    hits = []
    for t, poly in enumerate(polys):
        corners = (poly.a, poly.b, poly.c, poly.d)
        for local in range(4):
            p, q = corners[local], corners[(local + 1) % 4]
            if p == q:
                continue
            key = (p, q) if p < q else (q, p)
            if key == pair:
                hits.append(4 * t + local)
    return hits


def _find_edge_selection(op, name):
    """Return the BaseSelect of the edge-selection tag called ``name``."""
    for tag in op.GetTags():
        if tag.GetType() == c4d.Tedgeselection and tag.GetName() == name:
            return tag.GetBaseSelect()
    return None


def _gem_edge_pairs(op, polys):
    """Read the "Gem Edges" selection into a set of undirected point pairs.

    Returns None when the tag is absent, else a dict with the ``pairs`` set
    plus the raw per-side count and any strays.  Computed once and shared, so
    the short-edge cross-reference and the edge report cannot disagree.
    """
    bs = _find_edge_selection(op, GEM_EDGE_TAG)
    if bs is None:
        return None
    pairs = set()
    stray = 0
    sides = 0
    for gidx in range(4 * len(polys)):
        if not bs.IsSelected(gidx):
            continue
        sides += 1
        pair = _global_edge_to_pair(polys, gidx)
        if pair is None:
            stray += 1
        else:
            pairs.add(pair)
    return {"pairs": pairs, "sides": sides, "stray": stray}


def _dihedral_edges(pts, polys):
    """The edges the *surface itself* says are real: every manifold edge whose
    two facets meet at more than GEM_EDGE_MIN_DIHEDRAL degrees.

    This is the ground truth the "Gem Edges" tag is supposed to hold, derived
    from the mesh rather than trusted from the tag -- which is what lets the
    report catch a wrong selection and the fix rebuild a right one.  Facets
    with garbage normals (slivers) are excluded: they would otherwise report a
    bend at every edge they touch.
    """
    cop_dot = math.cos(math.radians(GEM_EDGE_MIN_DIHEDRAL))
    should_be = set()
    for e, owners in _unique_edges(polys).items():
        if len(owners) != 2:
            continue                      # boundary/non-manifold: reported above
        n0 = _poly_normal(pts, polys[owners[0]])
        n1 = _poly_normal(pts, polys[owners[1]])
        if n0.GetLength() < 1e-12 or n1.GetLength() < 1e-12:
            continue
        if n0.GetNormalized().Dot(n1.GetNormalized()) < cop_dot:
            should_be.add(e)              # surface changes angle -> real edge
    return should_be


def _gem_edges_report(op, pts, polys, gem, out):
    """Compare the mesh's edges against the "Gem Edges" selection.

    The goal for an exported gem is that every edge in the mesh IS a gem edge
    -- i.e. the fan-triangulation diagonals have been dissolved and each facet
    is a single n-gon.  This reports the gap between that target and reality,
    and independently re-derives which edges *should* be gem edges from the
    dihedral angle, so a wrong selection is caught rather than trusted.
    """
    if gem is None:
        out.append(f"  Gem edges: no '{GEM_EDGE_TAG}' selection tag "
                   f"(skipping edge-vs-selection check)")
        return
    selected_pairs = gem["pairs"]
    sel_side_count = gem["sides"]
    stray = gem["stray"]

    # --- all mesh edges + the polys touching each -------------------------
    edge_polys = _unique_edges(polys)
    total_edges = len(edge_polys)

    out.append("  Gem edges (vs mesh)")
    out.append(f"    '{GEM_EDGE_TAG}' selection : {sel_side_count} sides "
               f"-> {len(selected_pairs)} unique edges")
    out.append(f"    mesh unique edges      : {total_edges}")
    if stray:
        out.append(f"    !! {stray} selected sides map to degenerate/invalid "
                   f"edges")

    # --- re-derive the truth from dihedral angle --------------------------
    should_be = _dihedral_edges(pts, polys)

    extra = [e for e in edge_polys if e not in selected_pairs]
    missing = sorted(should_be - selected_pairs)
    false_pos = sorted(selected_pairs - should_be)

    # Extra edges split into the two cases that matter: flat interior edges
    # (dissolvable triangulation diagonals) vs edges that actually bend.
    extra_flat = [e for e in extra if e not in should_be]

    if not extra:
        out.append("    OK: every mesh edge is a gem edge (no extras)")
    else:
        pct = 100.0 * len(extra) / total_edges if total_edges else 0.0
        out.append(f"    !! extra edges (not gem edges): {len(extra)} "
                   f"({pct:.1f}% of mesh)")
        out.append(f"       of which flat/dissolvable diagonals: "
                   f"{len(extra_flat)}")
        # Dissolving one interior edge merges two polys into one.
        out.append(f"       -> dissolving them: {len(polys)} polys ->"
                   f" {len(polys) - len(extra_flat)} facets, "
                   f"{total_edges} edges -> {total_edges - len(extra_flat)}")

    _report_group(out, "MISSING gem edges (surface bends but not selected)",
                  missing, fmt=lambda e: f"{e[0]}-{e[1]}")
    _report_group(out, "false gem edges (selected but coplanar/flat)",
                  false_pos, fmt=lambda e: f"{e[0]}-{e[1]}")


def _tags_report(op, pts, polys, out):
    """Enumerate tags and dig into Phong / UVW / selection / material tags."""
    tags = op.GetTags()
    out.append(f"  Tags ({len(tags)})")
    for tag in tags:
        tid = tag.GetType()
        name = tag.GetName()
        if tid == c4d.Tphong:
            ang = tag[c4d.PHONGTAG_PHONG_ANGLE]
            limit = tag[c4d.PHONGTAG_PHONG_ANGLELIMIT]
            out.append(f"    Phong        : angle={math.degrees(ang):.1f} deg"
                       f"  anglelimit={'on' if limit else 'off'}")
        elif tid == c4d.Tuvw:
            _uvw_report(tag, pts, polys, out)
        elif tid == c4d.Tnormal:
            out.append(f"    Normal tag   : '{name}' (explicit vertex normals)")
        elif tid == c4d.Tpolygonselection:
            cnt = tag.GetBaseSelect().GetCount()
            out.append(f"    Poly select  : '{name}' ({cnt} polys)")
        elif tid == c4d.Tpointselection:
            cnt = tag.GetBaseSelect().GetCount()
            out.append(f"    Point select : '{name}' ({cnt} points)")
        elif tid == c4d.Tedgeselection:
            cnt = tag.GetBaseSelect().GetCount()
            out.append(f"    Edge select  : '{name}' ({cnt} edges)")
        elif tid == c4d.Ttexture:
            mat = tag[c4d.TEXTURETAG_MATERIAL]
            proj = tag[c4d.TEXTURETAG_PROJECTION]
            matname = mat.GetName() if mat else "<none>"
            out.append(f"    Texture      : material='{matname}' "
                       f"projection={proj}")
        else:
            # C4D's internal Tpoint/Tpolygon data tags report an empty type
            # name, so fall back to the numeric id rather than a blank line.
            label = tag.GetTypeName() or f"<type {tid}>"
            out.append(f"    {label:13s}: '{name}'")


def _uvw_report(tag, pts, polys, out):
    """UV sanity: out-of-[0,1], zero-area UV faces, UV/geo winding mismatch."""
    n = tag.GetDataCount()
    out_of_bounds = 0
    zero_area = 0
    flipped = 0
    for i in range(min(n, len(polys))):
        uvw = tag.GetSlow(i)
        corners = [uvw["a"], uvw["b"], uvw["c"]]
        if not _poly_is_tri(polys[i]):
            corners.append(uvw["d"])
        for uv in corners:
            if uv.x < -1e-6 or uv.x > 1 + 1e-6 or uv.y < -1e-6 or uv.y > 1 + 1e-6:
                out_of_bounds += 1
                break
        # Signed UV area (a-b-c) for winding / collapse.
        a, b, cc = corners[0], corners[1], corners[2]
        sa = 0.5 * ((b.x - a.x) * (cc.y - a.y) - (cc.x - a.x) * (b.y - a.y))
        if abs(sa) < 1e-12:
            zero_area += 1
        elif sa < 0:
            flipped += 1
    out.append(f"    UVW          : {n} faces  out-of-[0,1]={out_of_bounds}  "
               f"zero-area={zero_area}  flipped-winding={flipped}")


def _report_group(out, label, items, fmt):
    """Report a problem list: count, then up to MAX_LIST formatted entries."""
    if not items:
        out.append(f"    {label}: 0")
        return
    marker = "!! " if items else ""
    out.append(f"    {marker}{label}: {len(items)}")
    shown = items[:MAX_LIST]
    out.append("       " + ", ".join(fmt(x) for x in shown)
               + (f"  ... (+{len(items) - MAX_LIST} more)"
                  if len(items) > MAX_LIST else ""))


def dump_object(op, doc, out):
    """Append a full geometry report for one object to ``out`` (list of str)."""
    out.append("=" * 72)
    out.append(f"OBJECT  '{op.GetName()}'   type={op.GetTypeName()}")

    poly, converted = _as_polygon_object(op, doc)
    if poly is None:
        out.append("  (not a polygon object and could not be polygonized; "
                   "nothing to inspect)")
        return None
    if converted:
        out.append("  [polygonized via Current-State-to-Object for inspection; "
                   "original unchanged]")

    _matrix_report(op, out)

    pts = poly.GetAllPoints()
    polys = poly.GetAllPolygons()
    if not pts or not polys:
        out.append("  (no points/polygons)")
        return None

    # Read once, share everywhere: the short-edge cross-reference and the
    # gem-edge report must be talking about the same set of edges.
    gem = _gem_edge_pairs(poly, polys)

    _counts_and_bbox(poly, pts, polys, out)
    _topology_report(pts, polys, out)
    _quality_report(pts, polys, gem, out)
    _near_meet_report(pts, polys, out)
    _convexity_report(pts, polys, out)
    _gem_metrics_report(pts, polys, out)
    _gem_edges_report(poly, pts, polys, gem, out)
    _tags_report(poly, pts, polys, out)

    if DUMP_ALL_POINTS:
        out.append("  Points")
        for i, p in enumerate(pts):
            out.append(f"    [{i}] {_fmt_vec(p)}")

    # The fix pass needs the real, persistent mesh -- a CSTO copy is thrown
    # away the moment this returns, so there is nothing to repair there.
    return None if converted else poly


# ============================================================================
# 4. Fix pass
# ============================================================================
#
# The three repairs are ordered by what each one invalidates:
#
#   1. weld      -- merges the clipper's split meet points.  Renumbers POINTS
#                   and deletes the degenerate polys that collapse.
#   2. dissolve  -- melts the flat triangulation diagonals so each facet is one
#                   n-gon.  Renumbers POLYGONS.
#   3. gem edges -- rebuilds the selection from the dihedral angle of the final
#                   mesh.  Must run last: an edge selection is addressed by
#                   4*polygon+side, so steps 1 and 2 both scramble it.
#
# Rebuilding the selection from geometry rather than remapping the old one is
# also what fixes the false gem edges for free -- a coplanar edge simply never
# gets re-selected.  The cost is that any hand-made deviation from "every edge
# that bends is a gem edge" is discarded, which is the intended contract here.

def _weld_tolerance(pts, polys, out):
    """Pick this object's weld tolerance from its own weld window.

    Returns the tolerance, or None when welding would not be safe.  A gem's
    defect scale is a property of the design and the clipper that cut it --
    Twisted Sixer's defects run to 1.7e-4 while SIUQRAM's stop at 3.1e-5 --
    so a single constant is either too timid for one or destructive to the
    other.  When the window is too narrow to separate the two populations,
    this refuses: no weld is better than one that eats real edges.
    """
    window = _weld_window(pts, polys)
    if window is None:
        out.append("    weld: no short edges -> nothing to weld")
        return None
    worst, nxt, suggest = window
    if nxt / worst < MIN_WELD_GAP:
        out.append(f"    !! weld SKIPPED: window {worst:.3g}..{nxt:.3g} cm is "
                   f"only {nxt / worst:.1f}x wide (need {MIN_WELD_GAP}x) -- no "
                   f"tolerance separates defects from real edges")
        return None
    return suggest


def _do_weld(op, doc, pts, polys, out):
    """Weld the split meet points via C4D's own Optimize.

    Optimize is used in preference to rebuilding the point list by hand
    because it also carries the UVW and selection tags across the renumbering;
    a hand-rolled weld would silently invalidate every tag on the object.
    """
    tol = _weld_tolerance(pts, polys, out)
    if tol is None:
        return False

    before_v, before_f = len(pts), len(polys)
    bc = c4d.BaseContainer()
    bc[c4d.MDATA_OPTIMIZE_TOLERANCE] = tol
    bc[c4d.MDATA_OPTIMIZE_POINTS] = True
    bc[c4d.MDATA_OPTIMIZE_POLYGONS] = True      # drops the collapsed polys
    bc[c4d.MDATA_OPTIMIZE_UNUSEDPOINTS] = True
    ok = utils.SendModelingCommand(
        command=c4d.MCOMMAND_OPTIMIZE,
        list=[op],
        bc=bc,
        mode=c4d.MODELINGCOMMANDMODE_ALL,
        doc=doc,
    )
    if not ok:
        out.append(f"    !! weld FAILED: Optimize rejected tol={tol:.3g} cm")
        return False
    op.Message(c4d.MSG_UPDATE)
    after_v = op.GetPointCount()
    after_f = op.GetPolygonCount()
    out.append(f"    weld @ {tol:.3g} cm: V {before_v} -> {after_v} "
               f"({before_v - after_v} merged), F {before_f} -> {after_f} "
               f"({before_f - after_f} degenerate polys removed)")
    return True


def _do_dissolve(op, doc, out):
    """Melt the flat triangulation diagonals so each facet becomes one n-gon.

    Re-reads the mesh rather than reusing the dump's arrays: the weld above
    renumbered everything, and the diagonals worth dissolving are the ones in
    the mesh as it stands now, not the ones the dump saw.
    """
    pts = op.GetAllPoints()
    polys = op.GetAllPolygons()
    should_be = _dihedral_edges(pts, polys)
    edge_polys = _unique_edges(polys)

    # A diagonal is an interior edge the surface does not bend across.  The
    # owner check matters: a boundary edge is flat-by-default (it has no second
    # facet to disagree with) and melting it would open the solid.
    diagonals = [e for e, owners in edge_polys.items()
                 if len(owners) == 2 and e not in should_be]
    if not diagonals:
        out.append("    dissolve: no flat diagonals -> facets already n-gons")
        return False

    es = op.GetEdgeS()
    es.DeselectAll()
    sides = 0
    for e in diagonals:
        for gidx in _pair_to_global_edges(polys, e):
            es.Select(gidx)
            sides += 1

    before_f = len(polys)
    ok = utils.SendModelingCommand(
        command=c4d.MCOMMAND_MELT,
        list=[op],
        mode=c4d.MODELINGCOMMANDMODE_EDGESELECTION,
        doc=doc,
    )
    es.DeselectAll()
    if not ok:
        out.append(f"    !! dissolve FAILED: Melt rejected {len(diagonals)} "
                   f"edges")
        return False
    op.Message(c4d.MSG_UPDATE)
    out.append(f"    dissolve: melted {len(diagonals)} flat diagonals "
               f"({sides} sides), F {before_f} -> {op.GetPolygonCount()}")
    return True


def _do_gem_edges(op, out):
    """Rebuild "Gem Edges" from the dihedral angle of the finished mesh.

    Rewrites the existing tag in place rather than replacing it, so anything
    else pointing at that tag (a Melt/Bevel deformer, an export step) keeps
    working.  Absent tag = nothing to rebuild; this does not invent one, since
    a gem with no gem-edge tag is a different problem than a wrong one.
    """
    tag = None
    for t in op.GetTags():
        if t.GetType() == c4d.Tedgeselection and t.GetName() == GEM_EDGE_TAG:
            tag = t
            break
    if tag is None:
        out.append(f"    gem edges: no '{GEM_EDGE_TAG}' tag -> nothing to "
                   f"rebuild")
        return False

    pts = op.GetAllPoints()
    polys = op.GetAllPolygons()
    should_be = _dihedral_edges(pts, polys)

    bs = tag.GetBaseSelect()
    before = bs.GetCount()
    bs.DeselectAll()
    sides = 0
    for e in should_be:
        for gidx in _pair_to_global_edges(polys, e):
            bs.Select(gidx)
            sides += 1
    op.Message(c4d.MSG_UPDATE)
    out.append(f"    gem edges: rebuilt from dihedral > "
               f"{GEM_EDGE_MIN_DIHEDRAL} deg -> {len(should_be)} edges "
               f"({sides} sides, was {before} sides)")
    return True


def fix_object(op, doc, out):
    """Repair one polygon object in place; append a "Fix" block to ``out``.

    ``op`` must be the real, persistent PolygonObject -- dump_object returns
    it, or None when there is nothing repairable.  The caller owns the undo
    step; this only touches the mesh.
    """
    out.append("  Fix")
    pts = op.GetAllPoints()
    polys = op.GetAllPolygons()
    if not pts or not polys:
        out.append("    (no points/polygons -- nothing to fix)")
        return

    changed = False
    if FIX_WELD:
        changed |= _do_weld(op, doc, pts, polys, out)
    if FIX_DISSOLVE:
        changed |= _do_dissolve(op, doc, out)
    if FIX_GEM_EDGES:
        changed |= _do_gem_edges(op, out)

    if not changed:
        out.append("    nothing changed -- mesh already meets the targets")


# ============================================================================
# 5. Entry point
# ============================================================================

def main():
    doc = c4d.documents.GetActiveDocument()
    selection = doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_CHILDREN)
    if not selection:
        c4d.gui.MessageDialog("Select at least one object to inspect.")
        return

    out = [f"Geometry dump: {len(selection)} object(s) selected", ""]
    doc.StartUndo()
    try:
        for op in selection:
            try:
                poly = dump_object(op, doc, out)
                if poly is not None:
                    doc.AddUndo(c4d.UNDOTYPE_CHANGE, poly)
                    fix_object(poly, doc, out)
                    if VERIFY_AFTER_FIX:
                        out.append("")
                        out.append("  --- after fix " + "-" * 57)
                        dump_object(poly, doc, out)
            except Exception as exc:  # noqa: BLE001
                out.append(f"  ERROR inspecting '{op.GetName()}': {exc}")
            out.append("")
    finally:
        doc.EndUndo()
    c4d.EventAdd()

    report = "\n".join(out)
    print(report)

    if COPY_TO_CLIPBOARD:
        c4d.CopyStringToClipboard(report)
        print("[dump] report copied to clipboard")


if __name__ == "__main__":
    if HAVE_C4D:
        main()
    else:
        print("This inspector requires Cinema 4D (run it from the Script "
              "Manager with an object selected).")
