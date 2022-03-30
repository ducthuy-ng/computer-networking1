import logging
import pathlib
import random
import socket
import threading
from enum import Enum
from typing import Tuple, Optional, List

from rtp_packet import RtpPacket
from video_stream import VideoStream


class RespondType(Enum):
    OK_200 = 200
    FILE_NOT_FOUND_404 = 404
    CON_ERR_500 = 500


class ServerState(Enum):
    INIT = 0
    READY = 1
    PLAYING = 2
    STOP = 3


class RequestType(Enum):
    SETUP = 'SETUP'
    PLAY = 'PLAY'
    PAUSE = 'PAUSE'
    TEARDOWN = 'TEARDOWN'


class ServerWorker(threading.Thread):
    def __init__(self, connection: socket.socket, client_addr: Tuple,
                 video_path: pathlib.Path):
        super(ServerWorker, self).__init__()

        self.connection_socket = connection
        self.connection_socket.settimeout(1)
        self.client_addr = client_addr
        self.video_path: pathlib.Path = video_path

        self.current_session_id: Optional[int] = None
        self.seq = 1
        self.streaming_thread = None

        self.stream_handler: Optional[VideoStream] = None
        self.stream_stop_flag: threading.Event = threading.Event()
        self.state = ServerState.INIT

        self.rtp_port: Optional[int] = None
        self.rtp_socket: Optional[socket.socket] = None

        self.logger = logging.getLogger(
            f"streaming-app.server.server-worker-{self.client_addr[0]}:{self.client_addr[1]}")

    def run(self) -> None:
        """
        Receive RTSP request from the client.
        """
        while True:
            try:
                data: bytes = self.connection_socket.recv(256)
                if not data:
                    raise ConnectionError

                self.logger.debug(f"Data received: {data}")
                self.process_rtsp_request(data.decode("utf-8"))
            except TimeoutError:
                # In the future, try to ping the client
                pass
            except ConnectionError:
                self._cleanup()
                break

    def process_rtsp_request(self, data):
        """Process RTSP request sent from the client."""
        # Get the request type
        request = data.split('\n')
        request_type = RequestType(request[0].split(' ')[0])

        # Get the RTSP sequence number
        seq = int(request[1].split(' ')[1])

        # Check if sequence number matches
        if seq != self.seq:
            self.reply_rtsp(RespondType.CON_ERR_500)
            return

        if request_type == RequestType.SETUP:
            self.handle_setup_req(request)
        elif request_type == RequestType.PLAY:
            self.handle_play_req(request)
        elif request_type == RequestType.PAUSE:
            self.handle_pause_req(request)
        elif request_type == RequestType.TEARDOWN:
            self.handle_teardown_req(request)

        self.seq += 1

    def handle_setup_req(self, request: List[str]):
        if self.state == ServerState.INIT:
            self.logger.debug("Processing SETUP")

            filename = request[0].split(' ')[1]

            # Generate a randomized RTSP session ID
            self.current_session_id = random.randint(100000, 999999)

            # Get the RTP/UDP port from the last line
            self.rtp_port = int(request[2].split(' ')[3])

            # Set up RTP port for streaming video
            self.rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

            # Send RTSP reply
            try:
                self.stream_handler = VideoStream(self.video_path / filename)
                self.state = ServerState.READY
                self.reply_rtsp(RespondType.OK_200)
            except IOError:
                self.reply_rtsp(RespondType.FILE_NOT_FOUND_404)
        else:
            self.logger.warning("Server has been set up")
            self.reply_rtsp(RespondType.CON_ERR_500)

    def handle_play_req(self, request: List[str]):
        if self.state == ServerState.READY:
            self.logger.debug("Processing PLAY")
            self.state = ServerState.PLAYING

            self.stream_stop_flag.clear()

            self.reply_rtsp(RespondType.OK_200)

            # Create a new thread and start sending RTP packets
            self.streaming_thread = threading.Thread(target=self.stream_video)
            self.streaming_thread.start()
        else:
            self.reply_rtsp(RespondType.CON_ERR_500)
            if self.state == ServerState.PLAYING:
                self.logger.warning("Server has already been playing")
            elif self.state != ServerState.READY:
                self.logger.warning("Server hasn't been set up")

    def handle_pause_req(self, request: List[str]):
        if self.state == ServerState.PLAYING:
            self.logger.debug("Processing PAUSE")
            self.state = ServerState.READY

            self.stream_stop_flag.set()

            self.reply_rtsp(RespondType.OK_200)
        else:
            self.reply_rtsp(RespondType.CON_ERR_500)
            if self.state == ServerState.READY:
                self.logger.warning("Streaming has already been paused")
            elif self.state != ServerState.PLAYING:
                self.logger.warning("Can't pause video")

    def handle_teardown_req(self, request: List[str]):
        if self.state == ServerState.INIT:
            self.logger.warning("Connection has already been tearing down")
        self.state = ServerState.INIT
        self.logger.debug("Processing TEARDOWN")

        self.stream_stop_flag.set()

        self.reply_rtsp(RespondType.OK_200)

    def stream_video(self):
        """Private method for sending RTP packets"""
        client_rtp_addr = (self.client_addr[0], self.rtp_port)

        data = None

        try:
            self.logger.debug(f"Starting stream to client: {client_rtp_addr}")
            while True:
                self.stream_stop_flag.wait(0.05)

                if self.stream_stop_flag.is_set():
                    break

                payload = self.stream_handler.next_frame()
                if not payload:
                    payload = bytes(5)

                frame_nbr = self.stream_handler.frame_nbr()

                data = RtpPacket.encode(
                    version=2,
                    padding=0,
                    extension=0,
                    cc=0,
                    marker=0,
                    payload_type=26,  # MJPEG
                    seq_num=frame_nbr,
                    ssrc=0,
                    payload=payload
                )

                try:
                    self.rtp_socket.sendto(data, client_rtp_addr)
                except OSError:
                    # Exception due to OSX not allowing UDP-package > 9216 bytes
                    # https://stackoverflow.com/a/35335138
                    continue

        finally:
            self.logger.debug("Stop streaming")

    def _cleanup(self):
        self.logger.info(f"Client has disconnected")
        self.connection_socket.close()
        if self.rtp_socket:
            self.rtp_socket.close()

    def reply_rtsp(self, code: RespondType) -> None:
        """Send RTSP reply to the client."""
        if code == RespondType.OK_200:
            reply = f"RTSP/1.0 200 OK\nCSeq: {self.seq}\nSession: {self.current_session_id}\n"
            self.connection_socket.sendall(reply.encode("utf-8"))

        # Error messages
        elif code == RespondType.FILE_NOT_FOUND_404:
            self.logger.error("404 NOT FOUND")
        elif code == RespondType.CON_ERR_500:
            self.logger.error("500 CONNECTION ERROR")
