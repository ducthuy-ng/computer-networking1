import io
import logging
import socket
import threading
import time
import tkinter as tk
from queue import SimpleQueue
from tkinter import messagebox
from typing import Optional

from PIL import Image, ImageTk

from client_utils import ClientState, RtspResponse
from rtp_packet import RtpPacket

SERVER_ADDR = '127.0.0.1'
SERVER_PORT = 2103
NUM_OF_RETRY = 5
DELAY_BETWEEN_RETRY = 2

CLIENT_RECV_BUFFER = 1024
RTP_RECV_BUFFER = 20480


class ResourceHolder(tuple):
    play_icon: tk.PhotoImage
    pause_icon: tk.PhotoImage

    splash_screen: Image


class Client:
    def __init__(self, master: tk.Tk):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self._on_close)
        self.logger = logging.getLogger("streaming-app.client")

        self.connection_socket: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connection_socket.settimeout(0.1)

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
        self.master.after(1000, self.connect_to_server)

        # Canvas settings
        self.canvas_width: int = 0
        self.canvas_height: int = 0
        self.canvas_buffer = None
        self.video_buffer: Image = self.resource_holder.splash_screen
        self.canvas_image_prev_id_queue: SimpleQueue = SimpleQueue()

    def setup_video(self, event=None):
        if self.current_state != ClientState.INIT:
            messagebox.showerror("Error", "Video has already been setup")
        else:
            self.logger.debug("Setting video up")

            self.setup_rtp()

            self.sequence_number += 1
            payload = f"SETUP {self.opening_filename} RTSP/1.0\n" \
                      f"CSeq: {self.sequence_number}\n" \
                      f"Transport: RTP/UDP; client_port= {self.rtp_socket.getsockname()[1]}\n"
            try:
                response = RtspResponse(self.send_request_and_receive_response(payload))
            except ConnectionError:
                self.connect_to_server()
                return

            if response.status_code == 200:
                self.session_id = response.get_session_id()
                self.current_state = ClientState.READY
            elif response.status_code == 404:
                messagebox.showerror("Error", "Video file not found")
            elif response.status_code == 500:
                messagebox.showerror("Error", "Connection error, please try again later")
                self._on_close()

    def play_video(self, event=None):
        if self.current_state == ClientState.PLAYING:
            messagebox.showwarning("Warning", "The video is already playing")
        elif self.current_state == ClientState.INIT:
            messagebox.showwarning("Warning", "No video to play, press SETUP to choose one")
        else:
            self.logger.debug("Playing video")

            self.sequence_number += 1
            payload = f"PLAY {self.opening_filename} RTSP/1.0\n" \
                      f"CSeq: {self.sequence_number}\n" \
                      f"Session: {self.session_id}\n"
            try:
                response = RtspResponse(self.send_request_and_receive_response(payload))
            except ConnectionError:
                self.connect_to_server()
                self.sequence_number -= 1
                return

            if response.status_code == 200:
                self.logger.debug(response.content)

                self.current_state = ClientState.PLAYING
                threading.Thread(target=self.listen_rtp).start()
                self.stream_stop_flag.clear()
            elif response.status_code == 404:
                messagebox.showerror("Error", "Video file not found")
            elif response.status_code == 500:
                messagebox.showerror("Error", "Connection error, please try again later")
                self._on_close()

    def pause_video(self, event=None):
        if self.current_state == ClientState.INIT or self.current_state == ClientState.READY:
            messagebox.showwarning("Warning", "The video is already paused")
        else:
            self.logger.debug("Pausing video")

            self.sequence_number += 1
            payload = f"PAUSE {self.opening_filename} RTSP/1.0\n" \
                      f"CSeq: {self.sequence_number}\n" \
                      f"Session: {self.session_id}\n"
            try:
                response = RtspResponse(self.send_request_and_receive_response(payload))
            except ConnectionError:
                self.stream_stop_flag.set()
                self.connect_to_server()
                self.sequence_number -= 1
                return

            if response.status_code == 200:
                self.logger.debug(response.content)

                self.current_state = ClientState.READY
                self.stream_stop_flag.set()
            elif response.status_code == 404:
                messagebox.showerror("Error", "Video file not found")
            elif response.status_code == 500:
                messagebox.showerror("Error", "Connection error, please try again later")
                self._on_close()

    def stop_video(self, event=None):
        if self.current_state == ClientState.INIT:
            messagebox.showwarning("Warning", "No video to tear down")
        else:
            self.logger.debug("Tearing video down")

            self.sequence_number += 1
            payload = f"TEARDOWN {self.opening_filename} RTSP/1.0\n" \
                      f"CSeq: {self.sequence_number}\n" \
                      f"Session: {self.session_id}\n"
            try:
                response = RtspResponse(self.send_request_and_receive_response(payload))
            except ConnectionError:
                self.stream_stop_flag.set()
                self.connect_to_server()
                self.sequence_number -= 1
                return

            if response.status_code == 200:
                self.logger.debug(response.content)

                # Re-set splash screen
                self.video_buffer = self.resource_holder.splash_screen.resize((self.canvas_width, self.canvas_height))
                self._update_image()

                self.current_state = ClientState.INIT
                self.stream_stop_flag.set()
            elif response.status_code == 404:
                messagebox.showerror("Error", "Video file not found")
            elif response.status_code == 500:
                messagebox.showerror("Error", "Connection error, please try again later")
                self._on_close()

    def _generate_layout(self):
        self._load_resources()

        self.master.minsize(width=300, height=275)

        # Title label
        title_label = tk.Label(text="Hello")
        title_label.pack(side=tk.TOP, fill=tk.X)

        self.video_canvas: tk.Canvas = tk.Canvas(self.master)
        self.video_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=1)
        self.video_canvas.config(bg='white')
        self.video_canvas.bind("<Configure>", self._on_window_resize)

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

        self.resource_holder.splash_screen = Image.open("res/splash_screen.png")

    def _on_close(self):
        self.connection_socket.close()
        if self.rtp_socket:
            self.rtp_socket.close()
            self.rtp_socket = None

        self.master.destroy()

    def _on_window_resize(self, event: tk.Event):
        self.canvas_width = event.width
        self.canvas_height = event.height

        self.video_buffer = self.video_buffer.resize((self.canvas_width, self.canvas_height))
        self._update_image()

    def connect_to_server(self):
        counter = 1
        while counter < NUM_OF_RETRY:
            try:
                self.logger.debug(f"Trying to connect to server. Attempt: {counter}")
                self.connection_socket.connect((SERVER_ADDR, SERVER_PORT))
            except socket.error:
                self.connection_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                counter += 1
                time.sleep(DELAY_BETWEEN_RETRY)
            else:
                break

        if counter == NUM_OF_RETRY:
            messagebox.showerror("Error", "Can't connect to server, please retry later")
            self._on_close()

    def send_request_and_receive_response(self, request: str) -> str:
        try:
            self.connection_socket.sendall(request.encode("utf-8"))

            response: bytes = self.connection_socket.recv(CLIENT_RECV_BUFFER)
            if not response:
                raise ConnectionError
        except ConnectionError:
            self.logger.error("Disconnected to Server")

            response = b''
        return response.decode("utf-8")

    def setup_rtp(self):
        self.rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtp_socket.settimeout(0.5)
        try:
            self.rtp_socket.bind(("", 0))
        except socket.error:
            print("An error occurred while setting UDP port, please try again later")

    def listen_rtp(self):
        self.logger.debug("Listening for streams")
        while True:
            try:
                data, addr = self.rtp_socket.recvfrom(RTP_RECV_BUFFER)
                if data:
                    rtp_packet = RtpPacket()
                    rtp_packet.decode(data)

                    # End of stream
                    if rtp_packet.payload == bytes(5):
                        self.logger.debug("Stream has ended")
                        self.stop_video()
                        break

                    self._update_image(rtp_packet.payload)
            except TimeoutError:
                # Stop listening upon requesting PAUSE or TEARDOWN
                if self.stream_stop_flag.is_set():
                    if self.current_state == ClientState.INIT:
                        # self.rtp_socket.shutdown()
                        self.rtp_socket.close()
                    break

    def _update_image(self, data: Optional[bytes] = None):
        if data:
            self.video_buffer = \
                Image.open(io.BytesIO(data)).resize((self.canvas_width, self.canvas_height))

        self.canvas_buffer = ImageTk.PhotoImage(self.video_buffer)
        self.canvas_image_prev_id_queue.put(
            self.video_canvas.create_image(0, 0, anchor="nw", image=self.canvas_buffer))

        if self.canvas_image_prev_id_queue.qsize() > 5:
            self.video_canvas.delete(self.canvas_image_prev_id_queue.get())


if __name__ == '__main__':
    logger = logging.getLogger("streaming-app.client")
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(asctime)s %(name)s %(levelname)s: %(message)s')

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    root = tk.Tk()

    player = Client(root)
    player.master.title = "Test Video Player"
    player.master.mainloop()
