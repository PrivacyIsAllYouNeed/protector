import os
from datetime import datetime
from typing import Optional, Tuple, Any
import cv2
import numpy as np
from numpy.typing import NDArray
from misc.logging import get_logger
from misc.config import (
    MODEL_PATH,
    FACE_SCORE_THRESHOLD,
    FACE_NMS_THRESHOLD,
    FACE_TOP_K,
    FACE_PADDING_RATIO,
)


logger = get_logger(__name__)


class ConsentCapture:
    SCREENSHOT_DIR = "consent_captures"

    @classmethod
    def save_head_image(
        cls, frame: NDArray[Any], speaker_name: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[NDArray[np.float32]]]:
        h, w = frame.shape[:2]

        detector: Any = cv2.FaceDetectorYN.create(
            model=str(MODEL_PATH),
            config="",
            input_size=(w, h),
            score_threshold=FACE_SCORE_THRESHOLD,
            nms_threshold=FACE_NMS_THRESHOLD,
            top_k=FACE_TOP_K,
        )

        _, faces = detector.detect(frame)

        if faces is None or len(faces) == 0:
            logger.warning("No faces detected in consent frame, skipping capture")
            return None, None

        largest_face_idx = 0
        largest_area = 0
        for i in range(len(faces)):
            x, y, face_w, face_h = faces[i][:4]
            area = face_w * face_h
            if area > largest_area:
                largest_area = area
                largest_face_idx = i

        face_coords = faces[largest_face_idx]
        x, y, face_w, face_h = face_coords[:4].astype(int)

        padding = int(min(face_w, face_h) * FACE_PADDING_RATIO)
        x1 = max(0, x - padding)
        y1 = max(0, y - padding)
        x2 = min(w, x + face_w + padding)
        y2 = min(h, y + face_h + padding)

        head_image = frame[y1:y2, x1:x2]

        os.makedirs(cls.SCREENSHOT_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        if speaker_name:
            safe_name = "".join(
                c for c in speaker_name.lower() if c.isalnum() or c in "_- "
            )
            safe_name = safe_name.replace(" ", "_").strip("_")
            filename = f"{timestamp}_{safe_name}_head.jpg"
        else:
            filename = f"{timestamp}_unknown_head.jpg"

        filepath = os.path.join(cls.SCREENSHOT_DIR, filename)
        success = cv2.imwrite(filepath, head_image, [cv2.IMWRITE_JPEG_QUALITY, 95])

        if not success:
            raise IOError(f"Failed to save head image to {filepath}")

        logger.info(
            f"Consent head image saved: {filepath} (face area: {face_w}x{face_h})"
        )
        return filepath, face_coords
