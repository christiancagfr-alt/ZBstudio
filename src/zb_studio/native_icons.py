"""Small vector icons, independent of platform symbol fonts."""
from PySide6.QtCore import QByteArray,Qt
from PySide6.QtGui import QIcon,QPainter,QPixmap
from PySide6.QtSvg import QSvgRenderer
PATHS={
'home':'M3 10 L12 3 L21 10 M5 9 V21 H19 V9 M9 21 V14 H15 V21',
'work':'M4 4 H20 V20 H4 Z M8 9 H16 M8 13 H16 M8 17 H13',
'upload':'M12 16 V3 M7 8 L12 3 L17 8 M4 14 V21 H20 V14',
'stats':'M5 21 V11 M12 21 V3 M19 21 V7',
'settings':'M5 6 H21 M3 12 H19 M5 18 H21 M8 3 V9 M16 9 V15 M10 15 V21'}
def icon(name,color='#6b7e98'):
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path d="{PATHS[name]}" fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    pix=QPixmap(24,24);pix.fill(Qt.GlobalColor.transparent);p=QPainter(pix);QSvgRenderer(QByteArray(svg.encode())).render(p);p.end();return QIcon(pix)
