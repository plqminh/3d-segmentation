"""
ModelSplitter - Batch Export Operators (STL / OBJ)
Exports separated parts as 3D print ready files for slicing software.
"""

import os
import bpy
from mathutils import Vector


class MODEL_SPLITTER_OT_batch_export(bpy.types.Operator):
    bl_idname = "modelsplitter.batch_export"
    bl_label = "Batch Export Parts"
    bl_description = "Exports split parts into individual STL/OBJ files"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        if any(obj.type == 'MESH' for obj in context.selected_objects):
            return True
        if context.active_object and context.active_object.type == 'MESH':
            return True
        settings = getattr(context.scene, "model_splitter", None)
        if settings and settings.export.batch_export:
            return any(
                obj.type == 'MESH' and not obj.hide_viewport and ("_Part_" in obj.name or "_Dowel_" in obj.name)
                for obj in bpy.data.objects
            )
        return False

    def execute(self, context):
        settings = context.scene.model_splitter.export
        export_dir = bpy.path.abspath(settings.export_dir)

        if not os.path.exists(export_dir):
            try:
                os.makedirs(export_dir, exist_ok=True)
            except Exception as e:
                self.report({'ERROR'}, f"Cannot create export directory: {e}")
                return {'CANCELLED'}

        if settings.batch_export:
            target_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
            if not target_meshes:
                target_meshes = [
                    obj for obj in bpy.data.objects
                    if obj.type == 'MESH' and not obj.hide_viewport and ("_Part_" in obj.name or "_Dowel_" in obj.name)
                ]
        else:
            active_obj = context.active_object
            target_meshes = [active_obj] if (active_obj and active_obj.type == 'MESH') else []

        if not target_meshes:
            self.report({'WARNING'}, "No mesh objects found for export.")
            return {'CANCELLED'}

        exported_count = 0
        fmt = settings.format
        raw_prefix = (settings.name_prefix or "").strip()
        clean_prefix = bpy.path.clean_name(raw_prefix) if raw_prefix else ""

        prev_active = context.view_layer.objects.active
        prev_selection = list(context.selected_objects)

        for obj in target_meshes:
            # Isolate selection for single part export
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj

            # Temporarily snap back to un-exploded base position if Explode Preview is active
            saved_loc = None
            if "ms_base_loc" in obj:
                try:
                    saved_loc = obj.location.copy()
                    obj.location = Vector(obj["ms_base_loc"])
                except Exception:
                    saved_loc = None

            safe_name = bpy.path.clean_name(obj.name)
            if clean_prefix and clean_prefix != "Part" and not safe_name.startswith(clean_prefix):
                out_stem = f"{clean_prefix}_{safe_name}"
            else:
                out_stem = safe_name
            filename = f"{out_stem}.{fmt.lower()}"
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
            finally:
                if saved_loc is not None:
                    obj.location = saved_loc

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
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
