import bpy
import math
import random
from mathutils import Vector

# =========================
# 使用前請修改這裡
# =========================
# 圖片完整路徑；一定要改成你電腦上的實際圖片位置。
IMAGE_PATH = r"C:\專題\resource\OIP-removebg-preview.png"
# 碎片數量；調大會更細碎、生成和渲染時間也會增加。
SHARD_COUNT = 9
# 圖片在 Blender 中的寬度；調大會讓整體模型變大。
IMAGE_WIDTH = 8.0
# 平均拉伸厚度；調大會讓碎片更有立體感。
THICKNESS = 2.0
# 最小拉伸厚度；避免不規則變化造成局部變成零厚度。
MIN_THICKNESS = 0.5
# 厚度起伏幅度；調大會讓每個頂點的厚薄差更明顯。
THICKNESS_VARIATION = 5.0
# 後表面相對前表面的縮放比例；調小會更像斜切、收尖的碎片。
BACK_SCALE = 0.5
# 後表面縮放比例的變化幅度；調大會讓每個角落的收縮程度更不一致。
BACK_SCALE_VARIATION = 1.0
# 後表面頂點的水平偏移量；調大會讓側面更歪、更不規則。
BACK_WOBBLE = 0.5
# 每片碎片沿 Z 軸前後散開的距離；調大會增加漂浮錯落感。
DEPTH_SCATTER = 7.0
# 隨機種子；改成其他整數可產生另一組碎片形狀，固定時每次結果相同。
RANDOM_SEED = 1
# 碎片之間的縫隙；調大縫隙更明顯，建議只使用很小的數值。
GAP = 0.006
# 攝影機正交視野大小；調大可看到更大的範圍，調小可讓圖片佔滿畫面。
CAMERA_ORTHO_SCALE = 8.8

# =========================
# 基本設定
# =========================
random.seed(RANDOM_SEED)

if IMAGE_PATH == r"C:\path\to\your_image.png":
    raise RuntimeError("請先修改 IMAGE_PATH，填入你的圖片完整路徑。")

try:
    image = bpy.data.images.load(IMAGE_PATH, check_existing=True)
except Exception as exc:
    raise RuntimeError(f"無法載入圖片，請檢查 IMAGE_PATH：{IMAGE_PATH}\n{exc}")

if image is None or image.size[0] == 0 or image.size[1] == 0:
    raise RuntimeError("圖片載入失敗或圖片尺寸無效。")

# 清除舊生成物件，保留場景其他設定
collection_name = "IllusionShards"
old_collection = bpy.data.collections.get(collection_name)
if old_collection:
    for obj in list(old_collection.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(old_collection)

collection = bpy.data.collections.new(collection_name)
bpy.context.scene.collection.children.link(collection)

def link_object(obj):
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)
    collection.objects.link(obj)

# =========================
# 材質
# =========================
def make_front_material(img):
    mat = bpy.data.materials.new("Illusion_Image_Material")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new(type="ShaderNodeOutputMaterial")
    output.location = (500, 0)

    principled = nodes.new(type="ShaderNodeBsdfPrincipled")
    principled.location = (220, 0)
    principled.inputs["Roughness"].default_value = 0.75

    tex = nodes.new(type="ShaderNodeTexImage")
    tex.location = (-100, 0)
    tex.image = img

    links.new(tex.outputs["Color"], principled.inputs["Base Color"])
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    return mat

def make_side_material():
    mat = bpy.data.materials.new("Shard_Sides_Dark")
    mat.diffuse_color = (0.025, 0.03, 0.04, 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.025, 0.03, 0.04, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.85
    return mat

front_mat = make_front_material(image)
side_mat = make_side_material()

# =========================
# 2D Voronoi 細胞切割
# =========================
def clip_polygon(poly, a, b, c, eps=1e-9):
    """保留滿足 a*x + b*y <= c 的多邊形區域。"""
    if not poly:
        return []
    result = []
    for i in range(len(poly)):
        p = poly[i]
        q = poly[(i + 1) % len(poly)]
        fp = a * p[0] + b * p[1] - c
        fq = a * q[0] + b * q[1] - c
        pin = fp <= eps
        qin = fq <= eps

        if pin and qin:
            result.append(q)
        elif pin and not qin:
            denom = fp - fq
            if abs(denom) > eps:
                t = fp / denom
                result.append((p[0] + t * (q[0] - p[0]),
                               p[1] + t * (q[1] - p[1])))
        elif not pin and qin:
            denom = fp - fq
            if abs(denom) > eps:
                t = fp / denom
                result.append((p[0] + t * (q[0] - p[0]),
                               p[1] + t * (q[1] - p[1])))
            result.append(q)
    return result

aspect = image.size[1] / image.size[0]
width = IMAGE_WIDTH
height = width * aspect
xmin, xmax = -width / 2, width / 2
ymin, ymax = -height / 2, height / 2

# 稍微過量取樣，確保邊界附近也有足夠的碎片種子
seed_count = max(SHARD_COUNT, 8)
seeds = [
    (random.uniform(xmin, xmax), random.uniform(ymin, ymax))
    for _ in range(seed_count)
]

# 加入邊界附近種子，讓細胞分布比較均勻
cols = max(2, int(math.sqrt(seed_count / max(aspect, 0.2))))
rows = max(2, int(math.ceil(seed_count / cols)))
for j in range(rows):
    for i in range(cols):
        if len(seeds) >= seed_count:
            break
        x = xmin + (i + 0.5) * width / cols + random.uniform(-width / cols * 0.22, width / cols * 0.22)
        y = ymin + (j + 0.5) * height / rows + random.uniform(-height / rows * 0.22, height / rows * 0.22)
        seeds.append((max(xmin, min(xmax, x)), max(ymin, min(ymax, y))))

# 使用格點種子搭配抖動，避免完全隨機造成碎片尺寸差異過大
seeds = []
for j in range(rows):
    for i in range(cols):
        if len(seeds) >= SHARD_COUNT:
            break
        x = xmin + (i + 0.5) * width / cols
        y = ymin + (j + 0.5) * height / rows
        x += random.uniform(-width / cols * 0.30, width / cols * 0.30)
        y += random.uniform(-height / rows * 0.30, height / rows * 0.30)
        seeds.append((max(xmin, min(xmax, x)), max(ymin, min(ymax, y))))

# 將每個種子裁成 Voronoi cell
cells = []
for i, p in enumerate(seeds):
    poly = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]
    for j, q in enumerate(seeds):
        if i == j:
            continue
        # |x-p|^2 <= |x-q|^2 的線性形式
        a = 2.0 * (q[0] - p[0])
        b = 2.0 * (q[1] - p[1])
        c = q[0] * q[0] + q[1] * q[1] - p[0] * p[0] - p[1] * p[1]
        poly = clip_polygon(poly, a, b, c)
        if len(poly) < 3:
            break
    if len(poly) >= 3:
        # 往中心縮一點，形成細縫
        cx = sum(v[0] for v in poly) / len(poly)
        cy = sum(v[1] for v in poly) / len(poly)
        shrunk = []
        for x, y in poly:
            shrunk.append((cx + (x - cx) * (1.0 - GAP / max(width, height)),
                           cy + (y - cy) * (1.0 - GAP / max(width, height))))
        cells.append(shrunk)

# =========================
# 生成有厚度的碎片並套 UV
# =========================
created = []
for idx, poly in enumerate(cells):
    n = len(poly)
    if n < 3:
        continue

    # 以每片自己的深度平移，正面視角仍能看到完整的圖像區塊
    z_front = random.uniform(-DEPTH_SCATTER, DEPTH_SCATTER)

    # 後表面不再是平面：每個頂點使用不同厚度，製造不規則的切面。
    # 以碎片中心附近的低頻變化加上頂點抖動，避免形狀看起來像完全隨機的鋸齒。
    center_x = sum(x for x, _ in poly) / n
    center_y = sum(y for _, y in poly) / n
    local_scale = max(
        max(abs(x - center_x) + abs(y - center_y) for x, y in poly),
        1e-6,
    )
    thicknesses = []
    back_points = []
    for vertex_index, (x, y) in enumerate(poly):
        radial = math.hypot(x - center_x, y - center_y) / local_scale
        wave = math.sin(vertex_index * 1.7 + idx * 0.83) * 0.5 + 0.5
        jitter = random.uniform(-0.28, 0.28)
        thickness = THICKNESS + THICKNESS_VARIATION * (
            0.45 * (wave - 0.5) + 0.35 * (radial - 0.5) + 0.20 * jitter
        )
        thicknesses.append(max(MIN_THICKNESS, thickness))

        # 後輪廓向中心收縮並稍微偏移，讓拉伸側面呈斜面，而不是直立柱狀。
        back_scale = BACK_SCALE + BACK_SCALE_VARIATION * (wave - 0.5)
        back_x = center_x + (x - center_x) * back_scale
        back_y = center_y + (y - center_y) * back_scale
        back_x += random.uniform(-BACK_WOBBLE, BACK_WOBBLE)
        back_y += random.uniform(-BACK_WOBBLE, BACK_WOBBLE)
        back_points.append((back_x, back_y))

    verts = []
    # 前面頂點
    for x, y in poly:
        verts.append((x, y, z_front))
    # 後面頂點
    for (x, y), thickness in zip(back_points, thicknesses):
        verts.append((x, y, z_front - thickness))

    faces = []
    # 前面
    faces.append(tuple(range(n)))
    # 後面，反轉順序
    faces.append(tuple(range(2 * n - 1, n - 1, -1)))
    # 側面
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))

    mesh = bpy.data.meshes.new(f"ShardMesh_{idx:03d}")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(front_mat)
    mesh.materials.append(side_mat)
    mesh.update()

    obj = bpy.data.objects.new(f"Shard_{idx:03d}", mesh)
    collection.objects.link(obj)

    # 預設側面材質，前表面使用圖片材質
    for poly_face in mesh.polygons:
        poly_face.material_index = 1
    mesh.polygons[0].material_index = 0

    # 前面 UV：依照原圖座標投影，V 軸需由 Blender 圖片 UV 座標決定
    uv_layer = mesh.uv_layers.new(name="ImageUV")
    for poly_face in mesh.polygons:
        for loop_index in poly_face.loop_indices:
            vertex_index = mesh.loops[loop_index].vertex_index
            if vertex_index < n:
                x, y = poly[vertex_index]
            else:
                x, y = poly[vertex_index - n]
            u = (x - xmin) / width
            v = (y - ymin) / height
            uv_layer.data[loop_index].uv = (u, v)

    # 正面法線朝 +Z；加小幅倒角，讓厚度邊緣有高光
    bevel = obj.modifiers.new("Tiny_Edge_Bevel", "BEVEL")
    bevel.width = min(THICKNESS * 0.12, 0.015)
    bevel.segments = 1

    created.append(obj)

# =========================
# 攝影機與燈光
# =========================
scene = bpy.context.scene

# 建立/重設攝影機
cam_data = bpy.data.cameras.new("IllusionCamera")
cam = bpy.data.objects.new("IllusionCamera", cam_data)
collection.objects.link(cam)
cam.location = (0, 0, max(width, height) * 2.5)
cam.rotation_euler = (0, 0, 0)
cam.data.type = "ORTHO"
cam.data.ortho_scale = max(CAMERA_ORTHO_SCALE, width * 1.05)
scene.camera = cam

# 主燈
light_data = bpy.data.lights.new("IllusionKeyLight", type="AREA")
light = bpy.data.objects.new("IllusionKeyLight", light_data)
collection.objects.link(light)
light.location = (-width * 0.2, height * 0.35, max(width, height) * 1.5)
light.data.energy = 1800
light.data.shape = "DISK"
light.data.size = max(width, height) * 0.8

# 燈光朝向畫面中心
direction = Vector((0, 0, 0)) - light.location
light.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

# 世界背景
scene.world.color = (0.08, 0.08, 0.08)

# 渲染設定
scene.render.resolution_x = 1200
scene.render.resolution_y = max(1, int(1200 * aspect))
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.engine = "BLENDER_EEVEE"

# 選取生成的碎片
bpy.ops.object.select_all(action="DESELECT")
for obj in created:
    obj.select_set(True)
if created:
    bpy.context.view_layer.objects.active = created[0]

# 切到正面視角（如果目前有 3D View）
for area in bpy.context.screen.areas:
    if area.type == "VIEW_3D":
        area.spaces.active.region_3d.view_perspective = "ORTHO"
        area.spaces.active.region_3d.view_rotation = Vector((0, 0, 1)).to_track_quat("Z", "Y")
        area.spaces.active.region_3d.view_location = (0, 0, 0)
        area.spaces.active.region_3d.view_distance = max(width, height) * 1.8

print(f"完成：已建立 {len(created)} 個 3D 圖片碎片。")
print("請按 F12 渲染預覽。若要修改碎片數量、厚度或深度差，請調整檔案最上方參數。")
