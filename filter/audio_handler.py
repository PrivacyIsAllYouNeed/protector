"""
Audio stream handling for RTMP/RTSP relay.
"""

import logging
from typing import Optional, Generator
from av.container import InputContainer, OutputContainer
from av.audio.stream import AudioStream
from av.audio.frame import AudioFrame
from av.packet import Packet


class AudioHandler:
    """Handles audio stream detection, setup, and remuxing."""

    def __init__(self):
        self.input_stream: Optional[AudioStream] = None
        self.output_stream: Optional[AudioStream] = None

    def detect_audio_stream(self, container: InputContainer) -> bool:
        """
        Detect and store audio stream from input container.

        Returns:
            True if audio stream was detected, False otherwise.
        """
        if container.streams.audio:
            self.input_stream = container.streams.audio[0]
            logging.info(
                "Audio stream detected: %s", self.input_stream.codec_context.name
            )
            return True
        return False

    def setup_output_stream(self, out_container: OutputContainer) -> bool:
        """
        Setup audio output stream matching input stream configuration.

        Returns:
            True if output stream was successfully created, False otherwise.
        """
        if not self.input_stream:
            return False

        # Copy audio codec from input
        codec_name = self.input_stream.codec_context.name
        audio_out = out_container.add_stream(codec_name, rate=self.input_stream.rate)

        # Type check to ensure we have an AudioStream
        if isinstance(audio_out, AudioStream):
            self.output_stream = audio_out

            # Copy codec context parameters
            self.output_stream.codec_context.layout = (
                self.input_stream.codec_context.layout
            )
            self.output_stream.codec_context.sample_rate = (
                self.input_stream.codec_context.sample_rate
            )

            logging.info(
                "Audio stream added to output: %s at %dHz with %d channels",
                codec_name,
                self.input_stream.rate,
                self.input_stream.codec_context.channels,
            )
            return True

        return False

    def remux_packet(self, packet: Packet, out_container: OutputContainer) -> None:
        """
        Remux audio packet to output container.

        Args:
            packet: Audio packet to remux
            out_container: Output container to mux packet into
        """
        if self.output_stream and packet.stream.type == "audio":
            # Store original stream to restore after remux
            original_stream = packet.stream
            packet.stream = self.output_stream
            out_container.mux(packet)
            # Restore original stream so packet can be decoded afterward
            packet.stream = original_stream

    def has_audio(self) -> bool:
        """Check if audio streams are configured."""
        return self.output_stream is not None

    def decode_packet(self, packet: Packet) -> Generator[AudioFrame, None, None]:
        """
        Decode audio packet into frames using the input stream's decoder.
        This method can be used even after the packet has been remuxed.

        Args:
            packet: Audio packet to decode

        Yields:
            Decoded audio frames
        """
        if packet.stream.type == "audio" and self.input_stream:
            # Use the input stream's decoder to decode the packet
            # This works even if packet.stream has been temporarily changed
            for frame in self.input_stream.decode(packet):
                if isinstance(frame, AudioFrame):
                    yield frame
