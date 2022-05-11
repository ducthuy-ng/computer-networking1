class VideoStream:
    def __init__(self, filename):
        self.filename = filename
        try:
            self.file = open(filename, 'rb')
        except Exception:
            raise IOError
        self._frame_num: int = 0

    def next_frame(self) -> bytes:
        """Get next frame."""
        data = self.file.read(5)  # Get the frame_length from the first 5 bits
        if data:
            frame_length = int(data)

            # Read the current frame
            data = self.file.read(frame_length)
            self._frame_num += 1
        return data

    def frame_nbr(self) -> int:
        """Get frame number."""
        return self._frame_num

    def __del__(self):
        """Destructor."""
        self.file.close()
