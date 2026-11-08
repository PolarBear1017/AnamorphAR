import bpy
import math
import random
from pathlib import Path
from mathutils import Vector

# ============================================================
# 使用前請修改這裡
# ============================================================
# 圖片隨 Blender 專案資料夾移動，不依賴 Windows 絕對路徑。
BASE_DIR = Path(bpy.data.filepath).parent if bpy.data.filepath else Path(__file__).resolve().parent
IMAGE_PATH = str(BASE_DIR / "resource" / "OIP-removebg-preview.png")

SHARD_COUNT = 9
IMAGE_WIDTH = 8.0

# 以下保留原始版本的不規則延伸參數
THICKNESS = 2.0
MIN_THICKNESS = 0.5
THICKNESS_VARIATION = 5.0
BACK_SCALE = 0.5
BACK_SCALE_VARIATION = 1.0
BACK_WOBBLE = 0.5

# 碎片沿 Z 軸前後散開的距離
DEPTH_SCATTER = 7.0

# 碎片之間的縫隙
GAP = 0.006

# Alpha 判定門檻：
# 0.05 表示只要幾乎不透明就保留；
# 如果背景邊緣還有白邊，可提高到 0.15 或 0.25。
ALPHA_THRESHOLD = 0.05

# 水平切割取樣解析度，越高越貼合去背輪廓，但生成越慢。
# 建議 256～512。
GRID_WIDTH = 384

RANDOM_SEED = 10

# ============================================================
# 載入圖片
# ============================================================
random.seed(RANDOM_SEED)

try:
    image = bpy.data.images.load(IMAGE_PATH, check_existing=True)
except Exception as exc:
    raise RuntimeError(f"無法載入圖片，請檢查 IMAGE_PATH：{IMAGE_PATH}\n{exc}")

img_w, img_h = image.size
if img_w <= 0 or img_h <= 0:
    raise RuntimeError("圖片尺寸無效。")

aspect = img_h / img_w
width = IMAGE_WIDTH
height = width * aspect

xmin, xmax = -width / 2, width / 2
ymin, ymax = -height / 2, height / 2

# ============================================================
# 讀取圖片 Alpha 通道
# 去背圖片透明的地方不會建立任何幾何面。
# ============================================================
pixels = [0.0] * (img_w * img_h * 4)
image.pixels.foreach_get(pixels)

def get_alpha(u, v):
    """依照 UV 座標讀取圖片 Alpha，UV 範圍限制在 0～1。"""
    u = max(0.0, min(1.0, u))
    v = max(0.0, min(1.0, v))

    px = min(img_w - 1, max(0, int(u * (img_w - 1))))
    py = min(img_h - 1, max(0, int(v * (img_h - 1))))

    return pixels[(py * img_w + px) * 4 + 3]

def alpha_at_xy(x, y):
    u = (x - xmin) / width
    v = (y - ymin) / height
    return get_alpha(u, v)

# ============================================================
# 清除上一次生成的碎片
# ============================================================
collection_name = "IllusionShards"
old_collection = bpy.data.collections.get(collection_name)

if old_collection:
    for obj in list(old_collection.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(old_collection)

collection = bpy.data.collections.new(collection_name)
bpy.context.scene.collection.children.link(collection)

# ============================================================
# 材質
# ============================================================
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

# ============================================================
# 建立 Voronoi 種子點
# 每個取樣三角形會分配給最近的種子點，形成不同碎片。
# ============================================================
cols = max(2, int(math.sqrt(SHARD_COUNT / max(aspect, 0.2))))
rows = max(2, int(math.ceil(SHARD_COUNT / cols)))

seeds = []
for j in range(rows):
    for i in range(cols):
        if len(seeds) >= SHARD_COUNT:
            break

        x = xmin + (i + 0.5) * width / cols
        y = ymin + (j + 0.5) * height / rows

        x += random.uniform(-width / cols * 0.30, width / cols * 0.30)
        y += random.uniform(-height / rows * 0.30, height / rows * 0.30)

        seeds.append((
            max(xmin, min(xmax, x)),
            max(ymin, min(ymax, y))
        ))

# ============================================================
# 以網格三角形建立碎片，只保留不透明區域
#
# 這是本次修改的核心：
# 1. 將圖片區域切成細小三角形。
# 2. 取樣三角形的三個頂點及中心點 Alpha。
# 3. 只要取樣點落在透明背景，就不建立該三角形。
# 4. 保留的三角形依最近的 Voronoi 種子點分組。
#
# 因此透明背景不會被建立成 3D 碎片。
# ============================================================
grid_w = max(32, int(GRID_WIDTH))
grid_h = max(32, int(round(GRID_WIDTH * aspect)))

dx = width / grid_w
dy = height / grid_h

# 每個碎片分別保存頂點、面、UV，以及頂點索引快取。
shard_data = []
for _ in seeds:
    shard_data.append({
        "verts": [],
        "faces": [],
        "uvs": [],
        "vertex_map": {}
    })

def nearest_seed_index(x, y):
    best_index = 0
    best_distance = float("inf")

    for index, (sx, sy) in enumerate(seeds):
        distance = (x - sx) ** 2 + (y - sy) ** 2
        if distance < best_distance:
            best_distance = distance
            best_index = index

    return best_index

def add_vertex(data, x, y):
    """同一碎片內共用相同座標的頂點，避免每個三角形完全分離。"""
    key = (round(x, 7), round(y, 7))

    if key in data["vertex_map"]:
        return data["vertex_map"][key]

    index = len(data["verts"])
    data["verts"].append((x, y, 0.0))

    u = (x - xmin) / width
    v = (y - ymin) / height
    data["uvs"].append((u, v))

    data["vertex_map"][key] = index
    return index

def triangle_is_visible(points):
    """三個頂點和中心點都必須有足夠 Alpha，避免切到透明背景。"""
    samples = list(points)
    cx = sum(p[0] for p in points) / 3.0
    cy = sum(p[1] for p in points) / 3.0
    samples.append((cx, cy))

    for x, y in samples:
        if alpha_at_xy(x, y) <= ALPHA_THRESHOLD:
            return False

    return True

def add_triangle(points):
    cx = sum(p[0] for p in points) / 3.0
    cy = sum(p[1] for p in points) / 3.0

    if not triangle_is_visible(points):
        return

    shard_index = nearest_seed_index(cx, cy)
    data = shard_data[shard_index]

    # 只在碎片邊界稍微內縮，形成細縫。
    sx, sy = seeds[shard_index]
    shrink = GAP / max(width, height)

    adjusted = []
    for x, y in points:
        x = sx + (x - sx) * (1.0 - shrink)
        y = sy + (y - sy) * (1.0 - shrink)
        adjusted.append((x, y))

    face = tuple(add_vertex(data, x, y) for x, y in adjusted)

    if len(set(face)) == 3:
        data["faces"].append(face)

for gy in range(grid_h):
    y0 = ymin + gy * dy
    y1 = y0 + dy

    for gx in range(grid_w):
        x0 = xmin + gx * dx
        x1 = x0 + dx

        # 將每個網格方形切成兩個三角形。
        # 交錯對角線可減少固定方向造成的視覺痕跡。
        if (gx + gy) % 2 == 0:
            triangles = [
                [(x0, y0), (x1, y0), (x1, y1)],
                [(x0, y0), (x1, y1), (x0, y1)]
            ]
        else:
            triangles = [
                [(x0, y0), (x1, y0), (x0, y1)],
                [(x1, y0), (x1, y1), (x0, y1)]
            ]

        for tri in triangles:
            add_triangle(tri)

# ============================================================
# 建立 3D 碎片
# 保留原始版本的不規則後表面延伸方式：
# - 每個頂點有不同厚度
# - 後表面向碎片中心收縮
# - 後表面加入隨機水平偏移
# - 只有碎片外圍邊界建立側面，不會把每個三角形變成獨立柱體
# ============================================================
def convex_hull(points):
    """計算 2D 凸包，供後表面頂點限制在碎片外框內。"""
    pts = sorted(set((p[0], p[1]) for p in points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for point in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper = []
    for point in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    return lower[:-1] + upper[:-1]


def point_inside_convex_polygon(point, poly, eps=1e-8):
    if len(poly) < 3:
        return True
    signs = []
    for i, p in enumerate(poly):
        q = poly[(i + 1) % len(poly)]
        cross_value = (q[0] - p[0]) * (point[1] - p[1]) - (q[1] - p[1]) * (point[0] - p[0])
        if abs(cross_value) > eps:
            signs.append(cross_value > 0)
    return not signs or all(value == signs[0] for value in signs)


def keep_point_inside(point, center, poly):
    """若後表面頂點越過碎片凸包，沿中心線拉回。"""
    if point_inside_convex_polygon(point, poly):
        return point

    low, high = 0.0, 1.0
    for _ in range(32):
        middle = (low + high) * 0.5
        candidate = (
            center[0] + (point[0] - center[0]) * middle,
            center[1] + (point[1] - center[1]) * middle
        )
        if point_inside_convex_polygon(candidate, poly):
            low = middle
        else:
            high = middle

    safe_scale = max(0.0, low - 1e-6)
    return (
        center[0] + (point[0] - center[0]) * safe_scale,
        center[1] + (point[1] - center[1]) * safe_scale
    )


created = []
for idx, data in enumerate(shard_data):
    front_faces = data["faces"]
    front_points = data["verts"]
    n = len(front_points)

    if not front_faces or n < 3:
        continue

    center_x = sum(point[0] for point in front_points) / n
    center_y = sum(point[1] for point in front_points) / n
    local_scale = max(
        max(abs(x - center_x) + abs(y - center_y) for x, y, _ in front_points),
        1e-6
    )
    hull = convex_hull(front_points)

    z_front = random.uniform(-DEPTH_SCATTER, DEPTH_SCATTER)

    verts = []
    # 前表面頂點
    for x, y, _ in front_points:
        verts.append((x, y, z_front))

    # 後表面頂點：沿用原本的厚度變化、收縮與 wobble 規則
    back_points = []
    thicknesses = []

    for vertex_index, (x, y, _) in enumerate(front_points):
        radial = math.hypot(x - center_x, y - center_y) / local_scale
        wave = math.sin(vertex_index * 1.7 + idx * 0.83) * 0.5 + 0.5
        jitter = random.uniform(-0.28, 0.28)

        thickness = THICKNESS + THICKNESS_VARIATION * (
            0.45 * (wave - 0.5) + 0.35 * (radial - 0.5) + 0.20 * jitter
        )
        thicknesses.append(max(MIN_THICKNESS, thickness))

        back_scale = BACK_SCALE + BACK_SCALE_VARIATION * (wave - 0.5)
        back_x = center_x + (x - center_x) * back_scale
        back_y = center_y + (y - center_y) * back_scale
        back_x += random.uniform(-BACK_WOBBLE, BACK_WOBBLE)
        back_y += random.uniform(-BACK_WOBBLE, BACK_WOBBLE)
        back_x, back_y = keep_point_inside((back_x, back_y), (center_x, center_y), hull)
        back_points.append((back_x, back_y))

    for (back_x, back_y), thickness in zip(back_points, thicknesses):
        verts.append((back_x, back_y, z_front - thickness))

    faces = []
    face_materials = []

    # 前表面三角形
    for face in front_faces:
        faces.append(face)
        face_materials.append(0)

    # 後表面三角形，反轉繞序
    for face in front_faces:
        faces.append(tuple(n + vertex_index for vertex_index in reversed(face)))
        face_materials.append(1)

    # 統計邊出現次數，只替外圍邊界建立側面。
    # 內部三角形共用邊不建立側面，避免變成一根根柱體。
    edge_usage = {}
    for face in front_faces:
        for i in range(3):
            a = face[i]
            b = face[(i + 1) % 3]
            key = (min(a, b), max(a, b))
            if key not in edge_usage:
                edge_usage[key] = [0, a, b]
            edge_usage[key][0] += 1

    for count, a, b in edge_usage.values():
        if count == 1:
            faces.append((a, b, n + b, n + a))
            face_materials.append(1)

    mesh = bpy.data.meshes.new(f"ShardMesh_{idx:03d}")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(front_mat)
    mesh.materials.append(side_mat)
    mesh.update()

    obj = bpy.data.objects.new(f"Shard_{idx:03d}", mesh)
    collection.objects.link(obj)

    for polygon, material_index in zip(mesh.polygons, face_materials):
        polygon.material_index = material_index

    # 前後表面都使用原圖 UV，側面則使用預設 UV。
    uv_layer = mesh.uv_layers.new(name="ImageUV")
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            vertex_index = mesh.loops[loop_index].vertex_index
            if vertex_index < n:
                u, v = data["uvs"][vertex_index]
                uv_layer.data[loop_index].uv = (u, v)
            elif vertex_index < 2 * n:
                u, v = data["uvs"][vertex_index - n]
                uv_layer.data[loop_index].uv = (u, v)

    bevel = obj.modifiers.new("Tiny_Edge_Bevel", "BEVEL")
    bevel.width = min(THICKNESS * 0.12, 0.015)
    bevel.segments = 1

    created.append(obj)

# ============================================================
# 場景與渲染設定
# ============================================================
scene = bpy.context.scene

scene.render.resolution_x = 1200
scene.render.resolution_y = max(1, int(1200 * aspect))
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
engines = scene.render.bl_rna.properties["engine"].enum_items.keys()
scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"

# 選取生成的碎片
bpy.ops.object.select_all(action="DESELECT")

for obj in created:
    obj.select_set(True)

if created:
    bpy.context.view_layer.objects.active = created[0]

# 切到正面視角
for area in (bpy.context.screen.areas if bpy.context.screen else []):
    if area.type == "VIEW_3D":
        area.spaces.active.region_3d.view_perspective = "ORTHO"
        area.spaces.active.region_3d.view_rotation = Vector((0, 0, 1)).to_track_quat("Z", "Y")
        area.spaces.active.region_3d.view_location = (0, 0, 0)
        area.spaces.active.region_3d.view_distance = max(width, height) * 1.8

print(f"完成：已建立 {len(created)} 個 3D 碎片。")
print("透明背景不會建立幾何面，因此不會被切割或拉伸。")
print("若輪廓太粗糙，請提高 GRID_WIDTH；若背景邊緣殘留，請提高 ALPHA_THRESHOLD。")
