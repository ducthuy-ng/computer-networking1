import logging
import pathlib
import random
import socket
import threading
from enum import Enum
from typing import Tuple, Optional
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
        self.streaming_thread = None

        self.stream_handler: Optional[VideoStream] = None
        self.stream_stop_flag: threading.Event = threading.Event()
        self.state = ServerState.INIT

        self.rtp_port: Optional[int] = None
        self.rtp_socket: Optional[socket.socket] = None

        self.logger = logging.getLogger(__name__)

    def _stream_video(self):
        """Private method for sending RTP packets"""

        # function to build an RTP packet
        build_rtp_packet = lambda payload, frame_nbr : RtpPacket.encode(
            version=2,
            padding=0,
            extension=0,
            cc=0,
            marker=0,
            payload_type=26, # MJPEG
            seq_num=frame_nbr,
            ssrc=0,
            payload=payload
        )
        
        while True:
            # 0.05s interval
            self.stream_stop_flag.wait(0.05)

            # terminate this thread when the client hits PAUSE or TEARDOWN
            if self.stream_stop_flag.is_set():
                break
            
            # send rtp packet
            payload = self.stream_handler.next_frame()
            if payload:
                frame_nbr = self.stream_handler.frame_nbr()
                try:
                    self.rtp_socket.sendto(
                        build_rtp_packet(payload, frame_nbr), 
                        (self.client_addr[0], self.rtp_port)
                    )
                except:
                    print("Connection Error")

    def run(self) -> None:
        """
        Receive RTSP request from the client.
        """
        while True:
            data = self.connection_socket.recv(256)
            if not data:
                self.logger.info(f"{self.client_addr[0]} has disconnected")
                break

            print("Data received:\n" + data.decode("utf-8"))
            self.process_rtsp_request(data.decode("utf-8"))

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
                self.rtp_port = int(request[2].split(' ')[3])

                # Set up RTP port for streaming video
                self.rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


        # Process PLAY request
        elif request_type == RequestType.PLAY:
            if self.state == ServerState.READY:
                self.logger.debug("processing PLAY")
                self.state = ServerState.PLAYING

                self.reply_rtsp(RespondType.OK_200, seq[1])

                # Create a new thread and start sending RTP packets

                self.streaming_thread = threading.Thread(target=self._stream_video)
                self.streaming_thread.start()
                    

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
            self.rtp_socket.close()
            self.rtp_socket = None

    def reply_rtsp(self, code: RespondType, seq: int) -> None:
        """Send RTSP reply to the client."""
        if code == RespondType.OK_200:
            # print("200 OK")
            reply = f"RTSP/1.0 200 OK\nCSeq: {seq}\nSession: {self.current_session_id}\n"
            self.connection_socket.send(reply.encode())

        # Error messages
        elif code == RespondType.FILE_NOT_FOUND_404:
            print("404 NOT FOUND")
        elif code == RespondType.CON_ERR_500:
            print("500 CONNECTION ERROR")
