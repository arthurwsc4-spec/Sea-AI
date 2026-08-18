import sys


from PyQt6.QtCore import Qt, QThread
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLineEdit,
)
from Jarvis_orb import SpeakingOrb
from worker import SeaAIWorker

class MainWindow(QWidget):
    def __init__(self, worker, thread):
        super().__init__()
        self.worker = worker
        self.thread = thread

        self.setWindowTitle("SeaAI")
        self.setStyleSheet("background-color: #121214; color: Gray;")
        self.resize(600, 340)

        root_layout = QHBoxLayout(self)

        orb_side = QVBoxLayout()

        self.toggle_button = QPushButton("Chat")
        self.toggle_button.clicked.connect(self._toggle_chat)
        orb_side.addWidget(self.toggle_button, alignment=Qt.AlignmentFlag.AlignRight)

        self.mic_button = QPushButton("Mic: On")
        self.mic_button.setCheckable(True)
        self.mic_button.setChecked(True)
        self.mic_button.clicked.connect(self._toggle_mic)
        orb_side.addWidget(self.mic_button, alignment=Qt.AlignmentFlag.AlignRight)

        if not self.worker.mic_available:
            self.mic_button.setChecked(False)
            self.mic_button.setText("Mic: Unavailable")
            self.mic_button.setEnabled(False)

        self.orb = SpeakingOrb()
        orb_side.addWidget(self.orb, alignment=Qt.AlignmentFlag.AlignCenter)
        orb_side.addStretch()

        root_layout.addLayout(orb_side)

        self.chat_panel = QWidget()
        chat_layout = QVBoxLayout(self.chat_panel)

        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True)
        chat_layout.addWidget(self.chat_log)

        input_row = QHBoxLayout()

        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Type a message (use /pdf <path> to load a PDF)")
        self.chat_input.returnPressed.connect(self._send_text)
        input_row.addWidget(self.chat_input)

        send_button = QPushButton("Send")
        send_button.clicked.connect(self._send_text)
        input_row.addWidget(send_button)

        chat_layout.addLayout(input_row)

        self.chat_panel.setVisible(False)
        root_layout.addWidget(self.chat_panel)

    def _toggle_chat(self):
        self.chat_panel.setVisible(not self.chat_panel.isVisible())

    def _toggle_mic(self):
        enabled = self.mic_button.isChecked()
        self.mic_button.setText("Mic: On" if enabled else "Mic: Off")
        self.worker.set_listening_enabled(enabled)

    def _send_text(self):
        text = self.chat_input.text().strip()
        if not text:
            return
        self.worker.submit_text(text)
        self.chat_input.clear()

    def append_user_message(self, text):
        self.chat_log.append(f"<b>You:</b> {text}")

    def append_ai_message(self, text):
        self.chat_log.append(f"<b>SeaAI:</b> {text}")

    def append_error(self, text):
        self.chat_log.append(f"<i>[Error] {text}</i>")

    def closeEvent(self, event):
        self.worker.stop()
        self.thread.quit()
        if not self.thread.wait(35000):
            self.thread.terminate()
            self.thread.wait()

        event.accept()

def main():
    app = QApplication(sys.argv)


    try:
        worker = SeaAIWorker()
    except RuntimeError as e:
        print(f"Failed to start SeaAI: {e}")
        sys.exit(1)


    thread = QThread()
    worker.moveToThread(thread)


    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.finished.connect(app.quit)

    window = MainWindow(worker, thread)
    worker.state_changed.connect(window.orb.State_Setting)
    worker.user_text_received.connect(window.append_user_message)
    worker.reply_ready.connect(window.append_ai_message)
    worker.error_occurred.connect(window.append_error)
    worker.error_occurred.connect(lambda msg: print(f"[Error] {msg}"))

    window.show()
    thread.start()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
