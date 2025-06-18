#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
rail_power_draw.py — 根据“里程-角度”表格，在 DXF 中对应铁路中心线上
绘制一定长度的标注折线（以表格中角度为右侧夹角）。

使用前请安装依赖：
  pip install ezdxf pandas
"""

import math
import re
import ezdxf
import pandas as pd
from pathlib import Path
from ezdxf.math import Vec2

# ---------- 配置区 --------------------------------------------------

# 1. 定义铁路图层及其起始里程偏置（单位：米）。
RAIL_LAYERS = {
    'dl1': 56700,
    'dl2': 74900,
    'dl3': 100000,
    'dl4': 125000,
    'dl5': 156000,
    'dl6': 163300,
}

# 2. 要处理的 DXF 文件路径（修改为你自己的文件路径）
DXF_FILE      = r'break.dxf'

# 3. 输入“里程-角度”表格路径，支持 .xlsx、.xls 或 .csv
#    表格第一列必须是里程（浮点数，单位米），第二列必须是角度（格式如 "12°30'"、"45°0'"）。
TABLE_FILE    = r'mileage_angle.xlsx'

# 4. 标注线段长度（米）
ANNOT_LENGTH  = 1000

# 5. 绘制标注的目标图层名称（如果不存在会自动创建）
ANNOT_LAYER   = '标注'

# 6. 加密阈值：如果相邻两个铁路顶点距离大于此值（米），则插入中间点
MAX_SEG_LEN   = 5.0

# 7. 几何容差
TOLERANCE     = 1e-6

# ------------------------------------------------------------------


def poly2d(entity):
    """把 LWPOLYLINE 或 POLYLINE 投影为 Vec2 列表。"""
    if entity.dxftype() not in ('LWPOLYLINE', 'POLYLINE'):
        raise TypeError(f'Unsupported entity type: {entity.dxftype()}')
    return [Vec2(pt[:2]) for pt in entity.get_points()]


def densify(points, max_len=MAX_SEG_LEN):
    """
    对一段折线的点坐标列表做“加密”，
    如果相邻点距离 > max_len，就在中间插入等间距的新点。
    """
    dense = []
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        dense.append(a)
        dist = a.distance(b)
        if dist > max_len:
            # 插入 int(dist//max_len) - 1 个等距点
            steps = int(dist // max_len)
            for k in range(1, steps + 1):
                t = k / (steps + 1)
                dense.append(a + (b - a) * t)
    dense.append(points[-1])
    return dense


def calc_cum_len(vecs):
    """
    对于密集点列表 vecs，计算从第 0 个点开始到每个点的累积长度。
    返回一个与 vecs 等长的数组 cum，其中 cum[i] = 从 vecs[0] 到 vecs[i] 的距离。
    """
    cum = [0.0]
    for i in range(len(vecs) - 1):
        cum.append(cum[-1] + vecs[i].distance(vecs[i + 1]))
    return cum


def get_point_and_tangent(vecs, cum, target_len):
    """
    在点列表 vecs（已 densify 过）上，找到累积长度 closest to target_len 处的坐标和切线方向。
    - cum: 对应 vecs 的累积长度数组
    - target_len: 目标长度
    返回 (pt, t_rail)，其中 pt 是 Vec2 坐标，t_rail 是切线单位向量。
    """
    # 如果 target_len 超过最后一点，则固定在终点
    if target_len <= 0:
        pt = vecs[0]
        # 切线取第二段
        t = vecs[1] - vecs[0] if len(vecs) >= 2 else Vec2(1, 0)
        return pt, t.normalize() if t.magnitude > TOLERANCE else Vec2(1, 0)

    if target_len >= cum[-1]:
        pt = vecs[-1]
        t = vecs[-1] - vecs[-2] if len(vecs) >= 2 else Vec2(1, 0)
        return pt, t.normalize() if t.magnitude > TOLERANCE else Vec2(1, 0)

    # 否则在两段之间插值
    for i in range(len(cum) - 1):
        if cum[i] <= target_len <= cum[i + 1]:
            a, b = vecs[i], vecs[i + 1]
            seg_len = cum[i + 1] - cum[i]
            if seg_len < TOLERANCE:
                # 退化到顶点处
                pt = a
                t = b - a
            else:
                ratio = (target_len - cum[i]) / seg_len
                pt = a + (b - a) * ratio
                t = b - a
            t_rail = t.normalize() if t.magnitude > TOLERANCE else Vec2(1, 0)
            return pt, t_rail

    # 实际不会走到这里
    return vecs[-1], Vec2(1, 0)


def parse_angle(angle_str: str) -> float:
    """
    将以下几种格式的字符串转换为浮点角度（单位：度）：
      1) "12°30'" → 12 度 30 分
      2) "6815"   → 68 度 15 分（当纯数字且长度为 3 或 4 位时，最后两位作为分）
      3) 纯数字如 "45" 或 "45.5" → 直接转换为 45.0 或 45.5

    返回值示例：
      "12°30'"  → 12.5
      "6815"    → 68.25
      "45"      → 45.0
      "45.5"    → 45.5
    """
    s = angle_str.strip()

    # 情况 A：形如 123°45'
    # 正确匹配形如 "12°30'" 的角度格式
    pattern1 = re.compile(r"^\s*(\d+)\s*°\s*(\d+)\s*'\s*$")
    m1 = pattern1.match(s)
    if m1:
        deg = int(m1.group(1))
        minute = int(m1.group(2))
        return deg + minute / 60.0

    # 情况 B：纯数字且长度为 3 或 4 位（例如 915, 6815），把最后两位当作分
    if s.isdigit() and 3 <= len(s) <= 4:
        # 最后两位是分，其余是度
        deg = int(s[:-2])
        minute = int(s[-2:])
        # 如果 minute >= 60，需要转换（98′ → 1°38′），但是一般输入不会这么大，这里简化不做额外处理
        return deg + minute / 60.0

    # 情况 C：其他形式，尝试直接转换为 float
    try:
        return float(s)
    except Exception:
        raise ValueError(f"无法解析角度格式：{angle_str}")



def rotate_vec(vec: Vec2, angle_deg: float) -> Vec2:
    """
    将 vec（单位向量）绕原点顺时针旋转 angle_deg 度，返回新的 Vec2。
    注意：顺时针旋转即用 -angle_deg 作为数学上逆时针旋转的负值。
    """
    rad = math.radians(-angle_deg)
    cosA = math.cos(rad)
    sinA = math.sin(rad)
    x, y = vec.x, vec.y
    x_new = x * cosA - y * sinA
    y_new = x * sinA + y * cosA
    return Vec2(x_new, y_new).normalize()


def main():
    # 1. 检查文件存在性
    dxf_path = Path(DXF_FILE)
    if not dxf_path.exists():
        print(f"DXF 文件未找到：{dxf_path}")
        return

    table_path = Path(TABLE_FILE)
    if not table_path.exists():
        print(f"里程-角度表格未找到：{table_path}")
        return

    # 2. 读取 DXF
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    # 3. 准备“标注”图层
    if ANNOT_LAYER not in {layer.dxf.name for layer in doc.layers}:
        doc.layers.new(name=ANNOT_LAYER, dxfattribs={'color': 1})

    # 4. 读取表格（兼容 .xlsx/.xls/.csv）
    #    假设表格有表头，里程列在第 0 列，角度列在第 1 列
    suffix = table_path.suffix.lower()
    if suffix in ('.xlsx', '.xls'):
        df = pd.read_excel(table_path, header=0)
    elif suffix == '.csv':
        df = pd.read_csv(table_path, header=0)
    else:
        raise ValueError("只能读取 .xlsx/.xls 或 .csv 格式的表格。")

    # 取出第一列和第二列
    # 若表格没有表头，可将 header=None，并用 df.iloc[:,0], df.iloc[:,1]
    mileage_list = df.iloc[:, 0].tolist()
    angle_list   = df.iloc[:, 1].tolist()

    if len(mileage_list) != len(angle_list):
        print("表格行数不匹配，请检查第一列和第二列是否对应。")
        return

    # 5. 预先处理：先把所有铁路图层的密集点及累积长度缓存起来
    rail_data = {}  # key = 图层名，value = (dense_pts, cum_len, offset)
    for layer_name, offset in RAIL_LAYERS.items():
        ents = list(msp.query(f'LWPOLYLINE[layer=="{layer_name}"]')) + \
               list(msp.query(f'POLYLINE[layer=="{layer_name}"]'))
        if not ents:
            print(f"Warning: 图层 {layer_name} 未找到任何折线，已跳过。")
            continue
        # 假设每个图层只有一条铁路，如果有多条，可以自行扩展
        rail_ent = ents[0]
        pts2d = poly2d(rail_ent)
        dense_pts = densify(pts2d, max_len=MAX_SEG_LEN)
        cum_len   = calc_cum_len(dense_pts)
        rail_data[layer_name] = (dense_pts, cum_len, offset)

    # 6. 对表格中每一行，去对应的铁路图层上定位并画线
    for M, ang_str in zip(mileage_list, angle_list):
        try:
            ang_deg = parse_angle(str(ang_str))
        except Exception as e:
            print(f"[跳过] 角度解析失败（{ang_str}）：{e}")
            continue

        placed = False
        # 在哪个铁路图层？寻找满足 offset <= M <= offset + total_length
        for layer_name, (dense_pts, cum_len, offset) in rail_data.items():
            total_len = cum_len[-1]
            # 表格中 M 已经是“含偏置”的里程，计算本地长度
            local_len = M - offset
            if local_len < -TOLERANCE or local_len > total_len + TOLERANCE:
                # 说明这条铁路不包含该里程，继续下一个图层
                continue

            # 在当前图层上插值定位
            pt, t_rail = get_point_and_tangent(dense_pts, cum_len, local_len)
            # 顺时针旋转 t_rail 得到 t_pwr
            t_pwr = rotate_vec(t_rail, ang_deg)

            # 新版：以 pt 为中心，沿 t_pwr 方向两端各延伸 ANNOT_LENGTH/2
            half_len = ANNOT_LENGTH / 2.0

            # 计算两个端点
            pt1 = pt + t_pwr * half_len     # 先向 “正向” 延伸半段
            pt2 = pt - t_pwr * half_len     # 再向 “反向” 延伸半段

            # 绘制一条双向延伸的折线（其实就是一条直线段）
            msp.add_lwpolyline(
                [(pt2.x, pt2.y), (pt1.x, pt1.y)],
                dxfattribs={'layer': ANNOT_LAYER, 'color': 1}
            )


            placed = True
            break  # 找到所属图层后就不继续再找了

        if not placed:
            print(f"[警告] 里程 {M} 米不在任何铁路图层的范围内，已跳过。")

    # 7. 保存修改后的 DXF
    out_path = dxf_path.with_name(dxf_path.stem + '_with_annotations.dxf')
    doc.saveas(out_path)
    print(f"[OK] 标注已完成，输出文件 → {out_path.name}")


if __name__ == '__main__':
    main()
