"""
ModelSplitter - Batch Export Operators (STL / OBJ)
Exports separated parts as 3D print ready files for slicing software.
"""

import os
import bpy


class MODEL_SPLITTER_OT_batch_export(bpy.types.Operator):
    bl_idname = "modelsplitter.batch_export"
    bl_label = "Batch Export Parts"
    bl_description = "Exports all selected split parts into individual STL/OBJ files"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return any(obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        settings = context.scene.model_splitter.export
        export_dir = bpy.path.abspath(settings.export_dir)

        if not os.path.exists(export_dir):
            try:
                os.makedirs(export_dir, exist_ok=True)
            except Exception as e:
                self.report({'ERROR'}, f"Cannot create export directory: {e}")
                return {'CANCELLED'}

        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not selected_meshes:
            self.report({'WARNING'}, "No mesh objects selected for export.")
            return {'CANCELLED'}

        exported_count = 0
        fmt = settings.format

        prev_active = context.view_layer.objects.active
        prev_selection = list(context.selected_objects)

        for obj in selected_meshes:
            # Isolate selection for single part export
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj

            safe_name = bpy.path.clean_name(obj.name)
            filename = f"{safe_name}.{fmt.lower()}"
            filepath = os.path.join(export_dir, filename)

            try:
                if fmt == 'STL':
                    if hasattr(bpy.ops.wm, "stl_export"):
                        bpy.ops.wm.stl_export(filepath=filepath, export_selected_objects=True)
                    else:
                        bpy.ops.export_mesh.stl(filepath=filepath, use_selection=True)
                elif fmt == 'OBJ':
                    if hasattr(bpy.ops.wm, "obj_export"):
                        bpy.ops.wm.obj_export(filepath=filepath, export_selected_objects=True)
                    else:
                        bpy.ops.export_scene.obj(filepath=filepath, use_selection=True)

                exported_count += 1
            except Exception as e:
                print(f"[ModelSplitter] Export error for {obj.name}: {e}")

        # Restore original selection
        bpy.ops.object.select_all(action='DESELECT')
        for obj in prev_selection:
            if obj and obj.name in bpy.data.objects:
                obj.select_set(True)
        if prev_active and prev_active.name in bpy.data.objects:
            context.view_layer.objects.active = prev_active

        self.report({'INFO'}, f"Successfully exported {exported_count} parts to {export_dir}")
        return {'FINISHED'}


classes = (
    MODEL_SPLITTER_OT_batch_export,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
