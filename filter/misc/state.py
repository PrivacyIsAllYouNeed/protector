import threading
from typing import Optional, Dict, Any
from datetime import datetime
from misc.types import ThreadState
from misc.logging import get_logger


logger = get_logger(__name__)


class ConnectionState:
    def __init__(self):
        self._lock = threading.RLock()
        self._input_connected = False
        self._output_connected = False
        self._input_connect_time: Optional[datetime] = None
        self._output_connect_time: Optional[datetime] = None
        self._stream_metadata: Dict[str, Any] = {}

    def set_input_connected(
        self, connected: bool, metadata: Optional[Dict[str, Any]] = None
    ):
        with self._lock:
            self._input_connected = connected
            if connected:
                self._input_connect_time = datetime.now()
                if metadata:
                    self._stream_metadata.update(metadata)
                logger.info(f"Input connected with metadata: {metadata}")
            else:
                self._input_connect_time = None
                self._stream_metadata.clear()
                logger.info("Input disconnected")

    def set_output_connected(self, connected: bool):
        with self._lock:
            self._output_connected = connected
            if connected:
                self._output_connect_time = datetime.now()
                logger.info("Output connected")
            else:
                self._output_connect_time = None
                logger.info("Output disconnected")

    def is_connected(self) -> bool:
        with self._lock:
            return self._input_connected and self._output_connected

    def is_input_connected(self) -> bool:
        with self._lock:
            return self._input_connected

    def is_output_connected(self) -> bool:
        with self._lock:
            return self._output_connected

    def get_stream_metadata(self) -> Dict[str, Any]:
        with self._lock:
            return self._stream_metadata.copy()

    def get_connection_duration(self) -> Optional[float]:
        with self._lock:
            if self._input_connect_time and self._output_connect_time:
                start_time = max(self._input_connect_time, self._output_connect_time)
                return (datetime.now() - start_time).total_seconds()
            return None


class ThreadStateManager:
    def __init__(self):
        self._states: Dict[str, ThreadState] = {}
        self._health_timestamps: Dict[str, datetime] = {}
        self._lock = threading.RLock()

    def register_thread(self, thread_name: str):
        with self._lock:
            self._states[thread_name] = ThreadState.IDLE
            self._health_timestamps[thread_name] = datetime.now()
            logger.debug(f"Registered thread: {thread_name}")

    def update_state(self, thread_name: str, state: ThreadState):
        with self._lock:
            if thread_name in self._states:
                old_state = self._states[thread_name]
                self._states[thread_name] = state
                self._health_timestamps[thread_name] = datetime.now()
                if old_state != state:
                    logger.info(
                        f"Thread {thread_name} state: {old_state.value} -> {state.value}"
                    )

    def heartbeat(self, thread_name: str):
        with self._lock:
            if thread_name in self._health_timestamps:
                self._health_timestamps[thread_name] = datetime.now()

    def get_state(self, thread_name: str) -> Optional[ThreadState]:
        with self._lock:
            return self._states.get(thread_name)

    def get_all_states(self) -> Dict[str, ThreadState]:
        with self._lock:
            return self._states.copy()

    def is_healthy(self, thread_name: str, timeout_seconds: float = 30.0) -> bool:
        with self._lock:
            if thread_name not in self._health_timestamps:
                return False
            last_heartbeat = self._health_timestamps[thread_name]
            elapsed = (datetime.now() - last_heartbeat).total_seconds()
            state = self._states.get(thread_name)
            return elapsed < timeout_seconds and state not in [
                ThreadState.ERROR,
                ThreadState.STOPPED,
            ]

    def all_healthy(self, timeout_seconds: float = 30.0) -> bool:
        with self._lock:
            return all(
                self.is_healthy(thread_name, timeout_seconds)
                for thread_name in self._states.keys()
            )

    def unregister_thread(self, thread_name: str):
        with self._lock:
            self._states.pop(thread_name, None)
            self._health_timestamps.pop(thread_name, None)
            logger.debug(f"Unregistered thread: {thread_name}")
