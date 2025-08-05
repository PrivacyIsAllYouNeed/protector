"""
Face detection and blurring module using YuNet.
"""

from typing import Any
import numpy as np
from numpy.typing import NDArray
import cv2
from av.video.frame import VideoFrame

from config import (
    MODEL_PATH,
    FACE_BLUR_KERNEL,
    FACE_SCORE_THRESHOLD,
    FACE_NMS_THRESHOLD,
    FACE_TOP_K,
    FACE_MIN_CONFIDENCE,
    FACE_PADDING_RATIO,
)


class FaceDetector:
    """Face detector and blurring processor using YuNet."""

    def __init__(self) -> None:
        """Initialize the YuNet face detector."""
        # Type as Any since cv2.FaceDetectorYN is not fully typed
        self.detector: Any = cv2.FaceDetectorYN.create(
            model=str(MODEL_PATH),
            config="",
            input_size=(320, 320),  # Default size, will be adjusted per frame
            score_threshold=FACE_SCORE_THRESHOLD,
            nms_threshold=FACE_NMS_THRESHOLD,
            top_k=FACE_TOP_K,
            backend_id=cv2.dnn.DNN_BACKEND_OPENCV,
            target_id=cv2.dnn.DNN_TARGET_CPU,
        )

    def blur_faces_in_frame(self, frame: VideoFrame) -> VideoFrame:
        """
        Detect and blur faces in a VideoFrame.

        Args:
            frame: Input video frame

        Returns:
            VideoFrame with faces blurred
        """
        # Convert PyAV frame to NumPy array (BGR format)
        bgr = frame.to_ndarray(format="bgr24")
        h, w = bgr.shape[:2]

        # Update detector input size to match frame dimensions
        self.detector.setInputSize((w, h))

        # Detect faces - returns tuple of (retval, faces)
        # faces can be None (when no faces) or np.ndarray
        _, faces_result = self.detector.detect(bgr)

        # Handle the union type properly
        faces: NDArray[np.float32] | None = faces_result

        # If no faces detected, return original frame
        if faces is None or len(faces) == 0:
            return frame

        # Apply blur to each detected face
        bgr_with_blur = self._apply_face_blur(bgr, faces, w, h)

        # Convert back to VideoFrame, preserving timing information
        new_frame = VideoFrame.from_ndarray(bgr_with_blur, format="bgr24")
        new_frame.pts = frame.pts
        new_frame.time_base = frame.time_base
        return new_frame

    def _apply_face_blur(
        self, bgr: NDArray[Any], faces: NDArray[np.float32], width: int, height: int
    ) -> NDArray[Any]:
        """
        Apply Gaussian blur to detected faces in the image.

        Args:
            bgr: BGR image array
            faces: Array of detected faces
            width: Image width
            height: Image height

        Returns:
            Image with faces blurred
        """
        for i in range(len(faces)):
            face_row = faces[i]
            x: float = float(face_row[0])
            y: float = float(face_row[1])
            face_w: float = float(face_row[2])
            face_h: float = float(face_row[3])
            score: float = float(face_row[4])

            # Skip low confidence detections
            if score < FACE_MIN_CONFIDENCE:
                continue

            # Calculate bounding box with padding
            padding = int(min(face_w, face_h) * FACE_PADDING_RATIO)
            x1 = int(max(0, x - padding))
            y1 = int(max(0, y - padding))
            x2 = int(min(width - 1, x + face_w + padding))
            y2 = int(min(height - 1, y + face_h + padding))

            # Extract ROI
            roi = bgr[y1:y2, x1:x2]

            # Apply Gaussian blur to ROI if it's not empty
            if roi.size > 0:
                roi_blurred = cv2.GaussianBlur(roi, FACE_BLUR_KERNEL, 0)
                # Replace original ROI with blurred version
                bgr[y1:y2, x1:x2] = roi_blurred

        return bgr


# Global face detector instance
_face_detector: FaceDetector | None = None


def get_face_detector() -> FaceDetector:
    """
    Get or create the global face detector instance.

    Returns:
        FaceDetector instance
    """
    global _face_detector
    if _face_detector is None:
        _face_detector = FaceDetector()
    return _face_detector
