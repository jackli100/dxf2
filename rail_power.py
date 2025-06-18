#!/usr/bin/env python
# -*- coding: utf-8 -*-
# rail_power_dynamic.py — 计算铁路-电力交叉的里程和右侧夹角（支持“电力”前缀图层）
# 1) 从所有以“电力”开头的图层提取电力折线
# 2) 对铁路折线和电力折线做“加密”处理，确保点位稠密
# 3) 计算交点处公里里程并排序，右侧夹角以度°分′（分精确到整数）表示
# 4) 在表格中只输出 Mileage_m、Angle、Remark 三列

import ezdxf, math, pandas as pd
from pathlib import Path
from ezdxf.math import Vec2, intersect_polylines_2d

# ---------- 配置区 --------------------------------------------------
RAIL_LAYERS = {
    'dl1': 56700,
    'dl2': 74900,
    'dl3': 100000,
    'dl4': 125000,
    'dl5': 156000,
    'dl6': 163300,
}
DXF_FILE    = r'break.dxf'    # <- 修改为你的 DXF 文件完整路径
MAX_SEG_LEN = 5.0            # 加密阈值：若相邻点间距 > 此值(m)，插值
TOLERANCE   = 1e-6           # 几何容差

# ---------- 工具函数 ------------------------------------------------
def poly2d(entity):
    """把 LWPOLYLINE/POLYLINE 投影到 Vec2 列表。"""
    if entity.dxftype() not in ('LWPOLYLINE', 'POLYLINE'):
        raise TypeError(f'Unsupported entity type: {entity.dxftype()}')
    return [Vec2(pt[:2]) for pt in entity.get_points()]

def densify(points, max_len=MAX_SEG_LEN):
    """对点列进行加密：将每段 > max_len 分割为等距小段。"""
    dense = []
    for i in range(len(points)-1):
        a, b = points[i], points[i+1]
        dense.append(a)
        dist = a.distance(b)
        if dist > max_len:
            steps = int(dist // max_len)
            for k in range(1, steps):
                t = k / steps
                dense.append(a + (b - a) * t)
    dense.append(points[-1])
    return dense

def segment_direction(vecs, point):
    """返回交点 point 在线段序列 vecs 上的方向向量（单位向量）。"""
    for i in range(len(vecs)-1):
        a, b = vecs[i], vecs[i+1]
        cross = (a.x - point.x)*(b.y - point.y) - (a.y - point.y)*(b.x - point.x)
        if abs(cross) < TOLERANCE:
            ab = b - a
            proj = (point - a).dot(ab) / (ab.magnitude**2)
            if 0 <= proj <= 1 and ab.magnitude > TOLERANCE:
                return ab.normalize()
    # fallback：找最近顶点并取相邻线段方向
    idx = min(range(len(vecs)), key=lambda j: point.distance(vecs[j]))
    if idx < len(vecs)-1:
        v = vecs[idx+1] - vecs[idx]
    else:
        v = vecs[idx] - vecs[idx-1]
    return v.normalize() if v.magnitude > TOLERANCE else Vec2(1, 0)

def calc_cum_len(vecs):
    """计算各点到起点的累积长度列表。"""
    cum = [0.0]
    for i in range(len(vecs)-1):
        cum.append(cum[-1] + vecs[i].distance(vecs[i+1]))
    return cum

def calc_mileage(vecs, cum, point, offset):
    """
    计算交点 point 在线段序列 vecs 上对应的里程值（累积长度 + offset）。
    返回 None 或 具体里程（float）。
    """
    best_len, best_dist = None, float('inf')
    for i in range(len(vecs)-1):
        a, b = vecs[i], vecs[i+1]
        ab = b - a
        if ab.magnitude < TOLERANCE:
            continue
        proj = (point - a).dot(ab) / (ab.magnitude**2)
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
    return None if best_len is None else best_len + offset

def angle_right(t_rail: Vec2, t_pwr: Vec2):
    """
    计算“右侧夹角”：以铁路方向向量 t_rail 为参考，
    将电力方向 t_pwr 相对于它的右侧夹角输出为“度°分′”格式，
    其中“分”四舍五入到整数。如出现 60' 则进位到下一度。
    """
    det = t_rail.x * t_pwr.y - t_rail.y * t_pwr.x
    dot = t_rail.x * t_pwr.x + t_rail.y * t_pwr.y
    theta = math.degrees(-math.atan2(det, dot))
    ang = abs(theta) if theta >= 0 else 180 - abs(theta)
    deg = int(ang)
    mins = int(round((ang - deg) * 60))
    if mins == 60:
        deg += 1
        mins = 0
    return f"{deg}°{mins}'"

# ---------- 主流程 --------------------------------------------------
def compute(dxf_path: Path):
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    # 动态获取所有以“电力”开头的图层名称
    all_layers = [layer.dxf.name for layer in doc.layers]
    pwr_layer_names = [name for name in all_layers if name.startswith("电力")]

    if not pwr_layer_names:
        print("未发现任何以“电力”开头的图层，终止计算。")
        return

    # 从各电力图层提取折线并加密，同时提取 remark
    pwr_polys = []
    for pl_name in pwr_layer_names:
        ents1 = list(msp.query(f'LWPOLYLINE[layer=="{pl_name}"]'))
        ents2 = list(msp.query(f'POLYLINE[layer=="{pl_name}"]'))
        for ent in (ents1 + ents2):
            pts = densify(poly2d(ent))
            parts = pl_name.split('--')
            remark = '--'.join(parts[1:-1]) if len(parts) >= 3 else ''
            pwr_polys.append((pts, remark))

    rows = []

    # 遍历每段铁路图层
    for layer, offset in RAIL_LAYERS.items():
        rails = list(msp.query(f'LWPOLYLINE[layer=="{layer}"]')) + \
                list(msp.query(f'POLYLINE[layer=="{layer}"]'))
        if not rails:
            print(f"Warning: layer {layer} 未找到，跳过。")
            continue
        for rail_ent in rails:
            rail_pts = densify(poly2d(rail_ent))
            cum_len = calc_cum_len(rail_pts)
            for pwr_pts, remark_text in pwr_polys:
                intersections = intersect_polylines_2d(rail_pts, pwr_pts)
                for ip in intersections:
                    t_rail = segment_direction(rail_pts, ip)
                    t_pwr  = segment_direction(pwr_pts, ip)
                    angle_str = angle_right(t_rail, t_pwr)
                    mileage  = calc_mileage(rail_pts, cum_len, ip, offset)

                    rows.append({
                        'Mileage_m': round(mileage, 3) if mileage is not None else None,
                        'Angle': angle_str,
                        'Remark': remark_text
                    })

    # 按里程升序排序，None 里程放到末尾
    rows.sort(key=lambda x: x['Mileage_m'] if x['Mileage_m'] is not None else float('inf'))

    # 转成 DataFrame 并写入 Excel，仅包含 三 列：Mileage_m, Angle, Remark
    df = pd.DataFrame(rows, columns=['Mileage_m', 'Angle', 'Remark'])
    output = dxf_path.with_suffix('.rail_power_dynamic.xlsx')
    df.to_excel(output, index=False)
    print(f"[OK] 结果已保存 → {output.name}")

if __name__ == '__main__':
    path = Path(DXF_FILE)
    if not path.exists():
        print('DXF 文件未找到：', path)
    else:
        compute(path)
