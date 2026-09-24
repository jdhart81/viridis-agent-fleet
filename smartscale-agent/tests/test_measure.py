from src.agent.cv.geometry import line_length_mm, angle_deg, circle_diameter_mm

def test_line():
    px_per_mm = 2.0
    val = line_length_mm([(0,0),(20,0)], px_per_mm)
    assert abs(val-10.0) < 1e-6

def test_angle():
    ang = angle_deg([(0,0),(0,0),(1,0)])
    assert 0.0 <= ang <= 180.0

def test_circle():
    px_per_mm = 2.0
    d = circle_diameter_mm([(0,0),(1,0),(0,1)], px_per_mm)
    assert d > 0
