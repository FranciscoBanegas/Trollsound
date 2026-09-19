def apply_theme(app):
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QWidget { font-family: 'Segoe UI'; font-size: 13px; }
        QMainWindow, QDialog { background: #f5f7f7; }
        QLabel, QCheckBox { color: #263432; }
        QPushButton { padding: 6px 10px; border: 1px solid #becbc8; border-radius: 4px; background: #ffffff; color: #263432; }
        QPushButton:hover { background: #e0efeb; border-color: #418477; }
        QPushButton:disabled { color: #89938f; background: #eef1f0; }
        QLineEdit, QComboBox { padding: 6px; border: 1px solid #bac8c5; border-radius: 3px; background: white; color: #263432; }
        QTableWidget { background: white; alternate-background-color: #f0f5f4; color: #263432; gridline-color: #e3e9e7; border: 1px solid #cbd5d2; selection-background-color: #d4e9e2; selection-color: #183c32; }
        QHeaderView::section { padding: 9px; background: #e7edeb; border: 0; border-bottom: 1px solid #cbd5d2; color: #334d44; }
        QStatusBar { color: #9b341e; }
    """)
