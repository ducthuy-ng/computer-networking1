from msilib.schema import SelfReg
import tkinter as tk
import logging
from enum import Enum


class State(Enum):
    INIT = 0
    READY = 1
    PLAYING = 2


class ResourceHolder(tuple):
    play_icon: tk.PhotoImage
    pause_icon: tk.PhotoImage


class Client:
    def __init__(self, master: tk.Tk, server_addr: str, server_port: str, rtp_port: str, file_name: str):
        self.master = master
        self.server_addr = server_addr
        self.server_port = server_port
        self.rtp_port = rtp_port
        self.file_name = file_name
        self.rtsp_seq = 0
        self.session_id=0
        ## test case:
        """
        self.file_name="movie.Mjpeg"
        self.rtp_port="2500"
        self.session_id=123456
        """
        ##
        self.resource_holder = ResourceHolder

        self.current_state: State = State.INIT

        self._generate_layout()

    def setup_video(self, event=None):
        if self.current_state != State.INIT:
            logging.error("Video has already been setup")
        else:
            self.rtsp_seq=1
            logging.info("\n"+"C: SETUP "+self.file_name+" RTSP/1.0"+"\n"+"C: CSeq: "+str(self.rtsp_seq)+"\n"+"C: Transport: RTP/UDP; client_port= "+self.rtp_port)
            
            self.current_state = State.READY

    def play_video(self, event=None):
        if self.current_state == State.PLAYING:
            logging.error("The video is already playing")
        elif self.current_state == State.INIT:
            logging.error("No video to play, press setup to choose one")
        else:
            self.rtsp_seq=self.rtsp_seq+1
            logging.info("\n"+"C: PLAY "+self.file_name+" RTSP/1.0"+"\n"+"C: CSeq: "+str(self.rtsp_seq)+"\n"+"C: Session: "+str(self.session_id))
            self.current_state = State.PLAYING

    def pause_video(self, event=None):
        if self.current_state == State.INIT:
            logging.error("No video to pause, press setup to choose one")
        elif self.current_state == State.READY:
            logging.error("The video is already paused")
        else:
            self.rtsp_seq=self.rtsp_seq+1
            logging.info("\n"+"C: PAUSE "+self.file_name+" RTSP/1.0"+"\n"+"C: CSeq: "+str(self.rtsp_seq)+"\n"+"C: Session: "+str(self.session_id))
            self.current_state = State.READY

    def stop_video(self, event=None):
        if self.current_state == State.INIT:
            logging.error("No video to tear down")
        else:
            self.rtsp_seq=self.rtsp_seq+1
            logging.info("\n"+"C: TEARDOWN "+self.file_name+" RTSP/1.0"+"\n"+"C: CSeq: "+str(self.rtsp_seq)+"\n"+"C: Session: "+str(self.session_id))
            self.current_state = State.INIT

    def _generate_layout(self):
        ## Create log file
        logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
        ##
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


if __name__ == '__main__':
    root = tk.Tk()

    player = Client(root, "", "", "", "")
    player.master.title = "Test Video Player"
    player.master.mainloop()
