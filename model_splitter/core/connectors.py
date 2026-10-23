"""
ModelSplitter - Connector Generation (Pins & Sockets)
Generates high-precision alignment pins (Cylinders, Cones, Rectangles, Custom Keys)
and matching clearance-dilated sockets for 3D printed assembly.
"""

import math
import bpy
import bmesh
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from ..utils.math_utils import mm_to_scene_units, rotation_align_vector, distribute_connectors_2d


def build_cylinder_mesh(radius, length, anchor_depth=0.0, taper_ratio=1.0, segments=32, double_sided=False):
    """
    Creates a cylinder or tapered frustum mesh in bmesh.
    - Single-sided: Root anchor extends into -Z by anchor_depth; shaft extends into +Z by length.
    - Double-sided: Symmetric dowel pin extending from -length to +length across Z=0.
    """
    bm = bmesh.new()

    r_base = radius
    r_top = radius * taper_ratio

    if double_sided:
        z_bottom = -length
        z_base = 0.0
        z_top = length
        r_bottom = r_top
    else:
        z_bottom = -anchor_depth
        z_base = 0.0
        z_top = length
        r_bottom = radius

    has_bottom_ring = double_sided or (anchor_depth > 0.0)

    # Build circle vertices
    bottom_verts = []
    base_verts = []
    top_verts = []

    for i in range(segments):
        theta = i * (2.0 * math.pi / segments)
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)

        if has_bottom_ring:
            bottom_verts.append(bm.verts.new(Vector((cos_t * r_bottom, sin_t * r_bottom, z_bottom))))
        base_verts.append(bm.verts.new(Vector((cos_t * r_base, sin_t * r_base, z_base))))
        top_verts.append(bm.verts.new(Vector((cos_t * r_top, sin_t * r_top, z_top))))

    # Connect side faces
    if has_bottom_ring:
        for i in range(segments):
            next_i = (i + 1) % segments
            bm.faces.new([bottom_verts[i], bottom_verts[next_i], base_verts[next_i], base_verts[i]])
        # Cap bottom
        bm.faces.new(list(reversed(bottom_verts)))
    else:
        # Cap base
        bm.faces.new(list(reversed(base_verts)))

    for i in range(segments):
        next_i = (i + 1) % segments
        bm.faces.new([base_verts[i], base_verts[next_i], top_verts[next_i], top_verts[i]])

    # Cap top
    bm.faces.new(top_verts)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def build_rectangular_mesh(width, depth, length, anchor_depth=0.0, double_sided=False):
    """
    Creates a rectangular key mesh with root anchor or symmetric double-sided dowel length.
    """
    bm = bmesh.new()
    hw = width * 0.5
    hd = depth * 0.5
    z_bottom = -length if double_sided else -anchor_depth
    z_top = length

    # 8 vertices of cuboid
    coords = [
        Vector((-hw, -hd, z_bottom)),
        Vector((hw, -hd, z_bottom)),
        Vector((hw, hd, z_bottom)),
        Vector((-hw, hd, z_bottom)),
        Vector((-hw, -hd, z_top)),
        Vector((hw, -hd, z_top)),
        Vector((hw, hd, z_top)),
        Vector((-hw, hd, z_top)),
    ]

    verts = [bm.verts.new(co) for co in coords]

    # 6 faces
    bm.faces.new([verts[0], verts[3], verts[2], verts[1]])  # Bottom
    bm.faces.new([verts[4], verts[5], verts[6], verts[7]])  # Top
    bm.faces.new([verts[0], verts[1], verts[5], verts[4]])  # Front
    bm.faces.new([verts[1], verts[2], verts[6], verts[5]])  # Right
    bm.faces.new([verts[2], verts[3], verts[7], verts[6]])  # Back
    bm.faces.new([verts[3], verts[0], verts[4], verts[7]])  # Left

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm



def build_d_pin_mesh(radius, length, anchor_depth=0.0, flat_ratio=0.35, segments=32, double_sided=False):
    """
    Creates a D-shaped pin with a planar flat chord to physically prevent rotation.
    """
    bm = bmesh.new()
    flat_x = radius * (1.0 - flat_ratio)
    z_bottom = -length if double_sided else -anchor_depth
    z_base = 0.0
    z_top = length
    has_bottom_ring = double_sided or (anchor_depth > 0.0)

    bottom_verts = []
    base_verts = []
    top_verts = []

    for i in range(segments):
        theta = i * (2.0 * math.pi / segments)
        px = math.cos(theta) * radius
        py = math.sin(theta) * radius
        if px > flat_x:
            px = flat_x
        if has_bottom_ring:
            bottom_verts.append(bm.verts.new(Vector((px, py, z_bottom))))
        base_verts.append(bm.verts.new(Vector((px, py, z_base))))
        top_verts.append(bm.verts.new(Vector((px, py, z_top))))

    if has_bottom_ring:
        for i in range(segments):
            next_i = (i + 1) % segments
            bm.faces.new([bottom_verts[i], bottom_verts[next_i], base_verts[next_i], base_verts[i]])
        bm.faces.new(list(reversed(bottom_verts)))
    else:
        bm.faces.new(list(reversed(base_verts)))

    for i in range(segments):
        next_i = (i + 1) % segments
        bm.faces.new([base_verts[i], base_verts[next_i], top_verts[next_i], top_verts[i]])

    bm.faces.new(top_verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def build_ball_joint_mesh(radius, length, anchor_depth=0.0, clearance=0.0, is_socket=False):
    """
    Creates a ball joint male pin (neck + sphere head) or dilated female socket cavity.
    """
    bm = bmesh.new()
    r_sphere = radius + clearance
    neck_r = (radius * 0.55) + clearance
    z_bottom = -(anchor_depth + clearance)

    sphere_center = Vector((0.0, 0.0, max(length * 0.6, radius * 1.1)))
    bmesh.ops.create_uvsphere(
        bm,
        u_segments=16,
        v_segments=16,
        radius=r_sphere,
    )
    for v in bm.verts:
        v.co += sphere_center

    neck_top_z = sphere_center.z - (r_sphere * 0.6)
    segments = 16
    bot_ring = []
    top_ring = []
    for i in range(segments):
        th = i * (2.0 * math.pi / segments)
        bx = math.cos(th) * neck_r
        by = math.sin(th) * neck_r
        bot_ring.append(bm.verts.new(Vector((bx, by, z_bottom))))
        top_ring.append(bm.verts.new(Vector((bx, by, neck_top_z))))

    for i in range(segments):
        ni = (i + 1) % segments
        bm.faces.new([bot_ring[i], bot_ring[ni], top_ring[ni], top_ring[i]])
    bm.faces.new(list(reversed(bot_ring)))

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm

def build_custom_connector_mesh(custom_obj, radius, length, anchor_depth=0.0, clearance=0.0, double_sided=False):
    """
    Normalizes a user-supplied custom mesh to the target connector diameter, length,
    anchor depth (or double-sided span), and radial/axial clearance.
    """
    bm = bmesh.new()
    bm.from_mesh(custom_obj.data)
    if not bm.verts:
        bm.free()
        return build_cylinder_mesh(radius + clearance, length + clearance, anchor_depth=anchor_depth, double_sided=double_sided)

    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    zs = [v.co.z for v in bm.verts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_z, max_z = min(zs), max(zs)

    cx = 0.5 * (min_x + max_x)
    cy = 0.5 * (min_y + max_y)
    span_xy = max(max_x - min_x, max_y - min_y, 1e-6)
    span_z = max(max_z - min_z, 1e-6)

    target_diam = (radius + clearance) * 2.0
    scale_xy = target_diam / span_xy
    z_bottom = -(length + clearance) if double_sided else -anchor_depth
    z_top = length + clearance
    target_z_span = max(z_top - z_bottom, 1e-6)

    for v in bm.verts:
        nx = (v.co.x - cx) * scale_xy
        ny = (v.co.y - cy) * scale_xy
        tz = (v.co.z - min_z) / span_z
        nz = z_bottom + tz * target_z_span
        v.co = Vector((nx, ny, nz))

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def create_single_connector_pair(
    context,
    shape='CYLINDER',
    radius=0.0025,
    length=0.01,
    clearance=0.0002,
    cut_gap=0.0,
    taper_angle_deg=5.0,
    double_sided=False,
    custom_obj=None,
    target_collection=None,
    name_prefix="Connector"
):
    """
    Creates (pin_obj, socket_obj) pair in world space aligned along local Z axis.
    pin_obj: Placed on male part with root anchor (or symmetric loose dowel when double_sided=True).
    socket_obj: Dilated by clearance in radius and depth for zero-friction fit.
    """
    col = target_collection or context.collection

    # Taper ratio for conical pins
    taper_ratio = 1.0
    if shape == 'CONICAL':
        taper_drop = math.tan(math.radians(taper_angle_deg)) * length
        taper_ratio = max(0.2, (radius - taper_drop) / radius)

    anchor_depth = max(length * 0.35, radius * 0.6) + cut_gap

    # --- 1. BUILD PIN OBJECT ---
    pin_mesh = bpy.data.meshes.new(f"{name_prefix}_Pin_Mesh")
    if shape in ('CYLINDER', 'CONICAL'):
        bm_pin = build_cylinder_mesh(
            radius, length, anchor_depth=anchor_depth, taper_ratio=taper_ratio, double_sided=double_sided
        )
    elif shape == 'D_PIN':
        bm_pin = build_d_pin_mesh(
            radius, length, anchor_depth=anchor_depth, double_sided=double_sided
        )
    elif shape == 'MAGNET':
        # Magnet pin is a disc marker in the cavity
        bm_pin = build_cylinder_mesh(
            radius, length, anchor_depth=anchor_depth, double_sided=True
        )
    elif shape == 'BALL_JOINT':
        bm_pin = build_ball_joint_mesh(
            radius, length, anchor_depth=anchor_depth, clearance=0.0, is_socket=False
        )
    elif shape == 'RECTANGULAR':
        bm_pin = build_rectangular_mesh(
            radius * 2, radius * 1.4, length, anchor_depth=anchor_depth, double_sided=double_sided
        )
    elif shape == 'CUSTOM' and custom_obj and custom_obj.type == 'MESH':
        bm_pin = build_custom_connector_mesh(
            custom_obj, radius, length, anchor_depth=anchor_depth, clearance=0.0, double_sided=double_sided
        )
    else:
        bm_pin = build_cylinder_mesh(radius, length, anchor_depth=anchor_depth, double_sided=double_sided)

    bm_pin.to_mesh(pin_mesh)
    bm_pin.free()

    pin_obj = bpy.data.objects.new(f"{name_prefix}_Pin", pin_mesh)
    col.objects.link(pin_obj)

    # --- 2. BUILD SOCKET OBJECT (DILATED BY CLEARANCE) ---
    socket_mesh = bpy.data.meshes.new(f"{name_prefix}_Socket_Mesh")
    s_radius = radius + clearance
    s_length = length + clearance + cut_gap * 0.5
    # Sockets extend slightly behind Z=0 so curved cutting surfaces or cut gaps never leave a skin over the opening
    s_anchor = max(clearance * 2.0, s_radius * 0.45) + cut_gap

    if shape in ('CYLINDER', 'CONICAL'):
        bm_socket = build_cylinder_mesh(
            s_radius, s_length, anchor_depth=s_anchor, taper_ratio=taper_ratio, double_sided=double_sided
        )
    elif shape == 'D_PIN':
        bm_socket = build_d_pin_mesh(
            s_radius, s_length, anchor_depth=s_anchor, double_sided=double_sided
        )
    elif shape == 'MAGNET':
        # Magnet socket carves recessed cavities into both split parts so disc magnets can be inserted
        bm_socket = build_cylinder_mesh(
            s_radius, s_length, anchor_depth=s_length, double_sided=True
        )
    elif shape == 'BALL_JOINT':
        bm_socket = build_ball_joint_mesh(
            radius, length, anchor_depth=s_anchor, clearance=clearance, is_socket=True
        )
    elif shape == 'RECTANGULAR':
        bm_socket = build_rectangular_mesh(
            (radius * 2) + (clearance * 2),
            (radius * 1.4) + (clearance * 2),
            s_length,
            anchor_depth=s_anchor,
            double_sided=double_sided,
        )
    elif shape == 'CUSTOM' and custom_obj and custom_obj.type == 'MESH':
        bm_socket = build_custom_connector_mesh(
            custom_obj, radius, s_length, anchor_depth=s_anchor, clearance=clearance, double_sided=double_sided
        )
    else:
        bm_socket = build_cylinder_mesh(s_radius, s_length, anchor_depth=s_anchor, double_sided=double_sided)

    bm_socket.to_mesh(socket_mesh)
    bm_socket.free()

    socket_obj = bpy.data.objects.new(f"{name_prefix}_Socket", socket_mesh)
    col.objects.link(socket_obj)

    return pin_obj, socket_obj


from .cutter_geometry import (
    build_cutter_surface_bvh,
    snap_local_xy_to_surface,
    is_point_inside_bvh,
    compute_cut_cross_section,
)


def _compute_cross_section_placements(cutter_obj, cut_plane_matrix, source_obj, count, pin_radius, fallback_bounds_radius):
    """
    Computes `count` (local_pos, local_norm) placements on the cutting surface strictly inside
    the 3D cross-section where the cutter slices `source_obj`, along with `max_wall`.
    Returns (placements, max_wall).
    """
    if count <= 0:
        return [], 0.0

    surface_bvh, src_bvh, cross_pts, interior_samples, best_center, bounds_2d = compute_cut_cross_section(
        cutter_obj, cut_plane_matrix, source_obj
    )

    if not best_center or not bounds_2d:
        # Fallback if cutter does not currently intersect source_obj
        spread_radius = max(pin_radius * 3.0, min(fallback_bounds_radius * 0.45, fallback_bounds_radius - pin_radius * 2.0))
        offsets_2d = distribute_connectors_2d(count, spread_radius)
        return [snap_local_xy_to_surface(surface_bvh, off.x, off.y) for off in offsets_2d], 0.0

    max_wall = max((s[2] for s in interior_samples), default=0.0)
    eff_pin_r = min(pin_radius, max_wall * 0.35) if max_wall > 1e-5 else pin_radius

    if count == 1:
        return [(best_center[0], best_center[1])], max_wall

    min_x, max_x, min_y, max_y = bounds_2d
    span_x = max_x - min_x
    span_y = max_y - min_y
    cx = best_center[0].x
    cy = best_center[0].y

    # Safe half-extents inside the actual cut cross-section
    rx = max(eff_pin_r * 1.15, min(span_x * 0.32, (span_x * 0.5) - eff_pin_r * 1.35))
    ry = max(eff_pin_r * 1.15, min(span_y * 0.32, (span_y * 0.5) - eff_pin_r * 1.35))

    # Build symmetric candidate 2D positions tailored to the cross-section aspect ratio
    sym_2d = []
    if count == 2:
        if span_x >= span_y:
            sym_2d = [(cx - rx, cy), (cx + rx, cy)]
        else:
            sym_2d = [(cx, cy - ry), (cx, cy + ry)]
    elif count == 3:
        if min(span_x, span_y) < eff_pin_r * 4.5:
            # Narrow cross-section: distribute colinearly along the longer axis
            if span_x >= span_y:
                sym_2d = [(cx - rx, cy), (cx, cy), (cx + rx, cy)]
            else:
                sym_2d = [(cx, cy - ry), (cx, cy), (cx, cy + ry)]
        else:
            for i in range(3):
                ang = i * (2.0 * math.pi / 3.0) + (math.pi * 0.5)
                sym_2d.append((cx + math.cos(ang) * rx * 0.85, cy + math.sin(ang) * ry * 0.85))
    elif count == 4:
        sym_2d = [
            (cx - rx * 0.8, cy - ry * 0.8),
            (cx + rx * 0.8, cy - ry * 0.8),
            (cx + rx * 0.8, cy + ry * 0.8),
            (cx - rx * 0.8, cy + ry * 0.8),
        ]
    else:
        sym_2d = [
            (cx, cy),
            (cx - rx * 0.85, cy),
            (cx + rx * 0.85, cy),
            (cx, cy - ry * 0.85),
            (cx, cy + ry * 0.85),
        ][:count]

    # Verify whether all symmetric candidates lie deep enough inside the solid cross-section
    min_req_wall = min(max_wall * 0.65, max(eff_pin_r * 1.1, max_wall * 0.28))

    valid_sym = []
    for sx, sy in sym_2d:
        loc_3d, norm_3d = snap_local_xy_to_surface(surface_bvh, sx, sy)
        if is_point_inside_bvh(src_bvh, loc_3d):
            _, _, _, w_dist = src_bvh.find_nearest(loc_3d) if src_bvh else (None, None, None, max_wall)
            w_d = float(w_dist or 0.0)
            if src_bvh:
                hp, np_h, _, dp = src_bvh.ray_cast(loc_3d, norm_3d, 10000.0)
                hn, nn_h, _, dn = src_bvh.ray_cast(loc_3d, -norm_3d, 10000.0)
                if hp is None or (np_h is not None and np_h.dot(norm_3d) <= 0.0):
                    w_d = 0.0
                if hn is not None and nn_h is not None and nn_h.dot(-norm_3d) <= 0.0:
                    w_d = 0.0
                if dp is not None:
                    w_d = min(w_d, float(dp))
                if dn is not None:
                    w_d = min(w_d, float(dn))
            if w_d >= min_req_wall:
                valid_sym.append((loc_3d, norm_3d))

    if len(valid_sym) == count:
        return valid_sym, max_wall

    # Fallback for concave / multi-island / L-shaped cross-sections:
    # Farthest-point sampling among deep interior cross-section samples
    pool = [s for s in interior_samples if s[2] >= min_req_wall]
    if len(pool) < count:
        pool = list(interior_samples)

    chosen = [best_center]
    while len(chosen) < count and pool:
        best_cand = None
        best_score = -1.0
        for cand in pool:
            min_d = min((cand[0] - c[0]).length for c in chosen)
            score = min_d + cand[2] * 0.35
            if score > best_score:
                best_score = score
                best_cand = cand
        if best_cand and best_score > 1e-5:
            chosen.append(best_cand)
        else:
            break

    return [(c[0], c[1]) for c in chosen], max_wall


def generate_cut_connectors(
    context,
    cut_plane_matrix,
    bounds_radius,
    target_collection=None,
    cutter_obj=None,
    source_obj=None,
    manual_xy_offsets=None,
):
    """
    Generates all requested connectors (1-5) positioned strictly inside the 3D cut cross-section
    (or at user-adjusted manual positions) and oriented perpendicular to the local cutting surface.
    Returns (list_of_pin_objs, list_of_socket_objs).
    """
    settings = context.scene.model_splitter
    con_props = settings.connector

    if getattr(con_props, "no_connectors", False):
        return [], []

    radius = mm_to_scene_units(context, con_props.diameter_mm * 0.5, ref_obj=source_obj)
    length = mm_to_scene_units(context, con_props.length_mm, ref_obj=source_obj)
    clearance = mm_to_scene_units(context, con_props.clearance_mm, ref_obj=source_obj)
    cut_gap = mm_to_scene_units(context, con_props.cut_gap_mm, ref_obj=source_obj)

    count = con_props.count
    auto_placements, max_wall = _compute_cross_section_placements(
        cutter_obj, cut_plane_matrix, source_obj, count, radius, bounds_radius
    )

    if manual_xy_offsets:
        surface_bvh = build_cutter_surface_bvh(cutter_obj) if cutter_obj else None
        placements = []
        for sx, sy in manual_xy_offsets[:count]:
            loc_3d, norm_3d = snap_local_xy_to_surface(surface_bvh, sx, sy)
            placements.append((loc_3d, norm_3d))
        # If user increased count while in MANUAL mode, fill remaining slots from auto_placements
        for extra in auto_placements[len(placements):count]:
            placements.append(extra)
    else:
        placements = auto_placements

    # If the cut is across a narrow appendage (e.g. ear or finger), clamp pin size so it fits inside the cross-section wall
    if max_wall > 1e-5 and getattr(con_props, "auto_fit_bounds", True) and not manual_xy_offsets:
        max_safe_r = max_wall * (0.48 if count == 1 else 0.35)
        max_safe_l = max_wall * 1.35
        if radius > max_safe_r or length > max_safe_l:
            clamp_scale = min(1.0, max_safe_r / max(radius, 1e-6), max_safe_l / max(length, 1e-6))
            radius *= clamp_scale
            length *= clamp_scale
            clearance *= clamp_scale


    pins = []
    sockets = []

    # Orientation:
    # Part A = source_obj DIFFERENCE cutter_volume -> occupies the -Z side of the cutting surface.
    # Part B = source_obj INTERSECT cutter_volume  -> occupies the +Z side of the cutting surface.
    # Pin mesh has root anchor in [-anchor_depth, 0] (-Z) and protruding shaft in [0, +length] (+Z).
    # Therefore:
    # - When target_side == 'PART_A' (male pin on Part A, socket in Part B), +Z already points from Part A into Part B!
    # - When target_side == 'PART_B' (male pin on Part B, socket in Part A), rotate 180 deg around local X (det = +1)
    #   so root is in +Z (Part B) and shaft points into -Z (Part A) without inverting face normals!
    use_double_span = bool(con_props.double_sided or getattr(con_props, "holes_only", False))
    if con_props.target_side == 'PART_A' or use_double_span:
        flip_mat = Matrix.Identity(4)
    else:
        flip_mat = Matrix.Rotation(math.pi, 4, Vector((1.0, 0.0, 0.0)))

    for i, (local_pos, local_norm) in enumerate(placements):
        pin_obj, socket_obj = create_single_connector_pair(
            context,
            shape=con_props.shape,
            radius=radius,
            length=length,
            clearance=clearance,
            cut_gap=cut_gap,
            taper_angle_deg=con_props.taper_angle,
            double_sided=use_double_span,
            custom_obj=con_props.custom_object,
            target_collection=target_collection,
            name_prefix=f"MS_Conn_{i+1}"
        )

        local_rot = rotation_align_vector(Vector((0.0, 0.0, 1.0)), local_norm)
        local_mat = Matrix.Translation(local_pos) @ local_rot @ flip_mat
        transform_mat = cut_plane_matrix @ local_mat

        pin_obj.matrix_world = transform_mat
        socket_obj.matrix_world = transform_mat

        pins.append(pin_obj)
        sockets.append(socket_obj)

    return pins, sockets
