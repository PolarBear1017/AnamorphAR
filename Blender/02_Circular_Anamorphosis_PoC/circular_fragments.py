"""Blender: perspective-correct circular anamorphosis. Run in Scripting.
Standalone geometry helpers also run under regular Python for validation.
"""
import math
import random
from array import array
from pathlib import Path

SHARD_COUNT = 450
RADIUS = 4.0
CAMERA_DISTANCE = 18.0
CLOUD_CENTER_Z = -6.5  # Move the cloud away from the solution camera to widen it along the rays.
DEPTH_SCATTER = 6.5  # Maximum displacement from the cloud center along Z.
GAP = 0.008  # Fraction of each polygon, not world units.
FRONT_RELIEF = 0.9  # Peak height relative to the shard's back depth. Zero gives flat fronts.
REVEAL_BANDS = ((4.0, 13.0), (7.0, 19.0), (10.0, 26.0))  # Late, middle, early.
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
    if DEPTH_SCATTER < 0 or CLOUD_CENTER_Z + DEPTH_SCATTER >= CAMERA_DISTANCE - 1:
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
        # The outer rim uses less depth, softening the outline of the cloud from the side.
        x_ratio, y_ratio = cx / RADIUS, cy / RADIUS
        radial_sq = x_ratio*x_ratio + y_ratio*y_ratio
        depth_taper = math.sqrt(1 - 0.46*radial_sq)
        drift = 0.10 * math.sin(3.4*x_ratio + 2.8*y_ratio) * (1 - radial_sq)
        depth_offset = 0.90 * depth_taper * rng.uniform(-1, 1) + drift
        z = CLOUD_CENTER_Z + DEPTH_SCATTER * depth_offset
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

def add_relief(outline, rim_start, z, height, profile, rng, vertices, uv_points):
    """Add an inner ring and center inside the rim's projected polygon."""
    n = len(outline)
    if height == 0:
        return [tuple(range(rim_start, rim_start + n))]

    cx = sum(x for x, _ in outline) / n
    cy = sum(y for _, y in outline) / n
    angle = rng.uniform(0, math.tau)
    direction_x, direction_y = math.cos(angle), math.sin(angle)
    extent = max(math.hypot(x - cx, y - cy) for x, y in outline)
    ring_start = len(vertices)
    for x, y in outline:
        along = ((x-cx)*direction_x + (y-cy)*direction_y) / extent
        if profile == 'ridge':
            weight = 0.23 + 0.72 * (1 - abs(along))**2
        elif profile == 'double':
            weight = 0.23 + 0.77 * abs(along)**0.6
        else:
            weight = rng.uniform(0.60, 0.93)
        inset = rng.uniform(0.36, 0.52)
        px, py = x + (cx-x)*inset, y + (cy-y)*inset
        pz = z + height * weight
        scale = (CAMERA_DISTANCE - pz) / CAMERA_DISTANCE
        vertices.append((px*scale, py*scale, pz))
        uv_points.append((px, py))

    center = len(vertices)
    pz = z + height * (0.36 if profile == 'double' else 1.0)
    scale = (CAMERA_DISTANCE - pz) / CAMERA_DISTANCE
    vertices.append((cx*scale, cy*scale, pz))
    uv_points.append((cx, cy))
    faces = []
    for j in range(n):
        nxt = (j + 1) % n
        faces.extend((
            (rim_start + j, rim_start + nxt, ring_start + nxt),
            (rim_start + j, ring_start + nxt, ring_start + j),
            (ring_start + j, ring_start + nxt, center),
        ))
    return faces


def shard_mesh(poly, front, back, rng):
    n = len(poly)
    vertices = front + back
    back_z = back[0][2]
    back_scale = (CAMERA_DISTANCE - back_z) / CAMERA_DISTANCE
    back_outline = [(x / back_scale, y / back_scale) for x, y, _ in back]
    uv_points = poly + back_outline
    front_z = front[0][2]
    thickness = front_z - back_z
    profiles = ('blunt', 'double', 'ridge')
    front_faces = add_relief(poly, 0, front_z, FRONT_RELIEF * thickness * rng.uniform(0.50, 1.0),
                             rng.choice(profiles), rng, vertices, uv_points)
    back_faces = add_relief(back_outline, n, back_z, -FRONT_RELIEF * thickness * rng.uniform(0, 0.95),
                            rng.choice(profiles), rng, vertices, uv_points)
    side_faces = [(j, n+j, n+(j+1)%n, (j+1)%n) for j in range(n)]
    return vertices, uv_points, [face[::-1] for face in back_faces] + side_faces, front_faces


def decoy_uvs(poly, uv_points, rng):
    cx = sum(x for x, _ in poly) / len(poly)
    cy = sum(y for _, y in poly) / len(poly)
    original_u = 0.5 + cx / (2 * RADIUS)
    original_v = 0.5 + cy / (2 * RADIUS)
    # Keep the sampled patches within the opaque disk of the source image.
    while True:
        radius = 0.34 * math.sqrt(rng.random())
        angle = rng.uniform(0, math.tau)
        u = 0.5 + radius * math.cos(angle)
        v = 0.5 + radius * math.sin(angle)
        if math.hypot(u - original_u, v - original_v) >= 0.22:
            break

    extent = max(math.hypot(x - cx, y - cy) for x, y in poly)
    crop_extent = rng.uniform(0.035, 0.085)
    scale = crop_extent / extent
    angle = rng.uniform(0, math.tau)
    cos_angle, sin_angle = math.cos(angle), math.sin(angle)
    patch = [
        (u + scale * ((x-cx)*cos_angle - (y-cy)*sin_angle),
         v + scale * ((x-cx)*sin_angle + (y-cy)*cos_angle))
        for x, y in uv_points
    ]
    return (u, v), crop_extent, patch


def side_uvs(vertices, face, center, extent, angle):
    # Flatten each side in its own plane, so steep shards retain the texture's proportions.
    from mathutils import Vector

    points = [Vector(vertices[i]) for i in face]
    origin = sum(points, Vector((0, 0, 0))) / len(points)
    across = (points[-1] - points[0]).normalized()
    down = (points[1] - points[0]).cross(across).cross(across).normalized()
    u, v = center
    cos_angle, sin_angle = math.cos(angle), math.sin(angle)
    offsets = [(across.dot(point - origin), down.dot(point - origin)) for point in points]
    scale = extent / max(math.hypot(x, y) for x, y in offsets)
    return [(u + scale*(x*cos_angle-y*sin_angle), v + scale*(x*sin_angle+y*cos_angle))
            for x, y in offsets]


def reveal_groups(data, image):
    """Prioritize detail-rich shards, such as coastlines and cloud edges."""
    width, height = image.size
    pixels = array('f', [0]) * len(image.pixels)
    image.pixels.foreach_get(pixels)
    channels = len(pixels) // (width * height)
    scores = []
    for index, (poly, _, _) in enumerate(data):
        samples = []
        cx = sum(x for x, _ in poly) / len(poly)
        cy = sum(y for _, y in poly) / len(poly)
        for x, y in [*poly, (cx, cy)]:
            u = 0.5 + x/(2*RADIUS)
            v = 0.5 + y/(2*RADIUS)
            row, column = min(height-1, int(v*height)), min(width-1, int(u*width))
            pixel = (row*width+column)*channels
            if channels < 4 or pixels[pixel+3] > 0.95:
                r, g, b = pixels[pixel:pixel+3]
                samples.append(0.2126*r + 0.7152*g + 0.0722*b)
        contrast = max(samples) - min(samples) if samples else 0
        scores.append((contrast, index))

    groups = [0.0] * len(scores)
    for rank, (_, index) in enumerate(sorted(scores)):
        groups[index] = min(2, 3*rank // len(scores)) / 2
    return groups


def add_image_texture(nodes, links, image, uv_name):
    uv = nodes.new('ShaderNodeUVMap')
    uv.uv_map = uv_name
    texture = nodes.new('ShaderNodeTexImage')
    texture.image = image
    links.new(uv.outputs['UV'], texture.inputs['Vector'])
    return texture

def add_decoy_blend(nodes, links, alpha, stagger=False):
    geometry = nodes.new('ShaderNodeNewGeometry')
    view = nodes.new('ShaderNodeVectorTransform')
    view.vector_type = 'VECTOR'
    view.convert_from = 'WORLD'
    view.convert_to = 'OBJECT'
    links.new(geometry.outputs['Incoming'], view.inputs['Vector'])
    direction = nodes.new('ShaderNodeVectorMath')
    direction.operation = 'NORMALIZE'
    links.new(view.outputs['Vector'], direction.inputs[0])

    # Mesh positions use the solution camera coordinates, with the cloud pivot handled by parenting.
    coords = nodes.new('ShaderNodeTexCoord')
    solution_ray = nodes.new('ShaderNodeVectorMath')
    solution_ray.operation = 'SUBTRACT'
    solution_ray.inputs[0].default_value = (0, 0, CAMERA_DISTANCE)
    links.new(coords.outputs['Object'], solution_ray.inputs[1])
    solution_direction = nodes.new('ShaderNodeVectorMath')
    solution_direction.operation = 'NORMALIZE'
    links.new(solution_ray.outputs['Vector'], solution_direction.inputs[0])
    alignment = nodes.new('ShaderNodeVectorMath')
    alignment.operation = 'DOT_PRODUCT'
    links.new(solution_direction.outputs['Vector'], alignment.inputs[0])
    links.new(direction.outputs['Vector'], alignment.inputs[1])

    blend = nodes.new('ShaderNodeMapRange')
    blend.interpolation_type = 'SMOOTHERSTEP'
    if stagger:
        info = nodes.new('ShaderNodeObjectInfo')
        tier = nodes.new('ShaderNodeSeparateColor')
        links.new(info.outputs['Color'], tier.inputs['Color'])
        for index, socket in ((1, 'From Min'), (0, 'From Max')):
            limit = nodes.new('ShaderNodeFloatCurve')
            curve = limit.mapping.curves[0]
            for point, band in zip(curve.points, (REVEAL_BANDS[0], REVEAL_BANDS[-1])):
                point.location.y = math.cos(math.radians(band[index]))
            curve.points.new(0.5, math.cos(math.radians(REVEAL_BANDS[1][index])))
            limit.mapping.update()
            links.new(tier.outputs['Red'], limit.inputs['Value'])
            links.new(limit.outputs['Value'], blend.inputs[socket])
    else:
        blend.inputs['From Min'].default_value = math.cos(math.radians(26))
        blend.inputs['From Max'].default_value = math.cos(math.radians(4))
    blend.inputs['To Min'].default_value = 0.92
    blend.inputs['To Max'].default_value = 0.0
    links.new(alignment.outputs['Value'], blend.inputs['Value'])
    mask = nodes.new('ShaderNodeMath')
    mask.operation = 'MULTIPLY'
    links.new(blend.outputs['Result'], mask.inputs[0])
    links.new(alpha, mask.inputs[1])
    return mask.outputs[0], blend.outputs['Result']


def matte_surface(nodes, links, color):
    shader = nodes.new('ShaderNodeBsdfPrincipled')
    shader.inputs['Roughness'].default_value = 0.9
    shader.inputs['Specular IOR Level'].default_value = 0.12
    shader.inputs['Emission Strength'].default_value = 0.55
    links.new(color, shader.inputs['Base Color'])
    links.new(color, shader.inputs['Emission Color'])
    return shader.outputs['BSDF']

def build():
    import bpy
    if not 0 <= FRONT_RELIEF <= 1:
        raise ValueError('Front relief must be between 0 and 1')
    scene = bpy.context.scene
    base = Path(bpy.data.filepath).parent if bpy.data.filepath else Path(__file__).resolve().parent
    source = base/'resource'/'earth_apollo17.png'
    image = bpy.data.images.load(str(source), check_existing=True)
    image.pack()
    data = generate()
    groups = reveal_groups(data, image)
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
    root.location.z = CLOUD_CENTER_Z
    mat = bpy.data.materials.new('Fragment_Front_View_Decoy')
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    tex = add_image_texture(nodes, links, image, 'ImageUV')
    decoy_tex = add_image_texture(nodes, links, image, 'DecoyUV')
    blend, angle_weight = add_decoy_blend(nodes, links, decoy_tex.outputs['Alpha'], stagger=True)
    front_color = nodes.new('ShaderNodeMixRGB')
    links.new(blend, front_color.inputs[0])
    links.new(tex.outputs['Color'], front_color.inputs[1])
    links.new(decoy_tex.outputs['Color'], front_color.inputs[2])
    emission = nodes.new('ShaderNodeEmission')
    links.new(front_color.outputs['Color'], emission.inputs['Color'])
    matte = matte_surface(nodes, links, front_color.outputs['Color'])
    front_surface = nodes.new('ShaderNodeMixShader')
    links.new(angle_weight, front_surface.inputs[0])
    links.new(emission.outputs[0], front_surface.inputs[1])
    links.new(matte, front_surface.inputs[2])
    transparent = nodes.new('ShaderNodeBsdfTransparent')
    mix = nodes.new('ShaderNodeMixShader')
    links.new(tex.outputs['Alpha'], mix.inputs[0])
    links.new(transparent.outputs[0], mix.inputs[1])
    links.new(front_surface.outputs[0], mix.inputs[2])
    output = nodes.new('ShaderNodeOutputMaterial')
    links.new(mix.outputs[0], output.inputs['Surface'])
    if hasattr(mat, 'surface_render_method'):
        mat.surface_render_method = 'DITHERED'
    side = bpy.data.materials.new('Fragment_Sides_and_Back_Decoy')
    side.diffuse_color = (.04,.065,.09,1)
    side.use_nodes = True
    side_nodes, side_links = side.node_tree.nodes, side.node_tree.links
    side_nodes.clear()
    side_tex = add_image_texture(side_nodes, side_links, image, 'DecoyUV')
    side_blend, _ = add_decoy_blend(side_nodes, side_links, side_tex.outputs['Alpha'])
    # Fade the backing seen through the transparent rim at the solution angle.
    backing = side_nodes.new('ShaderNodeMixRGB')
    backing.inputs[1].default_value = side.diffuse_color
    side_links.new(side_blend, backing.inputs[0])
    side_links.new(side_tex.outputs['Color'], backing.inputs[2])
    side_matte = matte_surface(side_nodes, side_links, backing.outputs['Color'])
    side_output = side_nodes.new('ShaderNodeOutputMaterial')
    side_links.new(side_matte, side_output.inputs['Surface'])
    relief_rng = random.Random(RANDOM_SEED)
    decoy_rng = random.Random(RANDOM_SEED + 1)
    side_rng = random.Random(RANDOM_SEED + 2)
    for i, (poly, front, back) in enumerate(data):
        vertices, uv_points, side_faces, front_faces = shard_mesh(poly, front, back, relief_rng)
        center, extent, patch = decoy_uvs(poly, uv_points, decoy_rng)
        mesh = bpy.data.meshes.new(f'CircularShardMesh_{i:04}')
        mesh.from_pydata(vertices, [], front_faces + side_faces)
        mesh.materials.append(mat)
        mesh.materials.append(side)
        mesh.update()
        mesh.uv_layers.new(name='ImageUV')
        decoy_uv = mesh.uv_layers.new(name='DecoyUV', do_init=False)
        uv = mesh.uv_layers['ImageUV']
        mesh.uv_layers.active = uv
        for face in mesh.polygons:
            is_front = face.index < len(front_faces)
            face.material_index = 0 if is_front else 1
            if face.index >= len(mesh.polygons) - len(poly):
                texture_uvs = side_uvs(vertices, face.vertices, center, extent, side_rng.uniform(0, math.tau))
            else:
                texture_uvs = [patch[index] for index in face.vertices]
            for loop_index, vertex_index, (u, v) in zip(face.loop_indices, face.vertices, texture_uvs):
                x, y = uv_points[vertex_index]
                uv.data[loop_index].uv = (.5+x/(2*RADIUS), .5+y/(2*RADIUS))
                decoy_uv.data[loop_index].uv = (u, v)
        obj = bpy.data.objects.new(f'CircularShard_{i:04}', mesh)
        collection.objects.link(obj)
        obj.parent = root
        obj.location.z = -CLOUD_CENTER_Z
        obj.color = (groups[i], 0, 0, 1)
    cam_data = bpy.data.cameras.new('AlignmentCamera')
    cam = bpy.data.objects.new('AlignmentCamera', cam_data)
    collection.objects.link(cam)
    cam_data.type = 'PERSP'
    cam_data.lens = 45
    cam_data.sensor_width = 36
    cam_data.clip_end = 200
    scene.camera = cam
    # Orbit around the cloud and return to the original solution camera position.
    orbit_center = root.location.copy()
    orbit_distance = CAMERA_DISTANCE - CLOUD_CENTER_Z
    for frame, degrees in ((1,0),(45,48),(90,-52),(130,28),(160,0)):
        a = math.radians(degrees)
        cam.location = (orbit_distance*math.sin(a), 0, CLOUD_CENTER_Z + orbit_distance*math.cos(a))
        offset = cam.location - orbit_center
        cam.rotation_euler = (-offset).to_track_quat('-Z','Y').to_euler()
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
