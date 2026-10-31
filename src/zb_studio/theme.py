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
QLabel#thumbnail{background:#edf4fc;color:#8a9cb4;border-radius:6px;font-size:11px;}
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
QComboBox{padding:6px 28px 6px 10px;min-height:24px;}
QComboBox::drop-down{width:22px;subcontrol-origin:padding;subcontrol-position:top right;border:0;}
QWidget#cardShelf,QWidget#uploadContent{background:#f5f7fb;}
QChartView{background:#f5f7fb;border:0;}
'''

DARK_STYLE=STYLE+'''
QWidget{color:#e4eaf4;}
QMainWindow,QWidget#workspace,QWidget#settingsContent{background:#151c29;}
QWidget#topbar,QWidget#sidebar{background:#1c2636;border-color:#344258;}
QWidget#panel,QFrame#personCard{background:#222e40;border:1px solid #3a4a61;}
QFrame#personCard[selected="true"]{background:#253e5d;border:2px solid #4d9dff;}
QLabel#brand,QLabel#title,QLabel#sectionTitle{color:#edf3ff;}
QLabel#muted{color:#a8b7cb;}
QLabel#notice{background:#253c59;color:#bbd8ff;border-color:#405c7b;}
QLabel#thumbnail{background:#304158;color:#c0cede;border-radius:6px;font-size:11px;}
QLineEdit,QComboBox,QDateEdit,QPlainTextEdit,QTextEdit{background:#263448;color:#eef4ff;border:1px solid #455871;border-radius:6px;}
QComboBox QAbstractItemView,QCalendarWidget QAbstractItemView{background:#263448;color:#eef4ff;selection-background-color:#176cd4;}
QCalendarWidget QWidget{background:#263448;color:#eef4ff;}
QPushButton{background:#2b3a4e;color:#e1e9f5;border:1px solid #455871;}
QPushButton:hover{background:#344c69;color:#fff;border-color:#68aaff;}
QPushButton#soft{background:#2a4160;color:#add4ff;border-color:#405d7d;}
QPushButton#nav{background:transparent;color:#c4d1e2;}
QPushButton#nav:checked{background:#0879ff;color:white;}
QPushButton:disabled{background:#263141;color:#7e8ba0;border-color:#354257;}
QTableWidget{background:#202c3d;alternate-background-color:#253346;color:#e4eaf4;border-color:#40506a;selection-background-color:#365475;selection-color:#fff;}
QTableWidget::item{border-bottom:1px solid #354358;}
QTableWidget::item:selected{background:#365475;color:#fff;}
QHeaderView::section{background:#29384c;color:#cfdaea;border-bottom:1px solid #40506a;}
QTabWidget::pane,QScrollArea{background:transparent;}
QStatusBar{background:#1c2636;color:#b5c6da;border-color:#344258;}
QScrollBar::handle:vertical{background:#60738b;}
QScrollBar:horizontal{background:#1c2636;height:10px;margin:0;}
QScrollBar::handle:horizontal{background:#60738b;border-radius:4px;min-width:24px;}
QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{width:0;}
QScrollBar::add-page:horizontal,QScrollBar::sub-page:horizontal{background:#1c2636;}
QWidget#cardShelf,QWidget#uploadContent,QScrollArea#cardArea,QScrollArea#cardArea > QWidget > QWidget{background:#151c29;}
QHeaderView,QTableCornerButton::section{background:#29384c;border:0;}
QChartView{background:#151c29;border:0;}
QComboBox{padding:6px 28px 6px 10px;min-height:24px;}
QComboBox::drop-down{width:22px;subcontrol-origin:padding;subcontrol-position:top right;border:0;}
QProgressBar{background:#263448;color:#eef4ff;border:1px solid #455871;border-radius:5px;text-align:center;}
QProgressBar::chunk{background:#1684ff;border-radius:4px;}
QToolTip{background:#253449;color:#f0f5ff;border:1px solid #637a96;}
'''
