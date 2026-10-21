"""
ModelSplitter - Mesh Utilities
Handles object copying, transform normalization, geometry cleanup, and collection management.
"""

import bpy
import bmesh
from mathutils import Vector


def get_or_create_collection(context, name="ModelSplitter_Draft"):
    """Gets an existing collection or creates a new one linked to scene collection."""
    if name in bpy.data.collections:
        col = bpy.data.collections[name]
    else:
        col = bpy.data.collections.new(name)
        context.scene.collection.children.link(col)
    return col


def remove_collection_and_objects(context, name="ModelSplitter_Draft"):
    """Removes a helper collection and frees all objects in it."""
    if name not in bpy.data.collections:
        return
    col = bpy.data.collections[name]
    for obj in list(col.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(col)


def apply_object_transforms(obj, location=False, rotation=True, scale=True):
    """
    Applies object scale and rotation so boolean operations and Euclidean measurements
    work accurately in world units.
    """
    prev_active = bpy.context.view_layer.objects.active
    prev_selected = list(bpy.context.selected_objects)

    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    bpy.ops.object.transform_apply(location=location, rotation=rotation, scale=scale)

    bpy.ops.object.select_all(action='DESELECT')
    for sel_obj in prev_selected:
        if sel_obj and sel_obj.name in bpy.data.objects:
            sel_obj.select_set(True)
    if prev_active and prev_active.name in bpy.data.objects:
        bpy.context.view_layer.objects.active = prev_active


def duplicate_object(context, obj, name_suffix="_copy", target_collection=None):
    """Duplicates an object with its own unique mesh datablock."""
    new_mesh = obj.data.copy()
    new_obj = bpy.data.objects.new(f"{obj.name}{name_suffix}", new_mesh)
    new_obj.matrix_world = obj.matrix_world.copy()

    col = target_collection or context.collection
    col.objects.link(new_obj)
    return new_obj


def cleanup_mesh(obj, merge_dist=0.0001):
    """
    Cleans up post-boolean geometry by merging duplicate vertices,
    removing loose geometry, and recalculating normals outwards.
    """
    if not obj or obj.type != 'MESH':
        return

    bm = bmesh.new()
    bm.from_mesh(obj.data)

    # Remove loose vertices and edges
    loose_verts = [v for v in bm.verts if not v.link_edges]
    bmesh.ops.delete(bm, geom=loose_verts, context='VERTS')

    loose_edges = [e for e in bm.edges if not e.link_faces]
    bmesh.ops.delete(bm, geom=loose_edges, context='EDGES')

    # Merge by distance to heal microscopic boolean cracks
    if merge_dist > 0.0:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge_dist)

    # Recalculate normals to ensure consistent solid orientation
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def separate_loose_parts(context, obj):
    """
    Separates disconnected geometric islands into individual objects.
    Returns list of resulting objects.
    """
    prev_selected = list(context.selected_objects)
    prev_active = context.view_layer.objects.active

    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    context.view_layer.objects.active = obj

    bpy.ops.mesh.separate(type='LOOSE')

    result_objects = list(context.selected_objects)

    # Restore context if needed
    return result_objects
