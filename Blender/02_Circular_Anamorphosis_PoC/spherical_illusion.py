"""Run in Blender. Orthographic image projection on depth-scattered sphere patches."""
import bpy
import math
import random
from pathlib import Path
from mathutils import Vector

BASE_DIR = Path(bpy.data.filepath).parent if bpy.data.filepath else Path(__file__).resolve().parent
IMAGE_PATH = BASE_DIR / 'resource' / 'OIP-removebg-preview.png'
RADIUS = 4.0
SHARD_COUNT = 9
DEPTH_SCATTER = 3.0
SHELL_THICKNESS = 0.06
SEGMENTS = 192
RINGS = 96
RANDOM_SEED = 10
# Centre square crop; transparent parts are filled to preserve the circular silhouette.
BACKGROUND = (0.035, 0.045, 0.065, 1.0)

if SHARD_COUNT < 1 or RADIUS <= 0:
    raise ValueError('SHARD_COUNT and RADIUS must be positive')
image = bpy.data.images.load(str(IMAGE_PATH), check_existing=True)
if min(image.size) <= 0:
    raise RuntimeError('Invalid source image')
rng = random.Random(RANDOM_SEED)
name = 'SphericalIllusion'
old = bpy.data.collections.get(name)
if old:
    for obj in list(old.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(old)
collection = bpy.data.collections.new(name)
bpy.context.scene.collection.children.link(collection)
# Uniformly distributed seeds over the projected disk.
seeds = []
for i in range(SHARD_COUNT):
    angle = i * math.pi * (3 - math.sqrt(5))
    radius = RADIUS * math.sqrt((i + .5) / SHARD_COUNT)
    seeds.append((radius * math.cos(angle), radius * math.sin(angle)))
offsets = [rng.uniform(-DEPTH_SCATTER, DEPTH_SCATTER) for _ in seeds]
mat = bpy.data.materials.new('Sphere_Projected_Image')
mat.use_nodes = True
nodes = mat.node_tree.nodes
nodes.clear()
links = mat.node_tree.links
tex = nodes.new('ShaderNodeTexImage')
tex.image = image
mix = nodes.new('ShaderNodeMixRGB')
mix.inputs[1].default_value = BACKGROUND
links.new(tex.outputs['Alpha'], mix.inputs[0])
links.new(tex.outputs['Color'], mix.inputs[2])
emission = nodes.new('ShaderNodeEmission')
links.new(mix.outputs[0], emission.inputs['Color'])
out = nodes.new('ShaderNodeOutputMaterial')
links.new(emission.outputs[0], out.inputs['Surface'])
side = bpy.data.materials.new('Sphere_Interior')
side.diffuse_color = BACKGROUND
# Shared poles and latitude vertices avoid degenerate pole triangles.
verts = [(0, 0, RADIUS)]
for j in range(1, RINGS):
    theta = math.pi * j / RINGS
    for i in range(SEGMENTS):
        phi = math.tau * i / SEGMENTS
        verts.append((RADIUS * math.sin(theta) * math.cos(phi), RADIUS * math.sin(theta) * math.sin(phi), RADIUS * math.cos(theta)))
south = len(verts)
verts.append((0, 0, -RADIUS))
def ring(j, i):
    return 1 + (j - 1) * SEGMENTS + i % SEGMENTS
faces = []
for i in range(SEGMENTS):
    faces.append((0, ring(1, i), ring(1, i + 1)))
    for j in range(1, RINGS - 1):
        faces.append((ring(j, i), ring(j + 1, i), ring(j + 1, i + 1), ring(j, i + 1)))
    faces.append((ring(RINGS - 1, i), south, ring(RINGS - 1, i + 1)))
groups = [[] for _ in seeds]
for face in faces:
    x, y = (sum(verts[v][axis] for v in face) / len(face) for axis in (0, 1))
    owner = min(range(len(seeds)), key=lambda k: (x-seeds[k][0])**2 + (y-seeds[k][1])**2)
    groups[owner].append(face)
created = []
for k, group in enumerate(groups):
    indices = sorted({v for face in group for v in face})
    remap = {v: i for i, v in enumerate(indices)}
    mesh = bpy.data.meshes.new(f'SphereShardMesh_{k:03}')
    mesh.from_pydata([verts[v] for v in indices], [], [tuple(remap[v] for v in f) for f in group])
    mesh.materials.append(mat)
    mesh.materials.append(side)
    mesh.update()
    uv = mesh.uv_layers.new(name='ProjectedImage')
    crop = min(image.size)
    for loop in mesh.loops:
        x, y, _ = mesh.vertices[loop.vertex_index].co
        uv.data[loop.index].uv = (.5 + x / (2*RADIUS) * crop/image.size[0], .5 + y / (2*RADIUS) * crop/image.size[1])
    obj = bpy.data.objects.new(f'SphereShard_{k:03}', mesh)
    collection.objects.link(obj)
    obj.location.z = offsets[k]
    obj['assembled_z'] = 0.0
    for poly in mesh.polygons:
        poly.use_smooth = True
    solid = obj.modifiers.new('Shell thickness', 'SOLIDIFY')
    solid.thickness = SHELL_THICKNESS
    solid.offset = -1
    solid.material_offset = 1
    solid.material_offset_rim = 1
    created.append(obj)
cam_data = bpy.data.cameras.new('Sphere_Alignment_Camera')
cam = bpy.data.objects.new('Sphere_Alignment_Camera', cam_data)
collection.objects.link(cam)
cam.location = (0, 0, 4 * RADIUS + DEPTH_SCATTER)
cam.rotation_euler = (0, 0, 0)
cam_data.type = 'ORTHO'
cam_data.ortho_scale = RADIUS * 2.15
scene = bpy.context.scene
scene.camera = cam
scene.render.resolution_x = scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.view_settings.view_transform = 'Standard'
# Hide previous PoC geometry in this new scene only.
for obj in scene.objects:
    if obj not in list(collection.objects):
        obj.hide_render = True
        obj.hide_set(True)
bpy.ops.object.select_all(action='DESELECT')
for obj in created:
    obj.select_set(True)
bpy.context.view_layer.objects.active = created[0]
image.pack()
print(f'Created {len(created)} spherical shards; camera looks along -Z.')
