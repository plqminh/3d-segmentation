"""
ModelSplitter - Mesh Remesh & Decimation Operators
Provides native high-performance watertight Voxel Remeshing and
ratio-based Decimation polycount reduction for 3D printing.
"""

import bpy
from ..utils.math_utils import mm_to_scene_units


class MODEL_SPLITTER_OT_voxel_remesh(bpy.types.Operator):
    """Watertight voxel remesh using millimeter-based voxel resolution"""
    bl_idname = "modelsplitter.voxel_remesh"
    bl_label = "Voxel Remesh"
    bl_description = "Rebuilds a 100% manifold, watertight mesh using Blender's high-speed voxel remesher"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH' and context.mode == 'OBJECT'

    def execute(self, context):
        obj = context.active_object
        mesh_props = context.scene.model_splitter.mesh_tools
        voxel_mm = mesh_props.remesh_voxel_size_mm

        voxel_scene = mm_to_scene_units(context, voxel_mm, ref_obj=obj)
        orig_faces = len(obj.data.polygons)

        obj.data.remesh_voxel_size = max(0.0001, voxel_scene)
        obj.data.remesh_voxel_adaptivity = 0.0

        try:
            bpy.ops.object.voxel_remesh()
            new_faces = len(obj.data.polygons)
            mesh_props.last_polycount = f"{new_faces:,} faces"
            self.report({'INFO'}, f"Voxel Remesh complete ({voxel_mm:.2f}mm): {orig_faces:,} -> {new_faces:,} faces")
        except Exception as e:
            self.report({'ERROR'}, f"Voxel remesh failed: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}


class MODEL_SPLITTER_OT_decimate(bpy.types.Operator):
    """Reduce mesh polycount while preserving overall geometry and shape"""
    bl_idname = "modelsplitter.decimate"
    bl_label = "Apply Decimation"
    bl_description = "Simplifies heavy meshes by reducing triangle count according to the ratio slider"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH' and context.mode == 'OBJECT'

    def execute(self, context):
        obj = context.active_object
        mesh_props = context.scene.model_splitter.mesh_tools
        ratio = mesh_props.decimate_ratio
        orig_faces = len(obj.data.polygons)

        mod = obj.modifiers.new(name="MS_Decimate", type='DECIMATE')
        mod.decimate_type = 'COLLAPSE'
        mod.ratio = ratio

        try:
            bpy.ops.object.modifier_apply(modifier=mod.name)
            new_faces = len(obj.data.polygons)
            mesh_props.last_polycount = f"{new_faces:,} faces"
            self.report({'INFO'}, f"Decimated mesh ({ratio*100:.0f}%): {orig_faces:,} -> {new_faces:,} faces")
        except Exception as e:
            self.report({'ERROR'}, f"Decimate failed: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}


classes = (
    MODEL_SPLITTER_OT_voxel_remesh,
    MODEL_SPLITTER_OT_decimate,
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
