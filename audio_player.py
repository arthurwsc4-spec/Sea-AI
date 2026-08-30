import ctypes
import itertools
import threading
import time

_POLL_SECONDS = 0.1
_alias_counter = itertools.count()


class AudioPlaybackError(RuntimeError):
    pass


class AudioPlayer:
    def __init__(self):
        try:
            self._winmm = ctypes.windll.winmm
        except (AttributeError, OSError) as e:
            raise AudioPlaybackError(f"winmm.dll unavailable: {e}")
        self._lock = threading.Lock()

    def _send(self, command):
        buffer = ctypes.create_unicode_buffer(256)
        code = self._winmm.mciSendStringW(command, buffer, 255, 0)
        if code:
            message = ctypes.create_unicode_buffer(256)
            self._winmm.mciGetErrorStringW(code, message, 255)
            raise AudioPlaybackError(message.value or f"MCI error {code}")
        return buffer.value

    def play(self, path, should_continue=lambda: True):
        """Play `path` and block until it ends, or until should_continue() is False."""
        alias = f"seaai{next(_alias_counter)}"
        with self._lock:
            self._send(f'open "{path}" type mpegvideo alias {alias}')
            try:
                self._send(f"play {alias}")
                while self._send(f"status {alias} mode") == "playing":
                    if not should_continue():
                        break
                    time.sleep(_POLL_SECONDS)
            finally:
                try:
                    self._send(f"close {alias}")
                except AudioPlaybackError:
                    pass
