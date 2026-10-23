"""
ModelSplitter - Mesh Diagnostics and Auto-Fix Operators
"""

import bpy
from ..core.mesh_check import validate_mesh, select_mesh_defects
from ..utils.mesh_utils import cleanup_mesh, apply_object_transforms


class MODEL_SPLITTER_OT_check_mesh(bpy.types.Operator):
    bl_idname = "modelsplitter.check_mesh"
    bl_label = "Check Mesh Health"
    bl_description = "Analyze active mesh for non-manifold edges, holes, and self-intersections"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        settings = context.scene.model_splitter.mesh_check

        results = validate_mesh(obj)

        settings.checked = results['checked']
        settings.is_clean = results['is_clean']
        settings.status_message = results['status_message']
        settings.non_manifold_count = results['non_manifold_count']
        settings.open_edges_count = results['open_edges_count']
        settings.self_intersect_count = results['self_intersect_count']
        settings.degenerate_count = results['degenerate_count']
        settings.total_verts = results['total_verts']
        settings.total_faces = results['total_faces']

        if results['is_clean']:
            self.report({'INFO'}, "Mesh is 100% clean and print-ready!")
        else:
            self.report({'WARNING'}, results['status_message'])

        return {'FINISHED'}


class MODEL_SPLITTER_OT_highlight_defects(bpy.types.Operator):
    bl_idname = "modelsplitter.highlight_defects"
    bl_label = "Show Issues in Edit Mode"
    bl_description = "Switches to Edit Mode and highlights defective edges"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        select_mesh_defects(context, obj)
        self.report({'INFO'}, "Defective geometry selected in Edit Mode.")
        return {'FINISHED'}


class MODEL_SPLITTER_OT_auto_fix(bpy.types.Operator):
    bl_idname = "modelsplitter.auto_fix"
    bl_label = "Auto-Heal Mesh"
    bl_description = "Merge duplicate vertices, remove loose geometry, and recalculate normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        apply_object_transforms(obj)
        cleanup_mesh(obj, merge_dist=0.0001)

        # Re-run validation
        bpy.ops.modelsplitter.check_mesh('INVOKE_DEFAULT')
        self.report({'INFO'}, "Auto-heal completed.")
        return {'FINISHED'}


classes = (
    MODEL_SPLITTER_OT_check_mesh,
    MODEL_SPLITTER_OT_highlight_defects,
    MODEL_SPLITTER_OT_auto_fix,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
