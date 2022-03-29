import logging
import socket
import threading
import tkinter as tk
from enum import Enum
from typing import Optional, Any
from PIL import Image, ImageTk
import io

from rtp_packet import RtpPacket

SERVER_ADDR = 'localhost'
SERVER_PORT = 2103

CLIENT_RECV_BUFFER = 1024
RTP_RECV_BUFFER = 20480


class ClientState(Enum):
    INIT = 0
    READY = 1
    PLAYING = 2


class ResourceHolder(tuple):
    play_icon: tk.PhotoImage
    pause_icon: tk.PhotoImage


class Client:
    def __init__(self, master: tk.Tk):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self._on_close)
        self.logger = logging.getLogger("streaming-app.client")

        self.connection_socket: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # RTP packet configuration
        self.rtp_socket: Optional[socket.socket] = None
        self.stream_stop_flag: threading.Event = threading.Event()

        self.resource_holder = ResourceHolder()

        self.opening_filename: str = "movie.Mjpeg"
        self.session_id: int = 0
        self.sequence_number: int = 0
        self.current_frame: int = 0
        self.current_state: ClientState = ClientState.INIT

        self._generate_layout()
        self.connect_to_server()

    def setup_video(self, event=None):
        if self.current_state != ClientState.INIT:
            self.logger.debug("Video has already been setup")
        else:
            self.logger.debug("Setting video up")

            self.setup_rtp()

            self.sequence_number += 1
            payload = f"SETUP {self.opening_filename} RTSP/1.0\n" \
                      f"CSeq: {self.sequence_number}\n" \
                      f"Transport: RTP/UDP; client_port= {self.rtp_socket.getsockname()[1]}\n"
            response = self._parse_simple_rtsp_response(self.send_request_and_receive_response(payload))

            self.session_id = response['session_id']

            self.current_state = ClientState.READY

    def play_video(self, event=None):
        if self.current_state == ClientState.PLAYING:
            self.logger.debug("The video is already playing")
        elif self.current_state == ClientState.INIT:
            self.logger.debug("No video to play, press setup to choose one")
        else:
            self.logger.debug("Playing video")

            self.sequence_number += 1
            payload = f"PLAY {self.opening_filename} RTSP/1.0\n" \
                      f"CSeq: {self.sequence_number}\n" \
                      f"Session: {self.session_id}\n"
            response = self.send_request_and_receive_response(payload)

            self.current_state = ClientState.PLAYING

            threading.Thread(target=self.listen_rtp).start()
            self.stream_stop_flag.clear()

    def pause_video(self, event=None):
        if self.current_state == ClientState.INIT:
            self.logger.debug("The video is paused")
        elif self.current_state == ClientState.READY:
            self.logger.debug("The video is already paused")
        else:
            self.logger.debug("Pausing video")

            self.sequence_number += 1
            payload = f"PAUSE {self.opening_filename} RTSP/1.0\n" \
                      f"CSeq: {self.sequence_number}\n" \
                      f"Session: {self.session_id}\n"
            response = self.send_request_and_receive_response(payload)

            self.current_state = ClientState.READY
            self.stream_stop_flag.set()

    def stop_video(self, event=None):
        if self.current_state == ClientState.INIT:
            self.logger.debug("No video to tear down")
        else:
            self.logger.debug("Tearing video down")

            self.sequence_number += 1
            payload = f"TEARDOWN {self.opening_filename} RTSP/1.0\n" \
                      f"CSeq: {self.sequence_number}\n" \
                      f"Session: {self.session_id}\n"
            response = self.send_request_and_receive_response(payload)

            self.current_state = ClientState.INIT
            self.stream_stop_flag.set()

    def _generate_layout(self):
        self._load_resources()

        self.master.minsize(width=300, height=275)

        # Title label
        title_label = tk.Label(text="Hello")
        title_label.pack(side=tk.TOP, fill=tk.X)

        self.video_canvas: tk.Canvas = tk.Canvas(self.master)
        self.video_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=1)
        self.video_canvas.config(bg='white')

        # Bottom row container
        button_container = tk.Frame(self.master, height=50)
        button_container.pack(side=tk.TOP, fill=tk.X)
        button_container.pack_propagate(False)

        setup_btn = tk.Button(button_container, text="Setup")
        setup_btn.bind("<Button-1>", self.setup_video)
        setup_btn.pack(side=tk.LEFT, fill=tk.Y, anchor='e', expand=True)

        play_btn = tk.Button(button_container, image=self.resource_holder.play_icon)
        play_btn.bind("<Button-1>", self.play_video)
        play_btn.pack(side=tk.LEFT, fill=tk.Y)

        pause_btn = tk.Button(button_container, image=self.resource_holder.pause_icon)
        pause_btn.bind("<Button-1>", self.pause_video)
        pause_btn.pack(side=tk.LEFT, fill=tk.Y)

        teardown_btn = tk.Button(button_container, text="Teardown")
        teardown_btn.bind("<Button-1>", self.stop_video)
        teardown_btn.pack(side=tk.LEFT, fill=tk.Y, anchor='w', expand=True)

    def _load_resources(self):
        self.resource_holder.play_icon = tk.PhotoImage(file="res/outline_play_arrow_black_24dp.png")
        self.resource_holder.pause_icon = tk.PhotoImage(file="res/outline_pause_black_24dp.png")

    def _on_close(self):
        self.connection_socket.close()
        if self.rtp_socket:
            self.rtp_socket.close()
            self.rtp_socket = None

        self.master.destroy()

    def connect_to_server(self):
        self.connection_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.connection_socket.connect((SERVER_ADDR, SERVER_PORT))
        except TimeoutError:
            self.logger.error(f"Connection to {SERVER_ADDR} failed.")

    def send_request_and_receive_response(self, request: str) -> str:
        try:
            self.connection_socket.sendall(request.encode("utf-8"))

            response: bytes = self.connection_socket.recv(CLIENT_RECV_BUFFER)
            if not response:
                raise ConnectionError
        except ConnectionError:
            self.logger.error("Server has crashed, please try again")
            response = b''
        return response.decode("utf-8")

    def setup_rtp(self):
        self.rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtp_socket.settimeout(0.5)
        try:
            self.rtp_socket.bind(("", 0))
        except socket.error:
            print(f"An error occurred while setting UDP port, please try again later")

    def listen_rtp(self):
        self.logger.debug(f"Listening for streams")
        while True:
            try:
                data, addr = self.rtp_socket.recvfrom(RTP_RECV_BUFFER)
                if data:
                    rtp_packet = RtpPacket()
                    rtp_packet.decode(data)
            except TimeoutError:
                # Stop listening upon requesting PAUSE or TEARDOWN
                if self.stream_stop_flag.is_set():
                    if self.current_state == ClientState.INIT:
                        self.rtp_socket.shutdown()
                        self.rtp_socket.close()
                    break

    @staticmethod
    def _parse_simple_rtsp_response(data: str) -> dict[str, Any]:
        split_data = data.split('\n')

        parse_response = {'status_code': int(split_data[0].split(' ')[1]),
                          'sequence_number': int(split_data[1].split(' ')[1]),
                          'session_id': int(split_data[2].split(' ')[1])}

        return parse_response

    def _update_image(self, data):
        try:
            photo = ImageTk.PhotoImage(Image.open(io.BytesIO(data)))
        except:
            self.logger.error('Image error')
        self.video_canvas.create_image(0, 0, anchor=tk.CENTER, image=photo)
        self.video_canvas.image = photo


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    root = tk.Tk()

    player = Client(root)
    player.master.title = "Test Video Player"
    player.master.mainloop()
