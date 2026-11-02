# Material Brush for Blender / 材质笔刷

A Blender add-on that lets you **paint with materials** — pick any material from your library, brush it onto a surface, and stack multiple layers with individual opacity, visibility and pattern scale. When you are done, one click bakes everything into a standard PBR asset that drops straight into a game engine.

一个让你**用材质当画笔**的 Blender 插件 —— 选一个材质，直接刷到模型表面，支持多层叠加、单独调透明度 / 显示 / 图案大小。做完后一键烘焙成标准 PBR 资产，可直接拖进游戏引擎使用。

---

## 中文

### 功能

- **材质当笔刷**：从材质库选一个材质，刷到物体上，遮罩自动生成，白色刷上、黑色擦除。
- **图层系统**：每层可独立调节 **透明度**、**显示开关**、**图案大小**（放大/缩小纹理，支持程序化材质如 Voronoi、噪波）。
- **中英文界面**：面板顶部「语言」可切 `中文 / English / 自动跟随 Blender`。
- **底材质完全保留**：插件不改动你原材质的节点，只在输出前插入混合链；随时可清空图层还原。
- **一键导出（引擎可用）**：自动烘焙基色 / 粗糙度 / 法线，导出 **glTF(.glb)** 或 **FBX**（贴图内嵌），并附 `manifest.json` 机器可读清单。引擎侧**不需要写任何 shader**。
- **高级：导出遮罩 + 图层清单**：如果需要在引擎里实时切换图层，可导出每层遮罩 PNG 与图层 JSON，配合自己的 shader 使用。

### 安装

1. 下载 `dist/material-brush-v1.6.0.zip`
2. Blender → `编辑 → 偏好设置 → 插件 → 从磁盘安装`
3. 选择该 zip，勾选 **Material Brush (材质笔刷)**
4. 3D 视图按 `N`，在侧栏找到「材质笔刷」标签

要求：Blender **4.2+**（在 5.2 上开发与测试）。

### 使用

1. 选中一个网格物体（需要已有材质和 UV）
2. 面板顶部选一个材质当笔刷
3. 点 **刷这个材质** → 自动建层并进入纹理绘制
4. 用白色刷，黑色擦；`🖼` 可查看遮罩
5. 选中图层行 → 出现 `图案大小` 滑杆；行内滑杆调 `透明度`
6. 完成后点 **一键导出（引擎可用）** → 选择 glTF / FBX / 两者

### 导出产物

```
<场景名>_export/
├─ <场景名>.glb / .fbx      烘焙好的模型
├─ textures/                基色 / 粗糙度 / 法线
├─ manifest.json            物体、材质、贴图路径清单
└─ README.txt
```

### 已知限制

- 金属度固定为 0（混合着色器无法直接采样金属度）
- **玻璃自动排除、金属可手动排除**：玻璃层检测到透射即跳过烘焙；金属等其它层可勾选「排除烘焙」。被排除层的遮罩统一输出到 `nonbake/`，在引擎里配对应材质即可（glTF 原生支持 `KHR_materials_transmission`，单独的玻璃物体可直接导出）
- 法线细节不随图层带过来（只取 Principled 上游 6 层、最多 48 个节点）
- 烘焙需要**不重叠的 UV**

### 许可

未附带开源协议，作者保留权利。如需转载或商用请联系作者。

---

## English

### Features

- **Paint with materials** — pick any material as a brush and paint it onto a mesh; a mask is generated automatically (white paints, black erases).
- **Layer stack** — per-layer **opacity**, **visibility** and **pattern scale** (works for procedural materials such as Voronoi / Noise).
- **Bilingual UI** — switch `中文 / English / Auto` from the Language dropdown at the top of the panel.
- **Non-destructive** — your original material nodes are never modified; the add-on only inserts a mix chain before the material output.
- **One-click engine export** — bakes base color / roughness / normal and exports **glTF (.glb)** or **FBX** with embedded textures, plus a machine-readable `manifest.json`. **No shader authoring required** on the engine side.
- **Advanced: mask + layer manifest export** — for real-time layer blending inside an engine.

### Install

1. Download `dist/material-brush-v1.6.0.zip`
2. Blender → `Edit → Preferences → Add-ons → Install from Disk`
3. Pick the zip and enable **Material Brush**
4. In the 3D Viewport press `N`, find the **材质笔刷** tab

Requires Blender **4.2+** (developed and tested on 5.2).

### Workflow

1. Select a mesh (needs a material and UVs)
2. Choose a material as the brush
3. Click **刷这个材质** — a layer is created and texture paint starts
4. Paint with white, erase with black; `🖼` shows the mask
5. Select a layer row to reveal the **pattern size** slider; the slider in the row controls opacity
6. Click **一键导出（引擎可用）** and pick glTF / FBX / both

### Output

```
<scene>_export/
├─ <scene>.glb / .fbx      baked model
├─ textures/               base color / roughness / normal
├─ manifest.json           object, material and texture listing
└─ README.txt
```

### Limitations

- Metallic is forced to 0 (cannot be sampled through a mix shader)
- **Glass is skipped automatically; metal can be excluded per layer** — excluded layers are not baked and their masks land in `nonbake/`, so you assign the matching material in the engine. glTF supports `KHR_materials_transmission`, so a standalone glass object can be exported directly.
- Normal detail is not carried per layer (Principled + up to 6 levels / 48 nodes)
- Baking requires **non-overlapping UVs**

### License

No open-source license is attached; all rights reserved. Contact the author for reuse.

---

## 结构 / Repository layout

```
material_brush/__init__.py   add-on source (single file)
dist/*.zip                   installable build
```
