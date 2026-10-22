"""
ModelSplitter - N-Panel Sidebar Interface
Provides full UI layout in 3D Viewport sidebar (press N -> ModelSplitter).
"""

import bpy


class MODEL_SPLITTER_PT_base:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "ModelSplitter"


class MODEL_SPLITTER_PT_main_panel(MODEL_SPLITTER_PT_base, bpy.types.Panel):
    bl_idname = "MODEL_SPLITTER_PT_main_panel"
    bl_label = "ModelSplitter"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.model_splitter
        cut_props = settings.cut

        # Workflow mode selector
        row = layout.row(align=True)
        row.prop(cut_props, "workflow_mode", expand=True)

        # Prominent Draft Mode Action Box
        if cut_props.is_in_draft:
            box = layout.box()
            box.label(text="DRAFT MODE ACTIVE", icon='TIME')
            box.label(text="Adjust plane / pins before final build")
            
            row = box.row(align=True)
            row.scale_y = 1.6
            row.operator("modelsplitter.apply_build", text="Apply Cut (Build)", icon='CHECKMARK')
            row.operator("modelsplitter.cancel_draft", text="Cancel", icon='CANCEL')

            box.separator()
            row = box.row(align=True)
            row.operator("modelsplitter.swap_pin", text="Swap Pin Side", icon='FILE_REFRESH')
            exp_row = box.row(align=True)
            exp_row.prop(cut_props, "explode_distance_mm", slider=True)
            if cut_props.explode_distance_mm > 0.0:
                exp_row.operator("modelsplitter.reset_explode", text="", icon='LOOP_BACK')
        elif cut_props.explode_distance_mm > 0.0 or any("ms_base_loc" in o for o in bpy.data.objects):
            box = layout.box()
            exp_row = box.row(align=True)
            exp_row.prop(cut_props, "explode_distance_mm", slider=True)
            if cut_props.explode_distance_mm > 0.0:
                exp_row.operator("modelsplitter.reset_explode", text="", icon='LOOP_BACK')


class MODEL_SPLITTER_PT_cutting_tools(MODEL_SPLITTER_PT_base, bpy.types.Panel):
    bl_idname = "MODEL_SPLITTER_PT_cutting_tools"
    bl_parent_id = "MODEL_SPLITTER_PT_main_panel"
    bl_label = "Cutting Tools"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.model_splitter
        cut_props = settings.cut

        # Interactive Drawing Section (CatPin primary workflow)
        box = layout.box()
        box.label(text="Interactive Viewport Drawing:", icon='GREASEPENCIL')
        box.prop(cut_props, "draw_mode", expand=True)
        if cut_props.draw_mode in ('CURVED', 'MANUAL'):
            box.prop(cut_props, "editable_points", slider=True)

        row = box.row()
        row.scale_y = 1.5
        row.operator("modelsplitter.draw_cut_line", text="Draw Cut Line", icon='GREASEPENCIL')

        det = layout.box()
        det.label(text="Curve Detail Extract:", icon='CURVE_BEZCIRCLE')
        det.prop(cut_props, "extrude_depth_mm")
        det.prop(cut_props, "curve_smoothness", slider=True)
        r = det.row(align=True)
        r.operator("modelsplitter.add_detail_curve", text="Add Curve", icon='CURVE_BEZCIRCLE')
        r.operator("modelsplitter.extrude_curve_cut", text="Extrude & Cut", icon='MOD_SOLIDIFY')

        layout.separator()
        layout.label(text="Parametric Cutters:")
        col = layout.column(align=True)
        col.scale_y = 1.2
        col.operator("modelsplitter.straight_cut", text="Straight Cut", icon='SNAP_FACE')
        col.operator("modelsplitter.curved_cut", text="Curved Cut", icon='FORCE_CURVE')
        col.operator("modelsplitter.separate_base", text="Separate from Base", icon='MOD_ARRAY')

        layout.separator()
        col = layout.column(align=True)
        col.prop(cut_props, "split_islands")
        col.prop(cut_props, "adaptive_surface")


class MODEL_SPLITTER_PT_connectors(MODEL_SPLITTER_PT_base, bpy.types.Panel):
    bl_idname = "MODEL_SPLITTER_PT_connectors"
    bl_parent_id = "MODEL_SPLITTER_PT_main_panel"
    bl_label = "Connectors & Tolerances"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.model_splitter
        con_props = settings.connector
        cut_props = settings.cut

        col = layout.column(align=True)
        col.prop(con_props, "no_connectors")
        sub = col.column(align=True)
        sub.enabled = not con_props.no_connectors
        sub.prop(con_props, "shape")
        sub.prop(con_props, "preset")
        sub.prop(con_props, "count", slider=True)
        sub.prop(con_props, "placement_mode")

        if con_props.placement_mode == 'MANUAL' and cut_props.is_in_draft:
            m_row = col.row(align=True)
            m_row.operator("modelsplitter.snap_manual_pins", text="Snap to Cut", icon='SNAP_ON')
            m_row.operator("modelsplitter.reset_pin_positions", text="Reset Auto", icon='LOOP_BACK')

        if con_props.shape == 'CUSTOM':
            col.prop(con_props, "custom_object")

        layout.separator()
        box = layout.box()
        box.label(text="Dimensions (mm):", icon='DRIVER_DISTANCE')
        b_col = box.column(align=True)
        b_col.prop(con_props, "diameter_mm", text="Diameter / Width")
        b_col.prop(con_props, "length_mm", text="Pin Length")
        if con_props.shape == 'CONICAL':
            b_col.prop(con_props, "taper_angle", text="Taper Angle")

        layout.separator()
        box = layout.box()
        box.label(text="Tolerances & Clearances:", icon='MOD_SOLIDIFY')
        b_col = box.column(align=True)
        b_col.prop(con_props, "clearance_mm", text="Pin Clearance (mm)")
        b_col.prop(con_props, "cut_gap_mm", text="Cut Gap (mm)")
        box.label(text="Resin: 0.1-0.2mm | FDM: 0.2-0.35mm", icon='INFO')

        layout.separator()
        col = layout.column(align=True)
        row = col.row(align=True)
        row.enabled = not (con_props.double_sided or con_props.holes_only)
        row.prop(con_props, "target_side", text="Male Pin On")
        row.operator("modelsplitter.swap_pin", text="Swap", icon='ARROW_LEFTRIGHT')
        ds_row = col.row(align=True)
        ds_row.enabled = not con_props.holes_only
        ds_row.prop(con_props, "double_sided")
        col.prop(con_props, "holes_only")


class MODEL_SPLITTER_PT_mesh_check(MODEL_SPLITTER_PT_base, bpy.types.Panel):
    bl_idname = "MODEL_SPLITTER_PT_mesh_check"
    bl_parent_id = "MODEL_SPLITTER_PT_main_panel"
    bl_label = "Mesh Health Pre-flight"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.model_splitter.mesh_check

        row = layout.row()
        row.scale_y = 1.2
        row.operator("modelsplitter.check_mesh", text="Check Active Mesh", icon='FILE_TICK')

        if settings.checked:
            box = layout.box()
            box.label(text=f"Verts: {settings.total_verts} | Faces: {settings.total_faces}", icon='MESH_DATA')
            if settings.is_clean:
                box.label(text="Mesh is 100% Manifold & Clean", icon='CHECKMARK')
            else:
                box.label(text=settings.status_message or "Defects Detected:", icon='ERROR')
                col = box.column(align=True)
                if settings.non_manifold_count > 0:
                    col.label(text=f"Non-Manifold Edges: {settings.non_manifold_count}", icon='RADIOBUT_OFF')
                if settings.open_edges_count > 0:
                    col.label(text=f"Open Boundary Edges: {settings.open_edges_count}", icon='HOLE_SHAPE')
                if settings.degenerate_count > 0:
                    col.label(text=f"Zero-Area Faces: {settings.degenerate_count}", icon='LAYER_USED')
                if settings.self_intersect_count > 0:
                    col.label(text=f"Self-Intersections: {settings.self_intersect_count}", icon='MOD_BOOLEAN')

                row = box.row(align=True)
                row.operator("modelsplitter.highlight_defects", text="Show in Edit Mode", icon='RESTRICT_VIEW_OFF')
                row.operator("modelsplitter.auto_fix", text="Auto-Heal", icon='BRUSH_SOFTEN')


class MODEL_SPLITTER_PT_export(MODEL_SPLITTER_PT_base, bpy.types.Panel):
    bl_idname = "MODEL_SPLITTER_PT_export"
    bl_parent_id = "MODEL_SPLITTER_PT_main_panel"
    bl_label = "Batch Export"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.model_splitter.export

        col = layout.column(align=True)
        col.prop(settings, "format")
        col.prop(settings, "export_dir")
        col.prop(settings, "name_prefix")
        col.prop(settings, "batch_export")

        row = layout.row()
        row.scale_y = 1.3
        btn_label = "Export All Parts" if settings.batch_export else "Export Active Part"
        row.operator("modelsplitter.batch_export", text=btn_label, icon='EXPORT')


classes = (
    MODEL_SPLITTER_PT_main_panel,
    MODEL_SPLITTER_PT_cutting_tools,
    MODEL_SPLITTER_PT_connectors,
    MODEL_SPLITTER_PT_mesh_check,
    MODEL_SPLITTER_PT_export,
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
