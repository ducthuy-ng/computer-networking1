import logging
import pathlib
import random
import socket
import threading
from enum import Enum
from typing import Tuple, Optional

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
    def __init__(self, connection: socket.socket, client_addr: Tuple, video_path: pathlib.Path):
        super(ServerWorker, self).__init__()

        self.connection_socket = connection
        self.client_addr = client_addr
        self.video_path: pathlib.Path = video_path

        self.current_session_id: Optional[int] = None
        self.streaming_thread = threading.Thread(target=self._stream_video)

        self.stream_handler: Optional[VideoStream] = None
        self.stream_stop_flag: threading.Event = threading.Event()
        self.state = ServerState.INIT

        self.rtp_port: Optional[int] = None
        self.rtp_socket: Optional[socket.socket] = None

        self.logger = logging.getLogger(__name__)

    def _stream_video(self):
        """Private method for sending RTP packets"""
        pass

    def run(self) -> None:
        """
        Receive RTSP request from the client.
        """
        try:
            while self.state != ServerState.STOP:
                data: bytes = self.connection_socket.recv(256)
                if not data:
                    raise ConnectionError

                print("Data received:\n" + data.decode("utf-8"))
                self.process_rtsp_request(data.decode("utf-8"))
        except ConnectionError:
            self._cleanup()

    def process_rtsp_request(self, data):
        """Process RTSP request sent from the client."""
        # Get the request type
        request = data.split('\n')
        line1 = request[0].split(' ')
        request_type = RequestType(line1[0])

        # Get the media file name
        filename = line1[1]

        # Get the RTSP sequence number
        seq = request[1].split(' ')

        # Process SETUP request
        if request_type == RequestType.SETUP:
            if self.state == ServerState.INIT:
                # Update state
                self.logger.debug("processing SETUP")

                try:
                    self.stream_handler = VideoStream(self.video_path / filename)
                    self.state = ServerState.READY
                except IOError:
                    self.reply_rtsp(RespondType.FILE_NOT_FOUND_404, seq[1])

                # Generate a randomized RTSP session ID
                self.current_session_id = random.randint(100000, 999999)

                # Send RTSP reply
                self.reply_rtsp(RespondType.OK_200, seq[1])

                # Get the RTP/UDP port from the last line
                self.rtp_port = request[2].split(' ')[3]

        # Process PLAY request
        elif request_type == RequestType.PLAY:
            if self.state == ServerState.READY:
                self.logger.debug("processing PLAY")
                self.state = ServerState.PLAYING

                # Create a new socket for RTP/UDP
                # self.rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

                self.reply_rtsp(RespondType.OK_200, seq[1])

                # # Create a new thread and start sending RTP packets
                # self.streaming_thread.start()

        # Process PAUSE request
        elif request_type == RequestType.PAUSE:
            if self.state == ServerState.PLAYING:
                self.logger.debug("processing PAUSE")
                self.state = ServerState.READY

                self.stream_stop_flag.set()

                self.reply_rtsp(RespondType.OK_200, seq[1])

        # Process TEARDOWN request
        elif request_type == RequestType.TEARDOWN:
            self.state = ServerState.INIT
            print("processing TEARDOWN\n")

            self.stream_stop_flag.set()

            self.reply_rtsp(RespondType.OK_200, seq[1])

            # Close the RTP socket
            # self.rtp_socket.close()
            # self.rtp_socket = None

    def _cleanup(self):
        self.logger.info(f"Client {self.client_addr} disconnected")
        self.connection_socket.close()
        self.state = ServerState.STOP

    def reply_rtsp(self, code: RespondType, seq: int) -> None:
        """Send RTSP reply to the client."""
        if code == RespondType.OK_200:
            # print("200 OK")
            reply = f"RTSP/1.0 200 OK\nCSeq: {seq}\nSession: {self.current_session_id}\n"
            try:
                self.connection_socket.sendall(reply.encode("utf-8"))
            except ConnectionError:
                self._cleanup()

        # Error messages
        elif code == RespondType.FILE_NOT_FOUND_404:
            print("404 NOT FOUND")
        elif code == RespondType.CON_ERR_500:
            print("500 CONNECTION ERROR")
