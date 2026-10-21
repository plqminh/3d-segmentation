"""
ModelSplitter - Straight and Curved Cut Operators
"""

import bpy
from ..core.draft_manager import enter_draft_mode, apply_draft_build


class MODEL_SPLITTER_OT_straight_cut(bpy.types.Operator):
    bl_idname = "modelsplitter.straight_cut"
    bl_label = "Straight Cut"
    bl_description = "Cut the model using a planar cutting surface"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        settings = getattr(context.scene, "model_splitter", None)
        in_draft = settings.cut.is_in_draft if settings else False
        return obj is not None and obj.type == 'MESH' and not in_draft

    def execute(self, context):
        obj = context.active_object
        settings = context.scene.model_splitter
        mode = settings.cut.workflow_mode

        if mode == 'EASY':
            # Easy mode: Setup and apply in a single automated step
            enter_draft_mode(context, obj, cut_type='STRAIGHT')
            results = apply_draft_build(context)
            if results:
                self.report({'INFO'}, f"Successfully split into {len(results)} parts with pins!")
            else:
                self.report({'WARNING'}, "Cut operation produced no results. Check mesh manifoldness.")
            return {'FINISHED'}
        else:
            # Draft mode: Set up non-destructive preview
            enter_draft_mode(context, obj, cut_type='STRAIGHT')
            self.report({'INFO'}, "Draft Mode active: Move/rotate the cutting plane, then click 'Apply Cut (Build)'")
            return {'FINISHED'}


class MODEL_SPLITTER_OT_curved_cut(bpy.types.Operator):
    bl_idname = "modelsplitter.curved_cut"
    bl_label = "Curved Cut"
    bl_description = "Cut the model using an organic curved cutting surface"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        settings = getattr(context.scene, "model_splitter", None)
        in_draft = settings.cut.is_in_draft if settings else False
        return obj is not None and obj.type == 'MESH' and not in_draft

    def execute(self, context):
        obj = context.active_object
        settings = context.scene.model_splitter
        mode = settings.cut.workflow_mode

        if mode == 'EASY':
            enter_draft_mode(context, obj, cut_type='CURVED')
            results = apply_draft_build(context)
            if results:
                self.report({'INFO'}, f"Curved cut finished: {len(results)} parts generated.")
            return {'FINISHED'}
        else:
            enter_draft_mode(context, obj, cut_type='CURVED')
            self.report({'INFO'}, "Draft Mode active: Adjust curved surface position, then click 'Apply Cut (Build)'")
            return {'FINISHED'}


classes = (
    MODEL_SPLITTER_OT_straight_cut,
    MODEL_SPLITTER_OT_curved_cut,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
