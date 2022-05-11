import configparser
import errno
import io
import logging
import socket
import threading
import time
import tkinter as tk
from queue import SimpleQueue
from tkinter import messagebox
from tkinter import ttk
from typing import Optional, List

from PIL import Image, ImageTk

from client_utils import ClientState, RtspResponse, ServerDisconnected
from rtp_packet import RtpPacket


class ResourceHolder(tuple):
    play_icon: tk.PhotoImage
    pause_icon: tk.PhotoImage
    reconnect_icon: tk.PhotoImage
    setting_icon: tk.PhotoImage
    info_icon: tk.PhotoImage

    splash_screen: Image


class Client:
    def __init__(self, master: tk.Tk):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self._on_close)
        self.logger = logging.getLogger("streaming-app.client")

        self.connection_socket: Optional[socket.socket] = None
        self.stop_connect_event = threading.Event()

        # RTP packet configuration
        self.rtp_socket: Optional[socket.socket] = None
        self.stream_stop_flag: threading.Event = threading.Event()

        self.resource_holder = ResourceHolder()

        self.label_txt = tk.StringVar()

        self.opening_filename: str = "movie.Mjpeg"
        self.session_id: int = 0
        self.sequence_number: int = 0
        self.current_frame: int
        self.current_state = ClientState.DISCONNECTED

        self._generate_layout()
        self.master.after(250, self.connect_to_server)

        # Config Parser
        self.config_parser: configparser.ConfigParser = configparser.ConfigParser()
        self.config_parser.read("./config/client.cfg")

        # Canvas settings
        self.canvas_width: int = 0
        self.canvas_height: int = 0
        self.canvas_buffer = None
        self.video_buffer: Image = self.resource_holder.splash_screen
        self.canvas_image_queue: SimpleQueue = SimpleQueue()

    def setup_video(self, event=None):
        if self.current_state == ClientState.DISCONNECTED:
            messagebox.showerror("Error", "Not connected to a server")
        elif self.current_state != ClientState.INIT:
            messagebox.showerror("Error", "Video has already been setup")
        else:
            self.logger.debug("Setting video up")

            self.setup_rtp()

            self.sequence_number += 1
            payload = f"SETUP {self.opening_filename} RTSP/1.0\n" \
                      f"CSeq: {self.sequence_number}\n" \
                      f"Transport: RTP/UDP; client_port= {self.rtp_socket.getsockname()[1]}\n"
            try:
                response = RtspResponse(self.send_request(payload))
            except ServerDisconnected:
                self.logger.info("Server has disconnected")
                self.disconnect_from_server()
                return

            if response.status_code == 200:
                self.session_id = response.get_session_id()
                self.current_state = ClientState.READY
            elif response.status_code == 404:
                messagebox.showerror("Error", "Video file not found")
            elif response.status_code == 500:
                messagebox.showerror("Error", "Connection error, please try again later")
                self.disconnect_from_server()

    def play_video(self, event=None):
        if self.current_state == ClientState.DISCONNECTED:
            messagebox.showerror("Error", "Not connected to a server")
        elif self.current_state == ClientState.PLAYING:
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
                response = RtspResponse(self.send_request(payload))
            except ServerDisconnected:
                self.disconnect_from_server()
                return

            if response.status_code == 200:
                self.logger.debug(response.content)

                self.current_state = ClientState.PLAYING
                self.stream_stop_flag.clear()
                threading.Thread(target=self.listen_rtp).start()
            elif response.status_code == 404:
                messagebox.showerror("Error", "Video file not found")
            elif response.status_code == 500:
                messagebox.showerror("Error", "Connection error, please try again later")
                self.disconnect_from_server()

    def pause_video(self, event=None):
        if self.current_state == ClientState.DISCONNECTED:
            messagebox.showerror("Error", "Not connected to a server")
        elif self.current_state == ClientState.INIT or self.current_state == ClientState.READY:
            messagebox.showwarning("Warning", "The video is already paused")
        else:
            self.logger.debug("Pausing video")

            self.sequence_number += 1
            payload = f"PAUSE {self.opening_filename} RTSP/1.0\n" \
                      f"CSeq: {self.sequence_number}\n" \
                      f"Session: {self.session_id}\n"
            try:
                response = RtspResponse(self.send_request(payload))
            except ConnectionError:
                self.stream_stop_flag.set()
                self.disconnect_from_server()
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
                self.disconnect_from_server()

    def stop_video(self, event=None):
        if self.current_state == ClientState.DISCONNECTED:
            messagebox.showerror("Error", "Not connected to a server")
        elif self.current_state == ClientState.INIT:
            messagebox.showwarning("Warning", "No video to tear down")
        else:
            self.logger.debug("Tearing video down")

            self.sequence_number += 1
            payload = f"TEARDOWN {self.opening_filename} RTSP/1.0\n" \
                      f"CSeq: {self.sequence_number}\n" \
                      f"Session: {self.session_id}\n"

            try:
                response = RtspResponse(self.send_request(payload))
            except ServerDisconnected:
                self.disconnect_from_server()
                self.stream_stop_flag.set()
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

    def describe_video(self, event=None):
        if self.current_state == ClientState.DISCONNECTED:
            messagebox.showerror("Error", "Not connected to a server")
            return

        self.logger.debug("Sending DESCRIBE request")

        self.sequence_number += 1
        payload = f"DESCRIBE {self.opening_filename} RTSP/1.0\n" \
                  f"CSeq: {self.sequence_number}\n"

        try:
            response = RtspResponse(self.send_request(payload))
        except ConnectionError:
            self.stream_stop_flag.set()
            self.connect_to_server()
            self.sequence_number -= 1
            return

        if response.status_code == 200:
            self.logger.debug(response.get_other_line())
            DescribeWindow(self.master, response.get_other_line()[:-1])

    def _generate_layout(self):
        self._load_resources()

        self.master.minsize(width=300, height=300)

        # Title label
        title_container = tk.Frame(self.master)
        title_container.pack(side=tk.TOP, fill=tk.X)

        info_btn = tk.Button(title_container, image=self.resource_holder.info_icon,
                             height=30, width=30, command=self.describe_video)
        info_btn.pack(side=tk.LEFT, padx=8, pady=8)

        title_label = tk.Label(title_container, textvariable=self.label_txt)
        title_label.pack(side=tk.LEFT, fill=tk.X, expand=1)

        setting_btn = tk.Button(title_container, image=self.resource_holder.setting_icon,
                                height=30, width=30,
                                command=lambda: SettingWindow(self.master, self, self.config_parser))
        setting_btn.pack(side=tk.RIGHT, padx=8, pady=8)

        # Reconnect button
        reconnect_btn = tk.Button(title_container, image=self.resource_holder.reconnect_icon,
                                  height=30, width=30,
                                  command=self.reconnect_to_server)
        reconnect_btn.pack(side=tk.RIGHT, padx=2, pady=2)

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
        self.resource_holder.reconnect_icon = \
            tk.PhotoImage(file="res/outline_retry_black_24dp.png").subsample(2)
        self.resource_holder.setting_icon = \
            tk.PhotoImage(file="res/outline_settings_black_24dp.png").subsample(2)
        self.resource_holder.info_icon = \
            tk.PhotoImage(file="res/outline_info_black_24dp.png").subsample(2)

        self.resource_holder.splash_screen = Image.open("res/splash_screen.png")

    def _on_close(self):
        self.logger.debug("Shutting down")
        if self.current_state == ClientState.PLAYING:
            self.stop_video()

        self.disconnect_from_server()
        if self.rtp_socket:
            self.rtp_socket.close()

        self.master.after(250, self.master.destroy)

    def _on_window_resize(self, event: tk.Event):
        self.canvas_width = event.width
        self.canvas_height = event.height

        self.video_buffer = self.video_buffer.resize((self.canvas_width, self.canvas_height))
        self._update_image()

    def connect_to_server(self):
        def _connect_to_server():
            self.label_txt.set("Connecting...")
            counter = 1
            connection_option = self.config_parser['Connection']
            # if self.connection_socket.
            while counter < self.config_parser.getint('Connection', 'num_of_retry'):
                try:
                    if self.stop_connect_event.is_set():
                        return
                    self.connection_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.connection_socket.settimeout(5)
                    self.logger.debug(f"Trying to connect to server. Attempt: {counter}")
                    self.connection_socket.connect((connection_option['server_addr'],
                                                    connection_option.getint('server_port')))
                except OSError as err:
                    if err.errno != errno.ECONNREFUSED:
                        raise err
                    counter += 1
                    self.connection_socket = None
                    time.sleep(self.config_parser.getint('Connection', 'delay_between_retry'))
                else:
                    self.current_state = ClientState.INIT
                    self.label_txt.set("Connected")
                    self.sequence_number = 0

                    return

            if counter == self.config_parser.getint('Connection', 'num_of_retry'):
                self.disconnect_from_server()
                messagebox.showerror("Error", "Can't connect to server, please retry later")

        self.stop_connect_event.clear()
        threading.Thread(target=_connect_to_server).start()

    def disconnect_from_server(self):
        self.stop_connect_event.set()
        if self.connection_socket:
            try:
                self.connection_socket.shutdown(socket.SHUT_WR)
                self.connection_socket.close()
            except OSError as err:
                if err.errno != errno.ENOTCONN:
                    raise err

            self.connection_socket = None
        self.current_state = ClientState.DISCONNECTED
        self.label_txt.set("Disconnected")
        self.logger.debug("Disconnected from server")

    def reconnect_to_server(self):
        self.disconnect_from_server()
        self.connect_to_server()

    def send_request(self, request: str) -> str:
        try:
            self.connection_socket.sendall(request.encode("utf-8"))
        except OSError as err:
            if err.errno == errno.EPIPE:
                raise ServerDisconnected()
            else:
                raise err

        response: bytes = self.connection_socket.recv(self.config_parser.getint('Client', 'rtsp_buffer_size'))
        if not response:
            raise ServerDisconnected()
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
        self.rtp_socket.settimeout(0.5)
        while not self.stream_stop_flag.is_set():
            try:
                data, addr = self.rtp_socket.recvfrom(self.config_parser.getint('Client', 'rtp_buffer_size'))
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
                        self.rtp_socket.close()
                    break

    def _update_image(self, data: Optional[bytes] = None):
        if data:
            self.video_buffer = \
                Image.open(io.BytesIO(data)).resize((self.canvas_width, self.canvas_height))

        self.canvas_buffer = ImageTk.PhotoImage(self.video_buffer)
        self.canvas_image_queue.put(
            self.video_canvas.create_image(0, 0, anchor="nw", image=self.canvas_buffer))

        if self.canvas_image_queue.qsize() > 5:
            self.video_canvas.delete(self.canvas_image_queue.get())


class SettingWindow(tk.Toplevel):
    def __init__(self, parent: tk.Tk, client: Client, client_settings: configparser.ConfigParser):
        super().__init__(parent)
        self.client: Client = client
        self.client_settings: configparser.ConfigParser = client_settings
        self.title("Settings")

        self.server_name_entry: ttk.Entry = self._make_entry("Server Name:")
        self.server_name_entry.insert(0, client_settings.get("Connection", "server_addr"))

        self.server_port_entry: ttk.Entry = self._make_entry("Server Port:")
        self.server_port_entry.insert(0, client_settings.getint("Connection", "server_port"))

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(side=tk.TOP, fill=tk.X, padx=8)

        self.num_of_retry_entry: ttk.Entry = self._make_entry("Num of Retries:")
        self.num_of_retry_entry.insert(0, client_settings.getint("Connection", "num_of_retry"))

        self.delay_between_retry_entry: ttk.Entry = self._make_entry("Delay of retry:")
        self.delay_between_retry_entry.insert(0, client_settings.getint("Connection", "delay_between_retry"))

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(side=tk.TOP, fill=tk.X, padx=8)

        self.rtsp_buffer_size_entry: ttk.Entry = self._make_entry("RTSP buffer size:")
        self.rtsp_buffer_size_entry.insert(0, client_settings.getint("Client", "rtsp_buffer_size"))

        self.rtp_buffer_size_entry: ttk.Entry = self._make_entry("RTP buffer size:")
        self.rtp_buffer_size_entry.insert(0, client_settings.getint("Client", "rtp_buffer_size"))

        button_container = ttk.Frame(self)
        button_container.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=8)

        save_btn = ttk.Button(button_container, text="Save", default=tk.ACTIVE, command=self.save)
        save_btn.pack(side=tk.RIGHT)

        cancel_btn = ttk.Button(button_container, text="Cancel", default=tk.NORMAL, command=self.destroy)
        cancel_btn.pack(side=tk.RIGHT)

    def save(self):
        self.client_settings.set("Connection", "server_addr", self.server_name_entry.get())
        self.client_settings.set("Connection", "server_port", self.server_port_entry.get())
        self.client_settings.set("Connection", "num_of_retry", self.num_of_retry_entry.get())
        self.client_settings.set("Connection", "delay_between_retry", self.delay_between_retry_entry.get())
        self.client_settings.set("Client", "rtsp_buffer_size", self.rtsp_buffer_size_entry.get())
        self.client_settings.set("Client", "rtp_buffer_size", self.rtp_buffer_size_entry.get())

        with open("config/client.cfg", 'w') as config_file:
            self.client_settings.write(config_file)

        if self.client.current_state != ClientState.INIT:
            self.client.stop_video()
        self.client.master.after(100, self.client.reconnect_to_server)
        self.destroy()

    def _make_entry(self, caption: str, **options) -> ttk.Entry:
        entry_container = ttk.Frame(self)
        entry_container.pack(side=tk.TOP, fill=tk.X, padx=8, pady=8)

        ttk.Label(entry_container, text=caption).pack(side=tk.LEFT)

        entry = ttk.Entry(entry_container, **options)
        entry.pack(side=tk.RIGHT)
        return entry


class DescribeWindow(tk.Toplevel):
    def __init__(self, parent: tk.Tk, fields_list: List[str]):
        super().__init__(parent)

        self.title("Info")

        for field in fields_list:
            attribute, value = field.split('=', maxsplit=1)
            self.add_field(attribute.title() + ':', value)

    def add_field(self, attribute: str, value: str):
        field_container = ttk.Frame(self)
        field_container.pack(side=tk.TOP, fill=tk.X, padx=8, pady=8)

        ttk.Label(field_container, text=attribute).pack(side=tk.LEFT)
        ttk.Label(field_container, text=value).pack(side=tk.LEFT)


if __name__ == '__main__':
    logger = logging.getLogger("streaming-app.client")
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(asctime)s %(name)s %(levelname)s: %(message)s')

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    root = tk.Tk()

    player = Client(root)
    player.master.title("Test Video Player")
    player.master.mainloop()
