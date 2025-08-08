import threading
from typing import Any, Optional, Tuple, List
from pathlib import Path
import numpy as np
from numpy.typing import NDArray
import cv2

from misc.logging import get_logger
from misc.config import BASE_DIR

SFACE_MODEL_PATH = BASE_DIR / "face_recognition_sface_2021dec.onnx"
COSINE_THRESHOLD = 0.363
L2_THRESHOLD = 1.128

logger = get_logger(__name__)


class FaceRecognizer:
    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        self._lock = threading.Lock()
        self._init_recognizer()
        self._init_database()

    def _init_recognizer(self) -> None:
        if not SFACE_MODEL_PATH.exists():
            raise FileNotFoundError(f"SFace model not found at {SFACE_MODEL_PATH}")

        self.recognizer: Any = cv2.FaceRecognizerSF.create(str(SFACE_MODEL_PATH), "")
        self.logger.info("Face recognizer initialized with SFace model")

    def _init_database(self) -> None:
        # Flat list of (file_path, name, feature) tuples
        self.consented_faces: List[Tuple[Path, str, NDArray[np.float32]]] = []
        self.logger.info("Consented faces database initialized")

    def extract_feature(
        self, face_img: NDArray[Any], face_coords: NDArray[np.float32]
    ) -> NDArray[np.float32]:
        aligned = self.recognizer.alignCrop(face_img, face_coords)
        feature = self.recognizer.feature(aligned)
        return feature

    def add_consented_face(
        self, name: str, feature: NDArray[np.float32], file_path: Path
    ) -> None:
        with self._lock:
            # Normalize name to lowercase for consistency
            name_lower = name.lower()
            # Check if this file already exists and remove it first
            self.consented_faces = [
                entry for entry in self.consented_faces if entry[0] != file_path
            ]
            # Add the new entry
            self.consented_faces.append((file_path, name_lower, feature))
            self.logger.info(
                f"Added consented face for: {name_lower} from {file_path.name} (total faces: {len(self.consented_faces)})"
            )

    def remove_consented_face_by_file(self, file_path: Path) -> None:
        """Remove a specific face feature by file path."""
        with self._lock:
            original_count = len(self.consented_faces)
            self.consented_faces = [
                entry for entry in self.consented_faces if entry[0] != file_path
            ]
            removed_count = original_count - len(self.consented_faces)

            if removed_count > 0:
                self.logger.info(
                    f"Removed consent face from {file_path.name} (remaining: {len(self.consented_faces)})"
                )

    def match_face(self, feature: NDArray[np.float32]) -> Tuple[bool, Optional[str]]:
        with self._lock:
            for _, name, known_feature in self.consented_faces:
                cosine_score = self.recognizer.match(
                    feature, known_feature, 0
                )  # FR_COSINE = 0
                l2_score = self.recognizer.match(
                    feature, known_feature, 1
                )  # FR_NORM_L2 = 1

                if cosine_score < COSINE_THRESHOLD or l2_score < L2_THRESHOLD:
                    return True, name

            return False, None

    def get_consented_count(self) -> int:
        """Get the total number of consented face entries."""
        with self._lock:
            return len(self.consented_faces)

    def get_unique_consented_count(self) -> int:
        """Get the number of unique individuals with consent."""
        with self._lock:
            unique_names = set(entry[1] for entry in self.consented_faces)
            return len(unique_names)

    def clear_database(self) -> None:
        with self._lock:
            self.consented_faces.clear()
            self.logger.info("Cleared consented faces database")


_face_recognizer: Optional[FaceRecognizer] = None
_face_recognizer_lock = threading.Lock()


def get_face_recognizer() -> FaceRecognizer:
    global _face_recognizer
    if _face_recognizer is None:
        with _face_recognizer_lock:
            if _face_recognizer is None:
                _face_recognizer = FaceRecognizer()
    return _face_recognizer
