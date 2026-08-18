import os
import asyncio
import tempfile
import queue

import edge_tts
import pygame
import speech_recognition as sr
from PyQt6.QtCore import QObject, pyqtSignal
from groq import Groq
from dotenv import load_dotenv
from pypdf import PdfReader

load_dotenv()

class SeaAIWorker(QObject):
    state_changed = pyqtSignal(str)
    user_text_received = pyqtSignal(str)
    reply_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()

    @staticmethod
    def _find_mic_device_index(name_hint):
        names = sr.Microphone.list_microphone_names()
        for index, name in enumerate(names):
            if name_hint.lower() in name.lower():
                return index
        return None

    def __init__(self, content_path=None):
        super().__init__()

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set in .env")
        self.client = Groq(api_key=api_key)

        if content_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            content_path = os.path.join(script_dir, "content.txt")

        try:
            with open(content_path, "r", encoding="utf-8") as f:
                system_prompt = f.read()
        except Exception as e:
            raise RuntimeError(f"Could not read '{content_path}': {e}")

        self.mic_device_index = self._find_mic_device_index("1- MICROPHONE") #change mic type

        try:
            sr.Microphone(device_index=self.mic_device_index)
            self.mic_available = True
            self._mic_error = None
        except Exception as e:
            self.mic_available = False
            self._mic_error = str(e)

        self.history = [{"role": "system", "content": system_prompt}]
        self.recognizer = sr.Recognizer()
        self.ai_voice = "pt-BR-FranciscaNeural"
        self.text_queue = queue.Queue()
        self._running = True
        self.listening_enabled = True

        try:
            pygame.mixer.init()
        except Exception as e:
            raise RuntimeError(f"Audio output device not available: {e}")

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
            self.state_changed.emit("Listening")
            text = self._get_input()
            if text is None:
                continue

            self.user_text_received.emit(text)

            if text.lower() in ("sair", "exit"):
                break

            if text.lower().startswith("/pdf "):
                self._handle_pdf(text[5:].strip())
                continue

            self.history.append({"role": "user", "content": text})

            self.state_changed.emit("Thinking")
            reply = self._get_reply()
            if reply is None:
                continue

            self.reply_ready.emit(reply)

            self.state_changed.emit("Speaking")
            self._speak(reply)

        self.state_changed.emit("Idle")
        self.finished.emit()

    def _get_input(self):
        try:
            return self.text_queue.get_nowait()
        except queue.Empty:
            pass

        if not self.mic_available or not self.listening_enabled:
            try:
                return self.text_queue.get(timeout=1)
            except queue.Empty:
                return None

        return self._listen_mic()

    def _listen_mic(self):
        try:
            with sr.Microphone(device_index=self.mic_device_index) as source:
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=15)
        except sr.WaitTimeoutError:
            return None
        except OSError as e:
            self.mic_available = False
            self.error_occurred.emit(f"Microphone error, switching to chat only: {e}")
            return None

        try:
            return self.recognizer.recognize_google(audio, language="pt-BR")
        except sr.UnknownValueError:
            self.error_occurred.emit("Could not understand the audio.")
            return None
        except sr.RequestError:
            self.error_occurred.emit("Could not reach the recognition service.")
            return None

    def _handle_pdf(self, pdf_path):
        if not os.path.isfile(pdf_path):
            self.error_occurred.emit(f"File not found: {pdf_path}")
            return

        reader = PdfReader(pdf_path)
        pages = [page.extract_text() for page in reader.pages if page.extract_text()]
        if not pages:
            self.error_occurred.emit("Could not extract any text from the PDF.")
            return

        text_pdf = "\n".join(pages)
        self.history.append({
            "role": "user",
            "content": f'Content from the extracted PDF "{pdf_path}":\n{text_pdf}',
        })

    def _get_reply(self):
        try:
            response = self.client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=self.history,
                temperature=0.7,
                max_tokens=1024,
                timeout=15.0,
            )
        except Exception as e:
            self.error_occurred.emit(f"Groq API error: {e}")
            return None

        reply = response.choices[0].message.content.strip()
        self.history.append({"role": "assistant", "content": reply})
        return reply

    def _speak(self, text):
        output_path = None
        try:
            tmp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            output_path = tmp_file.name
            tmp_file.close()

            communicate = edge_tts.Communicate(text, self.ai_voice, rate="-20%")
            try:
                asyncio.run(asyncio.wait_for(communicate.save(output_path), timeout=15.0))
            except asyncio.TimeoutError:
                self.error_occurred.emit("TTS request timed out after 15s.")
                return

            pygame.mixer.music.load(output_path)
            pygame.mixer.music.play()
            clock = pygame.time.Clock()
            while pygame.mixer.music.get_busy():
                clock.tick(10)
            pygame.mixer.music.unload()
        except Exception as e:
            self.error_occurred.emit(f"TTS playback failed: {e}")
        finally:
            if output_path and os.path.exists(output_path):
                os.remove(output_path)

    def set_listening_enabled(self, enabled: bool):
        self.listening_enabled = enabled
