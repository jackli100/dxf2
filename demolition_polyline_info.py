#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Analyse demolition polylines.

For each closed polyline on the demolition layer of ``room_and_number.dxf``
the centroid is projected onto the railway from ``break.dxf`` to obtain its
mileage. The script also calculates the minimum distance from any vertex to the
railway and the polygon area. Results are written to ``demolition_polyline_info.csv``.
"""

from pathlib import Path
import csv
import ezdxf
from ezdxf.math import Vec2

# ------------------ configuration ------------------------------------------
RAIL_LAYERS = {
    'dl1': 56700,
    'dl2': 74900,
    'dl3': 100000,
    'dl4': 125000,
    'dl5': 156000,
    'dl6': 163300,
}

DXF_BREAK = 'break.dxf'
DXF_ROOM = 'room_and_number.dxf'
DEMOLITION_LAYER = '房屋拆迁'
OUTPUT_CSV = 'demolition_polyline_info.csv'
MAX_SEG_LEN = 5.0
TOLERANCE = 1e-6
# ---------------------------------------------------------------------------

def poly2d(entity):
    """Project LWPOLYLINE/POLYLINE entity to a list of Vec2."""
    if entity.dxftype() not in ('LWPOLYLINE', 'POLYLINE'):
        raise TypeError(f'Unsupported entity type: {entity.dxftype()}')
    return [Vec2(pt[:2]) for pt in entity.get_points()]

def densify(points, max_len=MAX_SEG_LEN):
    dense = []
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        dense.append(a)
        dist = a.distance(b)
        if dist > max_len:
            steps = int(dist // max_len)
            for k in range(1, steps):
                t = k / steps
                dense.append(a + (b - a) * t)
    dense.append(points[-1])
    return dense

def calc_cum_len(vecs):
    cum = [0.0]
    for i in range(len(vecs) - 1):
        cum.append(cum[-1] + vecs[i].distance(vecs[i + 1]))
    return cum

def closest_mileage(vecs, cum, point, offset):
    best_len, best_dist = None, float('inf')
    for i in range(len(vecs) - 1):
        a, b = vecs[i], vecs[i + 1]
        ab = b - a
        if ab.magnitude < TOLERANCE:
            continue
        proj = (point - a).dot(ab) / (ab.magnitude ** 2)
        if proj < 0:
            proj_pt = a
        elif proj > 1:
            proj_pt = b
        else:
            proj_pt = a + ab * proj
        dist = point.distance(proj_pt)
        if dist < best_dist:
            best_dist = dist
            best_len = cum[i] + (proj_pt - a).magnitude
    if best_len is None:
        return None, None
    return best_len + offset, best_dist

def distance_to_rail(point, rail_data):
    best = float('inf')
    for pts, cum, offset in rail_data:
        _, dist = closest_mileage(pts, cum, point, offset)
        if dist < best:
            best = dist
    return best

def polygon_area_centroid(pts):
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    area2 = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        cross = x0 * y1 - x1 * y0
        area2 += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(area2) < TOLERANCE:
        cx = sum(p[0] for p in pts[:-1]) / (len(pts) - 1)
        cy = sum(p[1] for p in pts[:-1]) / (len(pts) - 1)
        area = 0.0
    else:
        area = abs(area2) / 2.0
        cx /= (3.0 * area2)
        cy /= (3.0 * area2)
    return area, Vec2(cx, cy)

def load_rails(path: Path):
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    data = []
    for layer, offset in RAIL_LAYERS.items():
        ents = list(msp.query(f'LWPOLYLINE[layer=="{layer}"]')) + \
               list(msp.query(f'POLYLINE[layer=="{layer}"]'))
        if not ents:
            continue
        pts = densify(poly2d(ents[0]))
        cum = calc_cum_len(pts)
        data.append((pts, cum, offset))
    return data

def load_polylines(path: Path):
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    polys = []
    for e in msp.query('LWPOLYLINE POLYLINE'):
        if e.dxf.layer != DEMOLITION_LAYER:
            continue
        pts = [tuple(pt[:2]) for pt in e.get_points()]
        if len(pts) < 3:
            continue
        if not e.closed and pts[0] != pts[-1]:
            pts.append(pts[0])
        polys.append(pts)
    return polys

def main():
    break_path = Path(DXF_BREAK)
    room_path = Path(DXF_ROOM)
    if not break_path.exists() or not room_path.exists():
        print('DXF files not found.')
        return

    rail_data = load_rails(break_path)
    if not rail_data:
        print('No railway polylines found.')
        return

    polys = load_polylines(room_path)
    rows = []
    for poly in polys:
        area, centroid = polygon_area_centroid(poly)
        best_mileage = None
        best_dist = float('inf')
        for pts, cum, offset in rail_data:
            mileage, dist = closest_mileage(pts, cum, centroid, offset)
            if mileage is not None and dist < best_dist:
                best_mileage = mileage
                best_dist = dist
        min_vertex_dist = float('inf')
        for x, y in poly:
            pt = Vec2(x, y)
            dist = distance_to_rail(pt, rail_data)
            if dist < min_vertex_dist:
                min_vertex_dist = dist
        rows.append({
            'mileage_m': round(best_mileage, 3) if best_mileage is not None else None,
            'min_vertex_dist': round(min_vertex_dist, 3) if min_vertex_dist != float('inf') else None,
            'area': round(area, 3)
        })

    if rows:
        with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['mileage_m', 'min_vertex_dist', 'area'])
            writer.writeheader()
            writer.writerows(rows)
        print(f'[OK] Saved {len(rows)} records to {OUTPUT_CSV}')
    else:
        print('No demolition polylines found.')

if __name__ == '__main__':
    main()
