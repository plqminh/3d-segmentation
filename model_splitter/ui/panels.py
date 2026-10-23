"""
ModelSplitter - N-Panel Sidebar Interface
Provides a clean, streamlined workflow in the 3D Viewport sidebar (N -> ModelSplitter).
Organized into 5 numbered step panels with Basic / Advanced mode switching and clean visual hierarchy.
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
        settings = getattr(context.scene, "model_splitter", None)
        if not settings:
            return

        cut_props = settings.cut
        is_advanced = settings.ui_mode == 'ADVANCED'

        # Mode Selection Bar (Basic vs Advanced)
        header_row = layout.row(align=True)
        header_row.prop(settings, "ui_mode", expand=True)

        if is_advanced:
            wf_row = layout.row(align=True)
            wf_row.prop(cut_props, "workflow_mode", expand=True)

        # Prominent Draft Mode Active Banner & HUD
        if cut_props.is_in_draft:
            box = layout.box()
            banner = box.row(align=True)
            banner.label(text="DRAFT CUT PREVIEW", icon='TIME')

            # Prominent Action Buttons
            action_row = box.row(align=True)
            action_row.scale_y = 1.4
            action_row.operator("modelsplitter.apply_build", text="Apply Cut", icon='CHECKMARK')
            action_row.operator("modelsplitter.cancel_draft", text="Cancel", icon='CANCEL')

            # Plane Manipulation Controls
            box.label(text="Cutter Transform & Alignment:", icon='ORIENTATION_GIMBAL')

            sel_row = box.row(align=True)
            sel_row.scale_y = 1.1
            sel_row.operator("modelsplitter.select_cutter", text="Select Plane", icon='RESTRICT_SELECT_OFF')
            btn_txt = "Finish Edit" if context.mode == 'EDIT_MESH' else "Edit Contour"
            sel_row.operator("modelsplitter.edit_contour", text=btn_txt, icon='EDITMODE_HLT')

            align_row = box.row(align=True)
            op_c = align_row.operator("modelsplitter.plane_align", text="Center", icon='PIVOT_CURSOR')
            op_c.action = 'CENTER'
            op_h = align_row.operator("modelsplitter.plane_align", text="Horizontal", icon='SNAP_NORMAL')
            op_h.action = 'HORIZONTAL'
            op_i = align_row.operator("modelsplitter.plane_align", text="Invert", icon='FILE_REFRESH')
            op_i.action = 'INVERT'

            # Numeric Transform Sliders in Advanced Mode
            cutter_obj = bpy.data.objects.get(cut_props.active_cutter_name)
            if cutter_obj and is_advanced:
                t_col = box.column(align=True)
                t_col.prop(cutter_obj, "location", text="Loc")
                t_col.prop(cutter_obj, "rotation_euler", text="Rot")

            col_scale = box.column(align=True)
            col_scale.prop(cut_props, "plane_scale", text="Plane Size", slider=True)

            pin_row = box.row(align=True)
            pin_row.operator("modelsplitter.swap_pin", text="Swap Pin Side", icon='ARROW_LEFTRIGHT')

            exp_row = box.row(align=True)
            exp_row.prop(cut_props, "explode_distance_mm", text="Explode Preview", slider=True)
            if cut_props.explode_distance_mm > 0.0:
                exp_row.operator("modelsplitter.reset_explode", text="", icon='LOOP_BACK')

        elif cut_props.explode_distance_mm > 0.0 or any("ms_base_loc" in o for o in bpy.data.objects):
            # Compact explode control when viewing already split parts
            box = layout.box()
            exp_row = box.row(align=True)
            exp_row.prop(cut_props, "explode_distance_mm", text="Explode Parts", slider=True)
            if cut_props.explode_distance_mm > 0.0:
                exp_row.operator("modelsplitter.reset_explode", text="", icon='LOOP_BACK')


class MODEL_SPLITTER_PT_scale_master(MODEL_SPLITTER_PT_base, bpy.types.Panel):
    bl_idname = "MODEL_SPLITTER_PT_scale_master"
    bl_parent_id = "MODEL_SPLITTER_PT_main_panel"
    bl_label = "1. Scale Master & Model Prep"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.model_splitter
        scale_props = settings.scale_master
        is_advanced = settings.ui_mode == 'ADVANCED'
        obj = context.active_object

        if not obj or obj.type != 'MESH':
            layout.label(text="Select a 3D model to scale", icon='INFO')
            return

        # Dimensions Overview
        dim_box = layout.box()
        h_row = dim_box.row(align=True)
        h_row.label(text=f"{obj.name[:20]}", icon='OBJECT_DATAMODE')
        h_row.operator("modelsplitter.read_dimensions", text="Read", icon='FILE_REFRESH')

        col = dim_box.column(align=True)
        r = col.row(align=True)
        r.prop(scale_props, "dim_x_mm", text="X")
        r.prop(scale_props, "dim_y_mm", text="Y")
        r.prop(scale_props, "dim_z_mm", text="Z")

        dim_box.prop(scale_props, "uniform_scale_lock", text="Uniform Scale", icon='LOCKED' if scale_props.uniform_scale_lock else 'UNLOCKED')

        scale_row = dim_box.row(align=True)
        scale_row.prop(scale_props, "target_max_dim_mm", text="Target (mm)")
        scale_row.operator("modelsplitter.apply_dimensions", text="Apply", icon='CHECKMARK')

        # One-Click Positioning Actions
        layout.label(text="Quick Alignment & Transforms:", icon='ORIENTATION_GIMBAL')
        al_col = layout.column(align=True)
        r1 = al_col.row(align=True)
        r1.operator("modelsplitter.reset_view", text="Focus View", icon='VIEWZOOM')
        r1.operator("modelsplitter.center_origin", text="To Origin", icon='PIVOT_CURSOR')
        r1.operator("modelsplitter.drop_to_bed", text="Drop Z=0", icon='SNAP_FACE_CENTER')

        r2 = al_col.row(align=True)
        op1 = r2.operator("modelsplitter.quick_rotate", text="Stand Up", icon='TRIA_UP')
        op1.action = 'STAND'
        op2 = r2.operator("modelsplitter.quick_rotate", text="Lay Flat", icon='TRIA_DOWN')
        op2.action = 'LAY'
        op3 = r2.operator("modelsplitter.quick_rotate", text="Turn 90°", icon='FILE_REFRESH')
        op3.action = 'TURN_Z'

        if is_advanced:
            layout.label(text="Fuse / Join Models:", icon='MOD_BOOLEAN')
            a_row = layout.row(align=True)
            op = a_row.operator("modelsplitter.union_join", text="Boolean Union", icon='AUTOMERGE_ON')
            op.method = 'BOOLEAN'
            op_j = a_row.operator("modelsplitter.union_join", text="Direct Join", icon='LINKED')
            op_j.method = 'JOIN'
            layout.operator("modelsplitter.toggle_gizmo", text="Toggle 3D Gizmo", icon='GIZMO')


class MODEL_SPLITTER_PT_cutting_tools(MODEL_SPLITTER_PT_base, bpy.types.Panel):
    bl_idname = "MODEL_SPLITTER_PT_cutting_tools"
    bl_parent_id = "MODEL_SPLITTER_PT_main_panel"
    bl_label = "2. Cutting Tools"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.model_splitter
        cut_props = settings.cut
        is_advanced = settings.ui_mode == 'ADVANCED'

        # Primary Cutting Methods (Clean 2x2 grid)
        cut_col = layout.column(align=True)
        r1 = cut_col.row(align=True)
        r1.scale_y = 1.3
        r1.operator("modelsplitter.plane_cut", text="Plane Cut", icon='EMPTY_SINGLE_ARROW')
        r1.operator("modelsplitter.curved_cut", text="Curved Cut", icon='FORCE_CURVE')

        r2 = cut_col.row(align=True)
        r2.scale_y = 1.3
        r2.operator("modelsplitter.straight_cut", text="Straight Cut", icon='SNAP_FACE')
        r2.operator("modelsplitter.draw_cut_line", text="Draw Line", icon='GREASEPENCIL')

        # Compact Draw Cut Style Selector
        style_row = layout.row(align=True)
        style_row.prop(cut_props, "draw_mode", text="Draw Style")

        if is_advanced:
            adv_col = layout.column(align=True)
            if cut_props.draw_mode in ('CURVED', 'MANUAL'):
                adv_col.prop(cut_props, "editable_points")
            adv_col.prop(cut_props, "cut_resolution_mm")
            adv_col.prop(cut_props, "split_islands")

            layout.label(text="Curve Detail & Separation:", icon='CURVE_BEZCIRCLE')
            det_col = layout.column(align=True)
            det_col.prop(cut_props, "extrude_depth_mm")
            det_col.prop(cut_props, "curve_smoothness", slider=True)
            r = det_col.row(align=True)
            r.operator("modelsplitter.add_detail_curve", text="Add Curve", icon='CURVE_BEZCIRCLE')
            r.operator("modelsplitter.extrude_curve_cut", text="Extrude Cut", icon='MOD_SOLIDIFY')
            layout.operator("modelsplitter.separate_base", text="Separate from Base", icon='MOD_ARRAY')


class MODEL_SPLITTER_PT_connectors(MODEL_SPLITTER_PT_base, bpy.types.Panel):
    bl_idname = "MODEL_SPLITTER_PT_connectors"
    bl_parent_id = "MODEL_SPLITTER_PT_main_panel"
    bl_label = "3. Connectors & Tolerances"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.model_splitter
        con_props = settings.connector
        is_advanced = settings.ui_mode == 'ADVANCED'

        layout.prop(con_props, "no_connectors", text="Disable Connectors (Cut Only)")

        main_col = layout.column(align=True)
        main_col.enabled = not con_props.no_connectors

        # Connector Shape & Preset Configuration
        shape_col = main_col.column(align=True)
        shape_col.prop(con_props, "shape", text="Shape")

        if con_props.shape == 'MAGNET':
            shape_col.prop(con_props, "magnet_preset", text="Size")
            if is_advanced:
                r = shape_col.row(align=True)
                r.prop(con_props, "diameter_mm", text="Dia (mm)")
                r.prop(con_props, "length_mm", text="Depth (mm)")
        else:
            shape_col.prop(con_props, "preset", text="Preset")
            shape_col.prop(con_props, "count", text="Pin Count", slider=True)
            shape_col.prop(con_props, "placement_mode", text="Placement")

            if is_advanced:
                if con_props.shape == 'CUSTOM':
                    shape_col.prop(con_props, "custom_object", text="Pin Mesh")

                r = shape_col.row(align=True)
                r.prop(con_props, "diameter_mm", text="Dia / Width")
                r.prop(con_props, "length_mm", text="Length")
                if con_props.shape == 'CONICAL':
                    shape_col.prop(con_props, "taper_angle", text="Taper Angle")

        # Tolerances & Auto-Fit
        main_col.separator()
        main_col.label(text="Fit & Tolerances:", icon='SNAP_VOLUME')
        tol_col = main_col.column(align=True)
        tol_col.prop(con_props, "auto_fit_bounds", text="Auto-Fit Within Mesh")
        tol_col.prop(con_props, "clearance_mm", text="Clearance (mm)")
        if is_advanced:
            tol_col.prop(con_props, "cut_gap_mm", text="Cut Gap (mm)")

        tip_row = tol_col.row()
        tip_row.scale_y = 0.75
        tip_row.label(text="Typical: Resin 0.1-0.2mm | FDM 0.25-0.35mm", icon='INFO')

        # Side Selection & Symmetry
        side_col = main_col.column(align=True)
        r = side_col.row(align=True)
        r.enabled = not (con_props.double_sided or con_props.holes_only)
        r.prop(con_props, "target_side", text="Pin On")
        r.operator("modelsplitter.swap_pin", text="Swap", icon='ARROW_LEFTRIGHT')

        if is_advanced:
            ds_row = side_col.row(align=True)
            ds_row.enabled = not con_props.holes_only
            ds_row.prop(con_props, "double_sided", text="Double-Sided")
            side_col.prop(con_props, "holes_only", text="Holes Only")


class MODEL_SPLITTER_PT_mesh_tools(MODEL_SPLITTER_PT_base, bpy.types.Panel):
    bl_idname = "MODEL_SPLITTER_PT_mesh_tools"
    bl_parent_id = "MODEL_SPLITTER_PT_main_panel"
    bl_label = "4. Mesh Health & Remesh"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.model_splitter
        mc = settings.mesh_check
        mt = settings.mesh_tools
        is_advanced = settings.ui_mode == 'ADVANCED'

        # Pre-flight Check
        row = layout.row(align=True)
        row.scale_y = 1.1
        row.operator("modelsplitter.check_mesh", text="Inspect Mesh Manifoldness", icon='FILE_TICK')

        if mc.checked:
            box = layout.box()
            box.label(text=f"Verts: {mc.total_verts:,} | Faces: {mc.total_faces:,}", icon='MESH_DATA')
            if mc.is_clean:
                box.label(text="Mesh is 100% Manifold & Clean", icon='CHECKMARK')
            else:
                box.label(text=mc.status_message or "Non-manifold defects detected", icon='ERROR')
                r = box.row(align=True)
                r.operator("modelsplitter.highlight_defects", text="Show Defects", icon='RESTRICT_VIEW_OFF')
                r.operator("modelsplitter.auto_fix", text="Auto-Heal", icon='MOD_SMOOTH')

        # Watertight Voxel Remesh
        layout.label(text="Watertight Voxel Remesh:", icon='MOD_REMESH')
        rem_col = layout.column(align=True)
        rem_col.prop(mt, "remesh_voxel_size_mm", text="Voxel Size (mm)")
        rem_col.operator("modelsplitter.voxel_remesh", text="Remesh Watertight", icon='SHADERFX')

        if is_advanced:
            layout.label(text="Decimation (Reduce Polycount):", icon='MOD_DECIM')
            dec_col = layout.column(align=True)
            dec_col.prop(mt, "decimate_ratio", text="Ratio", slider=True)
            dec_col.operator("modelsplitter.decimate", text="Apply Decimate", icon='MOD_DECIM')
            if mt.last_polycount:
                dec_col.label(text=f"Current: {mt.last_polycount}", icon='INFO')


class MODEL_SPLITTER_PT_export(MODEL_SPLITTER_PT_base, bpy.types.Panel):
    bl_idname = "MODEL_SPLITTER_PT_export"
    bl_parent_id = "MODEL_SPLITTER_PT_main_panel"
    bl_label = "5. Print Bed & Export"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.model_splitter
        bed_props = settings.print_bed
        exp_props = settings.export
        is_advanced = settings.ui_mode == 'ADVANCED'

        # 3D Print Bed View & Packing
        layout.label(text="3D Print Bed & Layout:", icon='MESH_PLANE')
        b_row = layout.row(align=True)
        b_row.operator(
            "modelsplitter.toggle_print_bed",
            text="Hide Bed" if bed_props.show_bed else "Show Bed",
            icon='HIDE_OFF' if bed_props.show_bed else 'RESTRICT_VIEW_ON'
        )
        b_row.operator("modelsplitter.pack_print_bed", text="Pack on Bed", icon='STICKY_UVS_LOC')

        if is_advanced and bed_props.show_bed:
            dim_col = layout.column(align=True)
            r = dim_col.row(align=True)
            r.prop(bed_props, "bed_x_mm", text="X")
            r.prop(bed_props, "bed_y_mm", text="Y")
            r.prop(bed_props, "bed_z_mm", text="Z")
            r.operator("modelsplitter.update_print_bed", text="", icon='FILE_REFRESH')
            dim_col.prop(bed_props, "part_spacing_mm", text="Margin (mm)")

        layout.separator()

        # Batch Export
        layout.label(text="Batch Export Parts:", icon='EXPORT')
        exp_col = layout.column(align=True)
        exp_col.prop(exp_props, "format", text="Format")
        exp_col.prop(exp_props, "export_dir", text="Folder")
        if is_advanced:
            exp_col.prop(exp_props, "name_prefix", text="Prefix")
            exp_col.prop(exp_props, "batch_export", text="All Parts")

        exp_row = layout.row(align=True)
        exp_row.scale_y = 1.2
        btn_label = "Export All Parts" if exp_props.batch_export else "Export Active Part"
        exp_row.operator("modelsplitter.batch_export", text=btn_label, icon='EXPORT')


classes = (
    MODEL_SPLITTER_PT_main_panel,
    MODEL_SPLITTER_PT_scale_master,
    MODEL_SPLITTER_PT_cutting_tools,
    MODEL_SPLITTER_PT_connectors,
    MODEL_SPLITTER_PT_mesh_tools,
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
