"""
ModelSplitter - Draft Mode Manager
Provides a non-destructive editing workflow allowing live interactive positioning of
the cutting plane and connectors before baking final geometry.
"""

import bpy
from mathutils import Vector
from ..utils.mesh_utils import (
    get_or_create_collection,
    remove_collection_and_objects,
    apply_object_transforms,
    separate_loose_parts,
)
from ..utils.math_utils import get_world_bounds, mm_to_scene_units
from .cutter_geometry import setup_straight_cutter, setup_curved_cutter
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
    else:
        cutter_obj, _ = setup_straight_cutter(context, source_obj, target_collection=draft_col)

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


def update_draft_connectors(context):
    """
    Regenerates connector preview objects in the draft collection to reflect
    changes in count, shape, diameter, and clearance.
    """
    from mathutils import Matrix
    settings = context.scene.model_splitter
    cut_props = settings.cut

    if not cut_props.is_in_draft:
        return

    cutter_obj = bpy.data.objects.get(cut_props.active_cutter_name)
    source_obj = bpy.data.objects.get(cut_props.active_source_name)
    draft_col = bpy.data.collections.get(DRAFT_COLLECTION_NAME)

    if not cutter_obj or not source_obj or not draft_col:
        return

    try:
        context.view_layer.update()
    except Exception:
        pass

    # Remove existing connector previews in draft collection
    for obj in list(draft_col.objects):
        if obj.name.startswith("MS_Conn_"):
            bpy.data.objects.remove(obj, do_unlink=True)

    _, _, _, dimensions = get_world_bounds(source_obj)
    bounds_radius = dimensions.length * 0.5
    cutter_mat = cutter_obj.matrix_world.copy()
    cutter_mat_inv = cutter_mat.inverted()

    # Generate preview pins and sockets snapped inside the actual cut cross-section
    pins, sockets = generate_cut_connectors(
        context,
        cut_plane_matrix=cutter_mat,
        bounds_radius=bounds_radius,
        target_collection=draft_col,
        cutter_obj=cutter_obj,
        source_obj=source_obj,
    )

    # Style preview connectors and parent in cutter local space without transform jump
    for pin in pins:
        local_mat = cutter_mat_inv @ pin.matrix_world
        pin.display_type = 'SOLID'
        pin.color = (0.1, 0.9, 0.3, 0.8)  # Bright green for male pin
        pin.show_wire = True
        pin.parent = cutter_obj
        pin.matrix_parent_inverse = Matrix.Identity(4)
        pin.matrix_basis = local_mat

    for socket in sockets:
        local_mat = cutter_mat_inv @ socket.matrix_world
        socket.display_type = 'WIRE'
        socket.color = (0.9, 0.2, 0.1, 0.6)  # Red wireframe for female socket clearance
        socket.show_wire = True
        socket.parent = cutter_obj
        socket.matrix_parent_inverse = Matrix.Identity(4)
        socket.matrix_basis = local_mat


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

    try:
        context.view_layer.update()
    except Exception:
        pass

    # Preserve cutter transformation
    cutter_matrix = cutter_obj.matrix_world.copy()
    _, _, _, dimensions = get_world_bounds(source_obj)
    bounds_radius = dimensions.length * 0.5

    # 1. Unlink draft preview connectors
    draft_col = bpy.data.collections.get(DRAFT_COLLECTION_NAME)
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
    )

    is_thin_blade = bool(cutter_obj.get("ms_is_thin_blade", False))

    # 3. Perform solid volume cut (keep parts unified while applying connectors)
    parts_a, parts_b = split_mesh_by_cutter_volume(
        context,
        source_obj,
        cutter_obj,
        split_islands=cut_props.split_islands if is_thin_blade else False
    )

    # 4. Apply connectors (Pins & Sockets) to unified halves before island separation
    apply_connectors_to_parts(
        context,
        parts_a,
        parts_b,
        pins,
        sockets,
        target_side=con_props.target_side
    )

    # 4b. Separate loose islands after pins/sockets have been cleanly attached/carved
    if cut_props.split_islands and not is_thin_blade:
        final_a = []
        for pa in parts_a:
            if pa and pa.name in bpy.data.objects and len(pa.data.polygons) > 0:
                islands = separate_loose_parts(context, pa)
                final_a.extend(islands if islands else [pa])
        parts_a = final_a

        final_b = []
        for pb in parts_b:
            if pb and pb.name in bpy.data.objects and len(pb.data.polygons) > 0:
                islands = separate_loose_parts(context, pb)
                final_b.extend(islands if islands else [pb])
        parts_b = final_b


    # 5. Clean up helper solids (pins/sockets)
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

    all_results = parts_a + parts_b

    # Visual explode separation if requested
    if cut_props.explode_distance_mm > 0.0 and parts_b:
        normal = (cutter_matrix.to_3x3() @ Vector((0, 0, 1))).normalized()
        offset = normal * mm_to_scene_units(context, cut_props.explode_distance_mm)
        for p in parts_b:
            if p and p.name in bpy.data.objects:
                p.location += offset

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
