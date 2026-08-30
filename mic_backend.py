import speech_recognition as sr
import sounddevice as sd

class SoundDeviceMicrophone(sr.AudioSource):
    SAMPLE_WIDTH = 2  # 16-bit signed samples
    CHUNK = 1024

    def __init__(self, device_index=None, sample_rate=None, chunk_size=CHUNK):
        info = sd.query_devices(device_index, "input")
        if info["max_input_channels"] < 1:
            raise OSError(f"Device {device_index} has no input channels")

        self.device_index = device_index
        self.SAMPLE_RATE = int(sample_rate or info["default_samplerate"])
        self.CHUNK = chunk_size
        self.stream = None
        self._raw_stream = None

    @staticmethod
    def list_input_devices():
        """Return [(index, name)] for every device that can capture audio."""
        return [
            (index, device["name"])
            for index, device in enumerate(sd.query_devices())
            if device["max_input_channels"] > 0
        ]

    @classmethod
    def find_device_index(cls, name_hint):
        if not name_hint:
            return None
        hint = name_hint.lower()
        for index, name in cls.list_input_devices():
            if hint in name.lower():
                return index
        return None

    def __enter__(self):
        if self.stream is not None:
            raise RuntimeError("This audio source is already inside a context manager")

        self._raw_stream = sd.RawInputStream(
            samplerate=self.SAMPLE_RATE,
            blocksize=self.CHUNK,
            device=self.device_index,
            channels=1,
            dtype="int16",
        )
        self._raw_stream.start()
        self.stream = _SoundDeviceStream(self._raw_stream)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stream = None
        try:
            self._raw_stream.stop()
        finally:
            self._raw_stream.close()
            self._raw_stream = None


class _SoundDeviceStream:
    """Adapts RawInputStream to the .read(n) -> bytes interface Recognizer expects."""

    def __init__(self, raw_stream):
        self._raw_stream = raw_stream

    def read(self, size):
        data, _overflowed = self._raw_stream.read(size)
        return bytes(data)
