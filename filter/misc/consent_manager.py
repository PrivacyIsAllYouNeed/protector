import threading
from pathlib import Path
from typing import Optional, Any
import cv2
import numpy as np
from numpy.typing import NDArray
from watchfiles import watch, Change

from misc.logging import get_logger
from misc.config import MODEL_PATH, FACE_SCORE_THRESHOLD, FACE_NMS_THRESHOLD, FACE_TOP_K
from misc.face_recognizer import get_face_recognizer
from misc.state import ConsentState

logger = get_logger(__name__)

CONSENT_DIR = Path("./consent_captures")


class ConsentManager:
    def __init__(self, consent_state: ConsentState):
        self.consent_state = consent_state
        self.face_recognizer = get_face_recognizer()
        self.monitor_thread: Optional[threading.Thread] = None
        self._stop_monitoring = threading.Event()
        self.logger = get_logger(__name__)

    def load_existing_consents(self) -> None:
        if not CONSENT_DIR.exists():
            CONSENT_DIR.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Created consent directory: {CONSENT_DIR}")
            return

        consent_files = list(CONSENT_DIR.glob("*.jpg"))
        self.logger.info(f"Loading {len(consent_files)} existing consent files")

        for file_path in consent_files:
            try:
                self._process_consent_file(file_path, is_startup=True)
            except Exception as e:
                self.logger.error(f"Failed to load consent file {file_path}: {e}")

        self.logger.info(
            f"Loaded {self.face_recognizer.get_consented_count()} consented individuals"
        )

    def _process_consent_file(self, file_path: Path, is_startup: bool = False) -> None:
        filename = file_path.name
        parts = filename.rsplit("_", 1)
        if len(parts) != 2:
            self.logger.warning(f"Invalid consent filename format: {filename}")
            return

        timestamp_str, name_with_ext = parts
        if not name_with_ext.endswith(".jpg"):
            self.logger.warning(f"Invalid consent file extension: {filename}")
            return

        name = name_with_ext[:-4]  # Remove .jpg

        image = cv2.imread(str(file_path))
        if image is None:
            self.logger.error(f"Failed to load image: {file_path}")
            return

        features = self._extract_face_features(image)
        if features is not None:
            self.face_recognizer.add_consented_face(name, features)
            self.consent_state.add_consented_name(name)
            if not is_startup:
                self.logger.info(f"Added consent for: {name} from {filename}")
        else:
            self.logger.warning(f"No face detected in consent image: {file_path}")

    def _extract_face_features(
        self, image: NDArray[Any]
    ) -> Optional[NDArray[np.float32]]:
        h, w = image.shape[:2]

        detector: Any = cv2.FaceDetectorYN.create(
            model=str(MODEL_PATH),
            config="",
            input_size=(w, h),
            score_threshold=FACE_SCORE_THRESHOLD,
            nms_threshold=FACE_NMS_THRESHOLD,
            top_k=FACE_TOP_K,
        )

        _, faces = detector.detect(image)

        if faces is None or len(faces) == 0:
            return None

        # Get the largest face (most likely the consenting person)
        largest_face_idx = 0
        largest_area = 0
        for i in range(len(faces)):
            x, y, face_w, face_h = faces[i][:4]
            area = face_w * face_h
            if area > largest_area:
                largest_area = area
                largest_face_idx = i

        face_coords = faces[largest_face_idx]

        # Extract features using face recognizer
        try:
            features = self.face_recognizer.extract_feature(image, face_coords)
            return features
        except Exception as e:
            self.logger.error(f"Failed to extract face features: {e}")
            return None

    def start_monitoring(self) -> None:
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.logger.warning("Consent monitoring already running")
            return

        self._stop_monitoring.clear()
        self.monitor_thread = threading.Thread(
            target=self._monitor_consent_directory, daemon=True, name="ConsentMonitor"
        )
        self.monitor_thread.start()
        self.logger.info("Started consent directory monitoring")

    def stop_monitoring(self) -> None:
        if self.monitor_thread and self.monitor_thread.is_alive():
            self._stop_monitoring.set()
            self.monitor_thread.join(timeout=5.0)
            self.logger.info("Stopped consent directory monitoring")

    def _monitor_consent_directory(self) -> None:
        def image_filter(change: Change, path: str) -> bool:
            return path.endswith(".jpg")

        try:
            for changes in watch(
                CONSENT_DIR,
                watch_filter=image_filter,
                stop_event=self._stop_monitoring,
                yield_on_timeout=True,
            ):
                if self._stop_monitoring.is_set():
                    break

                if changes:  # changes can be None on timeout
                    for change_type, file_path in changes:
                        try:
                            self._handle_file_change(change_type, Path(file_path))
                        except Exception as e:
                            self.logger.error(
                                f"Error handling file change {file_path}: {e}"
                            )

        except Exception as e:
            self.logger.error(f"Error in consent monitoring thread: {e}")

    def _handle_file_change(self, change_type: Change, file_path: Path) -> None:
        filename = file_path.name

        if change_type == Change.added:
            self._process_consent_file(file_path, is_startup=False)

        elif change_type == Change.deleted:
            parts = filename.rsplit("_", 1)
            if len(parts) == 2:
                _, name_with_ext = parts
                if name_with_ext.endswith(".jpg"):
                    name = name_with_ext[:-4]

                    # Check if there are other files for this person
                    other_files = list(CONSENT_DIR.glob(f"*_{name}.jpg"))
                    if not other_files:
                        # No other consent files for this person, remove from database
                        self.face_recognizer.remove_consented_face(name)
                        self.consent_state.remove_consented_name(name)
                        self.logger.info(f"Revoked consent for: {name}")
                    else:
                        # Reload all remaining files for this person
                        self.logger.info(
                            f"Reloading {len(other_files)} remaining files for {name}"
                        )
                        self.face_recognizer.remove_consented_face(name)
                        for other_file in other_files:
                            self._process_consent_file(other_file, is_startup=False)


_consent_manager: Optional[ConsentManager] = None
_consent_manager_lock = threading.Lock()


def get_consent_manager(consent_state: ConsentState) -> ConsentManager:
    global _consent_manager
    if _consent_manager is None:
        with _consent_manager_lock:
            if _consent_manager is None:
                _consent_manager = ConsentManager(consent_state)
    return _consent_manager
