"""Translate genuine Mathics 3D boxes into a finite, bounded mesh protocol.

Surface samples come from Mathics Plot3D. Tessellation of sphere/cylinder/cone
display primitives is derived geometry, not a replacement numerical evaluator.
Coordinates stay in data space; BoxRatios scaling is returned separately.
"""

import math

from mathics.core.expression import Expression
from mathics.core.list import ListExpression
from mathics.format.box.graphics3d import prepare_elements
from mathics.format.render.json import graphics_3D_elements

from errors import RequestError


MAX_VERTICES = 50_000
MAX_FACES = 30_000
MAX_LINES = 10_000
MAX_POINTS = 10_000
MAX_COORDINATES = 150_000


def normalize_primitives(expression):
    """Adapt the two-corner Cuboid syntax to pinned Mathics boxes.

    This only rebuilds the already evaluated display AST; it evaluates no
    coordinates or user code. Mathics 10.0.1 boxes accept Cuboid[{pmin,pmax}]
    but omit the equivalent three-dimensional Cuboid[pmin,pmax] rule.
    """
    elements = getattr(expression, "elements", ())
    if not elements:
        return expression
    normalized = tuple(normalize_primitives(element) for element in elements)
    if expression.get_head_name() == "System`Cuboid" and len(normalized) == 2:
        return Expression(expression.get_head(), ListExpression(*normalized))
    if any(first is not second for first, second in zip(elements, normalized)):
        return Expression(expression.get_head(), *normalized)
    return expression


def finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise RequestError("invalid_graphics3d", "3D geometry must contain finite real coordinates and sizes.")
    return float(value)


def coordinate(value):
    # Native Mathics Coords3D.pos() serializes as (position, offset).
    if isinstance(value, (list, tuple)) and len(value) == 2 and isinstance(value[0], (list, tuple)):
        if value[1] is not None:
            raise RequestError("unsupported_graphics3d", "3D screen-space Offset coordinates are unsupported.")
        value = value[0]
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise RequestError("invalid_graphics3d", "Each 3D coordinate must have three finite components.")
    return [finite_number(component) for component in value]


class Mesh:
    def __init__(self):
        self.vertices = []
        self.faces = []
        self.lines = []
        self.points = []
        self.colors = {"faces": [], "lines": [], "points": []}
        self.indices = {}
        self.coordinate_count = 0

    def _count(self, amount=1):
        self.coordinate_count += amount
        if self.coordinate_count > MAX_COORDINATES:
            raise RequestError("graphics3d_too_large", f"3D output exceeds {MAX_COORDINATES} coordinate references.")

    def vertex(self, point):
        self._count()
        point = coordinate(point)
        key = tuple(point)
        if key not in self.indices:
            if len(self.vertices) >= MAX_VERTICES:
                raise RequestError("graphics3d_too_large", f"3D output exceeds {MAX_VERTICES} vertices.")
            self.indices[key] = len(self.vertices)
            self.vertices.append(point)
        return self.indices[key]

    def face(self, points, color):
        if len(points) < 3:
            raise RequestError("invalid_graphics3d", "A polygon requires at least three vertices.")
        if len(self.faces) >= MAX_FACES:
            raise RequestError("graphics3d_too_large", f"3D output exceeds {MAX_FACES} faces.")
        self.faces.append([self.vertex(point) for point in points])
        self.colors["faces"].append(color)

    def line(self, points, color):
        if len(points) < 2:
            raise RequestError("invalid_graphics3d", "A line requires at least two vertices.")
        if len(self.lines) >= MAX_LINES:
            raise RequestError("graphics3d_too_large", f"3D output exceeds {MAX_LINES} lines.")
        self._count(len(points))
        self.lines.append(points)
        self.colors["lines"].append(color)

    def point(self, point, color):
        if len(self.points) >= MAX_POINTS:
            raise RequestError("graphics3d_too_large", f"3D output exceeds {MAX_POINTS} points.")
        self._count()
        self.points.append(point)
        self.colors["points"].append(color)

    def sphere(self, center, radius, color):
        latitude, longitude = 12, 24
        def point(i, j):
            phi, theta = math.pi * i / latitude, 2 * math.pi * j / longitude
            return [center[0] + radius * math.sin(phi) * math.cos(theta), center[1] + radius * math.sin(phi) * math.sin(theta), center[2] + radius * math.cos(phi)]
        for i in range(latitude):
            for j in range(longitude):
                if i == 0:
                    self.face([point(i, 0), point(i + 1, j), point(i + 1, j + 1)], color)
                elif i == latitude - 1:
                    self.face([point(i, j), point(i + 1, 0), point(i, j + 1)], color)
                else:
                    self.face([point(i, j), point(i + 1, j), point(i + 1, j + 1), point(i, j + 1)], color)

    def cuboid(self, first, last, color):
        x0, y0, z0 = first; x1, y1, z1 = last
        points = [[x0,y0,z0], [x1,y0,z0], [x1,y1,z0], [x0,y1,z0], [x0,y0,z1], [x1,y0,z1], [x1,y1,z1], [x0,y1,z1]]
        for indices in [[0,3,2,1], [4,5,6,7], [0,1,5,4], [1,2,6,5], [2,3,7,6], [3,0,4,7]]:
            self.face([points[index] for index in indices], color)

    def circular_solid(self, first, last, radius, color, cone=False):
        def cross(a, b):
            return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
        def normalize(vector):
            length = math.sqrt(sum(component*component for component in vector))
            if not length:
                raise RequestError("invalid_graphics3d", "Cylinder and Cone require distinct endpoints.")
            return [component/length for component in vector]
        axis = normalize([last[i]-first[i] for i in range(3)])
        first_basis = normalize(cross(axis, [1,0,0] if abs(axis[2]) > 0.9 else [0,0,1]))
        second_basis = cross(axis, first_basis)
        def ring(center):
            return [[center[i] + radius*(math.cos(2*math.pi*j/24)*first_basis[i] + math.sin(2*math.pi*j/24)*second_basis[i]) for i in range(3)] for j in range(24)]
        start = ring(first)
        end = ring(last) if not cone else None
        self.face(list(reversed(start)), color)
        if end:
            self.face(end, color)
        for j in range(24):
            following = (j + 1) % 24
            self.face([start[j], start[following], last] if cone else [start[j], start[following], end[following], end[j]], color)


def to_graphics3d(boxes, evaluation):
    try:
        elements, axes, _ticks, _styles, dimensions, boxscale = prepare_elements(boxes, boxes.content, {"evaluation": evaluation})
        if hasattr(elements, "background_color"):
            raise RequestError("unsupported_graphics3d", "Mathics could not decode one or more 3D primitives or directives.")
        native_elements = graphics_3D_elements(elements)
        limits = dimensions(final_pass=False)[:6]
    except RequestError:
        raise
    except Exception as exc:
        raise RequestError("unsupported_graphics3d", f"Mathics 3D conversion is unavailable for this expression: {exc}") from exc
    mesh = Mesh()
    for element in native_elements:
        points = [coordinate(point) for point in element["coords"]]
        color = element.get("color")
        if color is None:
            raise RequestError("unsupported_graphics3d", "Per-vertex 3D colors are unsupported by this mesh adapter.")
        color = [min(1, max(0, finite_number(component))) for component in color[:3]]
        if len(color) != 3:
            raise RequestError("invalid_graphics3d", "A 3D color requires three RGB components.")
        kind = element["type"]
        if kind == "polygon":
            mesh.face(points, color)
        elif kind == "line":
            mesh.line(points, color)
        elif kind == "point":
            for point in points:
                mesh.point(point, color)
        elif kind == "cuboid" and len(points) == 2:
            mesh.cuboid(*points, color)
        elif kind in {"sphere", "cylinder", "cone"}:
            radius = finite_number(element["radius"])
            if radius <= 0:
                raise RequestError("invalid_graphics3d", "Sphere, Cylinder and Cone require a positive finite radius.")
            if kind == "sphere":
                for point in points:
                    mesh.sphere(point, radius, color)
            elif len(points) == 2:
                mesh.circular_solid(*points, radius, color, cone=kind == "cone")
            else:
                raise RequestError("unsupported_graphics3d", "Cylinder and Cone require exactly two endpoints.")
        else:
            raise RequestError("unsupported_graphics3d", f"Unsupported 3D primitive: {kind}.")
    bounds = [[finite_number(limits[i]), finite_number(limits[i+1])] for i in (0,2,4)]
    return {
        "vertices": mesh.vertices, "faces": mesh.faces, "lines": mesh.lines, "points": mesh.points,
        "colors": mesh.colors, "bounds": bounds,
        "boxScale": [finite_number(component) for component in boxscale],
        "viewpoint": [finite_number(component) for component in boxes.viewpoint],
        "axes": list(axes), "coordinateSpace": "data", "source": "Mathics3 graphics boxes",
    }
