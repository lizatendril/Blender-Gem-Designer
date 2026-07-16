## Alias Documentation

Check Model Parameters
Rationals
Check for rational geometry.

Periodics
Check for periodic (closed) objects.

Multiple Trim Regions
Use this check to find instances where trims have made a single surface look like separate surfaces, which can confuse some CAD software packages.

Multiple Knots
Check for multi-knots (multiple edit points at the same point in space that may create a sharp corner in a curve or surface).

Internal Tangent Discontinuity
Report objects with internal tangent discontinuities due to multi-knots.

Non-Planar Curves
Check for curves that are not planar. This option only appears when Check is set to Curves or Both.

Product Data Quality Recommended Checks
Duplicate Geometry
Off – No check is done for duplicate or embedded geometry.

Copies – Checks for curves or surfaces that are exact duplicates of each other. Copies have the same CVs, same knots, and same degree. If Report is set to All, the original object is marked “Original” in the Copies column of the Check Model Results window.

Duplicates Within Tolerance – Checks for curves and surfaces that are duplicates of, or embedded into other curves and surfaces, within the tolerance given in the Duplicate Tolerance field.

Duplicate Tolerance
This field appears when Duplicate Geometry is set to Duplicates Within Tolerance. Curves or surfaces that lie within that distance of each other are reported.

Short edges
Check for edges (including trimmed edges) shorter than the distance specified in the text field. This check also finds T-connection situations where the corners of surfaces are close, but not close enough (they are within the topology distance but not within the max gap distance).

Tiny Spans
Check for curves and surfaces whose interior span/isoparm configuration results in the length of a span (or the length of both opposing patch segments for surfaces) being smaller than the distance tolerance specified in the text field.

Indistinct Knots
Check for curves and surfaces whose interior span/isoparm configuration results in knots being closer in parameter value than the tolerance specified in the text field.

Note: This check does not report multiple knots for which a separate check already exists (see Multiple Knots).
Minimum Radius of Curvature
Report surfaces that have a radius of curvature smaller than a user-defined value. The smallest radius found on those surfaces is reported.

Curve or Surf-Boundary Self-Intersect
Report curves, surface boundaries, or trimmed surface boundaries that contain interior self-intersections. A self-intersection refers to the curve or surface boundary intersecting itself at one or more locations that are not both endpoints.

Trimmed-Surf Boundary Intersect
Report trimmed surfaces containing boundaries that intersect other boundaries on the same surface, within the tolerance supplied in the text field.

Maximum Degree
Check for objects with a degree higher than the number specified in the text field.

Maximum Spans
Report curves and surfaces that contain a number of spans exceeding the value specified in the text field.

Surface or Planar Curve Waviness
Report surfaces or planar curves that have more than a user-defined number of inflections (change in curvature sign) over their entire length (or width for surfaces). The maximum number of inflections allowed is entered in the text field (default is 3).

Allowed Inflections Per Span
This field only appears when Surface Curvature Waviness is ON. When turned on, it controls the maximum number of inflections per span allowed for a surface to pass the waviness test, in addition to the overall number of inflection permitted (see previous option). The default is 1.

Degenerate Surfaces
When turned on, your model is checked for the following issues in order of decreasing severity:

Singular Edge - All CVs on some edge(s) have the same coordinates.
Null Span - All CVs which belong to the same NURBS span on the edge are equal.
Duplicate CVs - Two or more CVs on the edge are colliding.
Bad Corner - Angle between hull edges at a surface corner is either 0 or 180 degrees.
If more than one of these issues is detected, the most severe one is flagged and reported in the Check Model Results window.

Visual Normal Consistency
Check for surfaces whose normal direction is inconsistent with the visual normal direction of adjacent surfaces.

Note: The Topology Distance tolerance in Preferences > Construction Options must be larger than the Maximum Gap Distance for this check to find inconsistent normals.
Geometric Normal Consistency
Check for surfaces whose normal direction is inconsistent with the geometric normal direction of adjacent surfaces.

Note: The Topology Distance tolerance in Preferences > Construction Options must be larger than the Maximum Gap Distance for this check to find inconsistent normals.
Use Custom Tolerances
Override the tolerances selected in Construction Presets ( Preferences > Construction Options and perform checks using custom tolerances.

Max Gap Distance - G0
Report objects that exceed a user-defined tolerance for positional continuity between adjacent curves or surfaces.

The tolerance value is given by Maximum Gap Distance in the Tolerances Continuity section of Preferences > Construction Options. Select Use Custom Tolerances to override this value here.

Note: The Topology Distance tolerance in Preferences > Construction Options must be larger than the Maximum Gap Distance for this check to find gaps. Select Use Custom Tolerances to override this value under Report Parameters.
Tangent Angle - G1
Report objects that exceed a user-defined tolerance for tangent continuity between adjacent curves or surfaces.

The tolerance value is given by Continuity Angle in the Tolerances Continuity section of Preferences > Construction Options. Select Use Custom Tolerances to override this value here.

Note: The Topology Distance tolerance in Preferences > Construction Options must be larger than the Maximum Gap Distance for this check to find tangent discontinuities. Select Use Custom Tolerances to override this value under Report Parameters.
Curvature - G2
Report objects that exceed a user-defined tolerance for curvature continuity between adjacent curves or surfaces.

The curvature deviation is calculated as:



The tolerance value is given by Continuity Curvature in the Tolerances Continuity section of Preferences > Construction Options. Select Use Custom Tolerances to override this value here.

Note: The Topology Distance tolerance in Preferences > Construction Options must be larger than the Maximum Gap Distance for this check to find curvature discontinuities. Select Use Custom Tolerances to override this value under Report Parameters.
Report Parameters
Topology distance
Used to calculate which surface is adjacent to which surface when a tool needs to know the topology of the model. This is used by the Transformer Rig, Surface Continuity , and Check Model.

Note: This should be set to a value greater than Maximum Gap Distance.
Tangent Angle Maximum
Maximum angle allowed between the tangents (or normals) of objects for them to be included in the G1 continuity test.

Curvature Maximum
Maximum curvature deviation allowed between objects for them to be included in the G2 continuity test.

Note: G0, G1, G2, and Normal Consistency checks are only performed if the maximum distance between the objects is less than the Topology Distance found in Preferences > Construction Options.