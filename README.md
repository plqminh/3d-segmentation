# ModelSplitter — Blender 4.2+ / 5.x Add-on

A high-precision, non-destructive 3D model splitting and keying add-on for 3D printing (SLA/FDM), recreating the complete feature set of **CatPin**.

---

## 🌟 Key Features

1. **Interactive Viewport Cut Line Drawing (CatPin Workflow)**:
   - **Straight View Cut**: Angle your camera, click and drag across the model to slice cleanly along the line-of-sight.
   - **Curved Arc Cut**: Draw a gestural curved stroke across the viewport; sweeps into an organic cutting ribbon to hide seam lines.
   - **Manual Surface Contour**: Click points or paint directly onto the 3D mesh surface to carve around muscle groups, limb joints, or detached features.
   - **Camera Orbit during Drawing**: Hold `MMB` to freely rotate around the model while placing contour points without exiting the drawing tool.
   - **Real-time GPU Viewport HUD**: On-screen shortcuts banner, vivid red cutting line, yellow live rubber-band preview, and green closing anchor dot.
   - **Interactive Shortcuts**: `Enter` to commit, `Backspace` / `Ctrl+Z` to undo point, `Esc` to cancel.

2. **Non-Destructive Draft Mode vs. Easy Mode**:
   - **Draft Mode**: Real-time 3D preview of cutting planes and connector pins. Move, rotate, and resize before committing geometry.
   - **Easy Mode**: Slices and creates connectors in a single click directly upon releasing the drawn cut line.

3. **Intelligent Alignment Connectors (Pins & Sockets)**:
   - **Pin Shapes**: Cylindrical, Conical (Tapered), Rectangular, and Custom Rigid Profiles.
   - **Multi-Connector Support**: 1 to 5 connectors per cut with symmetric geometric distribution.
   - **Independent Clearance & Tolerance**: Millimeter dials (recommended: `0.1–0.2mm` for Resin SLA, `0.2–0.35mm` for FDM).
   - **Swap Pin Side**: Instant one-click toggle (`Swap`) to flip male pin placement between Part A and Part B.
   - **Double-Sided Pins**: Generates loose alignment dowels / keys.
   - **Explode Preview**: Slider to visually separate cut pieces along the cut normal to inspect joint fit before final printing.

4. **Mesh Health & Pre-flight Diagnostics**:
   - Accelerated **BVH-tree** analysis to detect non-manifold geometry, boundary edge holes, degenerate zero-area faces, and self-intersecting triangles.
   - One-click **"Show in Edit Mode"** to inspect defect loops.
   - **"Auto-Heal"** tool to weld vertices and recalculate surface normals.

5. **Batch Export**:
   - One-click batch export of separated parts to **STL** or **OBJ** formats ready for slicing (PrusaSlicer, Bambu Studio, Chitubox, Lychee).

---

## 🚀 Installation

### Option 1: Install from ZIP file
1. In Blender (4.2, 4.5, 5.0, or 5.1+), open **Edit > Preferences > Add-ons**.
2. Click the drop-down menu in the upper-right corner and select **Install from Disk...**
3. Select `model_splitter.zip` located in `e:\3D segmentation\model_splitter.zip`.
4. Enable the **ModelSplitter** extension.

### Option 2: Live Development Symlink
You can link the addon folder directly into your Blender extensions folder:
`%APPDATA%\Blender Foundation\Blender\5.1\extensions\user_default\model_splitter`

---

## 📖 How to Use

1. Press `N` in the 3D Viewport to open the sidebar and click on the **ModelSplitter** tab.
2. Select your 3D mesh in Object Mode.
3. *(Recommended)* Under **Mesh Health Pre-flight**, click **Check Active Mesh** to verify that your model is closed and manifold.
4. Select your **Workflow** (`Draft Mode` or `Easy Mode`).
5. Choose your **Draw Cut Style**:
   - `Straight`: For clean planar cuts across limbs or torso.
   - `Curved`: For organic contours.
   - `Manual Surface`: For surface-snapped boundaries around joints.
6. Click **Draw Cut Line**:
   - Drag or click points across the model.
   - Use `MMB` to rotate the view if drawing around the back.
   - Press `Enter` (or click the green start dot) to commit.
7. In **Draft Mode**, the cutting plane and preview pins appear at the exact drawn location:
   - Click **Swap Pin Side** if you want the pin on the opposite part.
   - Use the **Explode Preview** slider to inspect the seam.
   - Click **Apply Cut (Build)** to finalize.
8. Under **Batch Export**, select your export folder and click **Export Selected Parts**.
