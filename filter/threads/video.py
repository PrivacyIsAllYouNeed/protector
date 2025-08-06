import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Optional
from threads.base import BaseThread
from misc.state import ThreadStateManager
from misc.types import VideoData, ProcessedVideoData
from misc.queues import BoundedQueue
from misc.config import QUEUE_TIMEOUT
from misc.face_detector import FaceDetector


class VideoProcessingThread(BaseThread):
    def __init__(
        self,
        state_manager: ThreadStateManager,
        input_queue: BoundedQueue[VideoData],
        output_queue: BoundedQueue[ProcessedVideoData],
    ):
        super().__init__(
            name="VideoProcessor", state_manager=state_manager, heartbeat_interval=1.0
        )
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.face_detector: Optional[FaceDetector] = None
        self.frames_processed = 0

    def setup(self):
        self.face_detector = FaceDetector()
        self.logger.info("Video processing thread initialized with face detector")

    def process_iteration(self) -> bool:
        video_data = self.input_queue.get(timeout=QUEUE_TIMEOUT)

        if video_data is None:
            return False

        try:
            processed_frame = self._process_frame(video_data)

            if not self.output_queue.put(processed_frame, timeout=QUEUE_TIMEOUT):
                self.metrics.record_dropped_frame()
                self.logger.debug(f"Dropped processed frame {processed_frame.sequence}")

            self.frames_processed += 1

            if self.frames_processed % 100 == 0:
                self.logger.debug(f"Processed {self.frames_processed} frames")

            return True

        except Exception as e:
            self.logger.error(f"Error processing frame {video_data.sequence}: {e}")
            return False

    def _process_frame(self, video_data: VideoData) -> ProcessedVideoData:
        if not self.face_detector:
            raise RuntimeError("Face detector not initialized")

        processed_frame, faces_detected = self.face_detector.blur_faces_in_frame(
            video_data.frame
        )

        processed_video = ProcessedVideoData(
            frame=processed_frame,
            timestamp=video_data.timestamp,
            sequence=video_data.sequence,
            faces_detected=faces_detected,
        )

        self.metrics.record_frame(faces_detected)

        return processed_video

    def cleanup(self):
        self.logger.info(
            f"Video processor cleanup - processed {self.frames_processed} frames"
        )
        self.face_detector = None
