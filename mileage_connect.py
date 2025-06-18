#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Mileage Connect Tool
--------------------

Read a list of mileage values from a text file and draw a polyline from each
corresponding mileage position on the railway to a fixed coordinate.

依赖: ezdxf >= 0.18
"""

import re
from pathlib import Path
import ezdxf
from ezdxf.math import Vec2

# -------- 配置区 -----------------------------------------------------------

# 铁路图层及其里程起点偏置 (米)
RAIL_LAYERS = {
    'dl1': 56700,
    'dl2': 74900,
    'dl3': 100000,
    'dl4': 125000,
    'dl5': 156000,
    'dl6': 163300,
}

# DXF 文件路径
DXF_FILE = r'break.dxf'

# 里程文本文件路径 (每行一个里程值, 也允许以逗号分隔多值)
MILEAGE_FILE = r'mileage_list.txt'

# 固定目标坐标 (X, Y, Z)
TARGET_POINT = (553263.2769, 3430423.5097, 0.0)

# 输出连接线所在图层名称
CONNECT_LAYER = '连接线'

# 加密阈值 (若相邻点距离大于此值则插入中间点)
MAX_SEG_LEN = 5.0

# 几何容差
TOLERANCE = 1e-6

# ---------------------------------------------------------------------------


def poly2d(entity):
    """Project a LWPOLYLINE/POLYLINE entity to a list of Vec2."""
    if entity.dxftype() not in ('LWPOLYLINE', 'POLYLINE'):
        raise TypeError(f'Unsupported entity type: {entity.dxftype()}')
    return [Vec2(pt[:2]) for pt in entity.get_points()]


def densify(points, max_len=MAX_SEG_LEN):
    """Insert intermediate points so that no segment is longer than max_len."""
    dense = []
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        dense.append(a)
        dist = a.distance(b)
        if dist > max_len:
            steps = int(dist // max_len)
            for k in range(1, steps + 1):
                t = k / (steps + 1)
                dense.append(a + (b - a) * t)
    dense.append(points[-1])
    return dense


def calc_cum_len(vecs):
    cum = [0.0]
    for i in range(len(vecs) - 1):
        cum.append(cum[-1] + vecs[i].distance(vecs[i + 1]))
    return cum


def get_point_and_tangent(vecs, cum, target_len):
    if target_len <= 0:
        pt = vecs[0]
        t = vecs[1] - vecs[0] if len(vecs) >= 2 else Vec2(1, 0)
        return pt, t.normalize() if t.magnitude > TOLERANCE else Vec2(1, 0)
    if target_len >= cum[-1]:
        pt = vecs[-1]
        t = vecs[-1] - vecs[-2] if len(vecs) >= 2 else Vec2(1, 0)
        return pt, t.normalize() if t.magnitude > TOLERANCE else Vec2(1, 0)

    for i in range(len(cum) - 1):
        if cum[i] <= target_len <= cum[i + 1]:
            a, b = vecs[i], vecs[i + 1]
            seg_len = cum[i + 1] - cum[i]
            if seg_len < TOLERANCE:
                pt = a
                t = b - a
            else:
                ratio = (target_len - cum[i]) / seg_len
                pt = a + (b - a) * ratio
                t = b - a
            t_rail = t.normalize() if t.magnitude > TOLERANCE else Vec2(1, 0)
            return pt, t_rail
    return vecs[-1], Vec2(1, 0)


def read_mileages(file_path: Path):
    mileages = []
    with file_path.open('r', encoding='utf-8') as f:
        for line in f:
            tokens = re.split(r'[,\s]+', line.strip())
            for tok in tokens:
                if tok:
                    try:
                        mileages.append(float(tok))
                    except ValueError:
                        print(f'Skip invalid mileage: {tok}')
    return mileages


def main():
    dxf_path = Path(DXF_FILE)
    if not dxf_path.exists():
        print(f'DXF 文件未找到: {dxf_path}')
        return

    txt_path = Path(MILEAGE_FILE)
    if not txt_path.exists():
        print(f'里程文件未找到: {txt_path}')
        return

    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    if CONNECT_LAYER not in {layer.dxf.name for layer in doc.layers}:
        doc.layers.new(name=CONNECT_LAYER, dxfattribs={'color': 3})

    rail_data = {}
    for layer_name, offset in RAIL_LAYERS.items():
        ents = list(msp.query(f'LWPOLYLINE[layer=="{layer_name}"]')) + \
               list(msp.query(f'POLYLINE[layer=="{layer_name}"]'))
        if not ents:
            print(f"Warning: 图层 {layer_name} 未找到折线, 已跳过")
            continue
        rail_ent = ents[0]
        pts2d = poly2d(rail_ent)
        dense_pts = densify(pts2d)
        cum_len = calc_cum_len(dense_pts)
        rail_data[layer_name] = (dense_pts, cum_len, offset)

    mileages = read_mileages(txt_path)
    target3d = TARGET_POINT

    for M in mileages:
        placed = False
        for layer_name, (dense_pts, cum_len, offset) in rail_data.items():
            total_len = cum_len[-1]
            local_len = M - offset
            if local_len < -TOLERANCE or local_len > total_len + TOLERANCE:
                continue
            pt, _ = get_point_and_tangent(dense_pts, cum_len, local_len)
            msp.add_polyline3d([(pt.x, pt.y, 0.0), target3d],
                               dxfattribs={'layer': CONNECT_LAYER, 'color': 3})
            placed = True
            break
        if not placed:
            print(f"[警告] 里程 {M} 米不在任何铁路图层范围内, 已跳过")

    out_path = dxf_path.with_name(dxf_path.stem + '_connected.dxf')
    doc.saveas(out_path)
    print(f"[OK] 输出文件 → {out_path.name}")


if __name__ == '__main__':
    main()
