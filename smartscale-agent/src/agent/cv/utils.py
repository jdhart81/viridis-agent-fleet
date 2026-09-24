import io
import numpy as np
from PIL import Image

def load_image_bgr_from_bytes(data: bytes):
    img = Image.open(io.BytesIO(data)).convert("RGB")
    arr = np.array(img)[:, :, ::-1]  # RGB -> BGR
    return arr

def load_image_bgr_from_b64(b64: str):
    import base64
    return load_image_bgr_from_bytes(base64.b64decode(b64))
