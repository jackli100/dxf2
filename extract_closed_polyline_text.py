#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Extract TEXT entities lying inside closed polylines on the demolition layer
and compute their mileage by perpendicular projection onto the railway.
The railway geometry is read from ``break.dxf`` and mileage offsets are the
same as in ``rail_power.py``.
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
DEMOLITION_LAYER = '房屋拆迁'  # layer that contains closed polylines and texts
OUTPUT_CSV = 'room_and_number_extracted.csv'
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

def point_in_polygon(pt, polygon):
    x, y = pt
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1 + TOLERANCE) + x1):
            inside = not inside
    return inside

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

def load_room(path: Path):
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    texts = [e for e in msp.query('TEXT') if e.dxf.layer == DEMOLITION_LAYER]
    polylines = []
    for e in msp.query('LWPOLYLINE POLYLINE'):
        if e.dxf.layer != DEMOLITION_LAYER:
            continue
        pts = [tuple(pt[:2]) for pt in e.get_points()]
        if len(pts) < 3:
            continue
        if not e.closed and pts[0] != pts[-1]:
            pts.append(pts[0])
        polylines.append(pts)
    return texts, polylines

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

    texts, polygons = load_room(room_path)
    rows = []
    for txt in texts:
        ins = txt.dxf.insert
        pt = Vec2(ins.x, ins.y)
        inside_poly = None
        for poly in polygons:
            if point_in_polygon(pt, poly):
                inside_poly = poly
                break
        if not inside_poly:
            continue
        best_mileage = None
        best_dist = float('inf')
        for pts, cum, offset in rail_data:
            mileage, dist = closest_mileage(pts, cum, pt, offset)
            if mileage is not None and dist < best_dist:
                best_mileage = mileage
                best_dist = dist
        if best_mileage is None:
            continue
        poly_str = ';'.join(f"{x:.3f},{y:.3f}" for x, y in inside_poly)
        rows.append({'text': txt.dxf.text, 'polyline': poly_str, 'mileage_m': round(best_mileage, 3)})

    if rows:
        with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['text', 'polyline', 'mileage_m'])
            writer.writeheader()
            writer.writerows(rows)
        print(f'[OK] Saved {len(rows)} records to {OUTPUT_CSV}')
    else:
        print('No matching text inside demolition polylines found.')

if __name__ == '__main__':
    main()
