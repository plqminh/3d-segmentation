"""
ModelSplitter - Boolean Operations Engine
Wraps Blender's native Exact Boolean solver for rock-solid volumetric mesh splitting,
pin union, and socket subtraction.
"""

import math
import bpy
import bmesh
from ..utils.mesh_utils import cleanup_mesh, separate_loose_parts, duplicate_object


def apply_boolean_modifier(target_obj, tool_obj, operation='DIFFERENCE', solver='EXACT'):
    """
    Applies a boolean operation between target_obj and tool_obj.
    Operation: 'DIFFERENCE', 'UNION', 'INTERSECT'
    Solver: 'EXACT' (default, robust) or 'FAST'
    """
    if not target_obj or not tool_obj:
        return False

    prev_active = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = target_obj

    mod = target_obj.modifiers.new(name=f"MS_{operation}", type='BOOLEAN')
    mod.operation = operation
    mod.solver = solver
    mod.object = tool_obj

    try:
        bpy.ops.object.modifier_apply(modifier=mod.name)
        cleanup_mesh(target_obj)
        success = True
    except Exception as e:
        print(f"[ModelSplitter] Boolean {operation} failed: {e}")
        # Clean up modifier if failed
        if mod.name in target_obj.modifiers:
            target_obj.modifiers.remove(mod)
        success = False
    finally:
        bpy.context.view_layer.objects.active = prev_active

    return success


def _find_face_components(mesh_data):
    """Returns a list of connected face-index components (islands) in mesh_data."""
    bm = bmesh.new()
    bm.from_mesh(mesh_data)
    bm.faces.ensure_lookup_table()
    visited = set()
    components = []
    for f in bm.faces:
        if f.index in visited:
            continue
        comp_faces = []
        comp_verts = set()
        stack = [f]
        visited.add(f.index)
        while stack:
            curr = stack.pop()
            comp_faces.append(curr.index)
            for v in curr.verts:
                comp_verts.add(v.index)
            for e in curr.edges:
                for nb in e.link_faces:
                    if nb.index not in visited:
                        visited.add(nb.index)
                        stack.append(nb)
        components.append((comp_faces, list(comp_verts)))
    bm.free()
    return components


def _delete_face_indices(obj, face_indices_to_delete):
    """Deletes the specified polygon indices from obj.data using bmesh."""
    if not face_indices_to_delete:
        return
    del_set = set(face_indices_to_delete)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    faces_del = [bm.faces[i] for i in del_set if i < len(bm.faces)]
    if faces_del:
        bmesh.ops.delete(bm, geom=faces_del, context='FACES')
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def _split_mesh_by_thin_blade(context, source_obj, cutter_volume, target_col, split_islands=True):
    """
    Slices source_obj using ONLY the wafer-thin cutting plane (no cylinder extrusion),
    then partitions the severed mesh islands across the cutting plane into Part A (-Z)
    and Part B (+Z).
    """
    total_orig_faces = len(source_obj.data.polygons)
    min_sub_faces = max(16, int(total_orig_faces * 0.004))
    orig_comps = _find_face_components(source_obj.data)
    orig_sub_count = sum(1 for f_idx, _ in orig_comps if len(f_idx) >= min_sub_faces)

    sliced_obj = duplicate_object(context, source_obj, name_suffix="_Sliced", target_collection=target_col)
    diff_ok = apply_boolean_modifier(sliced_obj, cutter_volume, operation='DIFFERENCE', solver='EXACT')
    if not diff_ok:
        bpy.data.objects.remove(sliced_obj, do_unlink=True)
        return [], []

    components = _find_face_components(sliced_obj.data)
    sub_count = sum(1 for f_idx, _ in components if len(f_idx) >= min_sub_faces)
    blade_r = max((math.hypot(v.co.x, v.co.y) for v in cutter_volume.data.vertices), default=1.0)
    blade_t = float(cutter_volume.get("ms_blade_thickness", 1e-3))

    # If the contour was placed slightly inside the neck silhouette, progressively widen the outer rings in XY
    # (and flare outer rim thickness if a sparse chord missed a curved surface ridge)
    # while keeping the interior pin surface (r_idx <= 3) 100% fixed so pins/sockets always stay flush
    if sub_count <= orig_sub_count:
        orig_coords = [v.co.copy() for v in cutter_volume.data.vertices]
        cx0 = orig_coords[0].x if orig_coords else 0.0
        cy0 = orig_coords[0].y if orig_coords else 0.0
        num_ring = 64
        retry_steps = (
            (1.35, blade_r * 0.02),
            (1.60, blade_r * 0.05),
            (1.85, blade_r * 0.09),
        )
        for expand_xy, rim_half_z in retry_steps:
            bpy.data.objects.remove(sliced_obj, do_unlink=True)
            for idx_v, (v, co) in enumerate(zip(cutter_volume.data.vertices, orig_coords)):
                if idx_v < 2:
                    sign_z = -1.0 if idx_v == 0 else 1.0
                    r_idx = -1
                else:
                    ring_pair = (idx_v - 2) // (2 * num_ring)
                    in_pair = (idx_v - 2) % (2 * num_ring)
                    sign_z = -1.0 if in_pair < num_ring else 1.0
                    r_idx = ring_pair

                # Keep all interior rings (r_idx <= 6, up to 87.5% of seam radius) at exact wafer thickness
                # so pins/sockets anywhere inside the cross-section always penetrate both parts deeply.
                # Only ramp XY expansion from r_idx >= 5 and rim Z capture on the outer skin/skirt (r_idx >= 7).
                if r_idx >= 5:
                    t_xy = min(1.0, (r_idx - 4) / 4.0)
                    scale_r = 1.0 + (expand_xy - 1.0) * t_xy
                    v.co.x = cx0 + (co.x - cx0) * scale_r
                    v.co.y = cy0 + (co.y - cy0) * scale_r
                else:
                    v.co.x = co.x
                    v.co.y = co.y

                if r_idx >= 7:
                    t_z = min(1.0, (r_idx - 6) / 3.0)
                    v.co.z = co.z + sign_z * (rim_half_z * t_z)
                else:
                    v.co.z = co.z

            cutter_volume.data.update()


            sliced_obj = duplicate_object(context, source_obj, name_suffix="_Sliced", target_collection=target_col)
            diff_ok = apply_boolean_modifier(sliced_obj, cutter_volume, operation='DIFFERENCE', solver='EXACT')
            if not diff_ok:
                continue
            components = _find_face_components(sliced_obj.data)
            sub_count = sum(1 for f_idx, _ in components if len(f_idx) >= min_sub_faces)
            if sub_count > orig_sub_count:
                break

        for v, co in zip(cutter_volume.data.vertices, orig_coords):
            v.co = co
        cutter_volume.data.update()

        if not diff_ok or sliced_obj.name not in bpy.data.objects:
            return [], []


    if sub_count <= orig_sub_count:
        # Mesh was not severed into new substantial islands
        sliced_obj.name = f"{source_obj.name}_Part_A"
        return [sliced_obj], []

    world_to_blade = cutter_volume.matrix_world.inverted() @ sliced_obj.matrix_world
    blade_t = float(cutter_volume.get("ms_blade_thickness", 1e-3))

    # Filter out tiny boolean grazing slivers (< min_sub_faces) created along curved triangle edges
    valid_components = [
        (idx, f_indices, v_indices)
        for idx, (f_indices, v_indices) in enumerate(components)
        if len(f_indices) >= min_sub_faces
    ]
    sliver_faces = [
        fi
        for f_indices, _ in components
        if len(f_indices) < min_sub_faces
        for fi in f_indices
    ]

    verts = sliced_obj.data.vertices
    comp_info = []
    for idx, f_indices, v_indices in valid_components:
        pts_l = [world_to_blade @ verts[vi].co for vi in v_indices]
        in_radius_z = [abs(p.z) for p in pts_l if math.hypot(p.x, p.y) <= blade_r * 1.25]
        min_z_dist = min(in_radius_z) if in_radius_z else 1e9
        touched = (min_z_dist <= max(blade_t * 12.0, blade_r * 0.18))

        near_z = [p.z for p in pts_l if math.hypot(p.x, p.y) <= blade_r * 1.25 and abs(p.z) <= blade_r * 1.0]
        avg_z = (sum(near_z) / len(near_z)) if near_z else (sum(p.z for p in pts_l) / max(1, len(pts_l)))
        comp_info.append((idx, f_indices, touched, avg_z))

    touched_comps = [c for c in comp_info if c[2]]
    if len(touched_comps) < 2:
        touched_comps = comp_info

    faces_a = []
    faces_b = []

    pos_touched = [c for c in touched_comps if c[3] > 0.0]
    neg_touched = [c for c in touched_comps if c[3] <= 0.0]

    if pos_touched and neg_touched:
        b_set = {c[0] for c in pos_touched}
    else:
        # Fallback if all touched components share the same sign: highest avg_z is Part B
        highest_b = max(touched_comps, key=lambda c: c[3])[0]
        b_set = {highest_b}

    for idx, f_indices, _, _ in comp_info:
        if idx in b_set:
            faces_b.extend(f_indices)
        else:
            faces_a.extend(f_indices)

    part_a = duplicate_object(context, sliced_obj, name_suffix="", target_collection=target_col)
    part_a.name = f"{source_obj.name}_Part_A"
    part_b = duplicate_object(context, sliced_obj, name_suffix="", target_collection=target_col)
    part_b.name = f"{source_obj.name}_Part_B"
    bpy.data.objects.remove(sliced_obj, do_unlink=True)

    _delete_face_indices(part_a, faces_b + sliver_faces)
    _delete_face_indices(part_b, faces_a + sliver_faces)

    results_a = [part_a] if len(part_a.data.polygons) > 0 else []
    results_b = [part_b] if len(part_b.data.polygons) > 0 else []

    touched_a_count = sum(1 for idx, _, touched, _ in comp_info if touched and idx not in b_set)
    touched_b_count = sum(1 for idx, _, touched, _ in comp_info if touched and idx in b_set)

    if split_islands:
        if touched_a_count > 1 and part_a and len(part_a.data.polygons) > 0:
            islands_a = separate_loose_parts(context, part_a)
            if islands_a:
                results_a = []
                for o in islands_a:
                    if len(o.data.polygons) >= min_sub_faces:
                        results_a.append(o)
                    else:
                        bpy.data.objects.remove(o, do_unlink=True)
        if touched_b_count > 1 and part_b and len(part_b.data.polygons) > 0:
            islands_b = separate_loose_parts(context, part_b)
            if islands_b:
                results_b = []
                for o in islands_b:
                    if len(o.data.polygons) >= min_sub_faces:
                        results_b.append(o)
                    else:
                        bpy.data.objects.remove(o, do_unlink=True)

    return results_a, results_b




def split_mesh_by_cutter_volume(context, source_obj, cutter_volume, split_islands=True):
    """
    Splits source_obj into two solid halves using either a wafer-thin cutting plane
    (for Manual surface cuts) or a half-space cutter volume.
    Returns (part_a, part_b).
    """
    target_col = source_obj.users_collection[0] if source_obj.users_collection else context.collection

    if cutter_volume.get("ms_is_thin_blade", False):
        return _split_mesh_by_thin_blade(
            context, source_obj, cutter_volume, target_col, split_islands=split_islands
        )

    # Create duplicates for Part A and Part B
    part_a = duplicate_object(context, source_obj, name_suffix="_Part_A", target_collection=target_col)
    part_b = duplicate_object(context, source_obj, name_suffix="_Part_B", target_collection=target_col)

    # Execute Part A (DIFFERENCE)
    diff_ok = apply_boolean_modifier(part_a, cutter_volume, operation='DIFFERENCE', solver='EXACT')
    if not diff_ok:
        bpy.data.objects.remove(part_a, do_unlink=True)
        part_a = None

    # Execute Part B (INTERSECT)
    inter_ok = apply_boolean_modifier(part_b, cutter_volume, operation='INTERSECT', solver='EXACT')
    if not inter_ok:
        bpy.data.objects.remove(part_b, do_unlink=True)
        part_b = None

    results_a = [part_a] if part_a else []
    results_b = [part_b] if part_b else []

    # Optionally separate loose geometric islands if the cut severed disconnected limbs
    if split_islands:
        if part_a and len(part_a.data.polygons) > 0:
            islands_a = separate_loose_parts(context, part_a)
            if islands_a:
                results_a = islands_a
        if part_b and len(part_b.data.polygons) > 0:
            islands_b = separate_loose_parts(context, part_b)
            if islands_b:
                results_b = islands_b

    return results_a, results_b


def apply_connectors_to_parts(context, part_a_list, part_b_list, pins, sockets, target_side='PART_A'):
    """
    Unions pins into the male part(s), and carves sockets (with clearance) out of the female part(s).
    target_side: 'PART_A' means pins attached to Part A, sockets subtracted from Part B.
                 'PART_B' means pins attached to Part B, sockets subtracted from Part A.
    """
    if not pins or not sockets:
        return

    male_list = part_a_list if target_side == 'PART_A' else part_b_list
    female_list = part_b_list if target_side == 'PART_A' else part_a_list

    if not male_list or not female_list:
        return

    # 1. Union all pins into male target(s)
    for m_obj in male_list:
        if not m_obj or m_obj.name not in bpy.data.objects:
            continue
        for pin in pins:
            if pin and pin.name in bpy.data.objects:
                apply_boolean_modifier(m_obj, pin, operation='UNION', solver='EXACT')

    # 2. Difference all sockets from female target(s)
    for f_obj in female_list:
        if not f_obj or f_obj.name not in bpy.data.objects:
            continue
        for socket in sockets:
            if socket and socket.name in bpy.data.objects:
                apply_boolean_modifier(f_obj, socket, operation='DIFFERENCE', solver='EXACT')
