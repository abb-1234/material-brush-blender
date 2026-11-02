bl_info = {
    "name": "Material Brush (材质笔刷)",
    "author": "WorkBuddy",
    "version": (1, 4, 1),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > 材质笔刷",
    "description": "选材质当笔刷刷到物体表面；可按图层导出遮罩，或烘焙成 PBR 贴图 + GLB 给 Godot/Unity。",
    "category": "Material",
}

import bpy
import os
import json
import traceback

MB_TAG = "mb_owned"
MASK_PREFIX = "MB_MASK_"
ANCHOR = "MB_BASE_ANCHOR"
NTAG = "mb_node"
NODE_CAP = 48
MAX_DEPTH = 6

TEXTURE_NODES = {
    "ShaderNodeTexImage", "ShaderNodeTexVoronoi", "ShaderNodeTexNoise",
    "ShaderNodeTexWave", "ShaderNodeTexMagic", "ShaderNodeTexGradient",
    "ShaderNodeTexChecker", "ShaderNodeTexBrick", "ShaderNodeTexSky",
    "ShaderNodeTexMusgrave",
}


# ---------------------------------------------------------------- i18n

STRINGS = {
    "zh": {
        "lang": "语言",
        "add": "刷这个材质",
        "use_cur": "取当前材质",
        "layers": "图层（上层在上）",
        "hint_none": "先点上面那个按钮建一层",
        "hint_empty": "还没有图层",
        "paint": "绘制这一层",
        "size": "图案大小",
        "status_tex": "贴图 ",
        "status_proc": "程序化材质",
        "status_flat": "纯色（无底色贴图）",
        "status_trans": "该材质有透射，刷上去不明显",
        "export": "导出到游戏引擎",
        "tips1": "选中物体=只导这些；没选=整个场景",
        "tips2": "材质自动烘焙成标准 PBR，引擎侧不用写代码",
        "tips3": "透射材质（玻璃）烘出来是黑的",
        "export_all": "一键导出（引擎可用）",
        "masks": "导出遮罩 + 图层清单",
        "open_after": "导出后自动打开文件夹",
        "dir_empty": "留空 = blend 文件旁的 MB_Export",
        "dir_to": "输出到 ",
        "adv": "高级：需要引擎里实时调图层时用",
        "err_brush": "先在上方选一个笔刷材质",
        "err_uv": "物体没有 UV，先展 UV",
        "err_fail": "建层失败（已还原材质）：",
        "err_nolayer": "没有图层可导出",
        "err_notbrush": "当前材质不是笔刷材质",
        "err_nonmesh": "场景里没有网格物体",
        "ok_masks": "已导出 %d 张遮罩到 %s",
        "ok_objs": "已导出 %d 个物体到 %s",
        "err_export": "导出失败：",
        "pick_layer": "先选一个图层",
        "no_mask_node": "找不到遮罩节点，点『重建』",
        "warn_baked": "这是笔刷材质，请选原始材质",
    },
    "en": {
        "lang": "Language",
        "add": "Paint with this material",
        "use_cur": "Use current material",
        "layers": "Layers (top first)",
        "hint_none": "Click the button above to add a layer",
        "hint_empty": "No layers yet",
        "paint": "Paint this layer",
        "size": "Pattern size",
        "status_tex": "Texture ",
        "status_proc": "Procedural material",
        "status_flat": "Flat color (no base texture)",
        "status_trans": "Transmissive material - hard to see when painted",
        "export": "Export to game engine",
        "tips1": "Selected objects only; nothing selected = whole scene",
        "tips2": "Bakes to standard PBR - no shader coding needed",
        "tips3": "Transmissive materials (glass) bake to black",
        "export_all": "Export (engine ready)",
        "masks": "Export masks + layer list",
        "open_after": "Open folder after export",
        "dir_empty": "Empty = MB_Export next to the .blend",
        "dir_to": "Output to ",
        "adv": "Advanced: real-time layers inside the engine",
        "err_brush": "Pick a brush material first",
        "err_uv": "Object has no UVs - unwrap it first",
        "err_fail": "Layer creation failed (material restored): ",
        "err_nolayer": "No layers to export",
        "err_notbrush": "Current material is not a Material Brush material",
        "err_nonmesh": "No mesh objects in the scene",
        "ok_masks": "Exported %d masks to %s",
        "ok_objs": "Exported %d objects to %s",
        "err_export": "Export failed: ",
        "pick_layer": "Select a layer first",
        "no_mask_node": "Mask node missing - click Rebuild",
        "warn_baked": "This is a brush material - pick the original one",
    },
}


def cur_lang():
    try:
        v = bpy.context.scene.mb_state.lang
    except Exception:
        v = "AUTO"
    if v == "ZH":
        return "zh"
    if v == "EN":
        return "en"
    loc = getattr(bpy.app.translations, "locale", "en") or "en"
    return "zh" if loc.lower().startswith("zh") else "en"


def t(key):
    table = STRINGS.get(cur_lang(), STRINGS["en"])
    return table.get(key, STRINGS["en"].get(key, key))



# ---------------------------------------------------------------- basics

def _principled(mat):
    if not mat or not mat.use_nodes or not mat.node_tree:
        return None
    for n in mat.node_tree.nodes:
        if n.bl_idname == "ShaderNodeBsdfPrincipled":
            return n
    return None


def _upstream_image(sock, depth=5):
    cur = [l.from_node for l in sock.links] if sock else []
    seen = set()
    for _ in range(depth):
        nxt = []
        for n in cur:
            if n.name in seen:
                continue
            seen.add(n.name)
            if n.bl_idname == "ShaderNodeTexImage" and n.image:
                return n.image
            for i in n.inputs:
                for l in i.links:
                    nxt.append(l.from_node)
        cur = nxt
        if not cur:
            break
    return None


def _copy_props(src, dst):
    skip = {
        "name", "location", "width", "height", "label", "parent", "select",
        "hide", "mute", "show_options", "show_preview", "show_texture",
        "use_custom_color", "color", "type", "inputs", "outputs",
        "internal_links", "dimensions", "bl_idname", "bl_label",
        "bl_description", "bl_icon", "bl_static_type",
        "bl_width_default", "bl_width_min", "bl_width_max",
        "bl_height_default", "bl_height_min", "bl_height_max",
        "node_tree",
    }
    for prop in src.bl_rna.properties:
        pid = prop.identifier
        if pid in skip or prop.type in {"POINTER", "COLLECTION"}:
            continue
        try:
            setattr(dst, pid, getattr(src, pid))
        except Exception:
            pass
    if hasattr(src, "image") and hasattr(dst, "image"):
        try:
            dst.image = src.image
        except Exception:
            pass
    for i, inp in enumerate(src.inputs):
        if inp.is_linked or i >= len(dst.inputs):
            continue
        try:
            dv = inp.default_value
            if hasattr(dv, "__len__"):
                dst.inputs[i].default_value = list(dv)
            else:
                dst.inputs[i].default_value = dv
        except Exception:
            pass


def _collect(bsdf):
    """从 BSDF 往上收集要复制的节点；跳过节点组（EEVEE 展开内联会崩）。"""
    picked, seen = [], set()
    queue = [(bsdf, 0)]
    while queue and len(picked) < NODE_CAP:
        n, d = queue.pop(0)
        if n.name in seen:
            continue
        seen.add(n.name)
        picked.append(n)
        if d >= MAX_DEPTH:
            continue
        for i in n.inputs:
            for l in i.links:
                fn = l.from_node
                if fn.bl_idname in ("ShaderNodeGroup", "ShaderNodeOutputMaterial",
                                    "ShaderNodeOutputWorld"):
                    continue
                if fn.name not in seen:
                    queue.append((fn, d + 1))
    return picked


def inline_layer(nt, brush, prefix, scale):
    """把笔刷材质的节点直接复制进 nt，返回输出 shader 插槽。全程不使用节点组。"""
    src_bsdf = _principled(brush)
    if src_bsdf is None:
        return None

    picked = _collect(src_bsdf)
    if not picked:
        return None

    amap = {}
    for n in picked:
        try:
            nn = nt.nodes.new(n.bl_idname)
        except Exception:
            continue
        try:
            nn.name = (prefix + n.name)[:58]
        except Exception:
            pass
        nn[NTAG] = True
        _copy_props(n, nn)
        amap[n.name] = nn

    for n in picked:
        tn = amap.get(n.name)
        if tn is None:
            continue
        for i, inp in enumerate(n.inputs):
            for l in inp.links:
                fn = amap.get(l.from_node.name)
                if fn is None or i >= len(tn.inputs):
                    continue
                try:
                    si = list(l.from_node.outputs).index(l.from_socket)
                    nt.links.new(fn.outputs[si], tn.inputs[i])
                except Exception:
                    pass

    # 空着的着色器输入在 Blender 里等于纯黑，补中性 Principled（不会成环）
    for nn in list(amap.values()):
        if nn.bl_idname != "ShaderNodeMixShader":
            continue
        for idx in (1, 2):
            try:
                if nn.inputs[idx].is_linked:
                    continue
                p = nt.nodes.new("ShaderNodeBsdfPrincipled")
                p[NTAG] = True
                nt.links.new(p.outputs["BSDF"], nn.inputs[idx])
            except Exception:
                pass

    # 图案缩放：直接在每个纹理节点的 Vector 前插 Mapping。
    # 不依赖上游有没有 TexCoord —— 贴图用默认 UV 时也能生效。
    k = 1.0 / max(scale, 0.001)
    if abs(k - 1.0) > 1e-4:
        for nn in list(amap.values()):
            if nn.bl_idname not in TEXTURE_NODES:
                continue
            vin = nn.inputs.get("Vector")
            if vin is None:
                continue
            try:
                if vin.is_linked:
                    src = vin.links[0].from_socket
                    mpg = nt.nodes.new("ShaderNodeMapping")
                    mpg[NTAG] = True
                    mpg.label = "图案缩放"
                    mpg.inputs["Scale"].default_value = (k, k, k)
                    nt.links.new(src, mpg.inputs["Vector"])
                    nt.links.new(mpg.outputs["Vector"], vin)
                else:
                    kind = "UV" if nn.bl_idname == "ShaderNodeTexImage" else "Object"
                    tc = nt.nodes.new("ShaderNodeTexCoord")
                    tc[NTAG] = True
                    mpg = nt.nodes.new("ShaderNodeMapping")
                    mpg[NTAG] = True
                    mpg.label = "图案缩放"
                    mpg.inputs["Scale"].default_value = (k, k, k)
                    nt.links.new(tc.outputs[kind], mpg.inputs["Vector"])
                    nt.links.new(mpg.outputs["Vector"], vin)
            except Exception:
                pass

    new_bsdf = amap.get(src_bsdf.name)
    if new_bsdf is None:
        return None
    try:
        return new_bsdf.outputs["BSDF"]
    except Exception:
        return None


# ---------------------------------------------------------------- material

def _ensure_anchor(mat):
    """放一个 Fac=0 的直通 Mix Shader 当锚点；底材质原有节点完全不动。"""
    nt = mat.node_tree
    ang = nt.nodes.get(ANCHOR)
    if ang:
        return ang
    out = None
    for n in nt.nodes:
        if n.bl_idname == "ShaderNodeOutputMaterial":
            out = n
            break
    if not out:
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        out.location = (700, 0)

    ang = nt.nodes.new("ShaderNodeMixShader")
    ang.name = ANCHOR
    ang.location = (450, -250)
    ang.inputs[0].default_value = 0.0

    surf = out.inputs.get("Surface")
    src = surf.links[0].from_socket if (surf and surf.is_linked) else None
    if src is None:
        p = nt.nodes.new("ShaderNodeBsdfPrincipled")
        src = p.outputs["BSDF"]
    nt.links.new(src, ang.inputs[1])
    nt.links.new(src, ang.inputs[2])
    nt.links.new(ang.outputs[0], surf)
    return ang


def prepare_material(context):
    ob = context.active_object
    if not ob or ob.type != "MESH":
        return None
    mat = ob.active_material
    if not mat:
        return None
    if mat.library:
        try:
            mat.make_local()
        except Exception:
            pass
    _ensure_anchor(mat)
    mat[MB_TAG] = True
    return mat


def layers_of(mat):
    return mat.mb_layers if (mat and mat.get(MB_TAG)) else None


def ensure_uv(context):
    ob = context.active_object
    return bool(ob and ob.type == "MESH" and ob.data.uv_layers)


def rebuild(context, force_groups=False):
    ob = context.active_object
    if not ob or ob.type != "MESH":
        return None
    mat = ob.active_material
    if not mat or not mat.get(MB_TAG):
        return None
    st = context.scene.mb_state
    lst = mat.mb_layers
    nt = mat.node_tree

    ang = _ensure_anchor(mat)

    for n in list(nt.nodes):
        if n.get(NTAG):
            nt.nodes.remove(n)

    out = None
    for n in nt.nodes:
        if n.bl_idname == "ShaderNodeOutputMaterial":
            out = n
            break

    prev = ang.outputs[0]
    y = 0
    for i, layer in enumerate(reversed(list(lst.layers))):
        if not layer.visible:
            continue
        mask = bpy.data.images.get(layer.image_name)
        if not mask:
            continue
        brush = bpy.data.materials.get(layer.mat_name)
        if not brush:
            continue

        mnode = nt.nodes.new("ShaderNodeTexImage")
        mnode.name = MASK_PREFIX + layer.uid
        mnode.label = layer.name + " 遮罩"
        mnode.image = mask
        mnode.extension = "EXTEND"
        mnode[NTAG] = True
        mnode.location = (-900, y)

        mth = nt.nodes.new("ShaderNodeMath")
        mth.operation = "MULTIPLY"
        mth.inputs[1].default_value = layer.opacity
        mth.label = "透明度"
        mth[NTAG] = True
        mth.location = (-650, y)
        nt.links.new(mnode.outputs["Color"], mth.inputs[0])

        shader = inline_layer(nt, brush, "MB%d_" % i, layer.size)
        if shader is None:
            y -= 400
            continue

        mix = nt.nodes.new("ShaderNodeMixShader")
        mix[NTAG] = True
        mix.label = layer.name
        mix.location = (250, y)
        nt.links.new(mth.outputs[0], mix.inputs["Fac"])
        nt.links.new(prev, mix.inputs[1])
        nt.links.new(shader, mix.inputs[2])
        prev = mix.outputs[0]

        y -= 400

    if st.show_mask and 0 <= lst.active_index < len(lst.layers):
        am = nt.nodes.get(MASK_PREFIX + lst.layers[lst.active_index].uid)
        if am:
            emi = nt.nodes.new("ShaderNodeEmission")
            emi[NTAG] = True
            nt.links.new(am.outputs["Color"], emi.inputs["Color"])
            prev = emi.outputs[0]

    if out and prev is not None:
        nt.links.new(prev, out.inputs["Surface"])

    if 0 <= lst.active_index < len(lst.layers):
        an = nt.nodes.get(MASK_PREFIX + lst.layers[lst.active_index].uid)
        if an:
            nt.nodes.active = an
    return mat


def enter_paint(context, mat, layer):
    node = mat.node_tree.nodes.get(MASK_PREFIX + layer.uid)
    if not node:
        return False
    mat.node_tree.nodes.active = node

    # 必须先切模式：切之前 image_paint.brush 往往是空的，设了也会被忽略
    if context.object.mode != "TEXTURE_PAINT":
        bpy.ops.object.mode_set(mode="TEXTURE_PAINT")

    ip = context.tool_settings.image_paint
    try:
        ip.mode = "MATERIAL"
    except Exception:
        pass

    # 再上笔刷：遮罩是黑底，必须白笔刷、满强度，否则画了看不见
    try:
        if ip.brush is None:
            cand = bpy.data.brushes.get("Paint Hard")
            if cand is None:
                for b in bpy.data.brushes:
                    if b.use_paint_image:
                        cand = b
                        break
            if cand is not None:
                ip.brush = cand
        if ip.brush is not None:
            ip.brush.color = (1.0, 1.0, 1.0)
            ip.brush.strength = 1.0
    except Exception:
        pass

    try:
        ups = context.scene.tool_settings.unified_paint_settings
        ups.color = (1.0, 1.0, 1.0)
        ups.strength = 1.0
    except Exception:
        pass

    try:
        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                for sp in area.spaces:
                    if sp.type == "VIEW_3D":
                        sp.shading.type = "MATERIAL"
    except Exception:
        pass
    return True


# ---------------------------------------------------------------- properties

def _layer_param_update(self, context):
    """透明度 / 显示 / 图案大小 改动后立刻重建，否则调了没反应。"""
    try:
        rebuild(context)
    except Exception:
        pass


def _layer_size_update(self, context):
    # 直接重建（不走定时器：定时器在某些情况下不触发，表现为拖了没反应）
    try:
        rebuild(context)
    except Exception:
        pass


class MB_Layer(bpy.types.PropertyGroup):
    uid: bpy.props.StringProperty()
    name: bpy.props.StringProperty(name="图层名", default="图层")
    mat_name: bpy.props.StringProperty()
    image_name: bpy.props.StringProperty()
    opacity: bpy.props.FloatProperty(name="透明度", default=1.0, min=0.0, max=1.0,
                                     subtype="FACTOR", update=_layer_param_update)
    visible: bpy.props.BoolProperty(name="显示", default=True, update=_layer_param_update)
    size: bpy.props.FloatProperty(name="图案大小", default=1.0, min=0.05, max=50.0,
                                  soft_min=0.1, soft_max=10.0, update=_layer_param_update)


class MB_LayerList(bpy.types.PropertyGroup):
    layers: bpy.props.CollectionProperty(type=MB_Layer)
    active_index: bpy.props.IntProperty(default=-1)


class MB_State(bpy.types.PropertyGroup):
    brush_mat: bpy.props.PointerProperty(name="笔刷材质", type=bpy.types.Material)
    resolution: bpy.props.EnumProperty(
        name="分辨率",
        items=[("1024", "1K", ""), ("2048", "2K", ""), ("4096", "4K", "")],
        default="2048",
    )
    bake_size: bpy.props.EnumProperty(
        name="烘焙尺寸",
        items=[("512", "512", ""), ("1024", "1K", ""), ("2048", "2K", ""), ("4096", "4K", "")],
        default="1024",
    )
    export_dir: bpy.props.StringProperty(name="导出目录", subtype="DIR_PATH", default="")
    lang: bpy.props.EnumProperty(
        name="语言 / Language",
        items=[("AUTO", "Auto", "Follow Blender UI language"),
               ("ZH", "中文", ""),
               ("EN", "English", "")],
        default="AUTO",
    )
    auto_open_dir: bpy.props.BoolProperty(name="导出后打开文件夹", default=True)
    export_format: bpy.props.EnumProperty(
        name="格式",
        items=[("GLB", "glTF", "Godot / 通用"),
               ("FBX", "FBX", "Unity / UE"),
               ("BOTH", "两者", "")],
        default="GLB",
    )
    tex_scale: bpy.props.FloatProperty(name="纹理平铺", default=1.0, min=0.01, max=200.0)
    show_mask: bpy.props.BoolProperty(name="看遮罩", default=False)


# ---------------------------------------------------------------- operators

class MB_OT_add_layer(bpy.types.Operator):
    bl_idname = "mb.add_layer"
    bl_label = "刷这个材质"
    bl_description = "用选中的材质新建绘制图层，并直接进入纹理绘制模式"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return bool(ob and ob.type == "MESH" and ob.active_material)

    def execute(self, context):
        st = context.scene.mb_state
        ob = context.active_object
        brush = st.brush_mat
        if not brush:
            self.report({"ERROR"}, t("err_brush"))
            return {"CANCELLED"}
        if not ensure_uv(context):
            self.report({"ERROR"}, t("err_uv"))
            return {"CANCELLED"}

        orig_mat = ob.active_material
        img = None
        try:
            mat = prepare_material(context)
            if not mat:
                raise RuntimeError("无法准备材质")

            img = bpy.data.images.new(
                "%s%04d" % (MASK_PREFIX, len(bpy.data.images)),
                width=int(st.resolution), height=int(st.resolution),
                alpha=False, is_data=True,
            )
            img.use_fake_user = True

            lst = mat.mb_layers
            layer = lst.layers.add()
            layer.uid = img.name[len(MASK_PREFIX):] if img.name.startswith(MASK_PREFIX) else img.name
            layer.name = brush.name
            layer.mat_name = brush.name
            layer.image_name = img.name
            layer.opacity = 1.0
            n = len(lst.layers)
            if n > 1:
                lst.layers.move(n - 1, 0)
            lst.active_index = 0

            rebuild(context)
            enter_paint(context, mat, layer)
            return {"FINISHED"}

        except Exception as e:
            traceback.print_exc()
            try:
                if img and img.name in bpy.data.images:
                    bpy.data.images.remove(img)
            except Exception:
                pass
            try:
                if orig_mat and orig_mat.name in bpy.data.materials:
                    ob.material_slots[ob.active_material_index].material = orig_mat
            except Exception:
                pass
            self.report({"ERROR"}, t("err_fail") + str(e))
            return {"CANCELLED"}


class MB_OT_remove_layer(bpy.types.Operator):
    bl_idname = "mb.remove_layer"
    bl_label = "删除图层"
    bl_options = {"REGISTER", "UNDO"}

    index: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        lst = layers_of(context.active_object.active_material)
        if lst is None:
            return {"CANCELLED"}
        i = self.index if self.index >= 0 else lst.active_index
        if not (0 <= i < len(lst.layers)):
            return {"CANCELLED"}
        img = bpy.data.images.get(lst.layers[i].image_name)
        lst.layers.remove(i)
        if img:
            img.use_fake_user = False
            if img.users == 0:
                bpy.data.images.remove(img)
        lst.active_index = min(i, len(lst.layers) - 1)
        rebuild(context)
        return {"FINISHED"}


class MB_OT_move_layer(bpy.types.Operator):
    bl_idname = "mb.move_layer"
    bl_label = "移动图层"
    bl_options = {"REGISTER", "UNDO"}

    index: bpy.props.IntProperty(default=-1)
    direction: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        lst = layers_of(context.active_object.active_material)
        if lst is None:
            return {"CANCELLED"}
        i = self.index if self.index >= 0 else lst.active_index
        j = i + self.direction
        if not (0 <= i < len(lst.layers) and 0 <= j < len(lst.layers)):
            return {"CANCELLED"}
        lst.layers.move(i, j)
        lst.active_index = j
        rebuild(context)
        return {"FINISHED"}


class MB_OT_select_layer(bpy.types.Operator):
    bl_idname = "mb.select_layer"
    bl_label = "选择图层"
    bl_options = {"REGISTER", "UNDO"}

    index: bpy.props.IntProperty(default=0)

    def execute(self, context):
        mat = context.active_object.active_material
        lst = layers_of(mat)
        if lst is None:
            return {"CANCELLED"}
        if 0 <= self.index < len(lst.layers):
            lst.active_index = self.index
            node = mat.node_tree.nodes.get(MASK_PREFIX + lst.layers[self.index].uid)
            if node:
                mat.node_tree.nodes.active = node
        return {"FINISHED"}


class MB_OT_paint(bpy.types.Operator):
    bl_idname = "mb.paint"
    bl_label = "绘制这一层"
    bl_description = "进入纹理绘制模式，笔刷作用在当前图层的遮罩上"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.active_object and context.active_object.type == "MESH")

    def execute(self, context):
        mat = context.active_object.active_material
        lst = layers_of(mat)
        if lst is None or not (0 <= lst.active_index < len(lst.layers)):
            self.report({"ERROR"}, t("pick_layer"))
            return {"CANCELLED"}
        if not enter_paint(context, mat, lst.layers[lst.active_index]):
            self.report({"ERROR"}, t("no_mask_node"))
            return {"CANCELLED"}
        return {"FINISHED"}


class MB_OT_clear(bpy.types.Operator):
    bl_idname = "mb.clear_layers"
    bl_label = "清空图层"
    bl_description = "删掉所有图层，材质恢复成原来的样子"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        mat = context.active_object.active_material
        lst = layers_of(mat)
        if lst is None:
            self.report({"ERROR"}, t("err_notbrush"))
            return {"CANCELLED"}
        for _ in range(len(lst.layers)):
            img = bpy.data.images.get(lst.layers[0].image_name)
            lst.layers.remove(0)
            if img:
                img.use_fake_user = False
                if img.users == 0:
                    bpy.data.images.remove(img)
        nt = mat.node_tree
        ang = nt.nodes.get(ANCHOR)
        for n in list(nt.nodes):
            if n.get(NTAG):
                nt.nodes.remove(n)
        if ang:
            out = None
            for n in nt.nodes:
                if n.bl_idname == "ShaderNodeOutputMaterial":
                    out = n
                    break
            if out:
                nt.links.new(ang.outputs[0], out.inputs["Surface"])
        lst.active_index = -1
        return {"FINISHED"}


class MB_OT_toggle_mask(bpy.types.Operator):
    bl_idname = "mb.toggle_mask"
    bl_label = "看遮罩"
    bl_description = "临时把当前图层的遮罩显示成黑白图"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        st = context.scene.mb_state
        st.show_mask = not st.show_mask
        rebuild(context)
        return {"FINISHED"}


class MB_OT_rebuild(bpy.types.Operator):
    bl_idname = "mb.rebuild"
    bl_label = "重建"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if not rebuild(context):
            self.report({"ERROR"}, t("err_notbrush"))
            return {"CANCELLED"}
        return {"FINISHED"}


class MB_OT_use_active(bpy.types.Operator):
    bl_idname = "mb.use_active"
    bl_label = "取当前材质"
    bl_description = "把物体当前的原始材质设为笔刷"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ob = context.active_object
        if not ob or not ob.active_material:
            return {"CANCELLED"}
        mat = ob.active_material
        if mat.get(MB_TAG):
            self.report({"WARNING"}, t("warn_baked"))
            return {"CANCELLED"}
        context.scene.mb_state.brush_mat = mat
        return {"FINISHED"}


# ---------------------------------------------------------------- export

GODOT_SHADER = '''shader_type spatial;
render_mode blend_mix;

// 由 Material Brush 自动生成
uniform sampler2D base_albedo : source_color, hint_default_white;
{layer_uniforms}
void fragment() {{
    vec3 c = texture(base_albedo, UV).rgb;
{layer_body}
    ALBEDO = c;
}}
'''


def _copy_image(img, dst_path):
    """把图像另存到 dst，不破坏原数据块。
    注意：img.copy() 出来的副本没有像素数据，save() 会报错，不能用那条路。"""
    if img is None:
        return False
    fmt = None
    try:
        fmt = img.file_format
        img.file_format = "PNG"
    except Exception:
        pass

    ok = False
    try:
        img.save(filepath=dst_path, save_copy=True)
        ok = os.path.exists(dst_path) and os.path.getsize(dst_path) > 0
    except Exception:
        ok = False
    if not ok:
        try:
            img.save(filepath=dst_path)
            ok = os.path.exists(dst_path) and os.path.getsize(dst_path) > 0
        except Exception:
            ok = False
    if not ok:
        try:
            img.save_render(dst_path)
            ok = os.path.exists(dst_path) and os.path.getsize(dst_path) > 0
        except Exception:
            ok = False

    try:
        if fmt:
            img.file_format = fmt
    except Exception:
        pass
    return ok


def _walk_image(sock, depth=6):
    cur = [l.from_node for l in sock.links] if sock else []
    seen = set()
    for _ in range(depth):
        nxt = []
        for n in cur:
            if n.name in seen:
                continue
            seen.add(n.name)
            if n.bl_idname == "ShaderNodeTexImage" and n.image:
                return n.image
            for i in n.inputs:
                for l in i.links:
                    nxt.append(l.from_node)
        cur = nxt
        if not cur:
            break
    return None


def _is_transmissive(brush):
    """判断笔刷材质是否是透射型（玻璃）。"""
    p = _principled(brush)
    if not p:
        return False
    for i in p.inputs:
        if "Transmission" in i.name:
            try:
                return (not i.is_linked) and float(i.default_value) > 0.05
            except Exception:
                return False
    return False


def _brush_images(brush):
    """从笔刷材质里取 基色 / 粗糙度 / 法线 对应的图像。"""
    out = {}
    p = _principled(brush)
    if not p:
        return out
    bc = p.inputs.get("Base Color")
    if bc and bc.is_linked:
        im = _walk_image(bc)
        if im:
            out["albedo"] = im
    rg = p.inputs.get("Roughness")
    if rg and rg.is_linked:
        im = _walk_image(rg)
        if im:
            out["roughness"] = im
    for n in brush.node_tree.nodes:
        if n.bl_idname == "ShaderNodeNormalMap":
            im = _walk_image(n.inputs.get("Color"))
            if im:
                out["normal"] = im
                break
    return out


def _safe_name(s):
    bad = '\\/:*?"<>|'
    out = "".join("_" if c in bad else c for c in s)
    return out.strip()[:60] or "layer"


def export_dir(context):
    st = context.scene.mb_state
    if st.export_dir:
        d = bpy.path.abspath(st.export_dir)
    else:
        base = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else bpy.app.tempdir
        d = os.path.join(base, "MB_Export")
    os.makedirs(d, exist_ok=True)
    return d


def _new_bake_image(name, size):
    img = bpy.data.images.get(name)
    if img:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(name, width=size, height=size, alpha=False, float_buffer=False)
    return img


def bake_channel(context, ob, mat, kind, size, path):
    """用 Cycles 把某个通道烘到图片。kind: DIFFUSE / ROUGHNESS / NORMAL"""
    sc = context.scene
    prev_engine = sc.render.engine
    img = _new_bake_image("MB_BAKE_" + kind, size)
    node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = img
    node.select = True
    mat.node_tree.nodes.active = node
    try:
        sc.render.engine = "CYCLES"
        try:
            sc.cycles.samples = 8
        except Exception:
            pass
        if kind == "DIFFUSE":
            sc.render.bake.use_pass_direct = False
            sc.render.bake.use_pass_indirect = False
            sc.render.bake.use_pass_color = True
        sc.render.bake.margin = 8
        bpy.ops.object.bake(type=kind)
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
        return True
    finally:
        try:
            mat.node_tree.nodes.remove(node)
        except Exception:
            pass
        sc.render.engine = prev_engine
        try:
            bpy.data.images.remove(img)
        except Exception:
            pass


def build_baked_material(src_mat, bc_path, rough_path, normal_path):
    m = bpy.data.materials.new(src_mat.name + "_BAKED")
    m["mb_baked"] = True
    made_images = []
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.bl_idname != "ShaderNodeOutputMaterial":
            nt.nodes.remove(n)
    out = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(p.outputs["BSDF"], out.inputs["Surface"])
    p.inputs["Metallic"].default_value = 0.0

    def load(path, name, non_color=False):
        im = bpy.data.images.load(path, check_existing=True)
        im.name = name
        if non_color:
            im.colorspace_settings.name = "Non-Color"
        made_images.append(im)
        return im

    bc = nt.nodes.new("ShaderNodeTexImage")
    bc.image = load(bc_path, src_mat.name + "_BC")
    nt.links.new(bc.outputs["Color"], p.inputs["Base Color"])

    rg = nt.nodes.new("ShaderNodeTexImage")
    rg.image = load(rough_path, src_mat.name + "_ROUGH", True)
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(rg.outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Green"], p.inputs["Roughness"])

    nm = nt.nodes.new("ShaderNodeTexImage")
    nm.image = load(normal_path, src_mat.name + "_NRM", True)
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(nm.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], p.inputs["Normal"])
    return m, made_images


class MB_OT_open_export_dir(bpy.types.Operator):
    bl_idname = "mb.open_export_dir"
    bl_label = "打开输出目录"
    bl_description = "在系统文件管理器里打开导出目录"
    bl_options = {"REGISTER"}

    def execute(self, context):
        d = export_dir(context)
        try:
            bpy.ops.wm.path_open(filepath=d)
        except Exception as e:
            self.report({"ERROR"}, "无法打开：%s" % e)
            return {"CANCELLED"}
        return {"FINISHED"}


class MB_OT_export_all(bpy.types.Operator):
    bl_idname = "mb.export_all"
    bl_label = "一键导出整场景"
    bl_description = "把场景里的模型全部烘焙成标准 PBR 并导出 glTF/FBX，贴图随文件走，引擎侧不用写代码"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return any(o.type == "MESH" for o in context.scene.objects)

    def execute(self, context):
        st = context.scene.mb_state
        size = int(st.bake_size)
        fmt = st.export_format

        scn = context.scene
        objs = [o for o in context.selected_objects if o.type == "MESH"]
        scope = "selected"
        if not objs:
            objs = [o for o in scn.objects if o.type == "MESH"]
            scope = "scene"
        if not objs:
            self.report({"ERROR"}, t("err_nonmesh"))
            return {"CANCELLED"}

        root = os.path.join(export_dir(context), _safe_name(scn.name) + "_export")
        tex_dir = os.path.join(root, "textures")
        os.makedirs(tex_dir, exist_ok=True)

        restore = []
        baked_entries = []
        made_mats = []
        made_imgs = []

        # 清掉上次导出残留（只动带标记且没人用的）
        for m in list(bpy.data.materials):
            if m.get("mb_baked") and m.users == 0:
                try:
                    bpy.data.materials.remove(m)
                except Exception:
                    pass
        prev_sel = [o for o in context.selected_objects]
        prev_engine = scn.render.engine
        try:
            # 1) 逐个物体烘焙材质
            for ob in objs:
                mat = ob.active_material
                entry = {
                    "object": ob.name,
                    "material": mat.name if mat else None,
                    "baked": False,
                    "textures": {},
                }
                if mat and layers_of(mat) and ob.data.uv_layers:
                    stem = _safe_name(ob.name)

                    # 透射层（玻璃）不参与烘焙，否则会烘成黑块污染基色
                    holder = layers_of(mat)
                    trans_layers = []
                    hidden_ones = []
                    for L in holder.layers:
                        bm_ = bpy.data.materials.get(L.mat_name)
                        if bm_ and _is_transmissive(bm_):
                            trans_layers.append(L)
                            if L.visible:
                                L.visible = False
                                hidden_ones.append(L)
                    bc = os.path.join(tex_dir, stem + "_basecolor.png")
                    rg = os.path.join(tex_dir, stem + "_roughness.png")
                    nm = os.path.join(tex_dir, stem + "_normal.png")
                    for o in context.view_layer.objects:
                        try:
                            o.select_set(False)
                        except Exception:
                            pass
                    ob.select_set(True)
                    context.view_layer.objects.active = ob

                    if not bake_channel(context, ob, mat, "DIFFUSE", size, bc):
                        raise RuntimeError("%s 基色烘焙失败" % ob.name)
                    bake_channel(context, ob, mat, "ROUGHNESS", size, rg)
                    bake_channel(context, ob, mat, "NORMAL", size, nm)

                    baked, made = build_baked_material(mat, bc, rg, nm)
                    made_mats.append(baked)
                    made_imgs.extend(made)
                    idx = ob.active_material_index
                    restore.append((ob, idx, mat))
                    ob.material_slots[idx].material = baked
                    entry["baked"] = True
                    entry["textures"] = {
                        "basecolor": os.path.relpath(bc, root),
                        "roughness": os.path.relpath(rg, root),
                        "normal": os.path.relpath(nm, root),
                    }

                    # 恢复透射层可见性，并把它们的遮罩单独导出
                    for L in hidden_ones:
                        L.visible = True

                    if trans_layers:
                        tdir = os.path.join(root, "transparent")
                        os.makedirs(tdir, exist_ok=True)
                        tfiles = []
                        for k, L in enumerate(trans_layers):
                            im = bpy.data.images.get(L.image_name)
                            fn = "%s_trans_%02d_%s.png" % (stem, k, _safe_name(L.name))
                            if im and _copy_image(im, os.path.join(tdir, fn)):
                                tfiles.append(fn)
                        entry["transparent_layers"] = [
                            {"name": L.name, "material": L.mat_name, "mask": tfiles[k] if k < len(tfiles) else None}
                            for k, L in enumerate(trans_layers)
                        ]
                baked_entries.append(entry)

            # 2) 全选后一次性导出，保持相对位置
            for o in context.view_layer.objects:
                try:
                    o.select_set(False)
                except Exception:
                    pass
            for ob in objs:
                try:
                    ob.select_set(True)
                except Exception:
                    pass
            context.view_layer.objects.active = objs[0]

            files = []
            base_name = _safe_name(scn.name)
            if fmt in ("GLB", "BOTH"):
                p = os.path.join(root, base_name + ".glb")
                bpy.ops.export_scene.gltf(filepath=p, export_format="GLB", use_selection=True)
                files.append(os.path.basename(p))
            if fmt in ("FBX", "BOTH"):
                p = os.path.join(root, base_name + ".fbx")
                bpy.ops.export_scene.fbx(
                    filepath=p, use_selection=True,
                    path_mode="COPY", embed_textures=True,
                    mesh_smooth_type="FACE", apply_scale_options="FBX_SCALE_ALL",
                )
                files.append(os.path.basename(p))

            # 3) 机器可读清单
            manifest = {
                "scene": scn.name,
                "format": fmt,
                "files": files,
                "scope": scope,
                "bake_size": size,
                "objects": baked_entries,
                "engine_ready": True,
                "notes": [
                    "A 方案产物：模型 + 标准 PBR 贴图，直接拖进引擎即可，无需写 shader",
                    "Godot 用 .glb（原生支持）；Unity / UE 可用 .fbx（贴图已内嵌）",
                    "金属度固定 0；玻璃等透射层已被排除在烘焙外",
                    "透明层（玻璃）不参与烘焙，遮罩见 transparent/，引擎里配透明材质使用",
                    "如需在引擎里实时调平铺/换材质，用『导出遮罩』走 shader 路线",
                ],
            }
            with open(os.path.join(root, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

            readme = [
                "Material Brush 导出包（引擎可用）",
                "================================",
                "场景：%s    物体数：%d    烘焙尺寸：%d" % (scn.name, len(objs), size),
                "文件：%s" % ", ".join(files),
                "",
                "用法：",
                "  1. 直接把 %s 拖进引擎" % files[0],
                "  2. 材质已烘焙成标准 PBR（基色/粗糙度/法线），不需要写 shader",
                "  3. textures/ 里的贴图已随文件引用，FBX 内嵌、glTF 外部引用",
                "",
                "Godot → 用 .glb；Unity / UE → 用 .fbx",
                "",
                "已知限制：金属度 0；透射材质（玻璃）烘焙后为黑；逐层法线不参与烘焙。",
            ]
            with open(os.path.join(root, "README.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(readme))

            if st.auto_open_dir and not bpy.app.background:
                try:
                    bpy.ops.wm.path_open(filepath=root)
                except Exception:
                    pass
            self.report({"INFO"}, t("ok_objs") % (len(objs), root))
            return {"FINISHED"}

        except Exception as e:
            traceback.print_exc()
            self.report({"ERROR"}, t("err_export") + str(e))
            return {"CANCELLED"}
        finally:
            for ob, idx, mat in restore:
                try:
                    ob.material_slots[idx].material = mat
                except Exception:
                    pass
            # 回收烘焙用的临时材质与贴图，避免越导越多
            for m in made_mats:
                try:
                    bpy.data.materials.remove(m)
                except Exception:
                    pass
            for im in made_imgs:
                try:
                    if im.users == 0:
                        bpy.data.images.remove(im)
                except Exception:
                    pass
            scn.render.engine = prev_engine
            for o in context.selected_objects:
                try:
                    o.select_set(False)
                except Exception:
                    pass
            for o in prev_sel:
                try:
                    o.select_set(True)
                except Exception:
                    pass


class MB_OT_export_masks(bpy.types.Operator):
    bl_idname = "mb.export_masks"
    bl_label = "导出遮罩"
    bl_description = "把每层遮罩存成 PNG，并写一份图层清单 JSON（给 Godot 里混材质用）"
    bl_options = {"REGISTER"}

    def execute(self, context):
        mat = context.active_object.active_material
        lst = layers_of(mat)
        if lst is None or not len(lst.layers):
            self.report({"ERROR"}, t("err_nolayer"))
            return {"CANCELLED"}
        d = export_dir(context)
        files = []
        for i, L in enumerate(lst.layers):
            img = bpy.data.images.get(L.image_name)
            if not img:
                continue
            path = os.path.join(d, "mask_%02d_%s.png" % (i, _safe_name(L.name)))
            img.filepath_raw = path
            img.file_format = "PNG"
            img.save()
            files.append(os.path.basename(path))
        manifest = {
            "object": context.active_object.name,
            "material": mat.name,
            "uv": context.active_object.data.uv_layers.active.name if context.active_object.data.uv_layers else None,
            "layers": [
                {
                    "index": i,
                    "name": L.name,
                    "source_material": L.mat_name,
                    "opacity": round(L.opacity, 4),
                    "size": round(L.size, 4),
                    "visible": L.visible,
                    "mask": files[i] if i < len(files) else None,
                }
                for i, L in enumerate(lst.layers)
            ],
            "note": "index 0 = 最上层；Godot 里 color = mix(下层, 上层, mask * opacity)",
        }
        with open(os.path.join(d, "material_brush_layers.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        self.report({"INFO"}, t("ok_masks") % (len(files), d))
        return {"FINISHED"}


class MB_OT_bake_export(bpy.types.Operator):
    bl_idname = "mb.bake_export"
    bl_label = "烘焙并导出 GLB"
    bl_description = "烘焙基色/粗糙度/法线，生成可直接给 Godot 的 GLB"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return bool(ob and ob.type == "MESH" and ob.data.uv_layers and ob.active_material)

    def execute(self, context):
        ob = context.active_object
        mat = ob.active_material
        if layers_of(mat) is None:
            self.report({"ERROR"}, t("err_notbrush"))
            return {"CANCELLED"}
        st = context.scene.mb_state
        size = int(st.bake_size)
        d = export_dir(context)
        base = _safe_name(mat.name)
        bc = os.path.join(d, base + "_BaseColor.png")
        rg = os.path.join(d, base + "_Roughness.png")
        nm = os.path.join(d, base + "_Normal.png")

        prev_sel = [o for o in context.selected_objects]
        try:
            for o in context.view_layer.objects:
                try:
                    o.select_set(False)
                except Exception:
                    pass
            ob.select_set(True)
            context.view_layer.objects.active = ob
            if not bake_channel(context, ob, mat, "DIFFUSE", size, bc):
                raise RuntimeError("基色烘焙失败")
            bake_channel(context, ob, mat, "ROUGHNESS", size, rg)
            bake_channel(context, ob, mat, "NORMAL", size, nm)

            baked = build_baked_material(mat, bc, rg, nm)
            slot_idx = ob.active_material_index
            prev_mat = mat
            ob.material_slots[slot_idx].material = baked
            glb = os.path.join(d, base + ".glb")
            bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True)
            ob.material_slots[slot_idx].material = prev_mat
            self.report({"INFO"}, "已导出 %s" % glb)
            return {"FINISHED"}
        except Exception as e:
            traceback.print_exc()
            self.report({"ERROR"}, t("err_export") + str(e))
            return {"CANCELLED"}
        finally:
            for o in context.selected_objects:
                o.select_set(False)
            for o in prev_sel:
                try:
                    o.select_set(True)
                except Exception:
                    pass


# ---------------------------------------------------------------- UI

class MB_PT_panel(bpy.types.Panel):
    bl_label = "材质笔刷"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "材质笔刷"

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return bool(ob and ob.type == "MESH" and ob.active_material)

    def draw(self, context):
        try:
            self._draw(context)
        except Exception as e:
            self.layout.label(text="面板错误：" + str(e)[:80], icon="ERROR")

    def _draw(self, context):
        layout = self.layout
        st = context.scene.mb_state
        mat = context.active_object.active_material
        lst = layers_of(mat)

        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop_search(st, "brush_mat", bpy.data, "materials", text="", icon="BRUSH_DATA")
        row.operator("mb.use_active", text="", icon="EYEDROPPER")

        row = col.row(align=True)
        row.prop(st, "resolution", text="")
        row.prop(st, "lang", text="")

        row = col.row()
        row.scale_y = 1.6
        row.operator("mb.add_layer", icon="BRUSH_DATA", text=t("add"))

        bm = st.brush_mat
        if bm:
            bp = None
            if bm.use_nodes and bm.node_tree:
                for n in bm.node_tree.nodes:
                    if n.bl_idname == "ShaderNodeBsdfPrincipled":
                        bp = n
                        break
            if bp:
                bc = bp.inputs.get("Base Color")
                bimg = _upstream_image(bc) if (bc and bc.is_linked) else None
                if bimg:
                    col.label(text=t("status_tex") + bimg.name, icon="IMAGE_DATA")
                elif bc and bc.is_linked:
                    col.label(text=t("status_proc"), icon="NODETREE")
                else:
                    col.label(text=t("status_flat"), icon="INFO")
                tr = [i for i in bp.inputs if "Transmission" in i.name]
                if tr and float(tr[0].default_value) > 0.05:
                    col.label(text=t("status_trans"), icon="ERROR")

        layout.separator()
        box = layout.box()
        head = box.row()
        head.label(text=t("layers"))
        head.operator("mb.toggle_mask", text="", icon="IMAGE_ALPHA", depress=st.show_mask)
        head.operator("mb.clear_layers", text="", icon="TRASH")
        head.operator("mb.rebuild", text="", icon="FILE_REFRESH")

        if lst is None:
            box.label(text=t("hint_none"), icon="INFO")
            return
        if not len(lst.layers):
            box.label(text=t("hint_empty"), icon="INFO")
            return

        for i, layer in enumerate(lst.layers):
            is_active = (i == lst.active_index)
            r = box.row(align=True)
            r.alert = is_active
            r.prop(layer, "visible", text="",
                   icon="HIDE_OFF" if layer.visible else "HIDE_ON", emboss=False)
            op = r.operator("mb.select_layer",
                            text=("▶ " if is_active else "") + layer.name, emboss=True)
            op.index = i
            r.prop(layer, "opacity", text="", slider=True)
            up = r.operator("mb.move_layer", text="", icon="TRIA_UP")
            up.index, up.direction = i, -1
            dn = r.operator("mb.move_layer", text="", icon="TRIA_DOWN")
            dn.index, dn.direction = i, 1
            rm = r.operator("mb.remove_layer", text="", icon="X")
            rm.index = i

            if is_active:
                rs = box.row(align=True)
                rs.prop(layer, "size", text=t("size"), slider=True)
                rr = box.row()
                rr.scale_y = 1.4
                rr.operator("mb.paint", icon="PLAY", text=t("paint"))




class MB_PT_export(bpy.types.Panel):
    bl_label = "导出到游戏引擎"
    bl_parent_id = "MB_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return bool(ob and ob.type == "MESH" and ob.active_material)

    def draw(self, context):
        layout = self.layout
        st = context.scene.mb_state

        tips = layout.column(align=True)
        tips.scale_y = 0.85
        tips.label(text=t("tips1"))
        tips.label(text=t("tips2"))
        tips.label(text=t("tips3"))

        layout.separator(factor=0.5)
        row = layout.row(align=True)
        row.prop(st, "export_format", text="")
        row.prop(st, "bake_size", text="")

        big = layout.row()
        big.scale_y = 1.6
        big.operator("mb.export_all", text=t("export_all"), icon="PACKAGE")
        layout.prop(st, "auto_open_dir", text=t("open_after"))

        layout.separator(factor=0.5)
        layout.label(text=t("adv"))
        layout.operator("mb.export_masks", text=t("masks"), icon="IMAGE_DATA")

        layout.separator(factor=0.5)
        row = layout.row(align=True)
        row.prop(st, "export_dir", text="")
        row.operator("mb.open_export_dir", text="", icon="FILE_FOLDER")
        if st.export_dir:
            layout.label(text=t("dir_to") + bpy.path.abspath(st.export_dir), icon="FILE_FOLDER")
        else:
            layout.label(text=t("dir_empty"), icon="INFO")


# ---------------------------------------------------------------- register

classes = (
    MB_Layer,
    MB_LayerList,
    MB_State,
    MB_OT_add_layer,
    MB_OT_remove_layer,
    MB_OT_move_layer,
    MB_OT_select_layer,
    MB_OT_paint,
    MB_OT_clear,
    MB_OT_toggle_mask,
    MB_OT_rebuild,
    MB_OT_use_active,
    MB_OT_export_all,
    MB_OT_export_masks,
    MB_OT_bake_export,
    MB_OT_open_export_dir,
    MB_PT_panel,
    MB_PT_export,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.mb_state = bpy.props.PointerProperty(type=MB_State)
    bpy.types.Material.mb_layers = bpy.props.PointerProperty(type=MB_LayerList)


def unregister():
    del bpy.types.Material.mb_layers
    del bpy.types.Scene.mb_state
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
