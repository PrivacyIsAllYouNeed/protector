import os
from datetime import datetime
from typing import Optional
import cv2
import numpy as np
from misc.logging import get_logger


logger = get_logger(__name__)


class ConsentCapture:
    SCREENSHOT_DIR = "consent_captures"

    @classmethod
    def save_frame(cls, frame: np.ndarray, speaker_name: Optional[str] = None) -> str:
        os.makedirs(cls.SCREENSHOT_DIR, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        if speaker_name:
            safe_name = "".join(
                c for c in speaker_name.lower() if c.isalnum() or c in "_- "
            )
            safe_name = safe_name.replace(" ", "_").strip("_")
            filename = f"{timestamp}_{safe_name}.jpg"
        else:
            filename = f"{timestamp}_unknown.jpg"

        filepath = os.path.join(cls.SCREENSHOT_DIR, filename)

        success = cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])

        if not success:
            raise IOError(f"Failed to save screenshot to {filepath}")

        logger.info(f"Consent screenshot saved: {filepath}")
        return filepath
