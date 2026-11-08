"""Blender: perspective-correct circular anamorphosis. Run in Scripting.
Standalone geometry helpers also run under regular Python for validation.
"""
import math
import random
from pathlib import Path

SHARD_COUNT = 450
RADIUS = 4.0
CAMERA_DISTANCE = 18.0
DEPTH_SCATTER = 6.0
GAP = 0.008  # Fraction of each polygon, not world units.
RANDOM_SEED = 10
CIRCLE_SEGMENTS = 256

def clip(poly, nx, ny, limit):
    result = []
    if not poly:
        return result
    a = poly[-1]
    da = a[0]*nx + a[1]*ny - limit
    for b in poly:
        db = b[0]*nx + b[1]*ny - limit
        if (da <= 0) != (db <= 0):
            t = da / (da-db)
            result.append((a[0]+t*(b[0]-a[0]), a[1]+t*(b[1]-a[1])))
        if db <= 0:
            result.append(b)
        a, da = b, db
    return result

def generate():
    if SHARD_COUNT < 1 or RADIUS <= 0 or not 0 <= GAP < 1:
        raise ValueError('Invalid count, radius or gap')
    if not 0 <= DEPTH_SCATTER < CAMERA_DISTANCE - 1:
        raise ValueError('Depth must stay in front of camera')
    rng = random.Random(RANDOM_SEED)
    seeds = []
    for _ in range(SHARD_COUNT):
        r, angle = RADIUS*math.sqrt(rng.random()), rng.random()*math.tau
        seeds.append((r*math.cos(angle), r*math.sin(angle)))
    disk = [(RADIUS*math.cos(i*math.tau/CIRCLE_SEGMENTS), RADIUS*math.sin(i*math.tau/CIRCLE_SEGMENTS)) for i in range(CIRCLE_SEGMENTS)]
    result = []
    for i, (sx, sy) in enumerate(seeds):
        poly = disk[:]
        for j, (tx, ty) in enumerate(seeds):
            if i == j:
                continue
            poly = clip(poly, tx-sx, ty-sy, (tx*tx+ty*ty-sx*sx-sy*sy)/2)
            if not poly:
                break
        if len(poly) < 3:
            continue
        cx = sum(p[0] for p in poly)/len(poly)
        cy = sum(p[1] for p in poly)/len(poly)
        poly = [(cx+(x-cx)*(1-GAP), cy+(y-cy)*(1-GAP)) for x,y in poly]
        z = rng.uniform(-DEPTH_SCATTER, DEPTH_SCATTER)
        # Along rays from (0,0,D), keeping x/(D-z), y/(D-z) constant.
        scale = (CAMERA_DISTANCE-z)/CAMERA_DISTANCE
        front = [(x*scale,y*scale,z) for x,y in poly]
        # Back footprint shrinks in projected space; never hides neighbouring fronts.
        back_z = z-rng.uniform(.12,.65)
        back_scale = (CAMERA_DISTANCE-back_z)/CAMERA_DISTANCE
        inset = rng.uniform(.32,.72)
        back = [((cx+(x-cx)*inset)*back_scale, (cy+(y-cy)*inset)*back_scale, back_z) for x,y in poly]
        result.append((poly, front, back))
    return result

def build():
    import bpy
    from mathutils import Vector
    base = Path(bpy.data.filepath).parent if bpy.data.filepath else Path(__file__).resolve().parent
    source = base/'resource'/'earth_apollo17.png'
    image = bpy.data.images.load(str(source), check_existing=True)
    image.pack()
    data = generate()
    scene = bpy.context.scene
    # Keep existing collections intact; temporarily hide them for this demonstration.
    name = 'CircularAnamorphosis'
    old = bpy.data.collections.get(name)
    if old:
        for obj in list(old.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(old)
    for obj in scene.objects:
        obj.hide_render = True
        obj.hide_set(True)
    collection = bpy.data.collections.new(name)
    scene.collection.children.link(collection)
    root = bpy.data.objects.new('Illusion_Rotate_This', None)
    collection.objects.link(root)
    mat = bpy.data.materials.new('Earth_Front_Unlit')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = image
    emission = nodes.new('ShaderNodeEmission')
    links.new(tex.outputs['Color'], emission.inputs['Color'])
    transparent = nodes.new('ShaderNodeBsdfTransparent')
    mix = nodes.new('ShaderNodeMixShader')
    links.new(tex.outputs['Alpha'], mix.inputs[0])
    links.new(transparent.outputs[0], mix.inputs[1])
    links.new(emission.outputs[0], mix.inputs[2])
    output = nodes.new('ShaderNodeOutputMaterial')
    links.new(mix.outputs[0], output.inputs['Surface'])
    if hasattr(mat, 'surface_render_method'):
        mat.surface_render_method = 'DITHERED'
    side = bpy.data.materials.new('Fragment_Dark_Sides')
    side.diffuse_color = (.04,.065,.09,1)
    side.use_nodes = True
    side.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = side.diffuse_color
    for i, (poly, front, back) in enumerate(data):
        n = len(poly)
        faces = [tuple(range(n)), tuple(reversed(range(n,2*n)))]
        faces += [(j, n+j, n+(j+1)%n, (j+1)%n) for j in range(n)]
        mesh = bpy.data.meshes.new(f'CircularShardMesh_{i:04}')
        mesh.from_pydata(front+back, [], faces)
        mesh.materials.append(mat)
        mesh.materials.append(side)
        mesh.update()
        uv = mesh.uv_layers.new(name='ImageUV')
        for face in mesh.polygons:
            face.material_index = 0 if face.index == 0 else 1
            for loop_index in face.loop_indices:
                x,y = poly[mesh.loops[loop_index].vertex_index % n]
                uv.data[loop_index].uv = (.5+x/(2*RADIUS), .5+y/(2*RADIUS))
        obj = bpy.data.objects.new(f'CircularShard_{i:04}', mesh)
        collection.objects.link(obj)
        obj.parent = root
    cam_data = bpy.data.cameras.new('AlignmentCamera')
    cam = bpy.data.objects.new('AlignmentCamera', cam_data)
    collection.objects.link(cam)
    cam_data.type = 'PERSP'
    cam_data.lens = 45
    cam_data.sensor_width = 36
    cam_data.clip_end = 200
    scene.camera = cam
    # Animated orbit maintains fixed distance. Frame 1 / 160 are the solution.
    for frame, degrees in ((1,0),(45,48),(90,-52),(130,28),(160,0)):
        a = math.radians(degrees)
        cam.location = (CAMERA_DISTANCE*math.sin(a), 0, CAMERA_DISTANCE*math.cos(a))
        cam.rotation_euler = (-cam.location).to_track_quat('-Z','Y').to_euler()
        cam.keyframe_insert(data_path='location', frame=frame)
        cam.keyframe_insert(data_path='rotation_euler', frame=frame)
    light_data = bpy.data.lights.new('Fragment_Area', 'AREA')
    light_data.energy = 1800
    light_data.shape = 'DISK'
    light_data.size = 10
    light = bpy.data.objects.new('Fragment_Area', light_data)
    collection.objects.link(light)
    light.location = (3,5,12)
    light.rotation_euler = (-light.location).to_track_quat('-Z','Y').to_euler()
    scene.frame_start, scene.frame_end = 1,160
    scene.frame_set(1)
    scene.render.fps = 30
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 24
    scene.render.resolution_x = scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.view_settings.view_transform = 'Standard'
    scene.world.color = (.015,.015,.015)
    bpy.ops.object.select_all(action='DESELECT')
    root.select_set(True)
    bpy.context.view_layer.objects.active = root
    for area in (bpy.context.screen.areas if bpy.context.screen else []):
        if area.type == 'VIEW_3D':
            area.spaces.active.region_3d.view_perspective = 'CAMERA'
            area.spaces.active.shading.type = 'MATERIAL'
    print(f'Created {len(data)} irregular fragments. Frame 1: aligned; 45: scattered.')
    return base

if __name__ == '__main__':
    build()
