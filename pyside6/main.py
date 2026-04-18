import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QFrame, QLabel, QPushButton, QScrollArea, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, QSize, QPoint
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QPixmap, QIcon, QPolygon

# --- Industrial Tacticalism Design Constants ---
COLOR_PRIMARY = "#feef00"
COLOR_BG = "#f0f0f0"
COLOR_SURFACE = "#ffffff"
COLOR_TEXT = "#1d1c10"
COLOR_SECONDARY_TEXT = "#5e5e5e"
COLOR_BORDER = "#323123"
COLOR_SIDEBAR = "#f7f7f7"

FONT_HEADLINE = "Space Grotesk"
FONT_BODY = "Inter"
FONT_MONO = "Roboto Mono"

class TacticalCard(QFrame):
    """A card with the Industrial Tacticalism style."""
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("TacticalCard")
        self.setStyleSheet(f"""
            #TacticalCard {{
                background-color: {COLOR_SURFACE};
                border: 1px solid {COLOR_BORDER};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Header
        header_layout = QHBoxLayout()
        accent = QFrame()
        accent.setFixedSize(6, 12)
        accent.setStyleSheet(f"background-color: {COLOR_PRIMARY}; border: none;")
        header_layout.addWidget(accent)
        
        self.title_label = QLabel(title.upper())
        self.title_label.setStyleSheet(f"font-family: '{FONT_HEADLINE}'; font-weight: 900; font-size: 14px; color: {COLOR_TEXT};")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # Content area
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 10, 0, 0)
        layout.addWidget(self.content_widget)

class PerformanceChart(QWidget):
    """A custom widget to draw the performance chart."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(100)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w, h = self.width(), self.height()
        
        # Draw grid
        painter.setPen(QPen(QColor("#e0e0e0"), 1, Qt.DotLine))
        for i in range(1, 6):
            x = int(w * i / 6)
            painter.drawLine(x, 0, x, h)
        for i in range(1, 4):
            y = int(h * i / 4)
            painter.drawLine(0, y, w, y)
            
        # Draw data path
        points = [
            QPoint(0, h),
            QPoint(0, h*0.8),
            QPoint(w*0.1, h*0.7),
            QPoint(w*0.2, h*0.85),
            QPoint(w*0.3, h*0.6),
            QPoint(w*0.4, h*0.65),
            QPoint(w*0.5, h*0.4),
            QPoint(w*0.6, h*0.5),
            QPoint(w*0.7, h*0.3),
            QPoint(w*0.8, h*0.35),
            QPoint(w*0.9, h*0.2),
            QPoint(w, h*0.25),
            QPoint(w, h)
        ]
        
        poly = QPolygon(points)
        painter.setBrush(QBrush(QColor(255, 240, 0, 100)))
        painter.setPen(QPen(QColor(COLOR_PRIMARY), 2))
        painter.drawPolygon(poly)

class ModernWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ZMD LOGS - System Status")
        self.resize(1100, 800)
        
        # Modern Frameless Window (Optional, but for "Modern" feel)
        # self.setWindowFlags(Qt.FramelessWindowHint)
        # self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.setup_ui()
        
    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # --- Sidebar ---
        sidebar = QFrame()
        sidebar.setFixedWidth(250)
        sidebar.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_SIDEBAR};
                border-right: 3px solid {COLOR_BORDER};
            }}
        """)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        
        # Logo
        logo_container = QFrame()
        logo_container.setFixedHeight(100)
        logo_container.setStyleSheet("border-bottom: 1px solid rgba(0,0,0,0.1);")
        logo_layout = QVBoxLayout(logo_container)
        
        # Local Logo Loading
        logo = QLabel()
        logo_pixmap = QPixmap("logo.png") # Ensure logo.png is in the same directory
        if logo_pixmap.isNull():
            # Fallback text if logo file is missing
            logo.setText("ZMD LOGS")
            logo.setStyleSheet(f"font-family: '{FONT_HEADLINE}'; font-weight: 900; font-size: 24px; color: {COLOR_TEXT};")
        else:
            logo.setPixmap(logo_pixmap.scaled(180, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        logo.setFixedSize(180, 60)
        logo_layout.addWidget(logo, alignment=Qt.AlignCenter)
        sidebar_layout.addWidget(logo_container)
        
        # Nav Links
        nav_container = QWidget()
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(15, 20, 15, 20)
        nav_layout.setSpacing(10)
        
        status_btn = QPushButton("  STATUS")
        status_btn.setFixedHeight(40)
        status_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                font-family: '{FONT_HEADLINE}';
                font-weight: bold;
                font-size: 12px;
                text-align: left;
                padding-left: 10px;
            }}
        """)
        nav_layout.addWidget(status_btn)
        
        for text in ["FLOATING WINDOW SETTINGS", "COMBAT LOG LIST", "SETTINGS"]:
            btn = QPushButton(f"  {text}")
            btn.setFixedHeight(40)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: none;
                    color: {COLOR_SECONDARY_TEXT};
                    font-family: '{FONT_HEADLINE}';
                    font-weight: bold;
                    font-size: 11px;
                    text-align: left;
                    padding-left: 10px;
                }}
                QPushButton:hover {{
                    background-color: #e0e0e0;
                }}
            """)
            nav_layout.addWidget(btn)
            
        nav_layout.addStretch()
        sidebar_layout.addWidget(nav_container)
        
        # User Section
        user_section = QFrame()
        user_section.setFixedHeight(60)
        user_section.setStyleSheet("border-top: 1px solid rgba(0,0,0,0.1);")
        user_layout = QHBoxLayout(user_section)
        user_layout.setContentsMargins(15, 0, 15, 0)
        
        avatar = QFrame()
        avatar.setFixedSize(24, 24)
        avatar.setStyleSheet("background-color: #ccc; border: 1px solid #999;")
        user_layout.addWidget(avatar)
        
        user_name = QLabel("SQUAD_01")
        user_name.setStyleSheet(f"font-family: '{FONT_MONO}'; font-weight: bold; font-size: 10px;")
        user_layout.addWidget(user_name)
        user_layout.addStretch()
        
        logout_btn = QPushButton("⏻")
        logout_btn.setFixedSize(24, 24)
        logout_btn.setStyleSheet("border: none; color: #5e5e5e; font-size: 16px;")
        user_layout.addWidget(logout_btn)
        
        sidebar_layout.addWidget(user_section)
        main_layout.addWidget(sidebar)
        
        # --- Main Content ---
        content_area = QWidget()
        content_area.setStyleSheet(f"background-color: #fdfdfd;")
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # Header
        header = QFrame()
        header.setFixedHeight(80)
        header.setStyleSheet("background-color: white; border-bottom: 1px solid rgba(0,0,0,0.05);")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(30, 0, 30, 0)
        
        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        title_vbox.addStretch()
        main_title = QLabel("SYSTEM STATUS")
        main_title.setStyleSheet(f"font-family: '{FONT_HEADLINE}'; font-weight: 900; font-size: 24px; letter-spacing: -1px;")
        title_vbox.addWidget(main_title)
        
        sub_info = QHBoxLayout()
        live_tag = QLabel(" LIVE_FEED ")
        live_tag.setStyleSheet(f"background-color: {COLOR_BORDER}; color: {COLOR_PRIMARY}; font-family: '{FONT_MONO}'; font-weight: bold; font-size: 8px;")
        sub_info.addWidget(live_tag)
        sector_info = QLabel("SECTOR_G_ALPHA")
        sector_info.setStyleSheet(f"color: {COLOR_SECONDARY_TEXT}; font-family: '{FONT_MONO}'; font-weight: bold; font-size: 8px;")
        sub_info.addWidget(sector_info)
        sub_info.addStretch()
        title_vbox.addLayout(sub_info)
        title_vbox.addStretch()
        header_layout.addLayout(title_vbox)
        
        header_layout.addStretch()
        
        btn_folder = QPushButton("OPEN LOG FOLDER")
        btn_folder.setFixedSize(130, 32)
        btn_folder.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                font-family: '{FONT_HEADLINE}';
                font-weight: bold;
                font-size: 10px;
            }}
        """)
        header_layout.addWidget(btn_folder)
        
        btn_report = QPushButton("REPORT ISSUE")
        btn_report.setFixedSize(110, 32)
        btn_report.setStyleSheet(f"""
            QPushButton {{
                background-color: white;
                border: 1px solid {COLOR_BORDER};
                font-family: '{FONT_HEADLINE}';
                font-weight: bold;
                font-size: 10px;
            }}
        """)
        header_layout.addWidget(btn_report)
        
        content_layout.addWidget(header)
        
        # Grid Content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background-color: transparent;")
        grid_widget = QWidget()
        grid_layout = QVBoxLayout(grid_widget)
        grid_layout.setContentsMargins(30, 30, 30, 30)
        grid_layout.setSpacing(20)
        
        # Top Row
        top_row = QHBoxLayout()
        conn_card = TacticalCard("Game Connection")
        conn_card.setFixedHeight(180)
        
        def add_info_row(layout, label, value, color=COLOR_TEXT):
            row = QHBoxLayout()
            l = QLabel(label.upper() + ":")
            l.setStyleSheet(f"font-family: '{FONT_MONO}'; font-weight: bold; font-size: 10px; color: {COLOR_SECONDARY_TEXT};")
            v = QLabel(value)
            v.setStyleSheet(f"font-family: '{FONT_MONO}'; font-weight: bold; font-size: 10px; color: {color};")
            row.addWidget(l)
            row.addStretch()
            row.addWidget(v)
            layout.addLayout(row)
            
        add_info_row(conn_card.content_layout, "Status", "Connected", "#2e7d32")
        add_info_row(conn_card.content_layout, "Game", "Combat Protocol X")
        add_info_row(conn_card.content_layout, "Player", "factitiously")
        add_info_row(conn_card.content_layout, "Server", "ASIA_SOUTH")
        top_row.addWidget(conn_card, 7)
        
        rec_card = TacticalCard("Log Recording")
        rec_card.setFixedHeight(180)
        add_info_row(rec_card.content_layout, "Status", "ACTIVE")
        add_info_row(rec_card.content_layout, "Session Time", "01:45:22")
        add_info_row(rec_card.content_layout, "Logs Captured", "5,234 events")
        top_row.addWidget(rec_card, 5)
        grid_layout.addLayout(top_row)
        
        # Bottom Row
        bottom_row = QHBoxLayout()
        perf_card = TacticalCard("Performance Monitor")
        perf_card.setFixedHeight(250)
        
        stats_layout = QHBoxLayout()
        cpu_stat = QLabel("CPU: 12%")
        cpu_stat.setStyleSheet(f"font-family: '{FONT_MONO}'; font-weight: bold; font-size: 18px;")
        ram_stat = QLabel("RAM: 350MB")
        ram_stat.setStyleSheet(f"font-family: '{FONT_MONO}'; font-weight: bold; font-size: 18px;")
        stats_layout.addWidget(cpu_stat)
        stats_layout.addSpacing(40)
        stats_layout.addWidget(ram_stat)
        stats_layout.addStretch()
        perf_card.content_layout.addLayout(stats_layout)
        
        chart = PerformanceChart()
        perf_card.content_layout.addWidget(chart)
        bottom_row.addWidget(perf_card, 8)
        
        alert_card = TacticalCard("Recent Alerts")
        alert_card.setFixedHeight(250)
        
        def add_alert(layout, type_char, text, color=COLOR_TEXT):
            row = QHBoxLayout()
            row.setSpacing(10)
            icon = QLabel(f"[{type_char}]")
            icon.setStyleSheet(f"font-family: '{FONT_MONO}'; font-weight: bold; font-size: 10px; color: {COLOR_PRIMARY if type_char == '!' else COLOR_SECONDARY_TEXT};")
            msg = QLabel(text)
            msg.setWordWrap(True)
            msg.setStyleSheet(f"font-family: '{FONT_MONO}'; font-size: 10px; color: {color};")
            row.addWidget(icon, alignment=Qt.AlignTop)
            row.addWidget(msg)
            layout.addLayout(row)
            
        add_alert(alert_card.content_layout, "!", "High CPU usage detected during battle sequence_03")
        add_alert(alert_card.content_layout, "i", "New update v1.4.3 available for download")
        add_alert(alert_card.content_layout, "i", "Log session 442 closed successfully", COLOR_SECONDARY_TEXT)
        alert_card.content_layout.addStretch()
        
        bottom_row.addWidget(alert_card, 4)
        grid_layout.addLayout(bottom_row)
        
        grid_layout.addStretch()
        scroll.setWidget(grid_widget)
        content_layout.addWidget(scroll)
        
        # Footer
        footer = QFrame()
        footer.setFixedHeight(40)
        footer.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {COLOR_PRIMARY}, stop:0.5 {COLOR_PRIMARY}, stop:0.5 #d4c700, stop:1 #d4c700);
            border-top: 3px solid {COLOR_BORDER};
        """)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(30, 0, 30, 0)
        
        footer_text = QLabel("IN_COMBAT // 战斗中")
        footer_text.setStyleSheet("font-family: 'Space Grotesk'; font-weight: 900; font-size: 12px; color: black; letter-spacing: 2px;")
        footer_layout.addWidget(footer_text)
        footer_layout.addStretch()
        
        version_text = QLabel("v1.0.4_SQUAD_LOG")
        version_text.setStyleSheet("font-family: 'Roboto Mono'; font-weight: bold; font-size: 9px; color: rgba(0,0,0,0.7);")
        footer_layout.addWidget(version_text)
        
        content_layout.addWidget(footer)
        
        main_layout.addWidget(content_area)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Set global font
    font = QFont(FONT_BODY)
    app.setFont(font)
    
    window = ModernWindow()
    window.show()
    sys.exit(app.exec())
