import numpy as np
from typing import List, Tuple
Point = Tuple[float, float]

def line_length_mm(points: List[Point], px_per_mm: float) -> float:
    (x1,y1),(x2,y2) = points
    dpx = np.hypot(x2-x1, y2-y1)
    return float(dpx / px_per_mm)

def angle_deg(points: List[Point]) -> float:
    # three points: A (vertex), B, C; returns angle ABC
    (ax,ay),(bx,by),(cx,cy) = points
    v1 = np.array([ax-bx, ay-by])
    v2 = np.array([cx-bx, cy-by])
    cosang = np.dot(v1,v2) / (np.linalg.norm(v1)*np.linalg.norm(v2) + 1e-9)
    return float(np.degrees(np.arccos(np.clip(cosang, -1, 1))))

def circle_diameter_mm(points: List[Point], px_per_mm: float) -> float:
    # three points on circle -> fit circle, return diameter
    (x1,y1),(x2,y2),(x3,y3) = points
    A = np.array([[x1,y1,1],
                  [x2,y2,1],
                  [x3,y3,1]], dtype=float)
    B = -np.array([x1**2+y1**2, x2**2+y2**2, x3**2+y3**2], dtype=float)
    sol, *_ = np.linalg.lstsq(A, B, rcond=None)
    D,E,F = sol
    xc = -D/2; yc = -E/2
    r = np.sqrt(xc**2 + yc**2 - F)
    return float(2*r / px_per_mm)

def polygon_perimeter_mm(points: List[Point], px_per_mm: float) -> float:
    pts = np.array(points + [points[0]], dtype=float)
    d = np.sum(np.hypot(np.diff(pts[:,0]), np.diff(pts[:,1])))
    return float(d / px_per_mm)

def conservative_ci95_mm(px_sigma: float, px_per_mm: float, cond: float) -> float:
    # Very rough CI model: combine pixel sigma and homography condition
    base = px_sigma / max(px_per_mm, 1e-6)
    return float(base * (1.0 + 0.5*cond))
