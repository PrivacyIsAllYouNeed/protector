import threading
from typing import Any, Optional, Dict, Tuple
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
        self.consented_faces: Dict[str, list[NDArray[np.float32]]] = {}
        self.logger.info("Consented faces database initialized")

    def extract_feature(
        self, face_img: NDArray[Any], face_coords: NDArray[np.float32]
    ) -> NDArray[np.float32]:
        aligned = self.recognizer.alignCrop(face_img, face_coords)
        feature = self.recognizer.feature(aligned)
        return feature

    def add_consented_face(self, name: str, feature: NDArray[np.float32]) -> None:
        with self._lock:
            # Normalize name to lowercase for consistency
            name_lower = name.lower()
            if name_lower not in self.consented_faces:
                self.consented_faces[name_lower] = []
            self.consented_faces[name_lower].append(feature)
            self.logger.info(
                f"Added consented face for: {name_lower} (total: {len(self.consented_faces[name_lower])})"
            )

    def remove_consented_face(self, name: str) -> None:
        with self._lock:
            # Normalize name to lowercase for consistency
            name_lower = name.lower()
            if name_lower in self.consented_faces:
                del self.consented_faces[name_lower]
                self.logger.info(f"Removed all consent faces for: {name_lower}")

    def match_face(self, feature: NDArray[np.float32]) -> Tuple[bool, Optional[str]]:
        with self._lock:
            for name, known_features in self.consented_faces.items():
                for known_feature in known_features:
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
        with self._lock:
            return len(self.consented_faces)

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
