import sys

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout

from Jarvis_orb import SpeakingOrb
from worker import SeaAIWorker

class MainWindow(QWidget):
    def __init__(self, worker, thread):
        super().__init__()
        self.worker = worker
        self.thread = thread

        self.setWindowTitle("SeaAI")
        layout = QVBoxLayout(self)

        self.orb = SpeakingOrb()
        layout.addWidget(self.orb, alignment=Qt.AlignmentFlag.AlignCenter)
        self.resize(300, 300)

    def closeEvent(self, event):
        # Ask the worker loop to stop. Because _listen() now uses a 5s
        # timeout, the loop notices this within a few seconds instead of
        # hanging on a blocked microphone read.
        self.worker.stop()

        if not self.thread.wait(8000):
            # The worker did not stop in time. terminate() is a blunt,
            # unsafe last resort: it can leave a temp audio file or the
            # mixer in an inconsistent state. Acceptable only because this
            # is app shutdown, with nothing left to recover afterward.
            self.thread.terminate()
            self.thread.wait()

        event.accept()


def main_program():
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
    worker.reply_ready.connect(lambda text: print(f"SeaAI: {text}"))
    worker.error_occurred.connect(lambda msg: print(f"[Error] {msg}"))

    window.show()
    thread.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main_program()
