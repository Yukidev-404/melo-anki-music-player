
from __future__ import annotations

import random
import time
from pathlib import Path

from aqt import gui_hooks, mw
from PyQt6.QtCore import QEvent, QPoint, QPointF, QSettings, QUrl, Qt, QTimer, QVariantAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QBrush, QPixmap
from PyQt6.QtMultimedia import QAudioBufferOutput, QAudioFormat, QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QMenu,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QVBoxLayout,
    QWidget,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
    QStackedWidget,
)


AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".ogg", ".oga", ".flac",
    ".m4a", ".aac", ".opus", ".wma"
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

DEFAULT_CONFIG = {
    "tracks": [],
    "volume": 0.75,
    "shuffle": False,
    "repeat": False,
    "mode": "disc",
    "welcome_name": "",
    "name_configured": False,
    "recent": [],
    "favorites": [],
    "playlists": {},
    "background_path": "",
}


def get_config() -> dict:
    raw = mw.addonManager.getConfig("anki_retro_music_explore_final") or {}
    cfg = DEFAULT_CONFIG.copy()
    cfg.update(raw)
    return cfg


def save_config(cfg: dict) -> None:
    mw.addonManager.writeConfig("anki_retro_music_explore_final", cfg)


def find_cover(audio_path: Path) -> Path | None:
    candidates = []

    for ext in IMAGE_EXTENSIONS:
        candidates.append(audio_path.with_suffix(ext))

    for filename in (
        "cover.jpg", "cover.png",
        "folder.jpg", "folder.png",
        "album.jpg", "album.png",
    ):
        candidates.append(audio_path.parent / filename)

    try:
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate

        for candidate in audio_path.parent.iterdir():
            if candidate.is_file() and candidate.suffix.lower() in IMAGE_EXTENSIONS:
                return candidate
    except OSError:
        pass

    return None


class ClickableSlider(QSlider):
    """Seek slider: clicking anywhere jumps to that point; dragging remains native."""
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.orientation() == Qt.Orientation.Horizontal:
            minimum = int(self.minimum())
            maximum = int(self.maximum())
            if maximum <= minimum:
                event.accept()
                return

            # Map the click directly to the full slider value range. This avoids
            # the style-dependent groove math that could produce a zero seek.
            x = float(event.position().x())
            margin = max(0.0, float(self.width() - self.contentsMargins().left() - self.contentsMargins().right()))
            ratio = 0.0 if margin <= 1.0 else max(0.0, min(1.0, x / margin))
            value = int(round(minimum + ratio * (maximum - minimum)))

            self.setSliderPosition(value)
            self.setValue(value)
            self.sliderMoved.emit(value)
            self.sliderReleased.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class CircularPlayButton(QPushButton):
    """Custom circular play/pause button using the supplied icon shapes."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(46, 46)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        base = Path(__file__).parent
        self._play_icon = QPixmap(str(base / "play_icon.png"))
        self._pause_icon = QPixmap(str(base / "pause_icon.png"))
        self._playing = False

    def set_playing_icon(self, playing: bool):
        self._playing = bool(playing)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        c = self.rect().center()
        r = min(self.width(), self.height()) / 2 - 1

        # Black circular button.
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#000000"))
        p.drawEllipse(QPointF(c.x(), c.y()), r, r)

        # Supplied play/pause shape, recolored to white for visibility.
        icon = self._pause_icon if self._playing else self._play_icon
        if not icon.isNull():
            target = icon.scaled(
                19, 23,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.drawPixmap(
                c.x() - target.width() // 2,
                c.y() - target.height() // 2,
                target,
            )

        p.end()


class MarqueeLabel(QLabel):
    """Continuously scroll long text from right to left without ellipsis."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setWordWrap(False)
        self._scroll_x = 0.0
        self._gap = 42
        self._speed = 1.15
        self._text_width = 0
        self._active = False
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._advance_marquee)
        self.setMinimumHeight(24)

    def setText(self, text):
        super().setText(str(text))
        self._reset_marquee()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reset_marquee()

    def _reset_marquee(self):
        self._scroll_x = 0.0
        fm = self.fontMetrics()
        self._text_width = fm.horizontalAdvance(self.text())
        self._active = self._text_width > max(1, self.contentsRect().width())
        if self._active:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def _advance_marquee(self):
        if not self._active:
            return
        self._scroll_x -= self._speed
        if self._scroll_x <= -(self._text_width + self._gap):
            self._scroll_x = float(self.contentsRect().width())
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        r = self.contentsRect()
        p.save()
        p.setClipRect(r)
        color = self.palette().color(self.foregroundRole())
        p.setPen(color)
        p.setFont(self.font())
        fm = p.fontMetrics()
        y = r.y() + (r.height() + fm.ascent() - fm.descent()) // 2
        if not self._active:
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.text())
        else:
            x = r.x() + int(self._scroll_x)
            p.drawText(x, y, self.text())
            # Seamless repeat: second copy follows the first with a small gap.
            p.drawText(x + self._text_width + self._gap, y, self.text())
            # When the cycle resets to the widget edge, a third copy prevents a blank gap.
            p.drawText(x + 2 * (self._text_width + self._gap), y, self.text())
        p.restore()



class PixelVisualizer(QWidget):
    """Two-section audio visualizer: LOW on the left, HIGH on the right."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(58)
        self._playing = False
        self._low = [0.0] * 8
        self._high = [0.0] * 8
        self._target_low = [0.0] * 8
        self._target_high = [0.0] * 8

        self._timer = QTimer(self)
        self._timer.setInterval(25)  # responsive visual refresh
        self._timer.timeout.connect(self._animate)
        self._timer.start()

    def clear(self):
        self._playing = False
        self._low = [0.0] * 8
        self._high = [0.0] * 8
        self._target_low = [0.0] * 8
        self._target_high = [0.0] * 8
        self.update()

    def set_playing(self, playing):
        self._playing = bool(playing)
        if not self._playing:
            self._low = [0.0] * 8
            self._high = [0.0] * 8
            self._target_low = [0.0] * 8
            self._target_high = [0.0] * 8
        self.update()

    @staticmethod
    def _bytes_from_audio_buffer(buffer):
        try:
            count = int(buffer.byteCount())
            if count <= 0:
                return b""
            ptr = buffer.constData()
            if hasattr(ptr, "asstring"):
                return bytes(ptr.asstring(count))
            return bytes(ptr)
        except Exception:
            return b""

    def _decode_samples(self, buffer):
        raw = self._bytes_from_audio_buffer(buffer)
        if not raw:
            return None

        fmt = buffer.format()
        channels = int(fmt.channelCount())
        frames = int(buffer.frameCount())
        if channels <= 0 or frames <= 0:
            return None

        import struct
        sf = fmt.sampleFormat()
        try:
            if sf == QAudioFormat.SampleFormat.Float:
                count = len(raw) // 4
                vals = struct.unpack("<" + "f" * count, raw[:count * 4])
            elif sf == QAudioFormat.SampleFormat.Int16:
                count = len(raw) // 2
                vals0 = struct.unpack("<" + "h" * count, raw[:count * 2])
                vals = [v / 32768.0 for v in vals0]
            elif sf == QAudioFormat.SampleFormat.Int32:
                count = len(raw) // 4
                vals0 = struct.unpack("<" + "i" * count, raw[:count * 4])
                vals = [v / 2147483648.0 for v in vals0]
            elif sf == QAudioFormat.SampleFormat.UInt8:
                vals = [(b - 128) / 128.0 for b in raw]
            else:
                return None
        except Exception:
            return None

        actual_frames = min(frames, len(vals) // channels)
        if actual_frames <= 2:
            return None

        mono = [0.0] * actual_frames
        for i in range(actual_frames):
            base_idx = i * channels
            mono[i] = sum(vals[base_idx:base_idx + channels]) / channels
        return mono

    def feed_audio_buffer(self, buffer):
        if not self._playing or not buffer.isValid():
            return

        try:
            mono = self._decode_samples(buffer)
            if not mono:
                return

            n = len(mono)
            low_targets = []
            high_targets = []

            # Each visual column is one frequency section.
            # LOW = left 8 bars, HIGH = right 8 bars.
            for i in range(8):
                a = (i * n) // 8
                b = max(a + 1, ((i + 1) * n) // 8)
                seg = mono[a:min(b, n)] or [0.0]

                # Low-frequency proxy: moving-average / smoothed energy.
                prev = seg[0]
                smoothed = []
                for sample in seg:
                    prev += (sample - prev) * 0.10
                    smoothed.append(prev)
                low_rms = (sum(v * v for v in smoothed) / len(smoothed)) ** 0.5

                # High-frequency proxy: fast-change energy.
                if len(seg) > 1:
                    high_rms = (
                        sum((seg[j] - seg[j - 1]) ** 2 for j in range(1, len(seg)))
                        / (len(seg) - 1)
                    ) ** 0.5
                else:
                    high_rms = 0.0

                low_targets.append(max(0.0, min(1.0, (low_rms * 4.5) ** 0.72)))
                high_targets.append(max(0.0, min(1.0, (high_rms * 8.5) ** 0.68)))

            self._target_low = low_targets
            self._target_high = high_targets
        except Exception:
            return

    def _animate(self):
        if not self._playing:
            return

        # Fast attack, smooth release.
        self._low = [
            old + (target - old) * (0.58 if target > old else 0.25)
            for old, target in zip(self._low, self._target_low)
        ]
        self._high = [
            old + (target - old) * (0.62 if target > old else 0.28)
            for old, target in zip(self._high, self._target_high)
        ]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        if not self._playing:
            p.end()
            return

        r = self.rect().adjusted(5, 7, -5, -5)
        gap = 3
        count = 16
        bar_w = max(3, int((r.width() - gap * (count - 1)) / count))
        baseline = r.bottom()
        max_h = r.height()

        # All bars are pink. The only visual division is a clean center divider:
        # LOW on left, HIGH on right.
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#E86D90"))

        for i, level in enumerate(self._low):
            h = max(1, int(max_h * max(0.0, min(1.0, level))))
            x = r.left() + i * (bar_w + gap)
            p.drawRect(x, baseline - h, bar_w, h)

        right_start = r.left() + 8 * (bar_w + gap)
        for i, level in enumerate(self._high):
            h = max(1, int(max_h * max(0.0, min(1.0, level))))
            x = right_start + i * (bar_w + gap)
            p.drawRect(x, baseline - h, bar_w, h)

        # Center divider between LOW and HIGH.
        divider_x = r.left() + 8 * (bar_w + gap) - 2
        p.setBrush(QColor("#BFC3CB"))
        p.drawRect(divider_x, r.top(), 2, r.height())

        p.end()


class RoundArtwork(QWidget):
    def __init__(self, size=120, parent=None):
        super().__init__(parent)
        self.size_px = size
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.pixmap = None
        self._texture = QPixmap(str(Path(__file__).parent / "assets" / "melo_disc_texture_hr.png"))
        self._arm = QPixmap(str(Path(__file__).parent / "assets" / "melo_tonearm_hr.png"))
        self.angle = 0
        self.playing = False

        self.timer = QTimer(self)
        self.timer.setInterval(70)
        self.timer.timeout.connect(self._rotate)

    def set_art(self, path: str | None):
        # Never use MP3 embedded or sidecar cover art. The supplied vinyl
        # texture is always used for the disc.
        if self._texture and not self._texture.isNull():
            self.pixmap = self._texture.scaled(
                self.size_px - 6,
                self.size_px - 6,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            self.pixmap = None
        self.update()

    def set_playing(self, playing: bool):
        self.playing = playing
        if playing:
            self.timer.start()
        else:
            self.timer.stop()
        self.update()

    def _rotate(self):
        self.angle = (self.angle + 5) % 360
        self.update()

    def resizeEvent(self, event):
        self._background_cache = None
        self._background_cache_size = None
        super().resizeEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect().adjusted(0, 0, -1, -1)
        inner = rect

        if self.pixmap is not None:
            path = QPainterPath()
            path.addEllipse(float(inner.x()), float(inner.y()), float(inner.width()), float(inner.height()))
            p.save()
            p.setClipPath(path)
            p.translate(inner.center())
            p.rotate(self.angle if self.playing else 0)
            target = self.pixmap.rect()
            p.drawPixmap(
                -target.width() // 2,
                -target.height() // 2,
                self.pixmap,
            )
            p.restore()

            # The tonearm is a fixed layer; only the record itself rotates.
            if self._arm and not self._arm.isNull():
                arm = self._arm.scaled(
                    self.size_px - 6,
                    self.size_px - 6,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                p.save()
                p.setClipPath(path)
                p.drawPixmap(
                    inner.center().x() - arm.width() // 2,
                    inner.center().y() - arm.height() // 2,
                    arm,
                )
                p.restore()
        else:
            p.setBrush(QBrush(QColor("#171719")))
            p.setPen(QPen(QColor("#171719"), 1))
            p.drawEllipse(inner)

            center = inner.center()
            radius = min(inner.width(), inner.height()) // 2

            p.setPen(QPen(QColor("#414248"), 1))
            for r in range(radius - 5, 10, 6):
                p.drawEllipse(
                    center.x() - r,
                    center.y() - r,
                    r * 2,
                    r * 2,
                )

            p.setBrush(QBrush(QColor("#E86D90")))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(
                center.x() - 8,
                center.y() - 8,
                16,
                16,
            )

        p.end()


class WheelSelector(QWidget):
    """Circular, title-only wheel around a plain vinyl disc."""

    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self.owner = owner
        self.indices = []
        self.center_pos = 0
        self.turn_offset = 0.0
        self._turn_anim = None
        self._step = 0
        self.dragging = False
        self.last_point = QPoint()
        self._drag_distance = 0
        self.setMinimumHeight(285)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._background_cache = None
        self._background_cache_size = None
        self._disc_angle = 0.0
        self._disc_playing = False
        self._disc_timer = QTimer(self)
        self._disc_timer.setInterval(33)
        self._disc_timer.timeout.connect(self._spin_disc)

    def set_playing(self, playing):
        self._disc_playing = bool(playing)
        if self._disc_playing:
            self._disc_timer.start()
        else:
            self._disc_timer.stop()
        self.update()

    def _spin_disc(self):
        # Only the vinyl texture rotates; the title wheel, play control,
        # labels, and all other UI remain completely stationary.
        self._disc_angle = (self._disc_angle + 2.0) % 360.0
        self.update()

    def set_indices(self, indices, selected_index):
        self.indices = list(indices)
        if not self.indices:
            self.center_pos = 0
            self.turn_offset = 0.0
            self._stop_anim()
            self.update()
            return
        try:
            self.center_pos = self.indices.index(selected_index)
        except ValueError:
            self.center_pos = 0
        self.turn_offset = 0.0
        self.update()

    def selected_index(self):
        if not self.indices:
            return -1
        return self.indices[self.center_pos % len(self.indices)]

    def _stop_anim(self):
        if self._turn_anim is not None:
            self._turn_anim.stop()
        self._turn_anim = None
        self._step = 0

    def _rotate_steps(self, steps):
        if not self.indices or not steps:
            return
        if self._turn_anim is not None and self._turn_anim.state() == QVariantAnimation.State.Running:
            return

        self._step = 1 if steps > 0 else -1

        # Animate one complete title-slot (22 degrees) from the CURRENT
        # visual state to the NEXT state.  The center index is changed only
        # after the animation reaches the exact matching geometry, so there
        # is no snap/jitter at the end.
        start = float(self.turn_offset)
        end = start + float(self._step)

        anim = QVariantAnimation(self)
        self._turn_anim = anim
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setDuration(560)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.valueChanged.connect(self._on_turn_value)
        anim.finished.connect(self._finish_turn)
        anim.finished.connect(anim.deleteLater)
        anim.start()

    def _on_turn_value(self, value):
        try:
            self.turn_offset = float(value)
        except (TypeError, ValueError):
            self.turn_offset = 0.0
        self.update()

    def _finish_turn(self):
        if not self.indices:
            self._turn_anim = None
            return
        step = self._step

        # The animated end position already matches the geometry of the new
        # center item.  Commit the new center and normalize the visual phase
        # only AFTER the frame has reached that exact position.
        self.turn_offset = float(step)
        self.center_pos = (self.center_pos + step) % len(self.indices)
        self.turn_offset = 0.0
        self._step = 0
        self._turn_anim = None
        self.owner.select_from_wheel(self.selected_index())
        self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if not delta:
            event.ignore()
            return
        self._rotate_steps(-1 if delta > 0 else 1)
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Left:
            self._rotate_steps(-1)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Right:
            self._rotate_steps(1)
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.indices:
                self.owner.play_track(self.selected_index())
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.dragging = True
            self.last_point = event.position().toPoint()
            self._drag_distance = 0
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            pos = event.position().toPoint()
            dx = pos.x() - self.last_point.x()
            self.last_point = pos
            self._drag_distance += abs(dx)
            if self.indices and dx:
                # Drag directly in the same normalized slot units used by
                # the keyboard animation: 1.0 unit = one complete title step.
                self.turn_offset += dx / 110.0
                self.turn_offset = max(-0.85, min(0.85, self.turn_offset))
                self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self.unsetCursor()
            if self._drag_distance < 8 and self.indices:
                self.owner.play_track(self.selected_index())
                event.accept()
                return

            if self.indices:
                if self.turn_offset <= -0.28:
                    self._rotate_steps(-1)
                elif self.turn_offset >= 0.28:
                    self._rotate_steps(1)
                else:
                    self.turn_offset = 0.0
                    self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    @staticmethod
    def _polar(cx, cy, rx, ry, angle_deg):
        import math
        rad = math.radians(angle_deg)
        return cx + rx * math.cos(rad), cy + ry * math.sin(rad)

    def _ensure_background_cache(self):
        size = self.size()
        if self._background_cache is not None and self._background_cache_size == size:
            return self._background_cache

        from PyQt6.QtGui import QPixmap

        pix = QPixmap(size)
        pix.fill(QColor("#202329"))
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Disc mode is a child widget that paints over its parent, so it must
        # draw the configured background itself. Keep it identical to list
        # mode: cover the whole selector area, then add the readability tint.
        owner_pix = getattr(self.owner, "_background_pixmap", QPixmap())
        if not owner_pix.isNull():
            scaled = owner_pix.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = max(0, (scaled.width() - size.width()) // 2)
            y = max(0, (scaled.height() - size.height()) // 2)
            painter.drawPixmap(0, 0, scaled.copy(x, y, size.width(), size.height()))
            painter.fillRect(size.width() * 0, 0, size.width(), size.height(), QColor(15, 18, 23, 150))

        # The static cache contains ONLY the panel background. The vinyl is
        # deliberately excluded so it can be rotated independently in paintEvent.
        painter.end()
        self._background_cache = pix
        self._background_cache_size = size
        return pix

    def _title_slots(self):
        if not self.indices:
            return []
        n = len(self.indices)
        slots = []
        # Eight title slots travel around the circular wheel. Only text is
        # drawn; album covers and folder names are intentionally absent.
        for slot in range(-3, 5):
            idx = self.indices[(self.center_pos + slot) % n]
            slots.append((slot, idx))
        return slots

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        p.drawPixmap(0, 0, self._ensure_background_cache())

        # Draw the supplied vinyl as an independent rotating layer.  Nothing
        # else in this widget rotates with it.
        disc_cx = rect.width() + 105.0
        disc_cy = rect.height() / 2.0 + 2.0
        disc_radius = min(225.0, rect.height() * 0.68)
        texture_path = Path(__file__).parent / "assets" / "melo_disc_texture_hr.png"
        arm_path = Path(__file__).parent / "assets" / "melo_tonearm_hr.png"
        texture = QPixmap(str(texture_path))
        arm_texture = QPixmap(str(arm_path))
        if not texture.isNull():
            disc_pix = texture.scaled(
                int(disc_radius * 2),
                int(disc_radius * 2),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.save()
            p.setClipRect(rect)
            p.translate(disc_cx, disc_cy)
            p.rotate(self._disc_angle if self._disc_playing else 0.0)
            p.drawPixmap(-disc_pix.width() // 2, -disc_pix.height() // 2, disc_pix)
            p.restore()

            # Fixed tonearm layer: it never rotates with the record.
            if not arm_texture.isNull():
                arm_pix = arm_texture.scaled(
                    int(disc_radius * 2),
                    int(disc_radius * 2),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                p.save()
                p.setClipRect(rect)
                p.drawPixmap(
                    int(disc_cx - arm_pix.width() / 2),
                    int(disc_cy - arm_pix.height() / 2),
                    arm_pix,
                )
                p.restore()

        if not self.indices:
            p.setPen(QColor("#8A8D95"))
            p.setFont(QFont("Pixel Operator", 9, QFont.Weight.Normal))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "NO MUSIC")
            p.end()
            return

        # The five titles follow the LEFT ARC of the vinyl like a real wheel.
        # They move both horizontally and vertically along the circular path;
        # they must not simply slide straight up/down.
        n = len(self.indices)
        visible = min(5, n)
        # Always reserve five wheel positions: two above, the selected middle, and two below.
        # This keeps the selector visually populated whenever at least five tracks exist.
        half = 2
        slots = list(range(-half, half + 1)) if n >= 5 else list(range(-(n // 2), n // 2 + 1))

        disc_cx = rect.width() + 105.0
        disc_cy = rect.height() / 2.0 + 2.0
        disc_radius = min(225.0, rect.height() * 0.68)

        # This radius is just outside the physical vinyl edge.  The title's
        # RIGHT edge is anchored to this circular path, keeping the text
        # outside the record while following its arc.
        title_radius = disc_radius + 0.0
        phase = float(self.turn_offset)
        step_angle = 18.0

        for slot in slots:
            idx = self.indices[(self.center_pos + slot) % n]
            visual_slot = slot - phase

            angle = 180.0 - (visual_slot * step_angle)
            x, y = self._polar(disc_cx, disc_cy, title_radius, title_radius, angle)

            active = slot == 0
            alpha = 255 if active else max(145, 225 - abs(slot) * 24)
            if active:
                p.setPen(QColor('#E86D90'))
                font = QFont('Pixel Operator', 9, QFont.Weight.Normal)
                font.setWeight(700)
                p.setFont(font)
            else:
                p.setPen(QColor(245, 246, 249, alpha))
                p.setFont(QFont('Pixel Operator', 8, QFont.Weight.Normal))

            title = Path(self.owner.tracks[idx]).stem
            width = min(275, max(185, int(max(185, x - 6))))
            title = p.fontMetrics().elidedText(
                title,
                Qt.TextElideMode.ElideRight,
                width,
            )

            # Keep the title completely to the LEFT of its point on the arc.
            right = int(x)
            left = max(4, right - width)
            if left >= right:
                continue

            p.drawText(
                left, int(y - 9), right - left, 18,
                Qt.AlignmentFlag.AlignRight,
                title,
            )

        # SELECT stays fixed beside the middle title. Enter always plays the
        # title in this middle slot.
        marker_angle = 180.0
        marker_xf, marker_yf = self._polar(
            disc_cx, disc_cy, title_radius, title_radius, marker_angle
        )
        marker_x = int(marker_xf) + 3
        marker_y = int(marker_yf)
        p.setPen(QPen(QColor("#E86D90"), 2))
        p.drawLine(marker_x, marker_y - 18, marker_x, marker_y + 18)
        p.setPen(QColor("#E86D90"))
        p.setFont(QFont("Pixel Operator", 6, QFont.Weight.Normal))
        p.drawText(
            marker_x - 30, marker_y - 32, 60, 10,
            Qt.AlignmentFlag.AlignCenter, "SELECT"
        )

        p.setPen(QColor("#777D87"))
        p.setFont(QFont("Pixel Operator", 6, QFont.Weight.Normal))
        p.drawText(
            0, rect.height() - 9, rect.width(), 10,
            Qt.AlignmentFlag.AlignCenter,
            "SCROLL / DRAG TO TURN",
        )
        p.end()


class TrackRow(QWidget):
    def __init__(self, owner, index: int, path: str):
        super().__init__(owner.list_container)
        self.owner = owner
        self.index = index
        self.path = Path(path)

        self.setObjectName("trackRow")
        self.setFixedHeight(64)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(7, 5, 7, 5)
        layout.setSpacing(8)

        self.cover = RoundArtwork(48, self)
        cover = find_cover(self.path)
        self.cover.set_art(str(cover) if cover else None)
        layout.addWidget(self.cover)

        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(1)

        title = QLabel(self.path.stem)
        title.setObjectName("rowTitle")
        title.setText(
            title.fontMetrics().elidedText(
                self.path.stem,
                Qt.TextElideMode.ElideRight,
                220,
            )
        )

        artist = QLabel(self.path.parent.name or "LOCAL MUSIC")
        artist.setObjectName("rowArtist")
        artist.setText(
            artist.fontMetrics().elidedText(
                self.path.parent.name or "LOCAL MUSIC",
                Qt.TextElideMode.ElideRight,
                220,
            )
        )

        info.addWidget(title)
        info.addWidget(artist)
        layout.addLayout(info, 1)

        play = QPushButton("▶")
        play.setObjectName("rowPlay")
        play.setFixedSize(34, 34)
        play.setCursor(Qt.CursorShape.PointingHandCursor)
        play.clicked.connect(lambda: self.owner.play_track(self.index))
        layout.addWidget(play)


class ResizeGrip(QWidget):
    """Small bottom-right resize handle for the in-Anki child widget."""

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setFixedSize(18, 18)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setMouseTracking(True)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor("#7B8089"), 1.3)
        p.setPen(pen)
        for offset in (4, 8, 12):
            p.drawLine(self.width() - offset, self.height() - 2,
                       self.width() - 2, self.height() - offset)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.owner.begin_resize(event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.owner.update_resize(event.globalPosition().toPoint())
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.owner.end_resize()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class BackgroundPanel(QWidget):
    """Container that paints the configurable library background behind its child."""
    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self.owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#202329"))
        pix = getattr(self.owner, "_background_pixmap", QPixmap())
        if not pix.isNull():
            target = self.rect()
            scaled = pix.scaled(
                target.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = max(0, (scaled.width() - target.width()) // 2)
            y = max(0, (scaled.height() - target.height()) // 2)
            p.drawPixmap(target.topLeft(), scaled.copy(x, y, target.width(), target.height()))
            # Darken only the library canvas so the text remains readable.
            p.fillRect(target, QColor(15, 18, 23, 150))
        p.end()
        super().paintEvent(event)

class MELO(QWidget):
    def __init__(self):
        super().__init__(mw)

        self.setParent(mw)
        self.setObjectName("retroExplorePlayer")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.dragging = False
        self.drag_offset = QPoint()
        self.user_moved = False
        self.resizing = False
        self.resize_start_pos = QPoint()
        self.resize_start_size = None

        cfg = get_config()
        saved_name = str(cfg.get("welcome_name", "")).strip()
        name_configured = bool(cfg.get("name_configured", False))
        # Older development builds shipped with the author's name as the default.
        # Treat that value as unconfigured so a new user is prompted on first run.
        if saved_name.lower() == "yuki" and not name_configured:
            saved_name = ""
        self.welcome_name = saved_name or "there"
        self._name_needs_setup = not name_configured or not saved_name
        self.background_path = str(cfg.get("background_path", "")).strip()
        self._background_pixmap = (
            QPixmap(self.background_path)
            if self.background_path and Path(self.background_path).exists()
            else QPixmap()
        )

        # Preserve playlists from old builds too.
        saved = cfg.get("tracks", cfg.get("playlist", []))
        self.tracks = [
            str(Path(p))
            for p in saved
            if Path(str(p)).exists()
        ]

        self.current_index = 0 if self.tracks else -1
        self.shuffle = bool(cfg.get("shuffle", False))
        self.repeat = bool(cfg.get("repeat", False))
        self.recent = [str(Path(p)) for p in cfg.get("recent", []) if Path(str(p)).exists()]
        self.favorites = set(str(Path(p)) for p in cfg.get("favorites", []) if Path(str(p)).exists())
        self.playlists = {
            str(name): [str(Path(p)) for p in paths if Path(str(p)).exists()]
            for name, paths in (cfg.get("playlists", {}) or {}).items()
            if isinstance(paths, list)
        }
        self.library_tab = "LIST"
        self.active_playlist_name = None
        # Persist the last chosen view mode independently of addon config reloads.
        settings = QSettings("MELO", "Explore")
        stored_mode = settings.value("mode", cfg.get("mode", "disc"), type=str)
        self.mode = "list" if stored_mode == "list" else "disc"
        self._saved_player_x = settings.value("player_x", None, type=int)
        self._saved_player_y = settings.value("player_y", None, type=int)
        self._has_saved_player_position = (
            self._saved_player_x is not None and self._saved_player_y is not None
        )

        self.audio_output = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)

        # Qt 6.8+ can provide the exact decoded audio buffers to the UI.
        # This makes the visualizer react to the real audio stream without
        # FFmpeg binaries, file decoding, or fake/random animation.
        self.audio_buffer_output = QAudioBufferOutput(self)
        self.player.setAudioBufferOutput(self.audio_buffer_output)
        self.audio_output.setVolume(float(cfg.get("volume", 0.75)))

        self.build_ui()
        self.resize_grip = ResizeGrip(self)
        self._position_resize_grip()

        self.player.durationChanged.connect(self.on_duration)
        self.player.positionChanged.connect(self.on_position)
        self.player.playbackStateChanged.connect(self.on_state)
        self.audio_buffer_output.audioBufferReceived.connect(
            self.visualizer.feed_audio_buffer
        )
        self.player.mediaStatusChanged.connect(self.on_status)

        # Poll the player position as a fallback so the seek bar always visibly moves,
        # even if a Qt multimedia backend skips or delays positionChanged signals.
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(50)
        self.progress_timer.timeout.connect(self.update_progress_from_player)
        self.progress_timer.start()
        self._seek_override_until = 0.0

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        self.refresh_rows()
        self._apply_mode()
        self.load_current(False)
        self._update_favorite_action()

        self.show()
        self.raise_()
        QTimer.singleShot(0, self.place_default)

    # ---------------- Placement / dragging / resizing ----------------

    def place_default(self):
        """Place the player at a sensible default location inside Anki.

        Keep the saved/manual position when the user has already moved the
        widget.  On first launch, place it toward the right side of Anki.
        """
        if mw is None:
            return

        if getattr(self, "user_moved", False):
            self._clamp_to_main_window()
            return

        # Restore the last manually placed position across Anki restarts.
        if getattr(self, "_has_saved_player_position", False):
            self.move(int(self._saved_player_x), int(self._saved_player_y))
            self._clamp_to_main_window()
            self.raise_()
            return

        # Default placement: right side of Anki, around the user's marked area.
        # Values are Qt logical pixels; Windows display scaling may make the
        # player appear larger in screenshots.
        # MELO 1.0: keep the player comfortably separated from the Deck Browser
        # while staying aligned to the right edge.
        x = max(12, mw.width() - self.width() - 14)
        y = 190
        x = max(12, min(x, max(12, mw.width() - self.width() - 14)))
        y = max(52, min(y, max(52, mw.height() - self.height() - 8)))
        self.move(x, y)
        self.raise_()

    # ---------------- UI ----------------

    def build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(11, 10, 11, 10)
        root.setSpacing(6)

        # Header
        header = QHBoxLayout()
        header.setSpacing(8)

        heading = QLabel("welcome yuki ^-^!")
        heading.setObjectName("heading")
        header.addWidget(heading)

        header.addStretch(1)

        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("search music")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(235)
        self.search.textChanged.connect(self.refresh_rows)
        header.addWidget(self.search)

        self.menu_button = QToolButton()
        self.menu_button.setObjectName("dots")
        self.menu_button.setText("•••")
        self.menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_button.setAutoRaise(True)

        menu = QMenu(self.menu_button)
        self.music_action = menu.addAction("+ MUSIC")
        self.folder_action = menu.addAction("+ FOLDER")
        self.remove_folder_action = menu.addAction("REMOVE FOLDER FROM LIBRARY")
        menu.addSeparator()
        self.create_playlist_action = menu.addAction("+ PLAYLIST")
        self.add_to_playlist_action = menu.addAction("ADD CURRENT TO PLAYLIST")
        self.favorite_action = menu.addAction("♡ ADD TO FAVORITES")
        menu.addSeparator()
        self.background_action = menu.addAction("CHANGE BACKGROUND...")
        self.reset_background_action = menu.addAction("RESET BACKGROUND")
        self.music_action.triggered.connect(self.add_music)
        self.folder_action.triggered.connect(self.add_folder)
        self.remove_folder_action.triggered.connect(self.remove_folder)
        self.create_playlist_action.triggered.connect(self.create_playlist)
        self.add_to_playlist_action.triggered.connect(self.add_current_to_playlist)
        self.favorite_action.triggered.connect(self.toggle_favorite)
        self.background_action.triggered.connect(self.choose_background)
        self.reset_background_action.triggered.connect(self.reset_background)
        self.menu = menu
        self.menu_button.setMenu(menu)
        self.menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        header.addWidget(self.menu_button)

        root.addLayout(header)

        # Body
        body = QHBoxLayout()
        body.setSpacing(9)

        # Current track column
        current = QWidget()
        current.setFixedWidth(225)
        current_layout = QVBoxLayout(current)
        current_layout.setContentsMargins(0, 0, 0, 0)
        current_layout.setSpacing(5)

        self.big_cover = RoundArtwork(148, current)
        current_layout.addWidget(
            self.big_cover,
            alignment=Qt.AlignmentFlag.AlignCenter
        )
        # The vinyl artwork is intentionally larger visually under Windows
        # scaling, so reserve extra vertical space before the song title.
        # This keeps the title clearly below the record instead of crossing it.
        current_layout.addSpacing(72)

        self.current_title = MarqueeLabel(current)
        self.current_title.setObjectName("currentTitle")
        self.current_title.setFixedHeight(22)
        self.current_title.setMinimumWidth(0)
        # Keep the scrolling song title comfortably inside the vinyl column.
        # This prevents the marquee text from running into/under the disc.
        title_row = QHBoxLayout()
        title_row.setContentsMargins(12, 0, 12, 0)
        title_row.setSpacing(0)
        title_row.addWidget(self.current_title)
        current_layout.addLayout(title_row)

        self.current_artist = QLabel("LOCAL MUSIC")
        self.current_artist.setObjectName("currentArtist")
        self.current_artist.setAlignment(Qt.AlignmentFlag.AlignCenter)
        current_layout.addWidget(self.current_artist)

        # The seek/progress control belongs to the left playback block,
        # directly above the transport controls. It is no longer a bottom-row widget.
        left_times = QHBoxLayout()
        left_times.setContentsMargins(0, 0, 0, 0)
        left_times.setSpacing(2)
        self.now_time = QLabel("00:00")
        self.total_time = QLabel("00:00")
        self.now_time.setObjectName("time")
        self.total_time.setObjectName("time")
        left_times.addWidget(self.now_time)
        left_times.addStretch(1)
        left_times.addWidget(self.total_time)
        current_layout.addLayout(left_times)

        self.progress = ClickableSlider(Qt.Orientation.Horizontal)
        self.progress.setFixedHeight(10)
        self.progress.setRange(0, 0)
        self.progress.setObjectName("progress")
        self.progress.sliderMoved.connect(self.seek)
        current_layout.addWidget(self.progress)

        current_layout.addSpacing(3)

        transport_left = QHBoxLayout()
        transport_left.setSpacing(20)
        transport_left.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.shuffle_button = self.make_button("⇄", checkable=True)
        self.prev_button = self.make_button("|◀")
        self.play_button = CircularPlayButton()
        self.next_button = self.make_button("▶|")
        self.repeat_button = self.make_button("↻", checkable=True)
        self.favorite_playback_button = self.make_button("♡")
        self.favorite_playback_button.setObjectName("favoritePlaybackButton")
        self.favorite_playback_button.setToolTip("Add/remove current song from Favorites")

        self.play_button.setObjectName("mainPlay")
        self.shuffle_button.setFixedSize(24, 24)
        self.prev_button.setFixedSize(24, 24)
        self.next_button.setFixedSize(24, 24)
        self.repeat_button.setFixedSize(24, 24)
        self.favorite_playback_button.setFixedSize(24, 24)
        self.play_button.setFixedSize(44, 44)
        self._style_mode_button(self.shuffle_button, active=self.shuffle)
        self._style_mode_button(self.repeat_button, active=self.repeat)

        self.shuffle_button.clicked.connect(self.toggle_shuffle)
        self.prev_button.clicked.connect(self.previous)
        self.play_button.clicked.connect(self.toggle_play)
        self.next_button.clicked.connect(self.next_track)
        self.repeat_button.clicked.connect(self.toggle_repeat)
        self.favorite_playback_button.clicked.connect(self.toggle_favorite)

        for b in (
            self.shuffle_button, self.prev_button, self.play_button,
            self.next_button, self.repeat_button, self.favorite_playback_button,
        ):
            transport_left.addWidget(b)

        current_layout.addLayout(transport_left)
        current_layout.addSpacing(4)

        current_layout.addSpacing(3)

        self.personal_panel = QWidget()
        self.personal_panel.setObjectName("personalPanel")
        personal_layout = QVBoxLayout(self.personal_panel)
        personal_layout.setContentsMargins(10, 10, 10, 10)
        personal_layout.setSpacing(6)

        self.welcome_back = QLabel(f"welcome back, {self.welcome_name}!   LOW  |  HIGH")
        self.welcome_back.setObjectName("welcomeBack")
        self.welcome_back.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.visualizer = PixelVisualizer(self.personal_panel)
        self.visualizer.setObjectName("visualizer")

        personal_layout.addWidget(self.welcome_back)
        personal_layout.addWidget(self.visualizer)
        current_layout.addWidget(self.personal_panel)
        current_layout.addStretch(1)

        body.addWidget(current)

        # Library column
        library = QVBoxLayout()
        library.setSpacing(5)

        title = QLabel("Your Music")
        title.setObjectName("libraryTitle")
        library.addWidget(title)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(4)

        self.mode_button = QPushButton()
        self.mode_button.setObjectName("modeButton")
        self.mode_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_button.clicked.connect(self.toggle_mode)
        filter_row.addWidget(self.mode_button)

        self.tab_buttons = {}
        for tab_name in ("LIST", "QUEUE", "PLAYLISTS", "RECENT", "FAVORITES"):
            btn = QPushButton(tab_name)
            btn.setObjectName("libraryTabButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.setFixedHeight(23)
            btn.clicked.connect(lambda checked=False, name=tab_name: self.set_library_tab(name))
            filter_row.addWidget(btn)
            self.tab_buttons[tab_name] = btn

        filter_row.addStretch(1)
        library.addLayout(filter_row)

        self.view_stack = QStackedWidget()
        self.view_stack.setObjectName("viewStack")

        self.list_page = BackgroundPanel(self)
        list_layout = QVBoxLayout(self.list_page)
        list_layout.setContentsMargins(0, 0, 0, 0)

        self.music_list = QListWidget()
        self.music_list.setObjectName("musicList")
        self.music_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.music_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.music_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.music_list.itemClicked.connect(self.select_from_list)
        self.music_list.itemDoubleClicked.connect(self.play_from_list)
        list_layout.addWidget(self.music_list)
        self.view_stack.addWidget(self.list_page)

        self.disc_page = BackgroundPanel(self)
        disc_layout = QVBoxLayout(self.disc_page)
        disc_layout.setContentsMargins(0, 0, 0, 0)

        self.wheel = WheelSelector(self)
        self.wheel.setObjectName("wheelSelector")
        disc_layout.addWidget(self.wheel)
        self.view_stack.addWidget(self.disc_page)

        library.addWidget(self.view_stack, 1)

        body.addLayout(library, 1)

        root.addLayout(body, 1)


        self.setMinimumSize(420, 340)
        self.resize(528, 392)

        self.setStyleSheet(
            """
            QWidget#retroExplorePlayer {
                background: #F1F3F8;
                border: 1px solid #C7CCD6;
                border-radius: 16px;
            }

            QLabel#heading {
                color: #17191D;
                font-family: "Pixel Operator";
                font-size: 13pt;
                font-weight: 600;
                padding: 0px;
                margin: 0px;
            }

            QToolButton#dots {
                color: #70737B;
                background: transparent;
                border: none;
                padding: 0px 2px;
                font-family: "Pixel Operator";
                font-size: 9pt;
            }

            QMenu {
                background: #F1F3F8;
                color: #202228;
                border: 1px solid #C7CCD6;
                padding: 4px;
                font-family: "Pixel Operator";
                font-size: 8pt;
            }

            QMenu::item {
                padding: 7px 14px;
            }

            QMenu::item:selected {
                background: #E1E4EA;
            }

            QLineEdit#search {
                color: #30333A;
                background: #FFFFFF;
                border: 1px solid #B9BDC6;
                border-radius: 12px;
                padding: 4px 9px;
                font-family: "Pixel Operator";
                font-size: 7pt;
            }

            QLabel#currentTitle {
                color: #17191D;
                font-family: "Pixel Operator";
                font-size: 8pt;
            }

            QLabel#currentArtist,
            QLabel#tiny,
            QLabel#time {
                color: #7A7D86;
                font-family: "Pixel Operator";
                font-size: 6.5pt;
            }

            QLabel#libraryTitle {
                color: #202228;
                font-family: "Pixel Operator";
                font-size: 13pt;
            }

            QWidget#personalPanel {
                background: #ECEEF3;
                border: 1px solid #D0D4DC;
                border-radius: 12px;
            }

            QLabel#welcomeBack {
                color: #202228;
                font-family: "Pixel Operator";
                font-size: 8pt;
                padding: 2px 0px;
            }

            QWidget#visualizer {
                background: transparent;
            }

            QPushButton#favoritePlaybackButton {
                color: #383B42;
                background: transparent;
                border: none;
                padding: 0px;
                font-family: "Pixel Operator";
                font-size: 12pt;
                min-width: 20px;
            }

            QPushButton#favoritePlaybackButton:hover {
                color: #E86D90;
            }

            QPushButton#favoritePlaybackButton[favorited="true"] {
                color: #E86D90;
            }

            QPushButton#modeButton,
            QPushButton#libraryTabButton {
                color: #383B42;
                background: #E1E4EA;
                border: 1px solid #BFC3CB;
                border-radius: 8px;
                padding: 2px 6px;
                font-family: "Pixel Operator";
                font-size: 5.6pt;
                min-width: 0px;
            }

            QPushButton#modeButton:hover,
            QPushButton#libraryTabButton:hover {
                background: #D8DCE3;
            }

            QPushButton#libraryTabButton:checked {
                color: #E86D90;
                border-color: #E86D90;
            }

            QListWidget#musicList {
                background: transparent;
                color: #F1F3F8;
                border: 1px solid #17191D;
                border-radius: 0px;
                outline: none;
                padding: 6px;
                font-family: "Pixel Operator";
                font-size: 8pt;
            }

            QListWidget#musicList::item {
                padding: 8px 10px;
                border-bottom: 1px solid #30343B;
            }

            QListWidget#musicList::item:selected {
                color: #E86D90;
                background: #2A2E35;
            }

            QListWidget#musicList::item:hover {
                background: #282C32;
            }

            QWidget#wheelSelector {
                background: transparent;
                border: 1px solid #17191D;
                border-radius: 0px;
            }

            QScrollArea#scroll {
                background: transparent;
                border: none;
            }

            QWidget#trackRow {
                background: rgba(255,255,255,0);
                border: 1px solid transparent;
                border-radius: 11px;
            }

            QWidget#trackRow:hover {
                background: #FFFFFF;
                border: 1px solid #D7DADF;
            }

            QLabel#rowTitle {
                color: #24262C;
                font-family: "Pixel Operator";
                font-size: 7.5pt;
            }

            QLabel#rowArtist {
                color: #8A8D95;
                font-family: "Pixel Operator";
                font-size: 6pt;
            }

            QPushButton#rowPlay {
                color: #32343A;
                background: #FFFFFF;
                border: 1px solid #C4C7CD;
                border-radius: 9px;
                font-family: "Pixel Operator";
                font-size: 7pt;
            }

            QPushButton#rowPlay:hover {
                background: #E9EBEF;
            }

            QPushButton#musicButton {
                color: #111216;
                background: transparent;
                border: none;
                padding: 0px;
                font-family: "Pixel Operator";
                font-size: 12pt;
            }

            QPushButton#musicButton:hover {
                color: #000000;
                background: transparent;
            }

            QPushButton#musicButton:checked {
                color: #000000;
                background: transparent;
            }

            QPushButton#mainPlay {
                background: transparent;
                border: none;
                padding: 0px;
            }

            QSlider#progress::groove:horizontal {
                background: #D7D9DE;
                height: 5px;
                border-radius: 2px;
            }

            QSlider#progress::sub-page:horizontal {
                background: #44474D;
                border-radius: 2px;
            }

            QSlider#progress::handle:horizontal {
                background: #25272B;
                width: 10px;
                margin: -3px 0;
                border-radius: 5px;
            }
            """
        )

    def make_button(self, text, checkable=False):
        button = QPushButton(text)
        button.setObjectName("musicButton")
        button.setCheckable(checkable)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFont(QFont("Pixel Operator", 8, QFont.Weight.Normal))
        return button

    # ---------------- Placement / dragging / resizing ----------------

    def _position_resize_grip(self):
        if not hasattr(self, "resize_grip"):
            return
        margin = 2
        self.resize_grip.move(
            self.width() - self.resize_grip.width() - margin,
            self.height() - self.resize_grip.height() - margin,
        )
        self.resize_grip.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_resize_grip()
        self._adapt_header()
        # Keep the player inside Anki after a manual resize.
        if getattr(self, "user_moved", False) and not self.dragging and not self.resizing:
            self._clamp_to_main_window()

    def _adapt_header(self):
        if not hasattr(self, "search"):
            return
        # Preserve the compact look while allowing the widget to become smaller.
        width = max(150, min(235, self.width() - 190))
        self.search.setFixedWidth(width)

    def _clamp_to_main_window(self):
        min_x, min_y = 6, 52
        max_x = max(min_x, mw.width() - self.width() - 6)
        max_y = max(min_y, mw.height() - self.height() - 8)
        self.move(
            max(min_x, min(self.x(), max_x)),
            max(min_y, min(self.y(), max_y)),
        )

    def begin_resize(self, global_pos):
        self.resizing = True
        self.user_moved = True
        self.resize_start_pos = global_pos
        self.resize_start_size = self.size()
        self.raise_()

    def update_resize(self, global_pos):
        if not self.resizing or self.resize_start_size is None:
            return
        delta = global_pos - self.resize_start_pos
        min_w = self.minimumWidth()
        min_h = self.minimumHeight()
        new_w = max(min_w, self.resize_start_size.width() + delta.x())
        new_h = max(min_h, self.resize_start_size.height() + delta.y())

        # Do not let resizing make the widget extend beyond Anki's lower-right edge.
        max_w = max(min_w, mw.width() - self.x() - 6)
        max_h = max(min_h, mw.height() - self.y() - 8)
        self.resize(min(new_w, max_w), min(new_h, max_h))
        self.raise_()

    def end_resize(self):
        self.resizing = False
        self.resize_start_size = None
        self.raise_()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            interactive = {
                self.search,
                self.progress,
                self.menu_button,
                self.shuffle_button,
                self.prev_button,
                self.play_button,
                self.next_button,
                self.repeat_button,
                self.wheel,
                getattr(self, "resize_grip", None),
            }

            # Empty player/header space is draggable.
            if child not in interactive:
                self.dragging = True
                self.user_moved = True
                self.drag_offset = event.position().toPoint()
                self.raise_()
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            p = self.pos() + event.position().toPoint() - self.drag_offset
            min_x, min_y = 6, 52
            max_x = max(min_x, mw.width() - self.width() - 6)
            max_y = max(min_y, mw.height() - self.height() - 8)
            self.move(
                max(min_x, min(p.x(), max_x)),
                max(min_y, min(p.y(), max_y)),
            )
            self.raise_()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            was_dragging = self.dragging
            self.dragging = False
            if was_dragging:
                self._save_player_position()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _save_player_position(self):
        """Persist the player's current position so it is restored after restart."""
        settings = QSettings("MELO", "Explore")
        settings.setValue("player_x", int(self.x()))
        settings.setValue("player_y", int(self.y()))
        settings.setValue("player_position_saved", True)
        settings.sync()
        self._saved_player_x = int(self.x())
        self._saved_player_y = int(self.y())
        self._has_saved_player_position = True

    def closeEvent(self, event):
        # Preserve the latest position even if Anki closes without another drag.
        if getattr(self, "user_moved", False):
            self._save_player_position()
        super().closeEvent(event)

    # ---------------- Library ----------------

    def set_library_tab(self, tab_name):
        self.library_tab = tab_name
        self.active_playlist_name = None
        if self.mode != "list":
            self.mode = "list"
        self.refresh_rows()

    def refresh_rows(self):
        if not hasattr(self, "search") or not hasattr(self, "music_list"):
            return

        query = self.search.text().strip().lower()

        def matches(path):
            p = Path(path)
            return (
                not query
                or query in p.stem.lower()
                or query in p.name.lower()
                or query in p.parent.name.lower()
            )

        self.music_list.blockSignals(True)
        self.music_list.clear()

        def add_track(index):
            if not (0 <= index < len(self.tracks)):
                return
            path = Path(self.tracks[index])
            if not matches(path):
                return
            item = QListWidgetItem(path.stem)
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.music_list.addItem(item)

        if self.library_tab == "LIST":
            for index in range(len(self.tracks)):
                add_track(index)

        elif self.library_tab == "QUEUE":
            order = []
            if self.tracks:
                if self.shuffle and len(self.tracks) > 1:
                    candidates = [i for i in range(len(self.tracks)) if i != self.current_index]
                    random.shuffle(candidates)
                    order = candidates[:8]
                else:
                    for step in range(1, min(9, len(self.tracks))):
                        order.append((self.current_index + step) % len(self.tracks))
            for index in order:
                add_track(index)

        elif self.library_tab == "RECENT":
            for path in self.recent:
                if path in self.tracks:
                    add_track(self.tracks.index(path))

        elif self.library_tab == "FAVORITES":
            for index, path in enumerate(self.tracks):
                if path in self.favorites:
                    add_track(index)

        elif self.library_tab == "PLAYLISTS":
            if self.active_playlist_name is None:
                for name in sorted(self.playlists.keys(), key=str.lower):
                    if not query or query in name.lower():
                        item = QListWidgetItem(name)
                        item.setData(Qt.ItemDataRole.UserRole, ("playlist", name))
                        self.music_list.addItem(item)
                if not self.playlists:
                    self.music_list.addItem(QListWidgetItem("No playlists yet — use ••• to create one"))
            else:
                title = self.active_playlist_name
                for path in self.playlists.get(title, []):
                    if path in self.tracks:
                        add_track(self.tracks.index(path))

        if self.library_tab != "PLAYLISTS" or self.active_playlist_name is not None:
            if 0 <= self.current_index < len(self.tracks):
                for row in range(self.music_list.count()):
                    item = self.music_list.item(row)
                    if item.data(Qt.ItemDataRole.UserRole) == self.current_index:
                        self.music_list.setCurrentRow(row)
                        break

        self.music_list.blockSignals(False)

        if hasattr(self, "wheel"):
            self.wheel.set_indices(self._filtered_indices(), self.current_index)

        self._apply_mode()

    def _filtered_indices(self):
        query = self.search.text().strip().lower() if hasattr(self, "search") else ""

        def matches(path):
            p = Path(path)
            return (
                not query
                or query in p.stem.lower()
                or query in p.name.lower()
                or query in p.parent.name.lower()
            )

        if self.library_tab == "LIST":
            source = list(range(len(self.tracks)))
        elif self.library_tab == "FAVORITES":
            source = [i for i, p in enumerate(self.tracks) if p in self.favorites]
        elif self.library_tab == "RECENT":
            source = [self.tracks.index(p) for p in self.recent if p in self.tracks]
        elif self.library_tab == "QUEUE":
            source = [((self.current_index + step) % len(self.tracks)) for step in range(1, min(9, len(self.tracks)))] if self.tracks else []
        elif self.library_tab == "PLAYLISTS" and self.active_playlist_name:
            source = [self.tracks.index(p) for p in self.playlists.get(self.active_playlist_name, []) if p in self.tracks]
        else:
            source = []

        return [i for i in source if matches(self.tracks[i])]

    def _apply_tab_styles(self):
        for name, button in getattr(self, "tab_buttons", {}).items():
            button.setChecked(name == self.library_tab)

    def _apply_mode(self):
        if not hasattr(self, "view_stack"):
            return
        is_list = self.mode == "list"
        self.view_stack.setCurrentWidget(self.list_page if is_list else self.disc_page)
        self.mode_button.setText("DISC" if is_list else "LIST")
        for button in getattr(self, "tab_buttons", {}).values():
            button.setVisible(True)
        self._apply_tab_styles()

    def toggle_mode(self):
        self.mode = "list" if self.mode == "disc" else "disc"
        self._apply_mode()
        self.save_state()
        QSettings("MELO", "Explore").setValue("mode", self.mode)

    def select_from_list(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, tuple) and len(data) == 2 and data[0] == "playlist":
            self.active_playlist_name = data[1]
            self.refresh_rows()
            return
        if isinstance(data, int):
            self.select_from_wheel(data)

    def play_from_list(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, tuple) and len(data) == 2 and data[0] == "playlist":
            self.active_playlist_name = data[1]
            self.refresh_rows()
            return
        if isinstance(data, int):
            self.play_track(data)

    def create_playlist(self):
        name, ok = QInputDialog.getText(self, "Create Playlist", "Playlist name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        self.playlists.setdefault(name, [])
        self.save_state()
        self.library_tab = "PLAYLISTS"
        self.active_playlist_name = None
        self.mode = "list"
        self.refresh_rows()

    def add_current_to_playlist(self):
        if not (0 <= self.current_index < len(self.tracks)):
            return

        names = sorted(self.playlists.keys(), key=str.lower)
        if not names:
            self.create_playlist()
            names = sorted(self.playlists.keys(), key=str.lower)
            if not names:
                return

        name, ok = QInputDialog.getItem(
            self, "Add to Playlist", "Playlist:", names, 0, False
        )
        if not ok:
            return

        path = self.tracks[self.current_index]
        if path not in self.playlists[name]:
            self.playlists[name].append(path)
            self.save_state()

        self.library_tab = "PLAYLISTS"
        self.active_playlist_name = name
        self.mode = "list"
        self.refresh_rows()

    def toggle_favorite(self):
        if not (0 <= self.current_index < len(self.tracks)):
            return
        path = self.tracks[self.current_index]
        if path in self.favorites:
            self.favorites.remove(path)
        else:
            self.favorites.add(path)
        self._update_favorite_action()
        self.save_state()
        self.refresh_rows()

    def _update_favorite_action(self):
        if not hasattr(self, "favorite_action"):
            return
        active = (
            0 <= self.current_index < len(self.tracks)
            and self.tracks[self.current_index] in self.favorites
        )
        self.favorite_action.setText(
            "♡ REMOVE FROM FAVORITES" if active else "♡ ADD TO FAVORITES"
        )
        if hasattr(self, "favorite_playback_button"):
            self.favorite_playback_button.setText("♥" if active else "♡")
            self.favorite_playback_button.setProperty(
                "favorited", "true" if active else "false"
            )
            self.favorite_playback_button.style().unpolish(self.favorite_playback_button)
            self.favorite_playback_button.style().polish(self.favorite_playback_button)

    # ---------------- Background ----------------

    def _refresh_library_background(self):
        for widget_name in ("list_page", "disc_page"):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.update()
        if hasattr(self, "wheel"):
            self.wheel._background_cache = None
            self.wheel._background_cache_size = None
            self.wheel.update()
        if hasattr(self, "music_list"):
            self.music_list.viewport().update()

    def choose_background(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Music Player Background",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"
        )
        if not path:
            return
        pix = QPixmap(path)
        if pix.isNull():
            return
        self.background_path = path
        self._background_pixmap = pix
        cfg = get_config()
        cfg["background_path"] = path
        save_config(cfg)
        self._refresh_library_background()

    def reset_background(self):
        self.background_path = ""
        self._background_pixmap = QPixmap()
        cfg = get_config()
        cfg["background_path"] = ""
        save_config(cfg)
        self._refresh_library_background()

    # ---------------- Import ----------------

    def _append_files(self, files):
        changed = False

        for file in files:
            path = str(Path(file))
            if path not in self.tracks:
                self.tracks.append(path)
                changed = True

        if self.current_index < 0 and self.tracks:
            self.current_index = 0
            self.load_current(False)

        if changed:
            self.save_state()
            self.refresh_rows()

    def add_music(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Choose music",
            "",
            "Audio files (*.mp3 *.wav *.ogg *.oga *.flac *.m4a *.aac *.opus *.wma)",
        )
        self._append_files(files)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose a music folder",
            "",
        )
        if not folder:
            return

        root = Path(folder)
        files = [
            str(path)
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
        ]
        files.sort(key=str.lower)
        self._append_files(files)

    def remove_folder(self):
        """Remove library entries located inside a selected folder.

        This only removes the music paths from MELO's library. It never
        deletes the actual files from the user's disk. It also works for
        folders imported before this feature was added because it matches
        the stored track paths directly.
        """
        folder = QFileDialog.getExistingDirectory(
            self,
            "Remove a music folder from MELO",
            "",
        )
        if not folder:
            return

        root = Path(folder).resolve()
        matched = []
        for track in self.tracks:
            try:
                track_path = Path(track).resolve()
                track_path.relative_to(root)
            except (OSError, ValueError):
                continue
            matched.append(track)

        if not matched:
            QMessageBox.information(
                self,
                "MELO Library",
                "No music from that folder is currently in your MELO library.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Remove folder from library?",
            f"Remove {len(matched)} track(s) from MELO's library?\n\n"
            "Your actual music files will NOT be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        current_path = None
        if 0 <= self.current_index < len(self.tracks):
            current_path = self.tracks[self.current_index]

        remove_set = set(matched)
        self.tracks = [track for track in self.tracks if track not in remove_set]

        if not self.tracks:
            self.current_index = -1
            self.player.stop()
        elif current_path in remove_set:
            self.current_index = min(self.current_index, len(self.tracks) - 1)
            self.load_current(False)
        elif current_path in self.tracks:
            self.current_index = self.tracks.index(current_path)
        else:
            self.current_index = min(self.current_index, len(self.tracks) - 1)

        # Remove the same paths from MELO's secondary collections so that
        # Favorites, Recent, and Playlists do not retain dead library entries.
        self.favorites.difference_update(remove_set)
        self.recent = [path for path in self.recent if path not in remove_set]
        for playlist_name, playlist_tracks in list(self.playlists.items()):
            self.playlists[playlist_name] = [path for path in playlist_tracks if path not in remove_set]

        self.save_state()
        self.refresh_rows()
        self._update_favorite_action()

    # ---------------- Playback ----------------

    def select_from_wheel(self, index):
        """Update the highlighted/previewed track without touching the wheel geometry.

        During wheel animation this must NOT call refresh_rows() or setMediaSource(),
        because either operation can trigger extra repaints and make the finished
        frame visibly snap/jitter.  The actual media source is committed only when
        the user presses Enter or the main Play button.
        """
        if not (0 <= index < len(self.tracks)):
            return

        self.current_index = index
        path = Path(self.tracks[index])

        self.current_title.setText(path.stem)
        self.current_artist.setText(path.parent.name or "LOCAL MUSIC")

        cover = find_cover(path)
        self.big_cover.set_art(str(cover) if cover else None)

        if hasattr(self, "music_list"):
            self.music_list.blockSignals(True)
            for row in range(self.music_list.count()):
                item = self.music_list.item(row)
                if item.data(Qt.ItemDataRole.UserRole) == index:
                    self.music_list.setCurrentRow(row)
                    break
            self.music_list.blockSignals(False)

    def _filtered_indices(self):
        query = self.search.text().strip().lower() if hasattr(self, "search") else ""
        result = []
        for index, path in enumerate(self.tracks):
            p = Path(path)
            if (
                not query
                or query in p.stem.lower()
                or query in p.name.lower()
                or query in p.parent.name.lower()
            ):
                result.append(index)
        return result

    def play_track(self, index):
        if 0 <= index < len(self.tracks):
            self.current_index = index
            self.load_current(True)

    def load_current(self, auto_play=False):
        if not self.tracks or self.current_index < 0:
            self.current_title.setText("No music selected")
            self.current_artist.setText("LOCAL MUSIC")
            self.big_cover.set_art(None)
            self.big_cover.set_playing(False)
            return

        path = Path(self.tracks[self.current_index])

        self.current_title.setText(path.stem)
        self.current_artist.setText(path.parent.name or "LOCAL MUSIC")

        cover = find_cover(path)
        self.big_cover.set_art(str(cover) if cover else None)

        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.refresh_rows()

        if auto_play:
            current_path = str(path)
            if current_path in self.recent:
                self.recent.remove(current_path)
            self.recent.insert(0, current_path)
            self.recent = self.recent[:30]
            self._update_favorite_action()
            self.save_state()
            self.player.play()

    def toggle_play(self):
        if not self.tracks:
            self.add_music()
            if not self.tracks:
                return

        if (
            self.player.playbackState()
            == QMediaPlayer.PlaybackState.PlayingState
        ):
            self.player.pause()
        else:
            self.player.play()

    def previous(self):
        if not self.tracks:
            return

        if self.player.position() > 2500:
            self.player.setPosition(0)
            return

        self.current_index = (
            self.current_index - 1
        ) % len(self.tracks)
        self.load_current(True)

    def next_track(self):
        if not self.tracks:
            return

        if self.shuffle and len(self.tracks) > 1:
            choices = [
                i for i in range(len(self.tracks))
                if i != self.current_index
            ]
            self.current_index = random.choice(choices)
        else:
            self.current_index = (
                self.current_index + 1
            ) % len(self.tracks)

        self.load_current(True)

    def _style_mode_button(self, button, active=False):
        # Two clear visual states: idle black icon vs active pink icon with underline.
        if active:
            button.setStyleSheet(
                "QPushButton { background: transparent; border: none; "
                "border-bottom: 2px solid #E86D90; padding: 0; color: #E86D90; }"
                "QPushButton:hover { color: #E86D90; }"
            )
        else:
            button.setStyleSheet(
                "QPushButton { background: transparent; border: none; "
                "border-bottom: 2px solid transparent; padding: 0; color: #000000; }"
                "QPushButton:hover { color: #555555; }"
            )

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        self.shuffle_button.setChecked(self.shuffle)
        self._style_mode_button(self.shuffle_button, active=self.shuffle)
        self.save_state()

    def toggle_repeat(self):
        self.repeat = not self.repeat
        self.repeat_button.setChecked(self.repeat)
        self._style_mode_button(self.repeat_button, active=self.repeat)
        self.save_state()

    def seek(self, position):
        position = int(max(0, position))
        self._seek_override_until = time.monotonic() + 0.30
        self.progress.setValue(position)
        self.now_time.setText(self.format_ms(position))
        self.player.setPosition(position)

    def set_volume(self, value):
        self.audio_output.setVolume(value / 100.0)
        self.save_state()

    # ---------------- Media ----------------

    def update_progress_from_player(self):
        try:
            duration = int(self.player.duration())
            position = int(self.player.position())
        except Exception:
            return

        if duration > 0:
            if self.progress.maximum() != duration:
                self.progress.setRange(0, duration)
                self.total_time.setText(self.format_ms(duration))
            if not self.progress.isSliderDown() and time.monotonic() >= self._seek_override_until:
                self.progress.setValue(max(0, min(position, duration)))
                self.now_time.setText(self.format_ms(position))
            elif time.monotonic() >= self._seek_override_until:
                self.now_time.setText(self.format_ms(position))

    def on_duration(self, duration):
        duration = max(0, int(duration))
        self.progress.setRange(0, duration)
        self.total_time.setText(self.format_ms(duration))

    def on_position(self, position):
        if not self.progress.isSliderDown() and time.monotonic() >= self._seek_override_until:
            self.progress.setValue(position)
            self.now_time.setText(self.format_ms(position))
        elif time.monotonic() >= self._seek_override_until:
            self.now_time.setText(self.format_ms(position))

    def on_state(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.set_playing_icon(playing)
        if hasattr(self, "visualizer"):
            self.visualizer.set_playing(playing)
        self.big_cover.set_playing(playing)
        self.wheel.set_playing(playing)

    def on_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.repeat:
                self.player.setPosition(0)
                self.player.play()
            else:
                self.next_track()

    @staticmethod
    def format_ms(ms):
        total = max(0, int(ms // 1000))
        minutes, seconds = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _prompt_for_name(self):
        cfg = get_config()
        if bool(cfg.get("name_configured", False)) and str(cfg.get("welcome_name", "")).strip():
            return

        name, ok = QInputDialog.getText(
            self,
            "Welcome to MELO",
            "What should I call you?",
            QLineEdit.EchoMode.Normal,
            "",
        )
        name = name.strip() if ok else ""
        if not name:
            # Keep the first-run prompt pending so the user can set it later.
            self.welcome_name = "there"
            self._name_needs_setup = True
            return

        self.welcome_name = name
        self._name_needs_setup = False
        cfg["welcome_name"] = name
        cfg["name_configured"] = True
        save_config(cfg)
        self.welcome_back.setText(f"welcome back, {self.welcome_name}!   LOW  |  HIGH")

    # ---------------- Persistence ----------------

    def save_state(self):
        cfg = get_config()
        cfg["tracks"] = self.tracks
        cfg["volume"] = self.audio_output.volume()
        cfg["shuffle"] = self.shuffle
        cfg["repeat"] = self.repeat
        cfg["mode"] = self.mode
        cfg["recent"] = self.recent
        cfg["favorites"] = sorted(self.favorites)
        cfg["playlists"] = self.playlists
        cfg["background_path"] = self.background_path
        cfg["welcome_name"] = self.welcome_name if self.welcome_name != "there" else cfg.get("welcome_name", "")
        cfg["name_configured"] = bool(cfg.get("name_configured", False))
        save_config(cfg)
        QSettings("MELO", "Explore").setValue("mode", self.mode)

    def eventFilter(self, obj, event):
        # Keyboard navigation: Left/Right rotate the wheel, Enter plays the
        # centered song. Do not steal keys while typing in text fields.
        if (
            event.type() == QEvent.Type.KeyPress
            and self.isVisible()
            and mw.isActiveWindow()
        ):
            from PyQt6.QtWidgets import QLineEdit, QTextEdit
            focused = QApplication.focusWidget()
            if not isinstance(focused, (QLineEdit, QTextEdit)):
                if event.key() == Qt.Key.Key_Left:
                    if self.mode == "disc":
                        self.wheel._rotate_steps(-1)
                        event.accept()
                        return True
                if event.key() == Qt.Key.Key_Right:
                    if self.mode == "disc":
                        self.wheel._rotate_steps(1)
                        event.accept()
                        return True
                if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    if self.mode == "disc":
                        indices = self.wheel.indices
                        if indices:
                            self.play_track(self.wheel.selected_index())
                    elif self.mode == "list":
                        item = self.music_list.currentItem()
                        if item is not None:
                            data = item.data(Qt.ItemDataRole.UserRole)
                            if isinstance(data, int):
                                self.play_track(data)
                            elif isinstance(data, tuple) and data[0] == "playlist":
                                self.active_playlist_name = data[1]
                                self.refresh_rows()
                    event.accept()
                    return True
                if event.key() == Qt.Key.Key_Space:
                    self.toggle_play()
                    event.accept()
                    return True

        # Keep the player inside the Anki window when Anki is resized/shown.
        if obj is mw and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.WindowActivate,
        ):
            if not self.dragging and not self.resizing:
                self._clamp_to_main_window()
                self.raise_()
        return False


_player = None


def init_music():
    global _player
    if _player is None:
        _player = MELO()
    _player.show()
    _player.raise_()
    if getattr(_player, "_name_needs_setup", False):
        QTimer.singleShot(350, _player._prompt_for_name)

gui_hooks.main_window_did_init.append(init_music)
