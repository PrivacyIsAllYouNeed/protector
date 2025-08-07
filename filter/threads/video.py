from typing import Optional
from threads.base import BaseThread
from misc.state import ThreadStateManager, ConnectionState, ConsentState
from misc.types import VideoData, ProcessedVideoData
from misc.queues import BoundedQueue
from misc.config import QUEUE_TIMEOUT, DISABLE_VIDEO_PROCESSING
from misc.face_detector import FaceDetector
from misc.consent_capture import ConsentCapture


class VideoProcessingThread(BaseThread):
    def __init__(
        self,
        state_manager: ThreadStateManager,
        connection_state: ConnectionState,
        consent_state: ConsentState,
        input_queue: BoundedQueue[VideoData],
        output_queue: BoundedQueue[ProcessedVideoData],
    ):
        super().__init__(
            name="VideoProcessor", state_manager=state_manager, heartbeat_interval=1.0
        )
        self.connection_state = connection_state
        self.consent_state = consent_state
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.face_detector: Optional[FaceDetector] = None
        self.frames_processed = 0

    def setup(self):
        if not DISABLE_VIDEO_PROCESSING:
            self.face_detector = FaceDetector()
            self.logger.info("Video processing thread initialized with face detector")
        else:
            self.logger.info(
                "Video processing DISABLED - frames will pass through unmodified"
            )

    def process_iteration(self) -> bool:
        # Don't process if input is not connected
        if not self.connection_state.is_input_connected():
            return False

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
        # Check for consent-triggered capture BEFORE processing
        if self.consent_state.should_capture():
            try:
                # Convert VideoFrame to numpy array for saving
                bgr_frame = video_data.frame.to_ndarray(format="bgr24")
                capture_path = ConsentCapture.save_frame(
                    bgr_frame, self.consent_state.speaker_name
                )
                self.logger.info(f"Consent capture saved: {capture_path}")
                self.consent_state.reset_capture()
            except Exception as e:
                self.logger.error(f"Failed to save consent screenshot: {e}")

        if DISABLE_VIDEO_PROCESSING:
            # Pass through original frame without processing
            processed_video = ProcessedVideoData(
                frame=video_data.frame,
                timestamp=video_data.timestamp,
                sequence=video_data.sequence,
                faces_detected=0,
            )
            self.metrics.record_frame(0)
            return processed_video

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
