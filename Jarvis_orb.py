import sys
import math
import os
from PyQt6.QtWidgets import QWidget, QApplication, QVBoxLayout, QLineEdit
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QRadialGradient, QPen, QPixmap


class SpeakingOrb(QWidget):
    State_Colors = {"Idle": QColor(80, 80, 120),
                    "Listening": QColor(40, 120, 200),
                    "Thinking": QColor(180, 120, 220),
                    "Speaking": QColor(40, 170, 40)}

    State_Pulsing_Frequency = {"Idle": 0.015,
                               "Listening": 0.05,
                               "Thinking": 0.03,
                               "Speaking": 0.06}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(200, 200)

        self.state = "Idle"
        self.phase = 0.0

        # Load the logo once, resolved relative to this script's location
        script_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(script_dir, "shared image.png")
        self.logo = QPixmap(logo_path)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animation)
        self.timer.start(16)

    def State_Setting(self, new_state):
        if new_state not in self.State_Colors:
            raise ValueError(f'Unknown state mentioned: {new_state}')
        self.state = new_state

    def _animation(self):
        speed = self.State_Pulsing_Frequency[self.state]
        self.phase += speed
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center_x = self.width() / 2
        center_y = self.height() / 2

        base_radius = 75
        pulse_size = 8
        radius = base_radius + pulse_size * math.sin(self.phase)

        orb_color = self.State_Colors[self.state]

        gradient = QRadialGradient(center_x, center_y, radius)
        gradient.setColorAt(0.0, orb_color.lighter(140))
        gradient.setColorAt(0.7, orb_color)
        gradient.setColorAt(1.0, QColor(orb_color.red(), orb_color.green(), orb_color.blue(), 0))

        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.setBrush(gradient)
        painter.drawEllipse(int(center_x - radius), int(center_y - radius), int(radius * 2), int(radius * 2))

        # Draw the logo centered, scaled to fit inside the orb
        if not self.logo.isNull():
            logo_size = int(base_radius * 0.95)  # tweak scale as you like
            scaled_logo = self.logo.scaled(
                logo_size, logo_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            logo_x = center_x - scaled_logo.width() / 2
            logo_y = (center_y - scaled_logo.height() / 2) - 3
            painter.drawPixmap(int(logo_x), int(logo_y), scaled_logo)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = QWidget()
    window.setWindowTitle("SeaAI - Testing orb")
    layout = QVBoxLayout(window)

    orb = SpeakingOrb()
    layout.addWidget(orb, alignment=Qt.AlignmentFlag.AlignCenter)

    state_input = QLineEdit()
    state_input.setPlaceholderText("Write: Idle, Listening, Thinking, Speaking")
    state_input.returnPressed.connect(lambda: orb.State_Setting(state_input.text().strip()))
    layout.addWidget(state_input)

    window.setLayout(layout)
    window.resize(300, 300)
    window.show()

    sys.exit(app.exec())
