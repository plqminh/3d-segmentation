"""
ModelSplitter - Draft Mode Manager
Provides a non-destructive editing workflow allowing live interactive positioning of
the cutting plane and connectors before baking final geometry.
"""

import bpy
from mathutils import Vector, Matrix
from ..utils.mesh_utils import (
    get_or_create_collection,
    remove_collection_and_objects,
    apply_object_transforms,
    separate_loose_parts,
)
from ..utils.math_utils import get_world_bounds, mm_to_scene_units
from .cutter_geometry import setup_straight_cutter, setup_curved_cutter, setup_base_cutter
from .connectors import generate_cut_connectors
from .boolean_ops import split_mesh_by_cutter_volume, apply_connectors_to_parts


DRAFT_COLLECTION_NAME = "ModelSplitter_Draft"


def _move_object_hierarchy_to_collection(obj, target_col):
    """Links obj and all its children exclusively to target_col."""
    items = [obj] + list(obj.children)
    for item in items:
        for col in list(item.users_collection):
            if col != target_col:
                col.objects.unlink(item)
        if item.name not in target_col.objects:
            target_col.objects.link(item)


def enter_draft_mode(context, source_obj, cut_type='STRAIGHT', existing_cutter=None, custom_world_mat=None):
    """
    Initializes non-destructive Draft Mode for source_obj.
    Creates interactive cutter (or adopts drawn existing_cutter) and preview connectors.
    """
    settings = context.scene.model_splitter
    cut_props = settings.cut

    # Reset plane expand/contract factor for the new cut (draft flag is still False, so no callback work)
    if cut_props.plane_scale != 1.0:
        cut_props.plane_scale = 1.0

    # Ensure transforms are applied for accurate booleans
    apply_object_transforms(source_obj, location=False, rotation=True, scale=True)

    # Clean any stale draft state if we are not adopting an already-created cutter in the draft collection
    if not existing_cutter:
        cancel_draft_mode(context)

    draft_col = get_or_create_collection(context, name=DRAFT_COLLECTION_NAME)

    # Setup cutter based on chosen mode or adopt existing cutter
    if existing_cutter:
        cutter_obj = existing_cutter
        keep_objs = {cutter_obj} | set(cutter_obj.children)
        for obj in list(draft_col.objects):
            if obj not in keep_objs:
                bpy.data.objects.remove(obj, do_unlink=True)
        _move_object_hierarchy_to_collection(cutter_obj, draft_col)
    elif cut_type == 'CURVED':
        cutter_obj = setup_curved_cutter(context, source_obj, target_collection=draft_col)
    elif cut_type == 'SEPARATE_BASE':
        cutter_obj, _ = setup_base_cutter(context, source_obj, target_collection=draft_col)
    else:
        cutter_obj, _ = setup_straight_cutter(context, source_obj, target_collection=draft_col)

    cut_props.cut_type = cut_type if cut_type in ('STRAIGHT', 'CURVED', 'MANUAL', 'EXTRUDE_CURVE', 'POLYGONAL_LINE', 'POLYGONAL_CYLINDER', 'SEPARATE_BASE') else 'STRAIGHT'

    if custom_world_mat:
        cutter_obj.matrix_world = custom_world_mat

    cut_props.active_source_name = source_obj.name
    cut_props.active_cutter_name = cutter_obj.name
    cut_props.is_in_draft = True

    # Generate initial preview connectors
    update_draft_connectors(context)

    # Make cutter active and select it so user can move/rotate it with standard gizmo
    bpy.ops.object.select_all(action='DESELECT')
    cutter_obj.select_set(True)
    context.view_layer.objects.active = cutter_obj


def swap_pin_target(context):
    """Swaps the male pin assignment between Part A and Part B and updates preview."""
    settings = context.scene.model_splitter
    con_props = settings.connector
    con_props.target_side = 'PART_B' if con_props.target_side == 'PART_A' else 'PART_A'
    update_draft_connectors(context)


def _extract_draft_pin_xy_offsets(draft_col, cutter_mat_inv):
    """Extracts 2D (x, y) local coordinates of existing draft preview pins in cutter space."""
    if not draft_col:
        return []
    pin_objs = sorted(
        [obj for obj in draft_col.objects if obj.name.startswith("MS_Conn_") and obj.name.endswith("_Pin")],
        key=lambda o: o.name,
    )
    offsets = []
    for pin in pin_objs:
        local_pos = cutter_mat_inv @ pin.matrix_world.translation
        offsets.append((local_pos.x, local_pos.y))
    return offsets



def sync_draft_cutter_transforms(cutter_obj):
    """
    If the user directly transformed the visual cutting plane helper in the viewport,
    propagates the world transformation to the parent boolean cutter volume.
    """
    if not cutter_obj:
        return
    from .cutter_geometry import get_cutter_visual_surface_obj
    vis_obj = get_cutter_visual_surface_obj(cutter_obj)
    if vis_obj:
        loc_offset = vis_obj.location.length
        rot_offset = abs(vis_obj.rotation_euler.x) + abs(vis_obj.rotation_euler.y) + abs(vis_obj.rotation_euler.z)
        scale_offset = abs(vis_obj.scale.x - 1.0) + abs(vis_obj.scale.y - 1.0) + abs(vis_obj.scale.z - 1.0)
        if loc_offset > 1e-5 or rot_offset > 1e-4 or scale_offset > 1e-4:
            cutter_obj.matrix_world = vis_obj.matrix_world.copy()
            vis_obj.location = Vector((0.0, 0.0, 0.0))
            vis_obj.rotation_euler = (0.0, 0.0, 0.0)
            vis_obj.scale = Vector((1.0, 1.0, 1.0))
            try:
                bpy.context.view_layer.update()
            except Exception:
                pass


def rebuild_cutter_from_visual_surface(cutter_obj):
    """
    Rebuilds cutter_obj boolean volume mesh from the user-edited visual surface mesh
    by solidifying the sheet into a closed, watertight manifold blade.
    """
    if not cutter_obj or not cutter_obj.data:
        return False
    import bmesh
    from .cutter_geometry import get_cutter_visual_surface_obj
    vis_obj = get_cutter_visual_surface_obj(cutter_obj)
    if not vis_obj or not vis_obj.data or not vis_obj.data.polygons:
        return False

    blade_t = float(cutter_obj.get("ms_blade_thickness", 1e-3))

    bm_cut = bmesh.new()
    bm_cut.from_mesh(vis_obj.data)
    bmesh.ops.recalc_face_normals(bm_cut, faces=bm_cut.faces)
    try:
        bmesh.ops.solidify(bm_cut, geom=bm_cut.faces, thickness=blade_t)
        bmesh.ops.recalc_face_normals(bm_cut, faces=bm_cut.faces)
        bm_cut.to_mesh(cutter_obj.data)
        cutter_obj.data.update()
        return True
    except Exception as e:
        print("rebuild_cutter_from_visual_surface error:", e)
        return False
    finally:
        bm_cut.free()

def update_draft_connectors(context, force_auto=False):
    """
    Regenerates connector preview objects in the draft collection to reflect
    changes in count, shape, diameter, and clearance.
    Preserves custom pin positions when placement_mode == 'MANUAL' unless force_auto=True.
    """
    from mathutils import Matrix
    settings = context.scene.model_splitter
    cut_props = settings.cut
    con_props = settings.connector

    if not cut_props.is_in_draft:
        return

    cutter_obj = bpy.data.objects.get(cut_props.active_cutter_name)
    source_obj = bpy.data.objects.get(cut_props.active_source_name)
    draft_col = bpy.data.collections.get(DRAFT_COLLECTION_NAME)

    if not cutter_obj or not source_obj or not draft_col:
        return

    sync_draft_cutter_transforms(cutter_obj)

    try:
        context.view_layer.update()
    except Exception:
        pass

    cutter_mat = cutter_obj.matrix_world.copy()
    cutter_mat_inv = cutter_mat.inverted()

    manual_xy = None
    if con_props.placement_mode == 'MANUAL' and not force_auto:
        manual_xy = _extract_draft_pin_xy_offsets(draft_col, cutter_mat_inv)

    # Remove existing connector previews in draft collection
    for obj in list(draft_col.objects):
        if obj.name.startswith("MS_Conn_"):
            bpy.data.objects.remove(obj, do_unlink=True)

    _, _, _, dimensions = get_world_bounds(source_obj)
    bounds_radius = dimensions.length * 0.5

    # Generate preview pins and sockets snapped inside the actual cut cross-section
    pins, sockets = generate_cut_connectors(
        context,
        cut_plane_matrix=cutter_mat,
        bounds_radius=bounds_radius,
        target_collection=draft_col,
        cutter_obj=cutter_obj,
        source_obj=source_obj,
        manual_xy_offsets=manual_xy,
    )

    # Style preview connectors and parent in cutter local space without transform jump.
    # Parent each socket to its pin so moving a pin in MANUAL mode moves its socket wireframe automatically.
    is_holes_only = bool(getattr(con_props, "holes_only", False))
    for pin, socket in zip(pins, sockets):
        local_mat = cutter_mat_inv @ pin.matrix_world
        if is_holes_only:
            pin.display_type = 'WIRE'
            pin.color = (0.9, 0.2, 0.1, 0.6)  # Red wireframe marker when carving holes only
        else:
            pin.display_type = 'SOLID'
            pin.color = (0.1, 0.9, 0.3, 0.8)  # Bright green for male pin / dowel
        pin.show_wire = True
        pin.parent = cutter_obj
        pin.matrix_parent_inverse = Matrix.Identity(4)
        pin.matrix_basis = local_mat

        socket.display_type = 'WIRE'
        socket.color = (0.9, 0.2, 0.1, 0.6)  # Red wireframe for female socket clearance
        socket.show_wire = True
        socket.hide_select = True
        socket.parent = pin
        socket.matrix_parent_inverse = Matrix.Identity(4)
        socket.matrix_basis = Matrix.Identity(4)


def _rebuild_manual_cutter_scaled(context, old_cutter, source_obj, draft_col, target):
    """
    Expands / contracts a Manual Surface cut by adding or removing loops outside the
    cutting plane following the user's manual curve.
    The manual curve itself remains strictly unchanged.
    """
    from .cutter_geometry import create_cutter_from_surface_points

    flat = list(old_cutter.get("ms_surface_points", []))
    pts = [Vector((flat[i], flat[i + 1], flat[i + 2])) for i in range(0, len(flat) - 2, 3)]
    if len(pts) < 3:
        return False

    # The manual curve points `pts` NEVER change!
    # `target` (plane_scale) directly controls the number of outer skirt loops:
    # 0.0 -> 0 loops (cut plane stops exactly on the drawn manual curve)
    # 0.5 -> 1 loop outside
    # 1.0 -> 2 loops outside (default)
    # 1.5 -> 3 loops outside
    # 2.0 -> 4 loops outside
    # 3.0 -> 6 loops outside
    # 5.0 -> 10 loops outside
    skirt_loops = max(0, int(round(target * 2.0)))

    for obj in list(draft_col.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    new_cutter, _, _, _ = create_cutter_from_surface_points(
        context, source_obj, pts, target_collection=draft_col, skirt_loops=skirt_loops
    )
    # Keep ORIGINAL points and current scale factor
    new_cutter["ms_surface_points"] = flat
    new_cutter["ms_plane_scale"] = target
    new_cutter["ms_skirt_loops"] = skirt_loops
    context.scene.model_splitter.cut.active_cutter_name = new_cutter.name
    update_draft_connectors(context)

    bpy.ops.object.select_all(action='DESELECT')
    new_cutter.select_set(True)
    context.view_layer.objects.active = new_cutter
    return True


def apply_plane_scale(context):
    """
    Expands or contracts the active cutting plane (and its visuals) in its own local XY plane
    to match `cut_props.plane_scale`. Vertices are scaled around the cutter origin so the
    cutting surface keeps its position, orientation and thickness.
    Manual Surface cuts instead offset their drawn contour along the mesh skin.
    """
    settings = context.scene.model_splitter
    cut_props = settings.cut
    if not cut_props.is_in_draft:
        return

    cutter_obj = bpy.data.objects.get(cut_props.active_cutter_name)
    if not cutter_obj or not cutter_obj.data:
        return

    current = float(cutter_obj.get("ms_plane_scale", 1.0))
    target = max(0.05, float(cut_props.plane_scale))
    factor = target / max(current, 1e-6)
    if abs(factor - 1.0) < 1e-6:
        return

    source_obj = bpy.data.objects.get(cut_props.active_source_name)
    draft_col = bpy.data.collections.get(DRAFT_COLLECTION_NAME)
    if (
        cutter_obj.get("ms_is_thin_blade", False)
        and cutter_obj.get("ms_surface_points")
        and source_obj
        and draft_col
    ):
        if _rebuild_manual_cutter_scaled(context, cutter_obj, source_obj, draft_col, target):
            return

    meshes = [cutter_obj] + [c for c in cutter_obj.children if c.type == 'MESH']
    for obj in meshes:
        if not obj.data:
            continue
        for v in obj.data.vertices:
            v.co.x *= factor
            v.co.y *= factor
        obj.data.update()

    cutter_obj["ms_plane_scale"] = target
    update_draft_connectors(context)


def rebuild_extruded_cutter(context):
    """
    Rebuilds the active curve-detail cutter in Draft Mode from its stored control points using the
    current Curve Smoothness and Extrude Depth, then refreshes the connector previews.
    """
    from .cutter_geometry import create_extruded_curve_cutter_from_points
    settings = context.scene.model_splitter
    cut_props = settings.cut
    if not cut_props.is_in_draft:
        return

    old_cutter = bpy.data.objects.get(cut_props.active_cutter_name)
    source_obj = bpy.data.objects.get(cut_props.active_source_name)
    draft_col = bpy.data.collections.get(DRAFT_COLLECTION_NAME)
    if not old_cutter or not source_obj or not draft_col or not old_cutter.get("ms_is_extruded_detail", False):
        return

    flat = list(old_cutter.get("ms_detail_points", []))
    pts = [Vector((flat[i], flat[i + 1], flat[i + 2])) for i in range(0, len(flat) - 2, 3)]
    if len(pts) < 3:
        return

    for obj in list(draft_col.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    new_cutter, _, _, _ = create_extruded_curve_cutter_from_points(
        context,
        source_obj,
        pts,
        extrude_depth_mm=cut_props.extrude_depth_mm,
        target_collection=draft_col,
        smoothness=cut_props.curve_smoothness,
    )
    cut_props.active_cutter_name = new_cutter.name
    apply_plane_scale(context)
    update_draft_connectors(context)

    bpy.ops.object.select_all(action='DESELECT')
    new_cutter.select_set(True)
    context.view_layer.objects.active = new_cutter


def update_draft_extrude_depth(context):
    """
    Dynamically updates the extrusion depth of an active `MS_Curve_Detail_Cutter` in Draft Mode
    and refreshes the connector preview on its internal floor cap.
    """
    from mathutils import Matrix
    settings = context.scene.model_splitter
    cut_props = settings.cut
    if not cut_props.is_in_draft:
        return

    cutter_obj = bpy.data.objects.get(cut_props.active_cutter_name)
    source_obj = bpy.data.objects.get(cut_props.active_source_name)
    if not cutter_obj or not source_obj or not cutter_obj.get("ms_is_extruded_detail", False):
        return

    old_depth = float(cutter_obj.get("ms_extrude_depth_scene", 0.1))
    new_depth = max(1e-3, mm_to_scene_units(context, cut_props.extrude_depth_mm, ref_obj=source_obj))
    dz = new_depth - old_depth
    if abs(dz) < 1e-6:
        return

    # Shift cutter origin (internal floor cap Z=0) deeper along local -Z by dz,
    # and raise top vertices (v.co.z > 1e-4) by +dz so the outer cap stays fixed in world space
    cutter_obj.matrix_world = cutter_obj.matrix_world @ Matrix.Translation(Vector((0.0, 0.0, -dz)))
    for v in cutter_obj.data.vertices:
        if v.co.z > 1e-4:
            v.co.z = max(1e-3, v.co.z + dz)
    cutter_obj.data.update()

    for child in cutter_obj.children:
        if child.type == 'MESH' and child.data and "Extrude_Walls_Visual" in child.name:
            for v in child.data.vertices:
                if v.co.z > 1e-4:
                    v.co.z = max(1e-3, v.co.z + dz)
            child.data.update()

    cutter_obj["ms_extrude_depth_scene"] = float(new_depth)
    update_draft_connectors(context)


def apply_draft_build(context):
    """
    Bakes and applies the split and connector operations permanently.
    Cleans up draft helpers and generates final separated parts.
    Returns list of resulting part objects.
    """
    settings = context.scene.model_splitter
    cut_props = settings.cut
    con_props = settings.connector

    source_obj = bpy.data.objects.get(cut_props.active_source_name)
    cutter_obj = bpy.data.objects.get(cut_props.active_cutter_name)

    if not source_obj or not cutter_obj:
        cancel_draft_mode(context)
        return []

    if context.mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

    sync_draft_cutter_transforms(cutter_obj)
    rebuild_cutter_from_visual_surface(cutter_obj)

    try:
        context.view_layer.update()
    except Exception:
        pass

    # Preserve cutter transformation
    cutter_matrix = cutter_obj.matrix_world.copy()
    cutter_mat_inv = cutter_matrix.inverted()
    _, _, _, dimensions = get_world_bounds(source_obj)
    bounds_radius = dimensions.length * 0.5

    # 1. Capture manual pin positions (if any) and unlink draft preview connectors
    draft_col = bpy.data.collections.get(DRAFT_COLLECTION_NAME)
    manual_xy = None
    if draft_col and con_props.placement_mode == 'MANUAL':
        manual_xy = _extract_draft_pin_xy_offsets(draft_col, cutter_mat_inv)

    if draft_col:
        for obj in list(draft_col.objects):
            if obj.name.startswith("MS_Conn_"):
                bpy.data.objects.remove(obj, do_unlink=True)

    # 2. Generate final pin and socket solids snapped inside the cut cross-section
    target_col = source_obj.users_collection[0] if source_obj.users_collection else context.collection
    pins, sockets = generate_cut_connectors(
        context,
        cut_plane_matrix=cutter_matrix,
        bounds_radius=bounds_radius,
        target_collection=target_col,
        cutter_obj=cutter_obj,
        source_obj=source_obj,
        manual_xy_offsets=manual_xy,
    )

    is_thin_blade = bool(cutter_obj.get("ms_is_thin_blade", False))
    cut_gap = mm_to_scene_units(context, con_props.cut_gap_mm, ref_obj=source_obj)

    # 3. Perform solid volume cut (keep parts unified while applying connectors)
    parts_a, parts_b = split_mesh_by_cutter_volume(
        context,
        source_obj,
        cutter_obj,
        split_islands=cut_props.split_islands if is_thin_blade else False,
        cut_gap=cut_gap,
    )

    # 4. Apply connectors (Pins & Sockets) to unified halves before island separation
    is_holes_only = bool(getattr(con_props, "holes_only", False))
    apply_connectors_to_parts(
        context,
        parts_a,
        parts_b,
        pins,
        sockets,
        target_side=con_props.target_side,
        double_sided=con_props.double_sided,
        holes_only=is_holes_only,
    )

    # 4b. Separate loose islands after pins/sockets have been cleanly attached/carved
    if cut_props.split_islands and not is_thin_blade:
        final_a = []
        for pa in parts_a:
            if pa and pa.name in bpy.data.objects and len(pa.data.polygons) > 0:
                islands = separate_loose_parts(context, pa)
                if islands and len(islands) > 1:
                    valid_a = [o for o in islands if len(o.data.polygons) >= 4]
                    if valid_a:
                        for o in islands:
                            if len(o.data.polygons) < 4:
                                bpy.data.objects.remove(o, do_unlink=True)
                        islands = valid_a
                final_a.extend(islands if islands else [pa])
        parts_a = final_a

        final_b = []
        for pb in parts_b:
            if pb and pb.name in bpy.data.objects and len(pb.data.polygons) > 0:
                islands = separate_loose_parts(context, pb)
                if islands and len(islands) > 1:
                    valid_b = [o for o in islands if len(o.data.polygons) >= 4]
                    if valid_b:
                        for o in islands:
                            if len(o.data.polygons) < 4:
                                bpy.data.objects.remove(o, do_unlink=True)
                        islands = valid_b
                final_b.extend(islands if islands else [pb])
        parts_b = final_b


    # 5. Clean up helper solids (sockets, and pins unless double_sided loose dowels are requested)
    dowel_objs = []
    if con_props.double_sided and not is_holes_only and parts_a and parts_b:
        for idx_p, p in enumerate(pins):
            if p and p.name in bpy.data.objects:
                p.name = f"{source_obj.name}_Dowel_{idx_p + 1}"
                p.display_type = 'TEXTURED'
                p.show_wire = False
                p.color = (1.0, 1.0, 1.0, 1.0)
                dowel_objs.append(p)
    else:
        for p in pins:
            if p and p.name in bpy.data.objects:
                bpy.data.objects.remove(p, do_unlink=True)

    for s in sockets:
        if s and s.name in bpy.data.objects:
            bpy.data.objects.remove(s, do_unlink=True)

    # 6. Clean up draft collection & cutter
    remove_collection_and_objects(context, name=DRAFT_COLLECTION_NAME)

    # Hide or archive original source object
    source_obj.hide_viewport = True
    source_obj.hide_render = True

    cut_props.is_in_draft = False
    cut_props.active_cutter_name = ""
    cut_props.active_source_name = ""

    all_results = parts_a + parts_b + dowel_objs

    # Tag resulting parts with base location and explode direction for live Explode Preview
    normal = (cutter_matrix.to_3x3() @ Vector((0, 0, 1))).normalized()
    offset = normal * mm_to_scene_units(context, cut_props.explode_distance_mm, ref_obj=source_obj)

    for p in parts_a:
        if p and p.name in bpy.data.objects:
            p["ms_base_loc"] = tuple(p.location)
            p["ms_explode_vec"] = (0.0, 0.0, 0.0)

    for p in parts_b:
        if p and p.name in bpy.data.objects:
            p["ms_base_loc"] = tuple(p.location)
            p["ms_explode_vec"] = tuple(normal)
            if cut_props.explode_distance_mm > 0.0:
                p.location = p.location + offset

    for d in dowel_objs:
        if d and d.name in bpy.data.objects:
            d["ms_base_loc"] = tuple(d.location)
            d["ms_explode_vec"] = tuple(normal * 0.5)
            if cut_props.explode_distance_mm > 0.0:
                d.location = d.location + offset * 0.5

    # Select all resulting parts
    bpy.ops.object.select_all(action='DESELECT')
    for part in all_results:
        if part and part.name in bpy.data.objects:
            part.select_set(True)
    if all_results and all_results[0].name in bpy.data.objects:
        context.view_layer.objects.active = all_results[0]

    return all_results


def cancel_draft_mode(context):
    """Cancels Draft Mode and deletes all temporary helper objects."""
    settings = context.scene.model_splitter
    cut_props = settings.cut

    remove_collection_and_objects(context, name=DRAFT_COLLECTION_NAME)

    source_obj = bpy.data.objects.get(cut_props.active_source_name)
    if source_obj:
        source_obj.hide_viewport = False
        bpy.ops.object.select_all(action='DESELECT')
        source_obj.select_set(True)
        context.view_layer.objects.active = source_obj

    cut_props.is_in_draft = False
    cut_props.active_cutter_name = ""
    cut_props.active_source_name = ""
