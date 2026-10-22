"""
ModelSplitter - Cutter Geometry Engine
Builds half-space cutting volumes, planar visualizers, and interactive helper objects
from screen-space lines, curved sweeps, and 3D surface-drawn contours.
"""

import math
import bpy
import bmesh
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from bpy_extras import view3d_utils
from ..utils.math_utils import get_world_bounds, rotation_align_vector, mm_to_scene_units


def create_half_space_box(width, depth, height):
    """
    Creates a solid box where the bottom face lies precisely on the XY plane (Z = 0.0).
    The volume occupies Z in [0, height].
    This ensures clean half-space boolean cuts where Z < 0 is preserved by DIFFERENCE
    and Z > 0 is preserved by INTERSECT.
    """
    bm = bmesh.new()
    hw = width * 0.5
    hd = depth * 0.5

    coords = [
        Vector((-hw, -hd, 0.0)),
        Vector((hw, -hd, 0.0)),
        Vector((hw, hd, 0.0)),
        Vector((-hw, hd, 0.0)),
        Vector((-hw, -hd, height)),
        Vector((hw, -hd, height)),
        Vector((hw, hd, height)),
        Vector((-hw, hd, height)),
    ]

    verts = [bm.verts.new(co) for co in coords]

    # Solid box faces
    bm.faces.new([verts[0], verts[3], verts[2], verts[1]])  # Cutting face (bottom)
    bm.faces.new([verts[4], verts[5], verts[6], verts[7]])  # Top face
    bm.faces.new([verts[0], verts[1], verts[5], verts[4]])  # Front
    bm.faces.new([verts[1], verts[2], verts[6], verts[5]])  # Right
    bm.faces.new([verts[2], verts[3], verts[7], verts[6]])  # Back
    bm.faces.new([verts[3], verts[0], verts[4], verts[7]])  # Left

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def create_visual_plane_mesh(width, depth):
    """Creates a thin 2D planar helper mesh showing the exact cutting plane surface."""
    bm = bmesh.new()
    hw = width * 0.5
    hd = depth * 0.5

    v1 = bm.verts.new(Vector((-hw, -hd, 0.0)))
    v2 = bm.verts.new(Vector((hw, -hd, 0.0)))
    v3 = bm.verts.new(Vector((hw, hd, 0.0)))
    v4 = bm.verts.new(Vector((-hw, hd, 0.0)))

    bm.faces.new([v1, v2, v3, v4])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def build_orthonormal_cutter_matrix(origin, x_hint, z_normal):
    """
    Constructs a right-handed 4x4 world matrix centered at `origin` where:
    - Local Z axis aligns with `z_normal` (cutting plane normal)
    - Local X axis aligns with `x_hint` projected onto the cutting plane (along the cut stroke)
    - Local Y axis completes the orthonormal basis (depth axis)
    """
    axis_z = z_normal.normalized()
    if axis_z.length < 1e-6:
        axis_z = Vector((0.0, 0.0, 1.0))

    axis_x = x_hint - axis_z * x_hint.dot(axis_z)
    if axis_x.length < 1e-6:
        fallback = Vector((1.0, 0.0, 0.0)) if abs(axis_z.x) < 0.9 else Vector((0.0, 1.0, 0.0))
        axis_x = (fallback - axis_z * fallback.dot(axis_z)).normalized()
    else:
        axis_x.normalize()

    axis_y = axis_z.cross(axis_x).normalized()

    return Matrix((
        (axis_x.x, axis_y.x, axis_z.x, origin.x),
        (axis_x.y, axis_y.y, axis_z.y, origin.y),
        (axis_x.z, axis_y.z, axis_z.z, origin.z),
        (0.0,      0.0,      0.0,      1.0),
    ))


def _attach_visual_surface(cutter_obj, bm_surface, col, name="MS_Cut_Plane_Visual", color=(0.1, 0.85, 0.35, 0.45)):
    """Creates a translucent green visual surface child object sharing cutter_obj's exact local space."""
    bmesh.ops.recalc_face_normals(bm_surface, faces=bm_surface.faces)
    for f in bm_surface.faces:
        f.smooth = True
    mesh_plane = bpy.data.meshes.new(f"{name}_Mesh")
    bm_surface.to_mesh(mesh_plane)
    bm_surface.free()

    plane_obj = bpy.data.objects.new(name, mesh_plane)
    plane_obj.parent = cutter_obj
    plane_obj.matrix_parent_inverse = Matrix.Identity(4)
    plane_obj.display_type = 'SOLID'
    plane_obj.color = color
    plane_obj.show_wire = False
    plane_obj.hide_select = True
    col.objects.link(plane_obj)
    return plane_obj


def get_cutter_visual_surface_obj(cutter_obj):
    """Returns the MS_Cut_Plane_Visual child object of cutter_obj if present."""
    if not cutter_obj:
        return None
    for child in cutter_obj.children:
        if child.type == 'MESH' and "Cut_Plane_Visual" in child.name:
            return child
    return None


def build_cutter_surface_bvh(cutter_obj):
    """Builds a local-space BVHTree from the cutter's visual cutting sheet."""
    vis_obj = get_cutter_visual_surface_obj(cutter_obj)
    if not vis_obj or not vis_obj.data or len(vis_obj.data.polygons) == 0:
        return None
    verts = [v.co.copy() for v in vis_obj.data.vertices]
    polys = [tuple(p.vertices) for p in vis_obj.data.polygons]
    try:
        return BVHTree.FromPolygons(verts, polys)
    except Exception:
        return None


def snap_local_xy_to_surface(surface_bvh, x, y):
    """Projects a 2D local position (x, y) along the local Z axis onto surface_bvh."""
    pt_2d = Vector((x, y, 0.0))
    if not surface_bvh:
        return pt_2d, Vector((0.0, 0.0, 1.0))

    loc, norm, _, _ = surface_bvh.ray_cast(Vector((x, y, 500.0)), Vector((0.0, 0.0, -1.0)), 1000.0)
    if loc is None:
        loc, norm, _, _ = surface_bvh.ray_cast(Vector((x, y, -500.0)), Vector((0.0, 0.0, 1.0)), 1000.0)
    if loc is None:
        loc, norm, _, _ = surface_bvh.find_nearest(pt_2d)

    if loc is not None and norm is not None:
        n = norm.normalized()
        if n.z < 0.0:
            n = -n
        return loc, n

    return pt_2d, Vector((0.0, 0.0, 1.0))


def is_point_inside_bvh(src_bvh, pt):
    """
    Determines whether 3D point `pt` lies inside a mesh BVH by verifying both local
    beneath-surface orientation and first-hit outward normal voting across multiple rays.
    Immune to open holes elsewhere on the mesh (such as Suzanne's open eye sockets).
    """
    if not src_bvh:
        return True

    near_loc, near_norm, _, _ = src_bvh.find_nearest(pt)
    if near_loc is not None and near_norm is not None:
        delta = pt - near_loc
        if delta.length > 1e-6 and delta.dot(near_norm) >= 0.0:
            return False

    ray_dirs = (
        Vector((0.57735027, 0.57735027, 0.57735027)),
        Vector((-0.40824829, 0.81649658, -0.40824829)),
        Vector((0.70614755, -0.70614755, 0.05245250)),
        Vector((-0.57735027, -0.57735027, 0.57735027)),
    )
    inside_votes = 0
    for d in ray_dirs:
        loc, hit_norm, _, _ = src_bvh.ray_cast(pt, d, 10000.0)
        if loc is not None and hit_norm is not None and hit_norm.dot(d) > 0.0:
            inside_votes += 1

    return inside_votes >= 3



def is_point_beneath_surface_bvh(src_bvh, pt, max_depth=None):
    """
    Determines whether 3D point `pt` lies locally beneath the surface of `src_bvh`
    by checking the signed dot product with the nearest triangle's outward normal.
    Unlike global ray parity, this is 100% immune to open holes elsewhere on the mesh (e.g. Suzanne's eyes).
    """
    if not src_bvh:
        return False, None, None, 0.0
    near_loc, near_norm, _, dist = src_bvh.find_nearest(pt)
    if near_loc is None or near_norm is None:
        return False, None, None, 0.0
    if max_depth is not None and dist > max_depth:
        return False, near_loc, near_norm, dist
    delta = pt - near_loc
    if delta.length < 1e-6:
        return False, near_loc, near_norm, dist
    return (delta.dot(near_norm) < 0.0), near_loc, near_norm, dist


def compute_cut_cross_section(cutter_obj, cut_plane_matrix, source_obj):
    """
    Computes the exact 3D intersection cross-section between `source_obj` and `cutter_obj`'s
    cutting surface in `cutter_obj`'s local coordinate space.
    Returns (surface_bvh, src_bvh, cross_pts, interior_samples, best_center_tuple, bounds_2d).
    """
    surface_bvh = build_cutter_surface_bvh(cutter_obj)
    if not surface_bvh or not source_obj or not source_obj.data:
        return surface_bvh, None, [], [], None, None

    vis_obj = get_cutter_visual_surface_obj(cutter_obj)
    vis_verts = vis_obj.data.vertices
    z_min = min(v.co.z for v in vis_verts) - 1e-3
    z_max = max(v.co.z for v in vis_verts) + 1e-3

    try:
        cut_inv_src = cut_plane_matrix.inverted() @ source_obj.matrix_world
    except Exception:
        return surface_bvh, None, [], [], None, None

    src_verts = [cut_inv_src @ v.co for v in source_obj.data.vertices]
    src_polys = [tuple(p.vertices) for p in source_obj.data.polygons]

    try:
        src_bvh = BVHTree.FromPolygons(src_verts, src_polys) if src_verts and src_polys else None
    except Exception:
        src_bvh = None

    is_extruded_detail = bool(cutter_obj.get("ms_is_extruded_detail", False))

    # Intersect source_obj edges with the cutting surface
    cross_pts = []
    for e in source_obj.data.edges:
        p0 = src_verts[e.vertices[0]]
        p1 = src_verts[e.vertices[1]]
        if max(p0.z, p1.z) < z_min or min(p0.z, p1.z) > z_max:
            continue
        seg = p1 - p0
        seg_len = seg.length
        if seg_len < 1e-7:
            continue
        ray_dir = seg / seg_len
        loc, _, _, _ = surface_bvh.ray_cast(p0, ray_dir, seg_len)
        if loc is None:
            loc, _, _, _ = surface_bvh.ray_cast(p1, -ray_dir, seg_len)
        if loc is not None:
            cross_pts.append(loc)

    if is_extruded_detail or len(cross_pts) < 3:
        inside_vis = [v.co.copy() for v in vis_verts if is_point_inside_bvh(src_bvh, v.co)]
        if len(inside_vis) >= 3:
            cross_pts.extend(inside_vis)
        elif is_extruded_detail and len(vis_verts) >= 3:
            cross_pts.extend([v.co.copy() for v in vis_verts])

    if len(cross_pts) < 3:
        return surface_bvh, src_bvh, cross_pts, [], None, None

    min_x = min(p.x for p in cross_pts)
    max_x = max(p.x for p in cross_pts)
    min_y = min(p.y for p in cross_pts)
    max_y = max(p.y for p in cross_pts)
    bbox_mid_x = 0.5 * (min_x + max_x)
    bbox_mid_y = 0.5 * (min_y + max_y)
    avg_x = sum(p.x for p in cross_pts) / len(cross_pts)
    avg_y = sum(p.y for p in cross_pts) / len(cross_pts)

    # Build 2D candidate grid across the cross-section bounding box
    candidates_2d = [
        (bbox_mid_x, bbox_mid_y),
        (avg_x, avg_y),
        (0.5 * (bbox_mid_x + avg_x), 0.5 * (bbox_mid_y + avg_y)),
    ]
    grid_n = 13
    span_x = max_x - min_x
    span_y = max_y - min_y
    for ix in range(grid_n):
        u = 0.06 + 0.88 * (ix / (grid_n - 1))
        gx = min_x + u * span_x
        for iy in range(grid_n):
            v = 0.06 + 0.88 * (iy / (grid_n - 1))
            gy = min_y + v * span_y
            candidates_2d.append((gx, gy))

    vis_ring_2d = [(v.co.x, v.co.y) for v in vis_verts] if is_extruded_detail and len(vis_verts) >= 3 else []
    n_vis_ring = len(vis_ring_2d)

    interior_samples = []
    for gx, gy in candidates_2d:
        if is_extruded_detail:
            hit_l, _, _, _ = surface_bvh.ray_cast(Vector((gx, gy, 500.0)), Vector((0.0, 0.0, -1.0)), 1000.0)
            if hit_l is None:
                hit_l, _, _, _ = surface_bvh.ray_cast(Vector((gx, gy, -500.0)), Vector((0.0, 0.0, 1.0)), 1000.0)
            if hit_l is None:
                continue

        loc_3d, norm_3d = snap_local_xy_to_surface(surface_bvh, gx, gy)
        if is_point_inside_bvh(src_bvh, loc_3d) or is_extruded_detail:
            _, _, _, wall_dist = src_bvh.find_nearest(loc_3d) if src_bvh else (None, None, None, 0.0)
            w_d = float(wall_dist or 0.0)
            if src_bvh and not is_extruded_detail:
                hp, np_h, _, dp = src_bvh.ray_cast(loc_3d, norm_3d, 10000.0)
                hn, nn_h, _, dn = src_bvh.ray_cast(loc_3d, -norm_3d, 10000.0)
                if hp is None or (np_h is not None and np_h.dot(norm_3d) <= 0.0):
                    continue
                if hn is not None and nn_h is not None and nn_h.dot(-norm_3d) <= 0.0:
                    continue
                if dp is not None:
                    w_d = min(w_d, float(dp))
                if dn is not None:
                    w_d = min(w_d, float(dn))
            if n_vis_ring >= 3:
                poly_d = 1e9
                for ri in range(n_vis_ring):
                    ax, ay = vis_ring_2d[ri]
                    bx, by = vis_ring_2d[(ri + 1) % n_vis_ring]
                    abx, aby = bx - ax, by - ay
                    ab_l2 = abx * abx + aby * aby
                    t_seg = max(0.0, min(1.0, ((gx - ax) * abx + (gy - ay) * aby) / ab_l2)) if ab_l2 > 1e-12 else 0.0
                    d_seg = math.hypot(gx - (ax + t_seg * abx), gy - (ay + t_seg * aby))
                    if d_seg < poly_d:
                        poly_d = d_seg
                w_d = poly_d if w_d <= 1e-6 else min(w_d, poly_d)
            interior_samples.append((loc_3d, norm_3d, w_d))


    if not interior_samples:
        # Fallback if mesh is non-manifold/open shell: use centroid snapped to cutting surface
        c_loc, c_norm = snap_local_xy_to_surface(surface_bvh, 0.5 * (bbox_mid_x + avg_x), 0.5 * (bbox_mid_y + avg_y))
        best_center = (c_loc, c_norm, 0.0)
        interior_samples = [best_center]
    else:
        max_wall = max(s[2] for s in interior_samples)
        threshold = max_wall * 0.65
        deep_candidates = [s for s in interior_samples if s[2] >= threshold]
        target_2d = Vector((0.5 * (bbox_mid_x + avg_x), 0.5 * (bbox_mid_y + avg_y)))
        best_center = min(
            deep_candidates,
            key=lambda s: (Vector((s[0].x, s[0].y)) - target_2d).length
        )

    return surface_bvh, src_bvh, cross_pts, interior_samples, best_center, (min_x, max_x, min_y, max_y)


def recenter_cutter_to_mesh_intersection(cutter_obj, source_obj):
    """
    Shifts cutter_obj's origin (and gizmo pivot) to the exact 3D center of the cut cross-section
    inside `source_obj`, while counter-shifting local mesh vertices so the world-space cutting
    surface does not move at all.
    """
    if not cutter_obj or not source_obj:
        return cutter_obj.matrix_world.translation.copy(), cutter_obj.matrix_world.copy()

    _, _, _, _, best_center, _ = compute_cut_cross_section(
        cutter_obj, cutter_obj.matrix_world, source_obj
    )
    if not best_center:
        return cutter_obj.matrix_world.translation.copy(), cutter_obj.matrix_world.copy()

    delta_local = best_center[0].copy()
    if delta_local.length < 1e-6:
        return cutter_obj.matrix_world.translation.copy(), cutter_obj.matrix_world.copy()

    # Counter-shift local vertices of cutter_obj and all its visual child meshes so world positions stay invariant
    for v in cutter_obj.data.vertices:
        v.co -= delta_local
    cutter_obj.data.update()

    for child in cutter_obj.children:
        if child.type == 'MESH' and child.data:
            for v in child.data.vertices:
                v.co -= delta_local
            child.data.update()

    world_mat = cutter_obj.matrix_world.copy()
    world_mat.translation = world_mat @ delta_local
    cutter_obj.matrix_world = world_mat
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass

    return world_mat.translation.copy(), world_mat


def setup_straight_cutter(context, source_obj, target_collection=None):
    """
    Initializes a default straight cutting volume and plane helper centered on source_obj.
    Returns (cutter_volume_obj, visual_plane_obj).
    """
    col = target_collection or context.collection

    _, _, center, dimensions = get_world_bounds(source_obj)
    diag = dimensions.length
    size = max(diag * 1.5, 0.1)

    mesh_box = bpy.data.meshes.new("MS_Straight_Cutter_Mesh")
    bm_box = create_half_space_box(width=size, depth=size, height=size)
    bm_box.to_mesh(mesh_box)
    bm_box.free()

    cutter_obj = bpy.data.objects.new("MS_Straight_Cutter", mesh_box)
    cutter_obj.matrix_world = Matrix.Translation(center)
    cutter_obj.display_type = 'WIRE'
    cutter_obj.show_in_front = True
    col.objects.link(cutter_obj)

    bm_plane = create_visual_plane_mesh(width=size, depth=size)
    plane_obj = _attach_visual_surface(
        cutter_obj, bm_plane, col, name="MS_Cut_Plane_Visual", color=(0.2, 0.7, 1.0, 0.35)
    )

    return cutter_obj, plane_obj


def setup_base_cutter(context, source_obj, target_collection=None):
    """
    Auto-detects the pedestal / base transition height near the bottom of `source_obj`
    and initializes a horizontal straight cutter right at the base seam.
    Returns (cutter_volume_obj, visual_plane_obj).
    """
    col = target_collection or context.collection
    min_corner, _, center, dimensions = get_world_bounds(source_obj)
    diag = dimensions.length
    size = max(diag * 1.5, 0.1)
    height_z = max(dimensions.z, 1e-4)

    # Default base cut height: 15% up from bottom Z
    z_cut = min_corner.z + height_z * 0.15

    # Analyze horizontal XY cross-section profile in the bottom 35% of the model using exact edge-plane intersections
    if source_obj and source_obj.data and len(source_obj.data.edges) > 0:
        mat_w = source_obj.matrix_world
        verts_w = [mat_w @ v.co for v in source_obj.data.vertices]
        edges = source_obj.data.edges
        num_slices = 24
        z_bottom = min_corner.z + height_z * 0.01
        z_scan_top = min_corner.z + height_z * 0.35
        slice_h = (z_scan_top - z_bottom) / max(1, num_slices - 1)

        slice_radii = []
        for s_idx in range(num_slices):
            zh = z_bottom + s_idx * slice_h
            cross_x = []
            cross_y = []
            for e in edges:
                p0 = verts_w[e.vertices[0]]
                p1 = verts_w[e.vertices[1]]
                if (p0.z <= zh <= p1.z) or (p1.z <= zh <= p0.z):
                    dz = p1.z - p0.z
                    t = (zh - p0.z) / dz if abs(dz) > 1e-6 else 0.5
                    cross_x.append(p0.x + (p1.x - p0.x) * t)
                    cross_y.append(p0.y + (p1.y - p0.y) * t)
            if len(cross_x) >= 2:
                sx_span = max(cross_x) - min(cross_x)
                sy_span = max(cross_y) - min(cross_y)
                r_xy = 0.5 * math.hypot(sx_span, sy_span)
            else:
                r_xy = slice_radii[-1][1] if slice_radii else 0.0
            slice_radii.append((zh, r_xy))

        if len(slice_radii) >= 4:
            # Find steepest inward step (largest drop in XY radius from slice i-1 to i)
            best_drop = 0.0
            best_z = z_cut
            max_base_r = max((r for _, r in slice_radii[:8]), default=0.0)
            for i in range(1, len(slice_radii)):
                drop = slice_radii[i - 1][1] - slice_radii[i][1]
                if drop > best_drop and drop > max_base_r * 0.12:
                    best_drop = drop
                    best_z = slice_radii[i][0]
            if best_drop > 0.0:
                z_cut = best_z

    cut_origin = Vector((center.x, center.y, z_cut))
    mesh_box = bpy.data.meshes.new("MS_Base_Cutter_Mesh")
    bm_box = create_half_space_box(width=size, depth=size, height=size)
    bm_box.to_mesh(mesh_box)
    bm_box.free()

    cutter_obj = bpy.data.objects.new("MS_Base_Cutter", mesh_box)
    cutter_obj.matrix_world = Matrix.Translation(cut_origin)
    cutter_obj.display_type = 'WIRE'
    cutter_obj.show_in_front = True
    col.objects.link(cutter_obj)

    bm_plane = create_visual_plane_mesh(width=size, depth=size)
    plane_obj = _attach_visual_surface(
        cutter_obj, bm_plane, col, name="MS_Cut_Plane_Visual", color=(0.95, 0.55, 0.15, 0.4)
    )

    recenter_cutter_to_mesh_intersection(cutter_obj, source_obj)
    return cutter_obj, plane_obj


def setup_curved_cutter(context, source_obj, target_collection=None):
    """
    Initializes a default curved cutting volume and visual surface centered on source_obj.
    """
    col = target_collection or context.collection
    _, _, center, dimensions = get_world_bounds(source_obj)
    diag = dimensions.length
    size = max(diag * 1.5, 0.1)

    bm = bmesh.new()
    bm_vis = bmesh.new()
    segments = 48
    hw = size * 0.5
    hd = size * 0.5
    height = size

    grid_bottom = []
    vis_grid = []
    for yi in range(segments + 1):
        row = []
        vis_row = []
        v_y = -hd + (yi / segments) * size
        for xi in range(segments + 1):
            v_x = -hw + (xi / segments) * size
            v_z = math.sin((v_x / size) * math.pi) * (size * 0.08)
            co = Vector((v_x, v_y, v_z))
            row.append(bm.verts.new(co))
            vis_row.append(bm_vis.verts.new(co))
        grid_bottom.append(row)
        vis_grid.append(vis_row)

    grid_top = []
    for yi in range(segments + 1):
        row = []
        v_y = -hd + (yi / segments) * size
        for xi in range(segments + 1):
            v_x = -hw + (xi / segments) * size
            row.append(bm.verts.new(Vector((v_x, v_y, height))))
        grid_top.append(row)

    for yi in range(segments):
        for xi in range(segments):
            f_bot = bm.faces.new([
                grid_bottom[yi][xi],
                grid_bottom[yi + 1][xi],
                grid_bottom[yi + 1][xi + 1],
                grid_bottom[yi][xi + 1]
            ])
            f_bot.smooth = True
            f_vis = bm_vis.faces.new([
                vis_grid[yi][xi],
                vis_grid[yi][xi + 1],
                vis_grid[yi + 1][xi + 1],
                vis_grid[yi + 1][xi]
            ])
            f_vis.smooth = True

    for yi in range(segments):
        for xi in range(segments):
            bm.faces.new([
                grid_top[yi][xi],
                grid_top[yi][xi + 1],
                grid_top[yi + 1][xi + 1],
                grid_top[yi + 1][xi]
            ])

    for xi in range(segments):
        bm.faces.new([grid_bottom[0][xi], grid_bottom[0][xi + 1], grid_top[0][xi + 1], grid_top[0][xi]])
        bm.faces.new([grid_bottom[segments][xi + 1], grid_bottom[segments][xi], grid_top[segments][xi], grid_top[segments][xi + 1]])

    for yi in range(segments):
        bm.faces.new([grid_bottom[yi + 1][0], grid_bottom[yi][0], grid_top[yi][0], grid_top[yi + 1][0]])
        bm.faces.new([grid_bottom[yi][segments], grid_bottom[yi + 1][segments], grid_top[yi + 1][segments], grid_top[yi][segments]])

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh_curved = bpy.data.meshes.new("MS_Curved_Cutter_Mesh")
    bm.to_mesh(mesh_curved)
    bm.free()

    cutter_obj = bpy.data.objects.new("MS_Curved_Cutter", mesh_curved)
    cutter_obj.matrix_world = Matrix.Translation(center)
    cutter_obj.display_type = 'WIRE'
    cutter_obj.show_in_front = True
    col.objects.link(cutter_obj)

    _attach_visual_surface(
        cutter_obj, bm_vis, col, name="MS_Cut_Plane_Visual", color=(0.1, 0.85, 0.35, 0.45)
    )

    return cutter_obj


def get_screen_ray_dir(region, rv3d, pt_2d, fallback_normal):
    """Returns the unit 3D camera ray direction through a 2D viewport pixel."""
    try:
        r_dir = view3d_utils.region_2d_to_vector_3d(region, rv3d, pt_2d)
        if r_dir.length > 1e-6:
            return r_dir.normalized()
    except Exception:
        pass
    return fallback_normal.normalized()


def unproject_screen_to_object_plane(region, rv3d, pt_2d, plane_center, plane_normal):
    """Unprojects a 2D viewport point onto a 3D plane passing through plane_center."""
    try:
        r_orig = view3d_utils.region_2d_to_origin_3d(region, rv3d, pt_2d)
        r_dir = view3d_utils.region_2d_to_vector_3d(region, rv3d, pt_2d)

        dot = r_dir.dot(plane_normal)
        if abs(dot) < 1e-6:
            return plane_center
        dist = (plane_center - r_orig).dot(plane_normal) / dot
        return r_orig + r_dir * dist
    except Exception:
        # Robust geometric fallback for headless tests or synthetic viewports
        w = max(1.0, float(getattr(region, 'width', 1920)))
        h = max(1.0, float(getattr(region, 'height', 1080)))
        norm_x = (pt_2d.x / w - 0.5) * 2.0
        norm_y = (pt_2d.y / h - 0.5) * 2.0
        return plane_center + Vector((norm_x, norm_y, 0.0))


def _catmull_rom_point(p0, p1, p2, p3, t):
    """Evaluates standard uniform Catmull-Rom spline at parameter t in [0, 1]."""
    t2 = t * t
    t3 = t2 * t
    return 0.5 * (
        (2.0 * p1)
        + (-p0 + p2) * t
        + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
        + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
    )


def resample_smooth_curve_2d(points_2d, num_samples=32):
    """
    Filters hand jitter from raw 2D screen stroke points and resamples them
    at uniform arc-length intervals along a smooth Catmull-Rom spline.
    """
    if not points_2d:
        return []

    # 1. Deduplicate near-coincident points
    clean = [Vector((points_2d[0].x, points_2d[0].y))]
    for pt in points_2d[1:]:
        v = Vector((pt.x, pt.y))
        if (v - clean[-1]).length > 1.0:
            clean.append(v)

    if len(clean) == 1:
        return clean

    num_samples = max(4, int(num_samples))

    if len(clean) == 2:
        p0, p1 = clean[0], clean[1]
        return [p0.lerp(p1, i / (num_samples - 1)) for i in range(num_samples)]

    # 2. Adaptive endpoint-preserving smoothing:
    #    - For sparse clicked control points (<= 10), keep exact control points (0 smoothing passes)
    #      so the spline passes directly through every clicked point without shifting!
    #    - For dense freehand drag strokes (> 10 points), smoothly ramp fairing to eliminate hand tremor.
    smoothed = list(clean)
    if len(smoothed) > 10:
        smooth_iters = min(120, (len(smoothed) - 10) * 3)
        for _ in range(smooth_iters):
            nxt = [smoothed[0]]
            for i in range(1, len(smoothed) - 1):
                nxt.append(smoothed[i - 1] * 0.25 + smoothed[i] * 0.5 + smoothed[i + 1] * 0.25)
            nxt.append(smoothed[-1])
            smoothed = nxt


    # 3. Evaluate dense Catmull-Rom polyline
    ext = [smoothed[0] * 2.0 - smoothed[1]] + smoothed + [smoothed[-1] * 2.0 - smoothed[-2]]
    substeps = max(12, 240 // max(1, len(smoothed) - 1))
    dense = []
    for i in range(len(smoothed) - 1):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        for s in range(substeps):
            t = s / substeps
            dense.append(_catmull_rom_point(p0, p1, p2, p3, t))
    dense.append(smoothed[-1].copy())

    # 4. Uniform arc-length resampling
    cum_len = [0.0]
    for i in range(1, len(dense)):
        cum_len.append(cum_len[-1] + (dense[i] - dense[i - 1]).length)

    total_len = cum_len[-1]
    if total_len < 1e-5:
        return [clean[0], clean[-1]]

    resampled = []
    idx = 0
    for i in range(num_samples):
        target_d = (i / (num_samples - 1)) * total_len
        while idx < len(cum_len) - 2 and cum_len[idx + 1] < target_d:
            idx += 1
        seg_len = cum_len[idx + 1] - cum_len[idx]
        if seg_len < 1e-6:
            resampled.append(dense[idx].copy())
        else:
            alpha = (target_d - cum_len[idx]) / seg_len
            resampled.append(dense[idx].lerp(dense[idx + 1], max(0.0, min(1.0, alpha))))

    return resampled


def resample_closed_curve_3d(points_3d, num_samples=64, smooth_passes=3):
    """
    Interpolates a closed 3D point loop with a periodic Catmull-Rom spline,
    resamples it at `num_samples` uniform arc-length intervals, and applies
    radial-scale-preserving periodic Laplacian smoothing for a silky-smooth loop.
    """
    if not points_3d:
        return []

    clean = [points_3d[0].copy()]
    for pt in points_3d[1:]:
        if (pt - clean[-1]).length > 1e-5:
            clean.append(pt.copy())
    if len(clean) > 2 and (clean[-1] - clean[0]).length <= 1e-5:
        clean.pop()

    m = len(clean)
    if m < 3:
        return clean

    num_samples = max(16, int(num_samples))
    substeps = max(16, 256 // m)
    dense = []
    for i in range(m):
        p0 = clean[(i - 1) % m]
        p1 = clean[i]
        p2 = clean[(i + 1) % m]
        p3 = clean[(i + 2) % m]
        for s in range(substeps):
            t = s / substeps
            dense.append(_catmull_rom_point(p0, p1, p2, p3, t))
    dense.append(clean[0].copy())

    cum_len = [0.0]
    for i in range(1, len(dense)):
        cum_len.append(cum_len[-1] + (dense[i] - dense[i - 1]).length)

    total_len = cum_len[-1]
    if total_len < 1e-6:
        return clean

    resampled = []
    idx = 0
    for i in range(num_samples):
        target_d = (i / num_samples) * total_len
        while idx < len(cum_len) - 2 and cum_len[idx + 1] < target_d:
            idx += 1
        seg_len = cum_len[idx + 1] - cum_len[idx]
        if seg_len < 1e-6:
            resampled.append(dense[idx].copy())
        else:
            alpha = (target_d - cum_len[idx]) / seg_len
            resampled.append(dense[idx].lerp(dense[idx + 1], max(0.0, min(1.0, alpha))))

    if smooth_passes > 0:
        center = sum(resampled, Vector()) / num_samples
        avg_r_before = sum((p - center).length for p in resampled) / num_samples
        for _ in range(smooth_passes):
            resampled = [
                resampled[(i - 1) % num_samples] * 0.25
                + resampled[i] * 0.5
                + resampled[(i + 1) % num_samples] * 0.25
                for i in range(num_samples)
            ]
        avg_r_after = sum((p - center).length for p in resampled) / num_samples
        if avg_r_after > 1e-6 and avg_r_before > 1e-6:
            scale = avg_r_before / avg_r_after
            resampled = [center + (p - center) * scale for p in resampled]

    return resampled


def create_cutter_from_screen_line(context, source_obj, p1_2d, p2_2d, region, rv3d, target_collection=None):
    """
    Creates a view-projected half-space cutting volume from a drawn 2D screen line.
    The cutting plane cuts through the model along the exact camera ray plane.
    Returns (cutter_obj, plane_obj, plane_center, plane_normal, world_mat).
    """
    col = target_collection or context.collection
    _, _, center, dimensions = get_world_bounds(source_obj)
    diag = dimensions.length
    size = max(diag * 2.0, 0.25)

    view_normal = rv3d.view_rotation @ Vector((0, 0, -1))

    # Midpoint and line endpoints in 3D on the object's view plane
    mid_2d = (p1_2d + p2_2d) * 0.5
    plane_center = unproject_screen_to_object_plane(region, rv3d, mid_2d, center, view_normal)
    pt1_3d = unproject_screen_to_object_plane(region, rv3d, p1_2d, center, view_normal)
    pt2_3d = unproject_screen_to_object_plane(region, rv3d, p2_2d, center, view_normal)

    line_vec = (pt2_3d - pt1_3d).normalized()
    if line_vec.length < 1e-4:
        line_vec = Vector((1, 0, 0))

    # Use exact camera ray at midpoint for zero perspective parallax
    mid_ray = get_screen_ray_dir(region, rv3d, mid_2d, view_normal)
    plane_normal = line_vec.cross(mid_ray).normalized()
    if plane_normal.length < 1e-4:
        plane_normal = Vector((0, 0, 1))

    world_mat = build_orthonormal_cutter_matrix(plane_center, line_vec, plane_normal)

    # Build cutter mesh
    mesh_box = bpy.data.meshes.new("MS_Drawn_Straight_Cutter_Mesh")
    bm_box = create_half_space_box(width=size, depth=size, height=size)
    bm_box.to_mesh(mesh_box)
    bm_box.free()

    cutter_obj = bpy.data.objects.new("MS_Straight_Cutter", mesh_box)
    cutter_obj.matrix_world = world_mat
    cutter_obj.display_type = 'WIRE'
    cutter_obj.show_in_front = True
    col.objects.link(cutter_obj)

    # Visual guide plane
    bm_plane = create_visual_plane_mesh(width=size, depth=size)
    plane_obj = _attach_visual_surface(
        cutter_obj, bm_plane, col, name="MS_Cut_Plane_Visual", color=(0.1, 0.85, 0.35, 0.45)
    )

    plane_center, world_mat = recenter_cutter_to_mesh_intersection(cutter_obj, source_obj)
    return cutter_obj, plane_obj, plane_center, plane_normal, world_mat


def create_cutter_from_screen_curve(context, source_obj, points_2d, region, rv3d, target_collection=None):
    """
    Creates an extruded curved cutting volume from a sequence of 2D screen points.
    1. Smooths and resamples the 2D stroke into a high-resolution Catmull-Rom spline.
    2. Sweeps each curve sample along its exact perspective camera ray (zero parallax).
    3. Automatically extends start and end tangents past the model's bounding box.
    4. Builds geometry in local space relative to `world_mat` (no double transform) and
       attaches a translucent green curved cutting surface preview (`MS_Cut_Plane_Visual`).
    """
    col = target_collection or context.collection
    _, _, center, dimensions = get_world_bounds(source_obj)
    diag = dimensions.length
    depth = max(diag * 2.2, 0.3)
    view_normal = rv3d.view_rotation @ Vector((0, 0, -1))

    settings = getattr(context.scene, "model_splitter", None)
    base_samples = getattr(settings.cut, "editable_points", 24) if settings else 24
    num_samples = max(48, int(base_samples) * 2)

    core_2d = resample_smooth_curve_2d(points_2d, num_samples=num_samples)
    if len(core_2d) < 2:
        cutter_obj = setup_curved_cutter(context, source_obj, target_collection=col)
        return cutter_obj, center, Vector((0, 0, 1)), cutter_obj.matrix_world.copy()

    # Unproject core curve points onto the object plane and capture exact perspective ray per sample
    core_3d = [unproject_screen_to_object_plane(region, rv3d, pt, center, view_normal) for pt in core_2d]
    core_rays = [get_screen_ray_dir(region, rv3d, pt, view_normal) for pt in core_2d]

    # Origin sits directly on the midpoint of the drawn curve so the center pin snaps to the curve
    mid_idx = len(core_3d) // 2
    curve_center = core_3d[mid_idx].copy()

    chord_vec = core_3d[-1] - core_3d[0]
    if chord_vec.length < 1e-4:
        # Fallback if start and end are nearly identical
        chord_vec = core_3d[mid_idx] - core_3d[0]
    chord_dir = chord_vec.normalized() if chord_vec.length >= 1e-4 else Vector((1, 0, 0))

    mid_ray = core_rays[mid_idx]
    plane_normal = chord_dir.cross(mid_ray).normalized()
    if plane_normal.length < 1e-4:
        plane_normal = Vector((0, 0, 1))

    # Build orthonormal local coordinate frame centered at curve_center
    world_mat = build_orthonormal_cutter_matrix(curve_center, chord_dir, plane_normal)
    world_mat_inv = world_mat.inverted()

    # Auto-extend curve endpoints outward past the model's bounding box silhouette
    k_step = min(4, len(core_3d) - 1)
    tan_start = (core_3d[0] - core_3d[k_step]).normalized()
    tan_end = (core_3d[-1] - core_3d[-1 - k_step]).normalized()

    if tan_start.length < 1e-5:
        tan_start = -chord_dir
    elif tan_start.dot(-chord_dir) < 0.2:
        tan_start = (tan_start - chord_dir).normalized()

    if tan_end.length < 1e-5:
        tan_end = chord_dir
    elif tan_end.dot(chord_dir) < 0.2:
        tan_end = (tan_end + chord_dir).normalized()

    extend_dist = max(diag * 1.25, 0.25)
    ext_steps = 6

    pts_3d = []
    ray_dirs = []

    for i in range(ext_steps):
        dist = extend_dist * ((ext_steps - i) / ext_steps)
        pts_3d.append(core_3d[0] + tan_start * dist)
        ray_dirs.append(core_rays[0])

    pts_3d.extend(core_3d)
    ray_dirs.extend(core_rays)

    for i in range(ext_steps):
        dist = extend_dist * ((i + 1) / ext_steps)
        pts_3d.append(core_3d[-1] + tan_end * dist)
        ray_dirs.append(core_rays[-1])

    # Build extruded ribbon solid in cutter local space
    bm = bmesh.new()
    bm_vis = bmesh.new()
    half_depth = depth * 0.5
    height = max(diag * 1.8, 0.25)

    num_pts = len(pts_3d)
    steps_depth = 16

    # Bottom surface (the exact curved cutting sheet) in local space
    grid_bottom = []
    vis_grid = []
    for di in range(steps_depth + 1):
        offset_depth = -half_depth + (di / steps_depth) * depth
        row = []
        vis_row = []
        for pi in range(num_pts):
            pt_world = pts_3d[pi] + ray_dirs[pi] * offset_depth
            pt_local = world_mat_inv @ pt_world
            row.append(bm.verts.new(pt_local))
            vis_row.append(bm_vis.verts.new(pt_local))
        grid_bottom.append(row)
        vis_grid.append(vis_row)

    max_local_z = max(v.co.z for row in grid_bottom for v in row)

    # Top surface (offset in local +Z to guarantee a self-intersection-free half-space prism)
    grid_top = []
    for di in range(steps_depth + 1):
        row = []
        for pi in range(num_pts):
            b_co = grid_bottom[di][pi].co
            top_z = max(b_co.z + height, max_local_z + height * 0.6)
            row.append(bm.verts.new(Vector((b_co.x, b_co.y, top_z))))
        grid_top.append(row)

    # Connect bottom surface faces & visual cutting sheet faces
    for di in range(steps_depth):
        for pi in range(num_pts - 1):
            f_bot = bm.faces.new([
                grid_bottom[di][pi],
                grid_bottom[di + 1][pi],
                grid_bottom[di + 1][pi + 1],
                grid_bottom[di][pi + 1]
            ])
            f_bot.smooth = True
            f_vis = bm_vis.faces.new([
                vis_grid[di][pi],
                vis_grid[di][pi + 1],
                vis_grid[di + 1][pi + 1],
                vis_grid[di + 1][pi]
            ])
            f_vis.smooth = True

    # Connect top surface faces
    for di in range(steps_depth):
        for pi in range(num_pts - 1):
            bm.faces.new([
                grid_top[di][pi],
                grid_top[di][pi + 1],
                grid_top[di + 1][pi + 1],
                grid_top[di + 1][pi]
            ])

    # Side walls
    for pi in range(num_pts - 1):
        bm.faces.new([grid_bottom[0][pi], grid_bottom[0][pi + 1], grid_top[0][pi + 1], grid_top[0][pi]])
        bm.faces.new([grid_bottom[steps_depth][pi + 1], grid_bottom[steps_depth][pi], grid_top[steps_depth][pi], grid_top[steps_depth][pi + 1]])

    for di in range(steps_depth):
        bm.faces.new([grid_bottom[di + 1][0], grid_bottom[di][0], grid_top[di][0], grid_top[di + 1][0]])
        bm.faces.new([grid_bottom[di][num_pts - 1], grid_bottom[di + 1][num_pts - 1], grid_top[di + 1][num_pts - 1], grid_top[di][num_pts - 1]])

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh_curved = bpy.data.meshes.new("MS_Drawn_Curved_Cutter_Mesh")
    bm.to_mesh(mesh_curved)
    bm.free()

    cutter_obj = bpy.data.objects.new("MS_Curved_Cutter", mesh_curved)
    cutter_obj.matrix_world = world_mat
    cutter_obj.display_type = 'WIRE'
    cutter_obj.show_in_front = True
    col.objects.link(cutter_obj)

    _attach_visual_surface(
        cutter_obj, bm_vis, col, name="MS_Cut_Plane_Visual", color=(0.1, 0.85, 0.35, 0.45)
    )

    curve_center, world_mat = recenter_cutter_to_mesh_intersection(cutter_obj, source_obj)
    return cutter_obj, curve_center, plane_normal, world_mat


def create_cutter_from_surface_points(context, source_obj, points_3d, target_collection=None, view_normal=None):
    """
    Creates a smooth, wafer-thin cutting plane tightly fitted just outside the 3D points
    placed on the model surface. Slices ONLY along the 2D cutting surface patch (no extruded cylinder).
    """
    col = target_collection or context.collection
    _, _, center, dimensions = get_world_bounds(source_obj)
    diag = dimensions.length

    if len(points_3d) < 2:
        cutter_obj, _ = setup_straight_cutter(context, source_obj, target_collection=col)
        return cutter_obj, center, Vector((0, 0, 1)), cutter_obj.matrix_world.copy()

    # If only 2 points were placed on the surface, build a localized wafer-thin plane just wider than the 2 points
    if len(points_3d) == 2:
        v_norm = view_normal.normalized() if view_normal and view_normal.length > 1e-5 else Vector((0, -1, 0))
        seg_vec = points_3d[1] - points_3d[0]
        seg_len = max(seg_vec.length, 0.05)
        seg = seg_vec.normalized() if seg_vec.length > 1e-5 else Vector((1, 0, 0))
        p_norm = seg.cross(v_norm).normalized()
        if p_norm.length < 1e-5:
            p_norm = Vector((0, 0, 1))
        mid = (points_3d[0] + points_3d[1]) * 0.5
        width = seg_len * 1.2
        depth = max(seg_len * 1.2, diag * 0.35)
        half_t = max(seg_len * 0.002, diag * 0.0002, 1e-4)
        world_mat = build_orthonormal_cutter_matrix(mid, seg, p_norm)

        mesh_box = bpy.data.meshes.new("MS_Manual_Surface_Cutter_Mesh")
        bm_box = create_half_space_box(width=width, depth=depth, height=half_t * 2.0)
        for v in bm_box.verts:
            v.co.z -= half_t
        bm_box.to_mesh(mesh_box)
        bm_box.free()

        cutter_obj = bpy.data.objects.new("MS_Manual_Cutter", mesh_box)
        cutter_obj.matrix_world = world_mat
        cutter_obj.display_type = 'WIRE'
        cutter_obj.show_in_front = True
        cutter_obj["ms_is_thin_blade"] = True
        cutter_obj["ms_blade_thickness"] = float(half_t * 2.0)
        col.objects.link(cutter_obj)

        bm_plane = create_visual_plane_mesh(width=width, depth=depth)
        _attach_visual_surface(cutter_obj, bm_plane, col, name="MS_Cut_Plane_Visual", color=(0.1, 0.85, 0.35, 0.45))
        mid, world_mat = recenter_cutter_to_mesh_intersection(cutter_obj, source_obj)
        return cutter_obj, mid, p_norm, world_mat

    centroid = sum(points_3d, Vector()) / len(points_3d)
    contour_radius = max(((p - centroid).length for p in points_3d), default=0.1)
    half_t = max(contour_radius * 0.002, diag * 0.0002, 1e-4)

    # Calculate average normal from Newell's polygon method (using centroid-relative coords for precision)
    avg_normal = Vector()
    n_raw = len(points_3d)
    rel_pts = [p - centroid for p in points_3d]
    for i in range(n_raw):
        curr = rel_pts[i]
        nxt = rel_pts[(i + 1) % n_raw]
        avg_normal.x += (curr.y - nxt.y) * (curr.z + nxt.z)
        avg_normal.y += (curr.z - nxt.z) * (curr.x + nxt.x)
        avg_normal.z += (curr.x - nxt.x) * (curr.y + nxt.y)


    if avg_normal.length < 1e-5:
        avg_normal = Vector((0, 0, 1))
    else:
        avg_normal = avg_normal.normalized()

    x_hint = (points_3d[0] - centroid).normalized()
    world_mat = build_orthonormal_cutter_matrix(centroid, x_hint, avg_normal)
    world_mat_inv = world_mat.inverted()

    # Build world-space BVHTree of source_obj so the seam hugs the mesh surface and the outer rim exits into open air
    src_bvh_w = None
    if source_obj and source_obj.data and len(source_obj.data.polygons) > 0:
        try:
            src_mat = source_obj.matrix_world
            src_verts_w = [src_mat @ v.co for v in source_obj.data.vertices]
            src_polys = [tuple(p.vertices) for p in source_obj.data.polygons]
            src_bvh_w = BVHTree.FromPolygons(src_verts_w, src_polys)
        except Exception:
            src_bvh_w = None

    # 1. Interpolate a 64-point closed Catmull-Rom spline through the placed 3D surface points
    #    and project intermediate chord points onto the outer mesh surface so sparse clicks never burrow under the skin
    seam_world = resample_closed_curve_3d(points_3d, num_samples=64, smooth_passes=0)
    num_ring = len(seam_world)

    if src_bvh_w is not None:
        # Step 1a: Geodesic surface relaxation (smooth along loop + snap to nearest mesh surface)
        # so the curve climbs out of any buried chord onto the true 3D surface height
        for i in range(num_ring):
            near_loc, _, _, _ = src_bvh_w.find_nearest(seam_world[i])
            if near_loc is not None:
                seam_world[i] = near_loc

        for _ in range(3):
            smoothed = [
                seam_world[(i - 1) % num_ring] * 0.22
                + seam_world[i] * 0.56
                + seam_world[(i + 1) % num_ring] * 0.22
                for i in range(num_ring)
            ]
            for i in range(num_ring):
                near_loc, _, _, _ = src_bvh_w.find_nearest(smoothed[i])
                seam_world[i] = near_loc if near_loc is not None else smoothed[i]

        # Step 1b: Cast outward rays (both horizontally at lp.z and radially from centroid through seam_world[i])
        # to push any point that lies inside a broad or sloped neck cross-section out to the outer neck skin
        rot_mat = world_mat.to_3x3()
        local_pts_1a = [world_mat_inv @ p for p in seam_world]
        max_r_xy = max((math.hypot(lp.x, lp.y) for lp in local_pts_1a), default=0.1)

        for i in range(num_ring):
            p_w = seam_world[i]
            lp = local_pts_1a[i]
            r_xy = math.hypot(lp.x, lp.y)
            if r_xy < 1e-6:
                continue

            candidate_rays = []
            # Ray 1: Horizontal radial ray in cutter XY plane at height lp.z
            rad_dir_local = Vector((lp.x / r_xy, lp.y / r_xy, 0.0))
            ray_dir_horiz = (rot_mat @ rad_dir_local).normalized()
            origin_at_z = world_mat @ Vector((0.0, 0.0, lp.z))
            candidate_rays.append((origin_at_z, ray_dir_horiz, r_xy))

            # Ray 2: Sloped radial ray from centroid through p_w (catches sloped ridges like ear creases)
            vec_c = p_w - centroid
            if vec_c.length > 1e-6:
                candidate_rays.append((centroid, vec_c.normalized(), vec_c.length))

            best_exit = None
            best_exit_r = r_xy
            for ray_orig, ray_dir_w, base_d in candidate_rays:
                cur_t = 0.65 * base_d
                max_t = max(base_d * 2.25, max_r_xy * 1.45)
                for _ in range(5):
                    if cur_t >= max_t:
                        break
                    hit_loc, hit_norm, _, hit_dist = src_bvh_w.ray_cast(
                        ray_orig + ray_dir_w * cur_t, ray_dir_w, max_t - cur_t
                    )
                    if hit_loc is None:
                        break
                    hit_t = cur_t + hit_dist
                    if hit_t >= base_d * 0.96 and hit_norm.dot(ray_dir_w) > 0.04:
                        hit_lp = world_mat_inv @ hit_loc
                        hit_r = math.hypot(hit_lp.x, hit_lp.y)
                        if hit_r > best_exit_r:
                            best_exit_r = hit_r
                            best_exit = hit_loc
                    cur_t = hit_t + max(1e-4, base_d * 0.02)
            if best_exit is not None:
                seam_world[i] = best_exit

        # Lightly smooth the resulting outer seam loop so there are no sharp radial steps
        for _ in range(3):
            seam_world = [
                seam_world[(i - 1) % num_ring] * 0.22
                + seam_world[i] * 0.56
                + seam_world[(i + 1) % num_ring] * 0.22
                for i in range(num_ring)
            ]




    seam_local = [world_mat_inv @ p for p in seam_world]
    z_center = sum(lp.z for lp in seam_local) / max(1, num_ring)


    # 2. Build 8 interior rings (r in 1/8 .. 8/8) where ring 7 (r=1.0) is the exact 3D surface seam,
    #    and relax the interior (rings 0..6 + center) as a 3D harmonic minimal soap-film surface
    inner_rings = 8
    rings_co = []
    for r_idx in range(1, inner_rings + 1):
        r = r_idx / inner_rings
        h = r * r * (3.0 - 2.0 * r)
        ring_pts = []
        for lp in seam_local:
            rz = z_center + (lp.z - z_center) * h
            ring_pts.append(Vector((lp.x * r, lp.y * r, rz)))
        rings_co.append(ring_pts)

    # Discrete harmonic (soap-film) Z relaxation on interior rings (0 .. inner_rings-2)
    # while keeping (x, y) uniformly spaced and keeping ring (inner_rings-1) fixed on the 3D surface seam
    for _ in range(35):
        z_center = 0.4 * z_center + 0.6 * (sum(p.z for p in rings_co[0]) / num_ring)
        for r_idx in range(inner_rings - 1):
            new_z = []
            for i in range(num_ring):
                z_in = z_center if r_idx == 0 else rings_co[r_idx - 1][i].z
                z_out = rings_co[r_idx + 1][i].z
                z_prev = rings_co[r_idx][(i - 1) % num_ring].z
                z_next = rings_co[r_idx][(i + 1) % num_ring].z
                avg_nb_z = 0.25 * (z_in + z_out + z_prev + z_next)
                new_z.append(0.1 * rings_co[r_idx][i].z + 0.9 * avg_nb_z)
            for i in range(num_ring):
                rings_co[r_idx][i].z = new_z[i]

    # 3. Add 2 smooth outer skirt rings (at r = 1.18 and r = 1.36) outside the surface seam
    #    while keeping ring (inner_rings-1) at r = 1.0 fixed right on the 3D surface seam!
    seam_ring_co = rings_co[inner_rings - 1]
    prev_ring_co = rings_co[inner_rings - 2]
    for r_skirt in (1.18, 1.36):
        skirt_ring = []
        ext_factor = (r_skirt - 1.0) * inner_rings
        for i in range(num_ring):
            s_pt = seam_ring_co[i]
            p_pt = prev_ring_co[i]
            sx = s_pt.x + (s_pt.x - p_pt.x) * ext_factor
            sy = s_pt.y + (s_pt.y - p_pt.y) * ext_factor
            sz = s_pt.z + (s_pt.z - p_pt.z) * (ext_factor * 0.5)
            skirt_ring.append(Vector((sx, sy, sz)))

        for _ in range(3):
            skirt_ring = [
                skirt_ring[(i - 1) % num_ring] * 0.25
                + skirt_ring[i] * 0.5
                + skirt_ring[(i + 1) % num_ring] * 0.25
                for i in range(num_ring)
            ]
        rings_co.append(skirt_ring)

    radial_rings = len(rings_co)

    # Build a wafer-thin cutting plane (NO extruded cylinder!) with parallel smooth top & bottom surfaces
    bm = bmesh.new()
    bm_vis = bmesh.new()
    dz_vec = Vector((0.0, 0.0, half_t))

    c_bottom = bm.verts.new(Vector((0.0, 0.0, z_center - half_t)))
    c_top = bm.verts.new(Vector((0.0, 0.0, z_center + half_t)))
    c_vis = bm_vis.verts.new(Vector((0.0, 0.0, z_center)))

    bottom_rings = []
    top_rings = []
    vis_rings = []
    for r_idx in range(radial_rings):
        b_ring = [bm.verts.new(co - dz_vec) for co in rings_co[r_idx]]
        t_ring = [bm.verts.new(co + dz_vec) for co in rings_co[r_idx]]
        bottom_rings.append(b_ring)
        top_rings.append(t_ring)
        if r_idx < inner_rings:
            v_ring = [bm_vis.verts.new(co) for co in rings_co[r_idx]]
            vis_rings.append(v_ring)

    # Innermost fan faces around center (bottom, top, and visual surface)
    for i in range(num_ring):
        next_i = (i + 1) % num_ring
        f_bot = bm.faces.new([c_bottom, bottom_rings[0][next_i], bottom_rings[0][i]])
        f_bot.smooth = True
        f_top = bm.faces.new([c_top, top_rings[0][i], top_rings[0][next_i]])
        f_top.smooth = True
        f_vis = bm_vis.faces.new([c_vis, vis_rings[0][i], vis_rings[0][next_i]])
        f_vis.smooth = True

    # Concentric quad rings across the cutting surface (bottom, top, and visual surface)
    for r_idx in range(radial_rings - 1):
        inner_b = bottom_rings[r_idx]
        outer_b = bottom_rings[r_idx + 1]
        inner_t = top_rings[r_idx]
        outer_t = top_rings[r_idx + 1]
        has_vis = (r_idx + 1) < len(vis_rings)
        if has_vis:
            inner_v = vis_rings[r_idx]
            outer_v = vis_rings[r_idx + 1]
        for i in range(num_ring):
            next_i = (i + 1) % num_ring
            f_bot = bm.faces.new([inner_b[i], inner_b[next_i], outer_b[next_i], outer_b[i]])
            f_bot.smooth = True
            f_top = bm.faces.new([inner_t[i], outer_t[i], outer_t[next_i], inner_t[next_i]])
            f_top.smooth = True
            if has_vis:
                f_vis = bm_vis.faces.new([inner_v[i], outer_v[i], outer_v[next_i], inner_v[next_i]])
                f_vis.smooth = True


    # Thin wafer outer rim (only 2 * half_t thick — no cylinder!)
    outer_bottom_ring = bottom_rings[-1]
    outer_top_ring = top_rings[-1]
    for i in range(num_ring):
        next_i = (i + 1) % num_ring
        bm.faces.new([outer_bottom_ring[i], outer_bottom_ring[next_i], outer_top_ring[next_i], outer_top_ring[i]])

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh_manual = bpy.data.meshes.new("MS_Manual_Surface_Cutter_Mesh")
    bm.to_mesh(mesh_manual)
    bm.free()

    cutter_obj = bpy.data.objects.new("MS_Manual_Cutter", mesh_manual)
    cutter_obj.matrix_world = world_mat
    cutter_obj.display_type = 'WIRE'
    cutter_obj.show_in_front = True
    cutter_obj["ms_is_thin_blade"] = True
    cutter_obj["ms_blade_thickness"] = float(half_t * 2.0)
    col.objects.link(cutter_obj)

    _attach_visual_surface(
        cutter_obj, bm_vis, col, name="MS_Cut_Plane_Visual", color=(0.1, 0.85, 0.35, 0.45)
    )

    centroid, world_mat = recenter_cutter_to_mesh_intersection(cutter_obj, source_obj)
    return cutter_obj, centroid, avg_normal, world_mat


def create_extruded_curve_cutter_from_points(
    context,
    source_obj,
    points_3d,
    extrude_depth_mm=10.0,
    target_collection=None,
    view_normal=None,
    smoothness=0.0,
):
    """
    Creates a watertight, manifold 3D extruded polygonal Boolean cutter volume from a closed
    3D curve contour on or near `source_obj`.
    - Extrudes inward into the mesh by `extrude_depth_mm` to form a flat internal floor cap (at local Z = 0)
      where alignment pins / holes are placed.
    - Extrudes outward past the highest point of the detail relief so Boolean DIFFERENCE + INTERSECT
      cleanly extracts the detail from the main body without cutting through the rest of the model.
    Returns (cutter_obj, floor_center, out_normal, world_mat).
    """
    col = target_collection or context.collection
    _, _, src_center, dimensions = get_world_bounds(source_obj)
    diag = max(dimensions.length, 0.1)

    if len(points_3d) < 3:
        cutter_obj, _ = setup_straight_cutter(context, source_obj, target_collection=col)
        return cutter_obj, src_center, Vector((0, 0, 1)), cutter_obj.matrix_world.copy()

    centroid = sum(points_3d, Vector()) / len(points_3d)

    # Build world-space BVHTree of source_obj to determine outward surface normal and relief height
    src_bvh_w = None
    if source_obj and source_obj.data and len(source_obj.data.polygons) > 0:
        try:
            src_mat = source_obj.matrix_world
            src_verts_w = [src_mat @ v.co for v in source_obj.data.vertices]
            src_polys = [tuple(p.vertices) for p in source_obj.data.polygons]
            src_bvh_w = BVHTree.FromPolygons(src_verts_w, src_polys)
        except Exception:
            src_bvh_w = None

    # 1. Compute outward extrusion normal (+Z points outward from main body through the detail)
    mesh_norm_sum = Vector((0.0, 0.0, 0.0))
    if src_bvh_w is not None:
        for p in list(points_3d) + [centroid]:
            _, near_norm, _, _ = src_bvh_w.find_nearest(p)
            if near_norm is not None:
                mesh_norm_sum += near_norm

    newell_norm = Vector((0.0, 0.0, 0.0))
    n_raw = len(points_3d)
    rel_pts = [p - centroid for p in points_3d]
    for i in range(n_raw):
        curr = rel_pts[i]
        nxt = rel_pts[(i + 1) % n_raw]
        newell_norm.x += (curr.y - nxt.y) * (curr.z + nxt.z)
        newell_norm.y += (curr.z - nxt.z) * (curr.x + nxt.x)
        newell_norm.z += (curr.x - nxt.x) * (curr.y + nxt.y)

    if mesh_norm_sum.length > 1e-5:
        ref_out = mesh_norm_sum.normalized()
    elif view_normal is not None and view_normal.length > 1e-5:
        ref_out = (-view_normal).normalized()
    elif (centroid - src_center).length > 1e-5:
        ref_out = (centroid - src_center).normalized()
    else:
        ref_out = Vector((0.0, 0.0, 1.0))

    if newell_norm.length > 1e-5:
        n_poly = newell_norm.normalized()
        if n_poly.dot(ref_out) < 0.0:
            n_poly = -n_poly
        out_normal = (ref_out * 0.65 + n_poly * 0.35).normalized()
    else:
        out_normal = ref_out

    if out_normal.length < 1e-5:
        out_normal = Vector((0.0, 0.0, 1.0))

    x_hint = (points_3d[0] - centroid).normalized()
    world_mat = build_orthonormal_cutter_matrix(centroid, x_hint, out_normal)
    world_mat_inv = world_mat.inverted()

    # 2. Densify the closed contour with STRAIGHT edges so every clicked / curve point stays exactly
    #    where the user put it (no spline overshoot, corner rounding or shrinkage that could drift
    #    outside the detail boundary), then snap intermediate points onto the mesh surface if close.
    clean_pts = [points_3d[0].copy()]
    for pt in points_3d[1:]:
        if (pt - clean_pts[-1]).length > 1e-6:
            clean_pts.append(pt.copy())
    if len(clean_pts) > 2 and (clean_pts[-1] - clean_pts[0]).length <= 1e-6:
        clean_pts.pop()
    m_pts = len(clean_pts)
    perimeter = sum((clean_pts[(i + 1) % m_pts] - clean_pts[i]).length for i in range(m_pts))
    target_total = 160
    smoothness = max(0.0, min(1.0, float(smoothness)))
    seam_world = []
    for i in range(m_pts):
        a = clean_pts[i]
        b = clean_pts[(i + 1) % m_pts]
        seg_len = (b - a).length
        n_sub = max(1, int(round(seg_len / max(perimeter, 1e-9) * target_total)))
        if smoothness > 1e-4 and m_pts >= 3:
            p0 = clean_pts[(i - 1) % m_pts]
            p3 = clean_pts[(i + 2) % m_pts]
        for s in range(n_sub):
            t = s / n_sub
            lin = a.lerp(b, t)
            if smoothness > 1e-4 and m_pts >= 3:
                # Catmull-Rom passes exactly through every control point; blend with the straight edge
                seam_world.append(lin.lerp(_catmull_rom_point(p0, a, b, p3, t), smoothness))
            else:
                seam_world.append(lin)
    if src_bvh_w is not None:
        for i in range(len(seam_world)):
            near_loc, _, _, dist = src_bvh_w.find_nearest(seam_world[i])
            if near_loc is not None and dist < diag * 0.2:
                seam_world[i] = near_loc

    seam_local = [world_mat_inv @ p for p in seam_world]
    num_ring = len(seam_local)

    # 3. Extract 2D polygon in cutter XY plane and enforce counter-clockwise winding
    poly_2d = [(lp.x, lp.y) for lp in seam_local]
    signed_area = 0.0
    for i in range(num_ring):
        x0, y0 = poly_2d[i]
        x1, y1 = poly_2d[(i + 1) % num_ring]
        signed_area += (x0 * y1 - x1 * y0)
    if signed_area < 0.0:
        poly_2d.reverse()

    # 4. Determine inward floor depth and outward relief clearance
    min_surf_z = min(lp.z for lp in seam_local)
    max_surf_z = max(lp.z for lp in seam_local)
    peak_z = max_surf_z

    if src_bvh_w is not None:
        min_x = min(x for x, _ in poly_2d)
        max_x = max(x for x, _ in poly_2d)
        min_y = min(y for _, y in poly_2d)
        max_y = max(y for _, y in poly_2d)
        ray_dir_w = (-out_normal).normalized()
        for u in (0.25, 0.5, 0.75):
            gx = min_x + u * (max_x - min_x)
            for v in (0.25, 0.5, 0.75):
                gy = min_y + v * (max_y - min_y)
                ray_start_w = world_mat @ Vector((gx, gy, max_surf_z + diag))
                hit_w, _, _, _ = src_bvh_w.ray_cast(ray_start_w, ray_dir_w, diag * 2.0)
                if hit_w is not None:
                    hit_l = world_mat_inv @ hit_w
                    if hit_l.z > peak_z:
                        peak_z = hit_l.z

    depth_scene = mm_to_scene_units(context, extrude_depth_mm, ref_obj=source_obj)
    depth_scene = max(1e-3, min(depth_scene, diag * 0.9))

    z_floor = min_surf_z - depth_scene
    z_top = max(max_surf_z, peak_z) + max(depth_scene * 0.4, diag * 0.08, 0.04)
    prism_height = max(z_top - z_floor, depth_scene + 0.02)

    # Shift world_mat along local +Z so the internal floor cap lies at local Z = 0.0
    world_mat.translation = world_mat @ Vector((0.0, 0.0, z_floor))

    # 5. Build watertight extruded polygonal mesh (bm), floor cap visual (bm_vis), and extruded walls visual (bm_walls)
    bm = bmesh.new()
    bm_vis = bmesh.new()
    bm_walls = bmesh.new()

    bot_verts = [bm.verts.new(Vector((x, y, 0.0))) for x, y in poly_2d]
    top_verts = [bm.verts.new(Vector((x, y, prism_height))) for x, y in poly_2d]
    vis_verts = [bm_vis.verts.new(Vector((x, y, 0.0))) for x, y in poly_2d]
    w_bot_verts = [bm_walls.verts.new(Vector((x, y, 0.0))) for x, y in poly_2d]
    w_top_verts = [bm_walls.verts.new(Vector((x, y, prism_height))) for x, y in poly_2d]

    for i in range(num_ring):
        next_i = (i + 1) % num_ring
        f_side = bm.faces.new([bot_verts[i], bot_verts[next_i], top_verts[next_i], top_verts[i]])
        f_side.smooth = True
        f_w = bm_walls.faces.new([w_bot_verts[i], w_bot_verts[next_i], w_top_verts[next_i], w_top_verts[i]])
        f_w.smooth = True

    f_bot = bm.faces.new(list(reversed(bot_verts)))
    f_top = bm.faces.new(top_verts)
    bmesh.ops.triangulate(bm, faces=[f_bot, f_top], quad_method='BEAUTY', ngon_method='EAR_CLIP')
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    f_vis = bm_vis.faces.new(vis_verts)
    bmesh.ops.triangulate(bm_vis, faces=[f_vis], quad_method='BEAUTY', ngon_method='EAR_CLIP')
    bmesh.ops.recalc_face_normals(bm_vis, faces=bm_vis.faces)

    mesh_cutter = bpy.data.meshes.new("MS_Curve_Detail_Cutter_Mesh")
    bm.to_mesh(mesh_cutter)
    bm.free()

    cutter_obj = bpy.data.objects.new("MS_Curve_Detail_Cutter", mesh_cutter)
    cutter_obj.matrix_world = world_mat
    cutter_obj.display_type = 'WIRE'
    cutter_obj.show_in_front = True
    cutter_obj["ms_is_extruded_detail"] = True
    cutter_obj["ms_extrude_depth_scene"] = float(depth_scene)
    col.objects.link(cutter_obj)

    _attach_visual_surface(
        cutter_obj, bm_vis, col, name="MS_Cut_Plane_Visual", color=(0.1, 0.85, 0.35, 0.45)
    )
    _attach_visual_surface(
        cutter_obj, bm_walls, col, name="MS_Extrude_Walls_Visual", color=(0.15, 0.75, 1.0, 0.28)
    )

    floor_center, world_mat = recenter_cutter_to_mesh_intersection(cutter_obj, source_obj)
    return cutter_obj, floor_center, out_normal, world_mat


def extract_points_from_curve_object(context, curve_obj, source_obj=None):
    """
    Samples a Blender CURVE object (Bezier, NURBS, or Poly, including Shrinkwrap or other modifiers)
    into an ordered list of 3D world-space loop points.
    """
    if not curve_obj or curve_obj.type != 'CURVE' or not curve_obj.data:
        return []

    curve_data = curve_obj.data
    orig_bevel = curve_data.bevel_depth
    orig_extrude = curve_data.extrude
    pts_3d = []

    try:
        curve_data.bevel_depth = 0.0
        curve_data.extrude = 0.0
        depsgraph = context.evaluated_depsgraph_get()
        eval_obj = curve_obj.evaluated_get(depsgraph)
        temp_mesh = eval_obj.to_mesh()
        if temp_mesh and len(temp_mesh.vertices) >= 3:
            mat_w = eval_obj.matrix_world
            pts_3d = [mat_w @ v.co for v in temp_mesh.vertices]
        eval_obj.to_mesh_clear()
    except Exception:
        pts_3d = []
    finally:
        curve_data.bevel_depth = orig_bevel
        curve_data.extrude = orig_extrude

    if len(pts_3d) < 3 and curve_data.splines:
        mat_w = curve_obj.matrix_world
        spline = curve_data.splines[0]
        if spline.type == 'BEZIER':
            pts_3d = [mat_w @ bp.co for bp in spline.bezier_points]
        else:
            pts_3d = [mat_w @ Vector((p.co.x, p.co.y, p.co.z)) for p in spline.points]

    if source_obj and source_obj.data and len(pts_3d) >= 3:
        try:
            src_mat = source_obj.matrix_world
            src_verts_w = [src_mat @ v.co for v in source_obj.data.vertices]
            src_polys = [tuple(p.vertices) for p in source_obj.data.polygons]
            src_bvh_w = BVHTree.FromPolygons(src_verts_w, src_polys)
            snapped = []
            for p in pts_3d:
                near_loc, _, _, _ = src_bvh_w.find_nearest(p)
                snapped.append(near_loc if near_loc is not None else p)
            pts_3d = snapped
        except Exception:
            pass

    return pts_3d


def create_editable_detail_curve(context, source_obj, region=None, rv3d=None):
    """
    Spawns an interactive 3D cyclic Bezier curve (`MS_Detail_Curve`) snapped onto the front
    surface of `source_obj` with a Shrinkwrap modifier so the user can shape the curve around
    a detail before extruding it into a Boolean polygon cutter.
    """
    _, _, center, dimensions = get_world_bounds(source_obj)
    diag = max(dimensions.length, 0.1)

    view_dir = Vector((0.0, 1.0, 0.0))
    if rv3d is not None:
        try:
            view_dir = (rv3d.view_rotation @ Vector((0.0, 0.0, -1.0))).normalized()
        except Exception:
            pass

    out_dir = -view_dir
    surface_origin = center + out_dir * (diag * 0.4)
    surface_normal = out_dir.copy()

    src_bvh_w = None
    if source_obj and source_obj.data and len(source_obj.data.polygons) > 0:
        try:
            src_mat = source_obj.matrix_world
            src_verts_w = [src_mat @ v.co for v in source_obj.data.vertices]
            src_polys = [tuple(p.vertices) for p in source_obj.data.polygons]
            src_bvh_w = BVHTree.FromPolygons(src_verts_w, src_polys)
            ray_start = center + out_dir * (diag * 2.0)
            hit_loc, hit_norm, _, _ = src_bvh_w.ray_cast(ray_start, view_dir, diag * 4.0)
            if hit_loc is not None:
                surface_origin = hit_loc
                if hit_norm is not None and hit_norm.length > 1e-5:
                    surface_normal = hit_norm.normalized()
        except Exception:
            pass

    frame_mat = build_orthonormal_cutter_matrix(surface_origin, Vector((1.0, 0.0, 0.0)), surface_normal)
    frame_inv = frame_mat.inverted()

    curve_data = bpy.data.curves.new("MS_Detail_Curve_Data", type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.resolution_u = 16
    curve_data.bevel_depth = max(diag * 0.0035, 0.001)

    spline = curve_data.splines.new('BEZIER')
    spline.use_cyclic_u = True
    num_ctrl = 8
    spline.bezier_points.add(num_ctrl - 1)
    radius = max(diag * 0.12, 0.04)

    for i in range(num_ctrl):
        ang = (2.0 * math.pi * i) / num_ctrl
        local_pt = Vector((math.cos(ang) * radius, math.sin(ang) * radius, 0.0))
        world_pt = frame_mat @ local_pt
        if src_bvh_w is not None:
            near_loc, _, _, _ = src_bvh_w.find_nearest(world_pt)
            if near_loc is not None:
                local_pt = frame_inv @ near_loc
        bp = spline.bezier_points[i]
        bp.co = local_pt
        bp.handle_left_type = 'AUTO'
        bp.handle_right_type = 'AUTO'

    curve_obj = bpy.data.objects.new("MS_Detail_Curve", curve_data)
    curve_obj.matrix_world = frame_mat
    curve_obj.color = (0.1, 0.9, 1.0, 1.0)
    curve_obj.show_in_front = True
    curve_obj["ms_source_obj"] = source_obj.name

    target_col = source_obj.users_collection[0] if source_obj.users_collection else context.collection
    target_col.objects.link(curve_obj)

    try:
        sw_mod = curve_obj.modifiers.new(name="MS_Surface_Snap", type='SHRINKWRAP')
        sw_mod.target = source_obj
        sw_mod.wrap_method = 'NEAREST_SURFACEPOINT'
        sw_mod.offset = curve_data.bevel_depth * 0.5
        if hasattr(sw_mod, "use_apply_on_spline"):
            sw_mod.use_apply_on_spline = True
    except Exception:
        pass

    return curve_obj
