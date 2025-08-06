"""
Face detection and blurring module using YuNet.
"""

import threading
import time
from typing import Any
import numpy as np
from numpy.typing import NDArray
import cv2
from av.video.frame import VideoFrame

from misc.logging import get_logger
from misc.config import (
    MODEL_PATH,
    FACE_BLUR_KERNEL,
    FACE_SCORE_THRESHOLD,
    FACE_NMS_THRESHOLD,
    FACE_TOP_K,
    FACE_MIN_CONFIDENCE,
    FACE_PADDING_RATIO,
    FACE_CACHE_DURATION_MS,
)


class FaceDetector:
    """Face detector and blurring processor using YuNet."""

    def __init__(self) -> None:
        """Initialize the YuNet face detector."""
        self.logger = get_logger(__name__)

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
        # Track current input size to avoid unnecessary updates
        self.current_input_size: tuple[int, int] | None = None

        # Face detection caching for performance
        self.cached_faces: list[tuple[int, int, int, int]] | None = None
        self.cache_timestamp: float = 0
        self.cache_duration_ms: float = FACE_CACHE_DURATION_MS

        # Cache statistics
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.last_stats_log: float = 0

    def blur_faces_in_frame(self, frame: VideoFrame) -> tuple[VideoFrame, int]:
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

        current_time_ms = time.time() * 1000
        cache_age_ms = current_time_ms - self.cache_timestamp

        # Check if we need to run face detection or can use cached results
        if self.cached_faces is None or cache_age_ms > self.cache_duration_ms:
            # Cache miss - need to run face detection
            self.cache_misses += 1

            # Update detector input size only if frame dimensions changed
            new_size = (w, h)
            if self.current_input_size != new_size:
                self.detector.setInputSize(new_size)
                self.current_input_size = new_size

            # Detect faces - returns tuple of (retval, faces)
            # faces can be None (when no faces) or np.ndarray
            _, faces_result = self.detector.detect(bgr)

            # Handle the union type properly
            faces: NDArray[np.float32] | None = faces_result

            # Update cache
            if faces is None or len(faces) == 0:
                self.cached_faces = []
            else:
                # Store simplified face rectangles for reuse
                self.cached_faces = self._extract_face_rectangles(faces, w, h)

            self.cache_timestamp = current_time_ms
        else:
            # Cache hit - reusing cached face rectangles
            self.cache_hits += 1

        # Log cache statistics every 30 seconds
        if current_time_ms - self.last_stats_log > 30000:
            total = self.cache_hits + self.cache_misses
            if total > 0:
                hit_rate = (self.cache_hits / total) * 100
                self.logger.info(
                    f"Face detection cache stats: {self.cache_hits} hits, "
                    f"{self.cache_misses} misses, {hit_rate:.1f}% hit rate"
                )
            self.last_stats_log = current_time_ms

        # If no cached faces, return original frame
        if not self.cached_faces:
            return frame, 0

        # Apply blur using cached face rectangles
        bgr_with_blur = self._apply_cached_face_blur(bgr, self.cached_faces)
        faces_blurred = len(self.cached_faces)

        # Convert back to VideoFrame, preserving timing information
        new_frame = VideoFrame.from_ndarray(bgr_with_blur, format="bgr24")
        new_frame.pts = frame.pts
        new_frame.time_base = frame.time_base
        return new_frame, faces_blurred

    def _apply_face_blur(
        self, bgr: NDArray[Any], faces: NDArray[np.float32], width: int, height: int
    ) -> tuple[NDArray[Any], int]:
        """
        Apply Gaussian blur to detected faces in the image.

        Args:
            bgr: BGR image array
            faces: Array of detected faces
            width: Image width
            height: Image height

        Returns:
            Tuple of (Image with faces blurred, number of faces blurred)
        """
        faces_blurred = 0
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
                faces_blurred += 1

        return bgr, faces_blurred

    def _extract_face_rectangles(
        self, faces: NDArray[np.float32], width: int, height: int
    ) -> list[tuple[int, int, int, int]]:
        """
        Extract and validate face rectangles from detection results.

        Args:
            faces: Array of detected faces
            width: Image width
            height: Image height

        Returns:
            List of (x1, y1, x2, y2) face rectangles with padding
        """
        rectangles = []
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

            rectangles.append((x1, y1, x2, y2))

        return rectangles

    def _apply_cached_face_blur(
        self, bgr: NDArray[Any], face_rectangles: list[tuple[int, int, int, int]]
    ) -> NDArray[Any]:
        """
        Apply Gaussian blur to cached face rectangles.

        Args:
            bgr: BGR image array
            face_rectangles: List of (x1, y1, x2, y2) face rectangles

        Returns:
            Image with faces blurred
        """
        for x1, y1, x2, y2 in face_rectangles:
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
_face_detector_lock = threading.Lock()


def get_face_detector() -> FaceDetector:
    """
    Get or create the global face detector instance (thread-safe).

    Returns:
        FaceDetector instance
    """
    global _face_detector
    if _face_detector is None:
        with _face_detector_lock:
            # Double-check pattern for thread safety
            if _face_detector is None:
                _face_detector = FaceDetector()
    return _face_detector
