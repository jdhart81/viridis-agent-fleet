import cv2
import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple

DICT_MAP = {
    "DICT_4X4_50": cv2.aruco.DICT_4X4_50,
    "DICT_5X5_100": cv2.aruco.DICT_5X5_100,
    "DICT_6X6_100": cv2.aruco.DICT_6X6_100,
}

@dataclass
class CharucoDetectResult:
    ok: bool
    board_corners: Optional[np.ndarray]  # Nx2 image coords
    ids: Optional[np.ndarray]
    px_per_mm: Optional[float]
    homography: Optional[np.ndarray]
    confidence: float

def detect_charuco_and_scale(img_bgr: np.ndarray, squares_x: int, squares_y: int,
                             square_length_mm: float, marker_length_mm: float,
                             dictionary: str = "DICT_4X4_50") -> CharucoDetectResult:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    aruco_dict = cv2.aruco.getPredefinedDictionary(DICT_MAP.get(dictionary, cv2.aruco.DICT_4X4_50))
    params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, params)
    corners, ids, _ = detector.detectMarkers(gray)
    if ids is None or len(ids) < 4:
        return CharucoDetectResult(False, None, None, None, None, 0.0)

    # Charuco board
    board = cv2.aruco.CharucoBoard((squares_x, squares_y), square_length_mm, marker_length_mm, aruco_dict)
    charuco = cv2.aruco.CharucoDetector(board)
    charuco_corners, charuco_ids, _, _ = charuco.detectBoard(gray, corners, ids)

    if charuco_ids is None or len(charuco_ids) < 4:
        return CharucoDetectResult(False, None, None, None, None, 0.1)

    # Build ideal board coordinates in mm for matched corners
    obj_pts = board.getChessboardCorners()  # (N,3) in mm (z=0)
    # Map ids to corners
    matched = [(charuco_corners[i,0,:], obj_pts[int(charuco_ids[i,0]), :2]) for i in range(len(charuco_ids))]
    img_pts = np.array([m[0] for m in matched], dtype=np.float32)
    obj_xy = np.array([m[1] for m in matched], dtype=np.float32)

    # Estimate homography from object mm-space to image px-space
    H, mask = cv2.findHomography(obj_xy, img_pts, cv2.RANSAC, 3.0)
    if H is None:
        return CharucoDetectResult(False, None, None, None, None, 0.2)

    # Compute px_per_mm by projecting unit mm vectors
    # Take two points 100mm apart in board x and compute distance in pixels
    test_len_mm = 100.0
    P0 = np.array([0,0,1.0], dtype=np.float32)
    P1 = np.array([test_len_mm,0,1.0], dtype=np.float32)
    q0 = (H @ P0); q0 = q0[:2]/q0[2]
    q1 = (H @ P1); q1 = q1[:2]/q1[2]
    px_per_mm = float(np.linalg.norm(q1-q0)/test_len_mm)

    # Confidence heuristic: fraction inliers + corner count
    inlier_frac = float(np.mean(mask)) if mask is not None else 0.5
    conf = 0.5*inlier_frac + 0.5*min(1.0, len(charuco_ids)/40.0)

    return CharucoDetectResult(True, img_pts, charuco_ids, px_per_mm, H, conf)
