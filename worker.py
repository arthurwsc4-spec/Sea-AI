import os
import asyncio
import tempfile
import queue
import edge_tts
import speech_recognition as sr
from PyQt6.QtCore import QObject, pyqtSignal
from google import genai
from google.genai import types
from dotenv import load_dotenv
from pypdf import PdfReader
from audio_player import AudioPlaybackError, AudioPlayer
from mic_backend import SoundDeviceMicrophone

load_dotenv()
MODEL = "gemini-3.7-flash"
REQUEST_TIMEOUT_MS = 15_000
LISTEN_SLICE_SECONDS = 0.5  # how often the mic loop rechecks the toggle and the queue
IDLE_POLL_SECONDS = 0.25    # how often the chat-only loop rechecks for input
MAX_HISTORY_CHARS = 200_000  # roughly 50k tokens, well inside any Gemini context window

class SeaAIWorker(QObject):
    state_changed = pyqtSignal(str)
    user_text_received = pyqtSignal(str)
    reply_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    mic_availability_changed = pyqtSignal(bool)
    finished = pyqtSignal()

    def __init__(self, content_path=None):
        super().__init__()

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set in .env")
        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
        )

        if content_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            content_path = os.path.join(script_dir, "content.txt")

        try:
            with open(content_path, "r", encoding="utf-8") as f:
                self.system_prompt = f.read().strip()
        except Exception as e:
            raise RuntimeError(f"Could not read '{content_path}': {e}")
        if not self.system_prompt:
            raise RuntimeError(f"'{content_path}' is empty; it holds the system prompt")

        self._setup_microphone(os.getenv("MIC_NAME_HINT"))

        self.history = []
        self.recognizer = sr.Recognizer()
        self.ai_voice = "pt-BR-FranciscaNeural"
        self.text_queue = queue.Queue()
        self._running = True
        self.listening_enabled = True

        try:
            self.player = AudioPlayer()
        except AudioPlaybackError as e:
            raise RuntimeError(f"Audio output device not available: {e}")

    def _setup_microphone(self, name_hint):
        """Pick an input device. Falls back to the system default, then to chat only."""
        try:
            self.mic_device_index = SoundDeviceMicrophone.find_device_index(name_hint)
            with SoundDeviceMicrophone(device_index=self.mic_device_index):
                pass
            self.mic_available = True
            self._mic_error = None
        except Exception as e:
            self.mic_device_index = None
            self.mic_available = False
            self._mic_error = str(e)

    def stop(self):
        self._running = False

    def submit_text(self, text):
        text = text.strip()
        if text:
            self.text_queue.put(text)

    def run(self):
        if not self.mic_available:
            self.error_occurred.emit(
                f"Microphone unavailable ({self._mic_error}). Use the chat panel to type instead."
            )

        while self._running:
            try:
                if not self._step():
                    break
            except Exception as e:
                # One bad turn must not kill the thread and leave a dead window.
                self.error_occurred.emit(f"Unexpected error: {e}")

        self.state_changed.emit("Idle")
        self.finished.emit()

    def _step(self):
        """Run one listen/reply cycle. Returns False when the user asks to quit."""
        self.state_changed.emit("Listening")
        text = self._get_input()
        if text is None:
            return True

        self.user_text_received.emit(text)

        if text.lower() in ("sair", "exit"):
            return False

        if text.lower().startswith("/pdf "):
            self._handle_pdf(text[5:].strip())
            return True

        self.history.append(self._message("user", text))
        self._trim_history()

        self.state_changed.emit("Thinking")
        reply = self._get_reply()
        if reply is None:
            return True

        self.reply_ready.emit(reply)

        self.state_changed.emit("Speaking")
        self._speak(reply)
        return True

    @staticmethod
    def _message(role, text):
        return {"role": role, "parts": [{"text": text}]}

    def _trim_history(self):
        """Drop the oldest turns so a long session (or a big PDF) can't grow the
        request past the model's context window and start failing outright."""
        total = sum(len(m["parts"][0]["text"]) for m in self.history)
        dropped = 0
        while total > MAX_HISTORY_CHARS and len(self.history) > 1:
            total -= len(self.history.pop(0)["parts"][0]["text"])
            dropped += 1
        if dropped:
            self.error_occurred.emit(
                f"Dropped {dropped} older message(s) to stay within the context limit."
            )

    def _get_input(self):
        try:
            return self.text_queue.get_nowait()
        except queue.Empty:
            pass

        if not self.mic_available or not self.listening_enabled:
            try:
                return self.text_queue.get(timeout=IDLE_POLL_SECONDS)
            except queue.Empty:
                return None

        return self._listen_mic()

    def _listen_mic(self):
        """Wait for a spoken phrase, polling in short slices so that toggling the
        mic off, typing a message, or closing the window is acted on right away.
        Once speech starts it is captured whole, so nobody gets cut off."""
        audio = None
        try:
            with SoundDeviceMicrophone(device_index=self.mic_device_index) as source:
                while self._running and self.listening_enabled:
                    if not self.text_queue.empty():
                        return None  # a typed message takes priority
                    try:
                        audio = self.recognizer.listen(
                            source, timeout=LISTEN_SLICE_SECONDS, phrase_time_limit=15
                        )
                        break
                    except sr.WaitTimeoutError:
                        continue
        except Exception as e:
            self.mic_available = False
            self.mic_availability_changed.emit(False)
            self.error_occurred.emit(f"Microphone error, switching to chat only: {e}")
            return None

        if audio is None or not self.text_queue.empty():
            return None  # don't spend a network round trip on noise the user pre-empted

        try:
            return self.recognizer.recognize_google(audio, language="pt-BR")
        except sr.UnknownValueError:
            self.error_occurred.emit("Could not understand the audio.")
            return None
        except sr.RequestError as e:
            self.error_occurred.emit(f"Could not reach the recognition service: {e}")
            return None

    def _handle_pdf(self, pdf_path):
        if not os.path.isfile(pdf_path):
            self.error_occurred.emit(f"File not found: {pdf_path}")
            return

        try:
            reader = PdfReader(pdf_path)
            pages = [page.extract_text() for page in reader.pages if page.extract_text()]
        except Exception as e:
            self.error_occurred.emit(f"Could not read the PDF: {e}")
            return

        if not pages:
            self.error_occurred.emit("Could not extract any text from the PDF.")
            return

        text_pdf = "\n".join(pages)
        self.history.append(self._message(
            "user",
            f'Content from the extracted PDF "{pdf_path}":\n{text_pdf}',
        ))
        self._trim_history()

    def _get_reply(self):
        """Return the model's reply, or None. On failure the turn is rolled back
        so a retry doesn't stack consecutive user messages in the history."""
        try:
            response = self.client.models.generate_content(
                model=MODEL,
                contents=self.history,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    temperature=0.7,
                    max_output_tokens=1024,
                ),
            )
        except Exception as e:
            self.history.pop()
            self.error_occurred.emit(f"Gemini API error: {e}")
            return None

        reply = (response.text or "").strip()
        if not reply:
            self.history.pop()
            self.error_occurred.emit("The model returned an empty reply.")
            return None

        self.history.append(self._message("model", reply))
        return reply

    def _speak(self, text):
        output_path = None
        try:
            tmp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            output_path = tmp_file.name
            tmp_file.close()

            communicate = edge_tts.Communicate(text, self.ai_voice, rate="-10%")
            try:
                asyncio.run(asyncio.wait_for(communicate.save(output_path), timeout=15.0))
            except asyncio.TimeoutError:
                self.error_occurred.emit("TTS request timed out after 15s.")
                return

            self.player.play(output_path, should_continue=lambda: self._running)
        except Exception as e:
            self.error_occurred.emit(f"TTS playback failed: {e}")
        finally:
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass  # Windows may still hold the handle; it lands in %TEMP%

    def set_listening_enabled(self, enabled: bool):
        self.listening_enabled = enabled
