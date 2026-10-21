"""
ModelSplitter - Draft Mode Lifecycle Operators
"""

import bpy
from ..core.draft_manager import apply_draft_build, cancel_draft_mode, update_draft_connectors


class MODEL_SPLITTER_OT_apply_build(bpy.types.Operator):
    bl_idname = "modelsplitter.apply_build"
    bl_label = "Apply Cut (Build)"
    bl_description = "Bake cutting plane and generate alignment pins and sockets"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "model_splitter", None)
        return settings is not None and settings.cut.is_in_draft

    def execute(self, context):
        results = apply_draft_build(context)
        if results:
            self.report({'INFO'}, f"Successfully split model into {len(results)} parts with pins!")
        else:
            self.report({'ERROR'}, "Split operation failed. Ensure the cutting plane intersects the mesh.")
        return {'FINISHED'}


class MODEL_SPLITTER_OT_cancel_draft(bpy.types.Operator):
    bl_idname = "modelsplitter.cancel_draft"
    bl_label = "Cancel Cut"
    bl_description = "Cancel draft mode and discard temporary cutters and pins"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "model_splitter", None)
        return settings is not None and settings.cut.is_in_draft

    def execute(self, context):
        cancel_draft_mode(context)
        self.report({'INFO'}, "Draft mode cancelled.")
        return {'FINISHED'}


class MODEL_SPLITTER_OT_update_draft_preview(bpy.types.Operator):
    bl_idname = "modelsplitter.update_draft_preview"
    bl_label = "Update Preview"
    bl_description = "Refreshes connector previews to reflect modified parameters"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        update_draft_connectors(context)
        return {'FINISHED'}


classes = (
    MODEL_SPLITTER_OT_apply_build,
    MODEL_SPLITTER_OT_cancel_draft,
    MODEL_SPLITTER_OT_update_draft_preview,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
