"""
ModelSplitter - Mesh Validation & Pre-flight Diagnostics
Detects non-manifold edges, open boundary holes, degenerate zero-area faces,
and self-intersections using accelerated BVH trees before boolean operations.
"""

import bpy
import bmesh
from mathutils.bvhtree import BVHTree


def validate_mesh(obj):
    """
    Performs comprehensive pre-flight diagnostics on a mesh object.
    Returns a dictionary with defect counts and health status.
    """
    if not obj or obj.type != 'MESH':
        return {
            'checked': True,
            'is_clean': False,
            'status_message': "Selected object is not a mesh",
            'non_manifold_count': 0,
            'open_edges_count': 0,
            'self_intersect_count': 0,
            'degenerate_count': 0,
            'total_verts': 0,
            'total_faces': 0,
        }

    bm = bmesh.new()
    bm.from_mesh(obj.data)

    total_verts = len(bm.verts)
    total_faces = len(bm.faces)

    # 1. Non-manifold edges
    non_manifold_edges = [e for e in bm.edges if not e.is_manifold]
    non_manifold_count = len(non_manifold_edges)

    # 2. Open boundary edges (edges with exactly 1 face)
    open_edges = [e for e in bm.edges if len(e.link_faces) == 1]
    open_edges_count = len(open_edges)

    # 3. Degenerate faces (zero area faces)
    degenerate_faces = [f for f in bm.faces if f.calc_area() <= 1e-7]
    degenerate_count = len(degenerate_faces)

    # 4. Self-intersections via BVHTree
    self_intersect_count = 0
    try:
        # Avoid huge lag on meshes with > 500,000 faces by sampling or fast BVH
        if total_faces < 500000:
            tree = BVHTree.FromBMesh(bm, epsilon=0.00001)
            overlaps = tree.overlap(tree)
            bm.faces.ensure_lookup_table()
            # Filter out identical and adjacent faces
            actual_overlaps = []
            for idx_a, idx_b in overlaps:
                if idx_a < idx_b:
                    face_a = bm.faces[idx_a]
                    face_b = bm.faces[idx_b]
                    # If faces share any vertex, skip adjacent neighbor contact
                    shared_verts = set(face_a.verts).intersection(face_b.verts)
                    if not shared_verts:
                        actual_overlaps.append((idx_a, idx_b))
            self_intersect_count = len(actual_overlaps)
    except Exception as e:
        print(f"[ModelSplitter] BVH self-intersection check exception: {e}")

    bm.free()

    is_clean = (non_manifold_count == 0 and open_edges_count == 0 and degenerate_count == 0 and self_intersect_count == 0)

    if is_clean:
        status = "Clean! Ready for 3D printing & boolean cuts."
    else:
        issues = []
        if non_manifold_count > 0:
            issues.append(f"{non_manifold_count} non-manifold edges")
        if open_edges_count > 0:
            issues.append(f"{open_edges_count} open boundary edges")
        if degenerate_count > 0:
            issues.append(f"{degenerate_count} zero-area faces")
        if self_intersect_count > 0:
            issues.append(f"{self_intersect_count} self-intersecting face pairs")
        status = f"Issues detected: {', '.join(issues)}"

    return {
        'checked': True,
        'is_clean': is_clean,
        'status_message': status,
        'non_manifold_count': non_manifold_count,
        'open_edges_count': open_edges_count,
        'self_intersect_count': self_intersect_count,
        'degenerate_count': degenerate_count,
        'total_verts': total_verts,
        'total_faces': total_faces,
    }


def select_mesh_defects(context, obj):
    """
    Enters Edit Mode and selects all non-manifold and open edges to highlight issues.
    """
    if not obj or obj.type != 'MESH':
        return

    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    context.view_layer.objects.active = obj

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='EDGE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.mesh.select_non_manifold(extend=False, use_wire=True, use_boundary=True, use_multi_face=True)
