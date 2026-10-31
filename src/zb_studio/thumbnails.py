"""Deduplicated background thumbnails and hover previews; no UI-thread I/O."""
from collections import OrderedDict
import weakref
from PySide6.QtCore import QObject,Signal,QRunnable,QThreadPool,Qt,QPoint,QBuffer,QByteArray,QIODevice
from PySide6.QtGui import QPixmap,QImage,QImageReader
from PySide6.QtWidgets import QLabel
from shiboken6 import isValid
from .image_fetch import fetch_image

class Signals(QObject):
    done=Signal(str,object,str)
class Request(QRunnable):
    def __init__(self,url,signals):super().__init__();self.url=url;self.signals=signals
    def run(self):
        try:
            data=fetch_image(self.url);buf=QBuffer();buf.setData(QByteArray(data));buf.open(QIODevice.OpenModeFlag.ReadOnly)
            reader=QImageReader(buf);size=reader.size()
            if size.width()*size.height()>40_000_000:raise ValueError('图片尺寸过大')
            img=reader.read()
            if img.isNull():raise ValueError('无法解码图片')
            if img.width()*img.height()>40_000_000:raise ValueError('图片尺寸过大')
            self.signals.done.emit(self.url,img.scaled(640,640,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation),'')
        except Exception as e:self.signals.done.emit(self.url,None,str(e))

class Thumbnails(QObject):
    def __init__(self,parent):
        super().__init__(parent);self.pool=QThreadPool(self);self.pool.setMaxThreadCount(4);self.cache=OrderedDict();self.waiters={};self.signals=Signals(self);self.signals.done.connect(self.complete)
    def request(self,url,label):
        if not url:label.failed('图片链接为空');return
        if url in self.cache:label.ready(self.cache[url]);return
        if url in self.waiters:self.waiters[url].append(weakref.ref(label));return
        self.waiters[url]=[weakref.ref(label)];self.pool.start(Request(url,self.signals))
    def complete(self,url,img,error):
        if img is not None:
            self.cache[url]=QPixmap.fromImage(img)
            while len(self.cache)>128:self.cache.popitem(last=False)
        pix=self.cache.get(url)
        for ref in self.waiters.pop(url,[]):
            label=ref()
            if label is not None and isValid(label):
                if pix is not None:label.ready(pix)
                else:label.failed(error)

class Thumbnail(QLabel):
    def __init__(self,loader,url,width=42,height=46,zoom=True,on_click=None):
        super().__init__('加载中' if width>80 else '…');self.loader=loader;self.url=url;self.original=None;self.error='';self.preview=None;self.zoom=zoom;self.on_click=on_click
        self.setFixedSize(width,height);self.setAlignment(Qt.AlignmentFlag.AlignCenter);self.setObjectName('thumbnail');self.loader.request(url,self)
    def ready(self,pix):
        self.original=pix;self.error='';self.setPixmap(pix.scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));self.setToolTip('悬停放大' if self.zoom else '点击查看该组任务')
    def failed(self,error):self.error=error;self.setText('加载失败' if self.width()>80 else '重试');self.setToolTip(error+'；点击重试')
    def mousePressEvent(self,event):
        if self.on_click and event.button()==Qt.MouseButton.LeftButton:self.on_click()
        if self.error:self.setText('…');self.loader.request(self.url,self)
        super().mousePressEvent(event)
    def enterEvent(self,event):
        if self.zoom and self.original:
            self.preview=QLabel(self,Qt.WindowType.ToolTip);self.preview.setPixmap(self.original.scaled(300,340,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));self.preview.adjustSize()
            pos=self.mapToGlobal(QPoint(self.width()+8,0));screen=self.screen().availableGeometry();pos.setX(min(pos.x(),screen.right()-self.preview.width()));pos.setY(min(pos.y(),screen.bottom()-self.preview.height()));self.preview.move(pos);self.preview.show()
        super().enterEvent(event)
    def leaveEvent(self,event):
        if self.preview:self.preview.close();self.preview.deleteLater();self.preview=None
        super().leaveEvent(event)
