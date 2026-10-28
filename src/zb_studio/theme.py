"""Shared native visual system inspired by the supplied V6 reference."""
STYLE='''
QWidget{font-family:"Microsoft YaHei UI","PingFang SC","Noto Sans CJK SC","Segoe UI";font-size:13px;color:#34435b;}
QMainWindow,QWidget#workspace{background:#f5f7fb;}
QWidget#topbar{background:#ffffff;border-bottom:1px solid #e6ecf4;}
QWidget#sidebar{background:#f9fbfe;border-right:1px solid #e4ebf5;}
QWidget#panel,QFrame#personCard{background:white;border:1px solid #e3eaf4;border-radius:12px;}
QFrame#personCard[selected="true"]{border:2px solid #1684ff;background:#f0f7ff;}
QFrame#personCard:hover{border:1px solid #72b7ff;}
QLabel{background:transparent;border:0;}
QLabel#brand{font-size:27px;font-weight:800;color:#253044;}
QLabel#title{font-size:24px;font-weight:700;color:#202e40;}
QLabel#sectionTitle{font-size:17px;font-weight:700;color:#24344c;}
QLabel#muted{color:#8190a5;font-size:12px;}
QLabel#notice{background:#eef6ff;color:#4276ad;border:1px solid #dfedff;border-radius:8px;padding:12px;}
QLabel#avatar{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #e4efff,stop:1 #e5f7f6);color:#6e95c2;border-radius:8px;font-size:36px;}
QLineEdit,QComboBox{background:white;border:1px solid #dce5f1;border-radius:7px;padding:9px 12px;min-height:18px;selection-background-color:#137bfa;}
QLineEdit:focus,QComboBox:focus{border-color:#348eff;}
QPushButton{background:white;border:1px solid #dfe7f2;border-radius:7px;padding:10px 17px;color:#4c5d76;}
QPushButton:hover{background:#f0f7ff;border-color:#91c3ff;color:#0879ff;}
QPushButton#primary{background:#0879ff;border-color:#0879ff;color:white;font-weight:600;}
QPushButton#primary:hover{background:#0069e6;}
QPushButton#soft{background:#eef5ff;color:#1677ee;border-color:#dceaff;}
QPushButton#nav{border:0;background:transparent;text-align:left;padding:15px 18px;font-size:14px;}
QPushButton#nav:checked{background:#0879ff;color:white;font-weight:600;}
QPushButton:disabled{background:#f4f6fa;color:#a5afbd;border-color:#e9edf4;}
QTableWidget{background:white;alternate-background-color:#fbfcff;border:1px solid #e5ecf5;border-radius:9px;gridline-color:#edf1f7;selection-background-color:#eaf3ff;selection-color:#23436b;outline:0;}
QTableWidget::item{padding:9px;border-bottom:1px solid #eef2f7;}
QTableWidget::item:selected{background:#eaf3ff;color:#24558b;}
QHeaderView::section{background:#f1f5fb;color:#65758e;font-size:12px;font-weight:600;padding:12px;border:0;border-bottom:1px solid #e5ecf4;}
QTableWidget#compactStats::item{padding:3px;}
QTableWidget#compactStats QHeaderView::section{padding:7px 3px;}
QWidget#topbar QPushButton{padding:8px 12px;}
QTableWidget::indicator{width:17px;height:17px;}
QWidget#settingsContent{background:#f5f7fb;}
QScrollArea{background:transparent;border:0;}
QScrollBar:vertical{background:transparent;width:9px;margin:3px;}
QScrollBar::handle:vertical{background:#c6d1e0;border-radius:3px;min-height:24px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}
QTabWidget::pane{border:0;background:transparent;}
QTabBar::tab{background:transparent;color:#75849a;padding:13px 22px;border-bottom:2px solid transparent;}
QTabBar::tab:selected{color:#0879ff;border-bottom:2px solid #0879ff;font-weight:600;}
QStatusBar{background:#fff;color:#8190a5;border-top:1px solid #e9eef5;font-size:12px;}
'''
