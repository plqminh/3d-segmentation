"""
ModelSplitter - Property Groups and Settings
Defines properties for cutting modes, connector parameters, tolerances, mesh validation, and export.
"""

import bpy
from bpy.props import (
    StringProperty,
    BoolProperty,
    IntProperty,
    FloatProperty,
    EnumProperty,
    PointerProperty,
)


def update_connector_preset(self, context):
    """Updates connector dimensions based on standard 3D printing presets."""
    if self.preset == 'SMALL':
        self.diameter_mm = 3.0
        self.length_mm = 6.0
    elif self.preset == 'MEDIUM':
        self.diameter_mm = 5.0
        self.length_mm = 10.0
    elif self.preset == 'LARGE':
        self.diameter_mm = 8.0
        self.length_mm = 15.0


def update_draft_preview(self, context):
    """Triggers an update to the draft mode preview if currently active."""
    settings = getattr(context.scene, "model_splitter", None)
    if settings and settings.cut.is_in_draft:
        # Avoid circular imports by using operator if available
        try:
            bpy.ops.modelsplitter.update_draft_preview('INVOKE_DEFAULT')
        except Exception:
            pass


def update_extrude_depth(self, context):
    """Dynamically updates the extruded curve cutter depth and pins in Draft Mode."""
    settings = getattr(context.scene, "model_splitter", None)
    if settings and settings.cut.is_in_draft:
        try:
            from .core.draft_manager import update_draft_extrude_depth
            update_draft_extrude_depth(context)
        except Exception:
            pass


def update_explode_preview(self, context):
    """Dynamically updates the visual explode offset of split parts and draft sockets."""
    from mathutils import Vector
    from .utils.math_utils import mm_to_scene_units

    settings = getattr(context.scene, "model_splitter", None)
    if not settings:
        return

    dist_mm = settings.cut.explode_distance_mm
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and "ms_base_loc" in obj and "ms_explode_vec" in obj:
            try:
                base_loc = Vector(obj["ms_base_loc"])
                exp_vec = Vector(obj["ms_explode_vec"])
                offset_len = mm_to_scene_units(context, dist_mm, ref_obj=obj)
                obj.location = base_loc + exp_vec * offset_len
            except Exception:
                pass


def update_curve_smoothness(self, context):
    """Rebuilds the active extruded curve cutter in Draft Mode with the new smoothness."""
    settings = getattr(context.scene, "model_splitter", None)
    if settings and settings.cut.is_in_draft:
        try:
            from .core.draft_manager import rebuild_extruded_cutter
            rebuild_extruded_cutter(context)
        except Exception:
            pass


class ConnectorProperties(bpy.types.PropertyGroup):
    shape: EnumProperty(
        name="Pin Shape",
        description="Cross-sectional geometry of the alignment pin",
        items=[
            ('CYLINDER', "Cylinder", "Round cylindrical alignment pin (standard)"),
            ('CONICAL', "Conical (Tapered)", "Tapered pin for easy insertion"),
            ('RECTANGULAR', "Rectangular", "Rectangular alignment key / slot to prevent rotation"),
            ('CUSTOM', "Custom Shape", "Custom rigid mesh used as connector profile"),
        ],
        default='CYLINDER',
        update=update_draft_preview,
    )

    preset: EnumProperty(
        name="Size Preset",
        description="Quick size presets for pins",
        items=[
            ('CUSTOM', "Custom", "Set manual dimensions"),
            ('SMALL', "Small (3x6mm)", "Small figurines and fine details"),
            ('MEDIUM', "Medium (5x10mm)", "Standard statues and busts"),
            ('LARGE', "Large (8x15mm)", "Large props and multi-part statues"),
        ],
        default='MEDIUM',
        update=update_connector_preset,
    )

    count: IntProperty(
        name="Connectors",
        description="Number of alignment connectors (0 for none, up to 5)",
        default=1,
        min=0,
        max=5,
        update=update_draft_preview,
    )

    diameter_mm: FloatProperty(
        name="Diameter",
        description="Pin diameter / width in millimeters",
        default=5.0,
        min=0.5,
        max=100.0,
        unit='NONE',
        update=update_draft_preview,
    )

    length_mm: FloatProperty(
        name="Length",
        description="Pin total length in millimeters",
        default=10.0,
        min=1.0,
        max=200.0,
        unit='NONE',
        update=update_draft_preview,
    )

    taper_angle: FloatProperty(
        name="Taper Angle",
        description="Conical taper angle in degrees",
        default=5.0,
        min=1.0,
        max=30.0,
        update=update_draft_preview,
    )

    clearance_mm: FloatProperty(
        name="Clearance",
        description="Tolerance gap offset between pin and socket (mm). SLA resin: 0.1-0.2mm, FDM: 0.2-0.35mm",
        default=0.2,
        min=0.0,
        max=2.0,
        precision=3,
        unit='NONE',
        update=update_draft_preview,
    )

    cut_gap_mm: FloatProperty(
        name="Cut Gap",
        description="Microscopic spacing gap between split cut surfaces (mm)",
        default=0.0,
        min=0.0,
        max=2.0,
        precision=3,
        unit='NONE',
        update=update_draft_preview,
    )

    target_side: EnumProperty(
        name="Pin Location",
        description="Which part receives the male pin (the other receives socket)",
        items=[
            ('PART_A', "Part A (Top / Outer)", "Male pin attached to Part A"),
            ('PART_B', "Part B (Bottom / Base)", "Male pin attached to Part B"),
        ],
        default='PART_A',
        update=update_draft_preview,
    )

    double_sided: BoolProperty(
        name="Double-Sided Pin",
        description="Creates symmetric pins extending in both directions or a removable loose pin key",
        default=False,
        update=update_draft_preview,
    )

    holes_only: BoolProperty(
        name="Holes Only (No Pins)",
        description="Carve alignment socket holes into both parts without generating male pins or dowels",
        default=False,
        update=update_draft_preview,
    )

    no_connectors: BoolProperty(
        name="No Pins / Holes",
        description="Cut only: do not create any pins, sockets, or holes",
        default=False,
        update=update_draft_preview,
    )

    placement_mode: EnumProperty(
        name="Placement",
        description="How connectors are positioned on the cut plane",
        items=[
            ('AUTO', "Automatic", "Evenly distributed across the cut cross-section"),
            ('MANUAL', "Manual", "Freely position connector markers on the cut surface"),
        ],
        default='AUTO',
        update=update_draft_preview,
    )

    custom_object: PointerProperty(
        name="Custom Pin Object",
        type=bpy.types.Object,
        description="Custom mesh used as connector profile",
        update=update_draft_preview,
    )


class CutProperties(bpy.types.PropertyGroup):
    cut_type: EnumProperty(
        name="Cutting Mode",
        description="Method used to cut the model",
        items=[
            ('STRAIGHT', "Straight Cut", "Planar cutting plane that can be translated and rotated"),
            ('CURVED', "Curved Cut", "Organic curved cutting surface with contour control"),
            ('MANUAL', "Manual Cut", "Freehand polyline cut through the model"),
            ('EXTRUDE_CURVE', "Curve Detail (Extrude)", "Extrude a closed curve into polygons to Boolean out a detail"),
            ('POLYGONAL_LINE', "Polygonal (Line)", "Carve out openings or inset details"),
            ('POLYGONAL_CYLINDER', "Polygonal (Cylinder)", "Isolate protruding parts like ears, horns, or limbs"),
            ('SEPARATE_BASE', "Separate from Base", "Detaches figurine feet/pedestal cleanly"),
        ],
        default='STRAIGHT',
    )

    workflow_mode: EnumProperty(
        name="Workflow",
        description="Workflow mode",
        items=[
            ('DRAFT', "Draft Mode", "Non-destructive: preview and adjust plane & pins before applying"),
            ('EASY', "Easy Mode", "One-click split and keying executed immediately"),
        ],
        default='DRAFT',
    )

    is_in_draft: BoolProperty(
        name="In Draft Mode",
        description="True when currently previewing a cut in Draft Mode",
        default=False,
    )

    active_cutter_name: StringProperty(
        name="Active Cutter Object",
        default="",
    )

    active_source_name: StringProperty(
        name="Active Source Object",
        default="",
    )

    split_islands: BoolProperty(
        name="Split Disconnected Parts",
        description="Automatically separate isolated disconnected parts into individual objects",
        default=True,
    )

    draw_mode: EnumProperty(
        name="Draw Cut Style",
        description="Drawing method for the interactive cut line",
        items=[
            ('STRAIGHT', "Straight", "Draw a straight knife cut across the viewport"),
            ('CURVED', "Curved", "Draw a smooth curved arc cut across the viewport"),
            ('MANUAL', "Manual Surface", "Click or paint points directly on the 3D model surface"),
            ('EXTRUDE_CURVE', "Curve Detail", "Draw a closed curve and extrude it to polygons to Boolean out a detail"),
        ],
        default='STRAIGHT',
    )

    curve_smoothness: FloatProperty(
        name="Curve Smoothness",
        description="0 = straight polygon edges exactly through your points, 1 = fully rounded spline (still passes through every point)",
        default=0.0,
        min=0.0,
        max=1.0,
        subtype='FACTOR',
        update=update_curve_smoothness,
    )

    extrude_depth_mm: FloatProperty(
        name="Extrude Depth (mm)",
        description="Depth (in mm) to extrude the closed curve into the model to Boolean out the detail",
        default=10.0,
        min=0.5,
        max=500.0,
        unit='NONE',
        update=update_extrude_depth,
    )

    editable_points: IntProperty(
        name="Curve Samples",
        description="Number of sampled control points along curved cuts",
        default=16,
        min=4,
        max=64,
    )

    explode_distance_mm: FloatProperty(
        name="Explode Preview",
        description="Visually offsets cut parts along the cut axis to inspect joint fit",
        default=0.0,
        min=0.0,
        max=150.0,
        unit='NONE',
        update=update_explode_preview,
    )

    adaptive_surface: BoolProperty(
        name="Adaptive Surface",
        description="Optimizes geometry transitions along cut boundaries for dense/AI sculpts",
        default=True,
    )


class MeshCheckProperties(bpy.types.PropertyGroup):
    checked: BoolProperty(name="Checked", default=False)
    is_clean: BoolProperty(name="Is Clean", default=True)
    non_manifold_count: IntProperty(name="Non-Manifold Edges", default=0)
    open_edges_count: IntProperty(name="Open Boundary Edges", default=0)
    self_intersect_count: IntProperty(name="Self-Intersections", default=0)
    degenerate_count: IntProperty(name="Degenerate Faces", default=0)
    total_verts: IntProperty(name="Vertices", default=0)
    total_faces: IntProperty(name="Faces", default=0)
    status_message: StringProperty(name="Status", default="Not tested yet")


class ExportProperties(bpy.types.PropertyGroup):
    format: EnumProperty(
        name="Format",
        description="File format for export",
        items=[
            ('STL', "STL (.stl)", "Standard stereolithography file for 3D slicing software"),
            ('OBJ', "OBJ (.obj)", "Wavefront OBJ with normals and materials"),
        ],
        default='STL',
    )

    export_dir: StringProperty(
        name="Export Folder",
        description="Target directory for exported parts",
        default="//",
        subtype='DIR_PATH',
    )

    batch_export: BoolProperty(
        name="Batch Export All Parts",
        description="Exports all separated parts of the cut model into individual files",
        default=True,
    )

    name_prefix: StringProperty(
        name="Prefix",
        description="File name prefix for parts",
        default="Part",
    )


class ModelSplitterSettings(bpy.types.PropertyGroup):
    cut: PointerProperty(type=CutProperties)
    connector: PointerProperty(type=ConnectorProperties)
    mesh_check: PointerProperty(type=MeshCheckProperties)
    export: PointerProperty(type=ExportProperties)


classes = (
    ConnectorProperties,
    CutProperties,
    MeshCheckProperties,
    ExportProperties,
    ModelSplitterSettings,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.model_splitter = PointerProperty(type=ModelSplitterSettings)


def unregister():
    if hasattr(bpy.types.Scene, "model_splitter"):
        del bpy.types.Scene.model_splitter
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
