from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import sys
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--disable-gpu --disable-gpu-compositing --disable-software-rasterizer "
    "--disable-features=VizDisplayCompositor --no-sandbox",
)
os.environ.setdefault("QT_OPENGL", "software")

from PySide6.QtCore import QPoint, QRect, QTimer, QUrl, QUrlQuery, Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QWidget

from .models import OverlayEntry, OverlayGeometry, OverlaySourceType
from .runtime_paths import bundle_root
from .service import DamageLogService, ServiceConfig

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class OverlayWindowConfig:
    entry: OverlayEntry
    ws_port: int
    min_width: int = 640
    min_height: int = 320
    default_width: int = 980
    default_height: int = 492
    margin_top: int = 56
    margin_right: int = 56
    resize_margin: int = 10
    on_geometry_changed: Callable[[str, OverlayGeometry], None] | None = None
    on_closed: Callable[[str], None] | None = None


def _window_defaults(entry: OverlayEntry) -> dict[str, int]:
    builtin_key = (entry.source_value or "damage").strip().lower()
    if entry.source_type == OverlaySourceType.BUILTIN and builtin_key == "uid_mask":
        return {
            "min_width": 100,
            "min_height": 20,
            "default_width": 100,
            "default_height": 20,
        }
    if entry.source_type == OverlaySourceType.BUILTIN and builtin_key in {"combo_skill", "buff"}:
        return {
            "min_width": 180,
            "min_height": 1,
            "default_width": 300,
            "default_height": 200,
        }
    return {
        "min_width": 600,
        "min_height": 300,
        "default_width": 700,
        "default_height": 350,
    }


def _builtin_overlay_index(source_value: str) -> Path:
    package_asset_dir = Path(__file__).resolve().parent / "overlay_assets"
    repo_root = bundle_root()
    builtin_key = (source_value or "damage").strip().lower()
    builtin_paths = {
        "damage": repo_root / "overlay" / "dist" / "index.html",
        "combo_skill": repo_root / "overlay_comboskill" / "dist" / "index.html",
        "buff": repo_root / "overlay_buff" / "dist" / "index.html",
        "uid_mask": repo_root / "overlay_uid" / "dist" / "index.html",
    }
    target = builtin_paths.get(builtin_key)
    if target is not None and target.exists():
        return target
    return package_asset_dir / "index.html"


class OverlayWindow(QWidget):
    def __init__(self, config: OverlayWindowConfig) -> None:
        super().__init__(None)
        self.config = config
        self.entry = config.entry
        self._drag_origin: QPoint | None = None
        self._resize_origin: QPoint | None = None
        self._resize_geometry: QRect | None = None
        self._active_edges = Qt.Edge(0)
        self._suppress_geometry_callback = False
        self._content_timer: QTimer | None = None

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMouseTracking(True)
        self.setMinimumSize(config.min_width, config.min_height)
        self.setWindowTitle(self.entry.name)
        self._apply_window_flags()

        self.webview = QWebEngineView(self)
        self.webview.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.webview.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.webview.page().setBackgroundColor(QColor(0, 0, 0, 0))
        self.webview.setStyleSheet("background: transparent; border: 0;")
        self.webview.setMouseTracking(True)
        self.webview.loadFinished.connect(self._handle_load_finished)

        self._apply_initial_geometry()
        self.webview.resize(self.size())
        self.setWindowOpacity(self.entry.opacity)
        self.webview.setZoomFactor(self.entry.scale)
        self._load_overlay()

    def apply_entry(self, entry: OverlayEntry) -> None:
        previous = self.entry
        self.entry = entry
        self.setWindowTitle(entry.name)
        if entry.geometry is not None:
            self._suppress_geometry_callback = True
            self.setGeometry(entry.geometry.x, entry.geometry.y, entry.geometry.width, entry.geometry.height)
            self._suppress_geometry_callback = False
        if previous.click_through != entry.click_through:
            self._apply_window_flags()
        if previous.opacity != entry.opacity:
            self.setWindowOpacity(entry.opacity)
        if abs(previous.scale - entry.scale) > 0.0001:
            self.webview.setZoomFactor(entry.scale)
        if previous.locked != entry.locked:
            self._push_overlay_state()
        if (
            previous.source_type != entry.source_type
            or previous.source_value != entry.source_value
        ):
            self._load_overlay()
        if not self.isVisible():
            self.show()
        self._update_cursor(self._hit_test_edges(QPoint()))

    def resizeEvent(self, event) -> None:  # noqa: N802
        self.webview.resize(self.size())
        self._emit_geometry_changed()
        super().resizeEvent(event)

    def moveEvent(self, event) -> None:  # noqa: N802
        self._emit_geometry_changed()
        super().moveEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.config.on_closed is not None:
            self.config.on_closed(self.entry.id)
        super().closeEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self.entry.locked:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._handle_mouse_press(event.position().toPoint(), event.globalPosition().toPoint())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self.entry.locked:
            self.unsetCursor()
            return
        self._handle_mouse_move(event.position().toPoint(), event.globalPosition().toPoint(), event.buttons())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._handle_mouse_release(event.position().toPoint())
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._drag_origin is None and self._resize_origin is None:
            self.unsetCursor()
        super().leaveEvent(event)

    def _apply_initial_geometry(self) -> None:
        if self.entry.geometry is not None:
            geometry = self.entry.geometry
            self.setGeometry(geometry.x, geometry.y, geometry.width, geometry.height)
            return
        width = max(self.minimumWidth(), int(round(self.config.default_width * self.entry.scale)))
        height = max(self.minimumHeight(), int(round(self.config.default_height * self.entry.scale)))
        self.resize(width, height)
        self._move_to_default_position()

    def _move_to_default_position(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        x = geometry.x() + geometry.width() - self.width() - self.config.margin_right
        y = geometry.y() + self.config.margin_top
        self.move(max(geometry.x(), x), max(geometry.y(), y))

    def _apply_window_flags(self) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        if self.entry.click_through:
            flags |= Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)
        if self.isVisible():
            self.show()

    def _load_overlay(self) -> None:
        if self.entry.source_type == OverlaySourceType.BUILTIN:
            url = QUrl.fromLocalFile(str(_builtin_overlay_index(self.entry.source_value).resolve()))
        elif self.entry.source_type == OverlaySourceType.FILE:
            url = QUrl.fromLocalFile(str(Path(self.entry.source_value).resolve()))
        else:
            url = QUrl.fromUserInput(self.entry.source_value)
        query = QUrlQuery(url)
        query.addQueryItem("wsPort", str(self.config.ws_port))
        query.addQueryItem("builtin", self.entry.source_value or "damage")
        query.addQueryItem("locked", "1" if self.entry.locked else "0")
        query.addQueryItem("assetRoot", str(bundle_root()))
        url.setQuery(query)
        self.webview.setUrl(url)

    def _handle_load_finished(self, ok: bool) -> None:
        if ok:
            self._push_overlay_state()
            self._start_content_sync()

    def _push_overlay_state(self) -> None:
        payload = json.dumps(
            {
                "id": self.entry.id,
                "locked": self.entry.locked,
                "click_through": self.entry.click_through,
                "opacity": self.entry.opacity,
                "scale": self.entry.scale,
                "builtin": self.entry.source_value or "damage",
            },
            ensure_ascii=False,
        )
        script = (
            "window.dispatchEvent(new CustomEvent("
            "'endfield-overlay-config', { detail: " + payload + " }));"
        )
        self.webview.page().runJavaScript(script)

    def _start_content_sync(self) -> None:
        if self.entry.source_type != OverlaySourceType.BUILTIN or (self.entry.source_value or "").lower() != "combo_skill":
            return
        if self._content_timer is None:
            self._content_timer = QTimer(self)
            self._content_timer.setInterval(250)
            self._content_timer.timeout.connect(self._poll_combo_content_size)
        if not self._content_timer.isActive():
            self._content_timer.start()

    def _poll_combo_content_size(self) -> None:
        if self.entry.source_type != OverlaySourceType.BUILTIN or (self.entry.source_value or "").lower() != "combo_skill":
            return
        script = """
            (() => {
              const shell = document.querySelector('.combo-overlay-shell');
              if (!shell) {
                return { height: 0, placeholder: false };
              }
              const rect = shell.getBoundingClientRect();
              return {
                height: Math.ceil(rect.height || 0),
                placeholder: shell.classList.contains('is-placeholder'),
              };
            })();
        """
        self.webview.page().runJavaScript(script, self._apply_combo_content_size)

    def _apply_combo_content_size(self, result) -> None:
        if not isinstance(result, dict):
            return
        if self.entry.source_type != OverlaySourceType.BUILTIN or (self.entry.source_value or "").lower() != "combo_skill":
            return
        if not self.entry.locked:
            return
        if bool(result.get("placeholder")):
            return
        content_height = max(0, int(result.get("height", 0) or 0))
        target_height = max(1, content_height)
        if self.height() == target_height:
            return
        self._suppress_geometry_callback = True
        self.resize(self.width(), target_height)
        self._suppress_geometry_callback = False

    def _emit_geometry_changed(self) -> None:
        if self._suppress_geometry_callback or self.config.on_geometry_changed is None:
            return
        geometry = self.geometry()
        self.config.on_geometry_changed(
            self.entry.id,
            OverlayGeometry(
                x=geometry.x(),
                y=geometry.y(),
                width=geometry.width(),
                height=geometry.height(),
            ),
        )

    def _handle_mouse_press(self, local_pos: QPoint, global_pos: QPoint) -> None:
        edges = self._hit_test_edges(local_pos)
        if edges != Qt.Edge(0):
            self._resize_origin = global_pos
            self._resize_geometry = self.geometry()
            self._active_edges = edges
            return
        self._drag_origin = global_pos - self.frameGeometry().topLeft()

    def _handle_mouse_move(self, local_pos: QPoint, global_pos: QPoint, buttons) -> None:
        edges = self._hit_test_edges(local_pos)
        if self._resize_origin is not None and self._resize_geometry is not None:
            self._resize_from_drag(global_pos)
            return
        if self._drag_origin is not None and buttons & Qt.MouseButton.LeftButton:
            self.move(global_pos - self._drag_origin)
            return
        self._update_cursor(edges)

    def _handle_mouse_release(self, local_pos: QPoint) -> None:
        self._drag_origin = None
        self._resize_origin = None
        self._resize_geometry = None
        self._active_edges = Qt.Edge(0)
        self._update_cursor(self._hit_test_edges(local_pos))

    def _hit_test_edges(self, pos: QPoint):
        if self.entry.locked:
            return Qt.Edge(0)
        margin = self.config.resize_margin
        edges = Qt.Edge(0)
        if pos.x() <= margin:
            edges |= Qt.Edge.LeftEdge
        elif pos.x() >= self.width() - margin:
            edges |= Qt.Edge.RightEdge
        if pos.y() <= margin:
            edges |= Qt.Edge.TopEdge
        elif pos.y() >= self.height() - margin:
            edges |= Qt.Edge.BottomEdge
        return edges

    def _update_cursor(self, edges) -> None:
        if self.entry.locked:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        if edges == (Qt.Edge.LeftEdge | Qt.Edge.TopEdge) or edges == (Qt.Edge.RightEdge | Qt.Edge.BottomEdge):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edges == (Qt.Edge.RightEdge | Qt.Edge.TopEdge) or edges == (Qt.Edge.LeftEdge | Qt.Edge.BottomEdge):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif edges in {Qt.Edge.LeftEdge, Qt.Edge.RightEdge}:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edges in {Qt.Edge.TopEdge, Qt.Edge.BottomEdge}:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def _resize_from_drag(self, global_pos: QPoint) -> None:
        assert self._resize_origin is not None
        assert self._resize_geometry is not None

        delta = global_pos - self._resize_origin
        geometry = QRect(self._resize_geometry)
        min_width = self.minimumWidth()
        min_height = self.minimumHeight()

        if self._active_edges & Qt.Edge.LeftEdge:
            new_left = geometry.left() + delta.x()
            max_left = geometry.right() - min_width + 1
            geometry.setLeft(min(new_left, max_left))
        if self._active_edges & Qt.Edge.RightEdge:
            geometry.setWidth(max(min_width, geometry.width() + delta.x()))
        if self._active_edges & Qt.Edge.TopEdge:
            new_top = geometry.top() + delta.y()
            max_top = geometry.bottom() - min_height + 1
            geometry.setTop(min(new_top, max_top))
        if self._active_edges & Qt.Edge.BottomEdge:
            geometry.setHeight(max(min_height, geometry.height() + delta.y()))

        self.setGeometry(geometry)


class OverlayManager:
    def __init__(self, ws_port: int, on_entry_changed: Callable[[OverlayEntry], None] | None = None) -> None:
        self.ws_port = ws_port
        self.on_entry_changed = on_entry_changed
        self._entries: dict[str, OverlayEntry] = {}
        self._windows: dict[str, OverlayWindow] = {}
        self._visible = True

    def sync_entries(self, entries: list[OverlayEntry]) -> None:
        current_ids = {entry.id for entry in entries}
        for entry in entries:
            self.apply_entry(entry)
        for entry_id in list(self._entries):
            if entry_id not in current_ids:
                self.remove_entry(entry_id)

    def apply_entry(self, entry: OverlayEntry) -> None:
        self._entries[entry.id] = replace(entry)
        if entry.enabled:
            window = self._windows.get(entry.id)
            if window is None:
                window = OverlayWindow(
                    OverlayWindowConfig(
                        entry=replace(entry),
                        ws_port=self.ws_port,
                        **_window_defaults(entry),
                        on_geometry_changed=self._handle_geometry_changed,
                        on_closed=self._handle_window_closed,
                    )
                )
                self._windows[entry.id] = window
                if self._visible:
                    window.show()
            else:
                window.apply_entry(replace(entry))
                if self._visible:
                    window.show()
                else:
                    window.hide()
        else:
            self._close_window(entry.id)

    def remove_entry(self, entry_id: str) -> None:
        self._entries.pop(entry_id, None)
        self._close_window(entry_id)

    def close_all(self) -> None:
        for entry_id in list(self._windows):
            self._close_window(entry_id)

    def opened_window_count(self) -> int:
        return len(self._windows)

    def set_enabled_entries_visible(self, visible: bool) -> None:
        self._visible = visible
        for window in self._windows.values():
            if visible:
                window.show()
            else:
                window.hide()

    def enabled_entries_visible(self) -> bool:
        return self._visible

    def _close_window(self, entry_id: str) -> None:
        window = self._windows.pop(entry_id, None)
        if window is None:
            return
        window.config.on_closed = None
        window.close()

    def _handle_geometry_changed(self, entry_id: str, geometry: OverlayGeometry) -> None:
        entry = self._entries.get(entry_id)
        if entry is None:
            return
        updated = replace(entry, geometry=geometry)
        self._entries[entry_id] = updated
        if self.on_entry_changed is not None:
            self.on_entry_changed(replace(updated))

    def _handle_window_closed(self, entry_id: str) -> None:
        self._windows.pop(entry_id, None)
        entry = self._entries.get(entry_id)
        if entry is None:
            return
        updated = replace(entry, enabled=False)
        self._entries[entry_id] = updated
        if self.on_entry_changed is not None:
            self.on_entry_changed(replace(updated))


def run_with_overlay(service_config: ServiceConfig) -> int:
    service: DamageLogService | None = None
    service_thread: threading.Thread | None = None
    service_error: list[BaseException] = []

    def port_is_available(port: int) -> bool:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False
        finally:
            probe.close()

    def service_main() -> None:
        try:
            assert service is not None
            asyncio.run(service.run())
        except BaseException as exc:  # noqa: BLE001
            LOGGER.error("service thread failed", exc_info=(type(exc), exc, exc.__traceback__))
            service_error.append(exc)

    attach_only = not port_is_available(service_config.ws_port)
    if attach_only:
        LOGGER.warning(
            "ws port %d is already in use; the overlay will attach to the existing service instead of starting a new one",
            service_config.ws_port,
        )
    else:
        service = DamageLogService(service_config)
        service_thread = threading.Thread(target=service_main, name="damage-service", daemon=True)
        service_thread.start()

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    manager = OverlayManager(service_config.ws_port)
    manager.sync_entries(
        [
            OverlayEntry(
                id="builtin-overlay",
                name="伤害统计",
                source_type=OverlaySourceType.BUILTIN,
                source_value="damage",
                enabled=True,
                locked=False,
                click_through=False,
                opacity=1.0,
            )
        ]
    )

    def poll_state() -> None:
        if service_error:
            LOGGER.error("overlay is closing because the service thread exited with an error")
            app.quit()
            return
        if service_thread is not None and not service_thread.is_alive():
            app.quit()

    app.aboutToQuit.connect(manager.close_all)
    if service is not None:
        app.aboutToQuit.connect(service.request_stop)

    poll_timer = QTimer()
    poll_timer.setInterval(250)
    poll_timer.timeout.connect(poll_state)
    poll_timer.start()

    exit_code = app.exec()

    if service is not None:
        service.request_stop()
    if service_thread is not None:
        service_thread.join(timeout=5)
    if service_error:
        raise service_error[0]
    return exit_code
