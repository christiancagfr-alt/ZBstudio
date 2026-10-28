"""Native Qt desktop. Business work runs off the GUI thread."""
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer, QDate, QLocale
from PySide6.QtGui import QDesktopServices,QPixmap,QColor,QIcon
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QLineEdit,QComboBox,QTableWidget,QTableWidgetItem,QHeaderView,QStackedWidget,QFormLayout,QFileDialog,QMessageBox,QScrollArea,QAbstractItemView,QInputDialog,QTabWidget,QFrame,QCheckBox,QProgressBar,QPlainTextEdit,QDateEdit)
from PySide6.QtNetwork import QNetworkAccessManager,QNetworkRequest
from .config import load_settings,save_settings
from . import google_client,desktop_service
from .components import inspect_components
from .domain import allocate_numbers
from .journal import list_operations
from .reporting import report
from PySide6.QtCharts import QChart,QChartView,QLineSeries,QValueAxis
from .assets import save_image
from .thumbnails import Thumbnails,Thumbnail

from .theme import STYLE
from .native_icons import icon
from .source_settings import suggest_alias,merge_sources
from .version import APP_VERSION
from . import updater


class Worker(QThread):
    result=Signal(object)
    failed=Signal(str)
    progress=Signal(str)
    def __init__(self,fn):super().__init__();self.fn=fn
    def run(self):
        try:self.result.emit(self.fn(self.progress.emit))
        except Exception as e:self.failed.emit(str(e))

def button(text,callback,primary=False):
    b=QPushButton(text);b.clicked.connect(lambda:callback())
    if primary:b.setObjectName('primary')
    return b

def table(headers):
    t=QTableWidget(0,len(headers));t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    t.horizontalHeader().setStretchLastSection(True);t.verticalHeader().hide()
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);t.setShowGrid(False);t.setAlternatingRowColors(True);t.verticalHeader().setDefaultSectionSize(52)
    return t

def fill(t,rows):
    t.clearContents()
    t.setRowCount(len(rows))
    for r,row in enumerate(rows):
        for c,value in enumerate(row):
            item=QTableWidgetItem(str(value));item.setToolTip(str(value));t.setItem(r,c,item)

class Window(QMainWindow):
    def __init__(self,cfg=None):
        super().__init__();self.cfg=cfg or load_settings();self.tasks=[];self.jobs=[];self.paths=[];self.mine=False;self.group_filter=None;self.group_cards={}
        self.network=QNetworkAccessManager(self);self.thumbnails=Thumbnails(self)
        self.setWindowTitle(f'ZB Studio · V{APP_VERSION}');self.resize(1280,800);self.setMinimumSize(920,600);self.setAcceptDrops(True)
        root=QWidget();root.setObjectName('workspace');self.setCentralWidget(root);layout=QVBoxLayout(root);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        logo_path=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))/'zb_workflow_logo.svg'
        self.setWindowIcon(QIcon(str(logo_path)))
        header=QWidget();header.setObjectName('topbar');top=QHBoxLayout(header);top.setContentsMargins(14,10,14,10);top.setSpacing(8);self.top_controls=top
        logo=QLabel();logo.setFixedSize(32,32);logo.setPixmap(QIcon(str(logo_path)).pixmap(32,32));top.addWidget(logo)
        title=QLabel('ZB Studio');title.setFixedWidth(144);title.setToolTip('视频制作工作台');title.setObjectName('brand');top.addWidget(title)
        top.addSpacing(10);self.sheet_links=[]
        for text,fn in [('打开需求表 ↗',lambda:self.open_sheet(self.cfg.source_spreadsheet_id)),('打开制作表 ↗',lambda:self.open_sheet(self.cfg.production_spreadsheet_id))]:
            b=button(text,fn);b.setObjectName('soft');self.sheet_links.append(b)
        layout.addWidget(header)
        body=QHBoxLayout();body.setSpacing(0);sidebar=QWidget();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(156);nav=QVBoxLayout(sidebar);nav.setContentsMargins(12,18,12,20);nav.setSpacing(9);body.addWidget(sidebar)
        self.pages=QStackedWidget();body.addWidget(self.pages,1);layout.addLayout(body,1)
        self.build_hall();self.build_upload();self.build_stats();self.build_settings();self.build_activity();self.nav_buttons=[]
        for name,idx,mine,art in [('任务大厅',0,False,'home'),('我的制作',0,True,'work'),('成品上传',1,False,'upload'),('任务统计',2,False,'stats'),('系统设置',3,False,'settings'),('操作记录',4,False,'work')]:
            b=button(name,lambda i=idx,m=mine:self.navigate(i,m));b.setObjectName('nav');b.setIcon(icon(art));b.setProperty('art',art);b.setCheckable(True);nav.addWidget(b);self.nav_buttons.append((b,idx,mine))
        self.nav_buttons[0][0].setChecked(True);self.nav_buttons[0][0].setIcon(icon('home','#ffffff'))
        nav.addStretch()
        for link in self.sheet_links:nav.addWidget(link)
        foot=QLabel(f'ZB STUDIO\n桌面工作台 · V{APP_VERSION}');foot.setObjectName('muted');nav.addWidget(foot)
        self.statusBar().showMessage('先在系统设置导入 Google 桌面授权文件并配置工作表。')
    def build_activity(self):
        page=QWidget();v=QVBoxLayout(page);v.setContentsMargins(20,18,20,18)
        title=QLabel('操作记录');title.setObjectName('title');v.addWidget(title)
        bar=QHBoxLayout();bar.addWidget(button('读取历史记录',self.show_history));bar.addStretch();v.addLayout(bar)
        self.progress_label=QLabel('就绪');self.progress_label.setWordWrap(True)
        self.progress_bar=QProgressBar();self.progress_bar.setRange(0,1);self.progress_bar.setValue(0)
        self.activity=QPlainTextEdit();self.activity.setReadOnly(True);self.activity.document().setMaximumBlockCount(3000)
        self.activity.setPlaceholderText('领取、下载、回填进度与错误记录')
        v.addWidget(self.progress_label);v.addWidget(self.progress_bar);v.addWidget(self.activity,1);self.pages.addWidget(page)
    def announce(self,message):
        if not self.cfg.voice_enabled:return
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech
            if not hasattr(self,'speech'):
                self.speech=QTextToSpeech(self);self.speech.setLocale(QLocale('zh_CN'))
            if self.speech.state()==QTextToSpeech.State.Error:
                self.log('语音不可用：请检查系统是否已安装语音引擎');return
            self.speech.say(message)
        except Exception as e:self.log('语音提醒不可用：'+str(e))
    def navigate(self,index,mine=False):
        self.mine=mine;self.pages.setCurrentIndex(index)
        self.hall_controls.setVisible(index==0)
        for b,i,m in self.nav_buttons:
            selected=i==index and m==mine;b.setChecked(selected);b.setIcon(icon(b.property('art'),'#ffffff' if selected else '#6b7e98'))
        if index==0:self.refresh_table()
        if index==2:self.refresh_stats()
    def open_sheet(self,sid):
        if sid:QDesktopServices.openUrl(QUrl('https://docs.google.com/spreadsheets/d/'+sid+'/edit'))
        else:self.error('请先配置工作表 ID')
    def error(self,message):
        self.log('失败：'+message);QMessageBox.warning(self,'ZB Studio',message)
    def log(self,message):
        from datetime import datetime
        from .journal import append_activity
        try:append_activity(message)
        except OSError:pass
        if hasattr(self,'activity'):self.activity.appendPlainText(datetime.now().strftime('%H:%M:%S')+'  '+message);self.progress_label.setText(message)
        self.statusBar().showMessage(message[:100],8000)
    def run_job(self,fn,done):
        if self.jobs:self.error('正在执行任务，请等待完成');return
        worker=Worker(fn);worker.had_error=False;self.jobs.append(worker)
        self.progress_bar.setRange(0,0);self.log('正在执行，请稍候…')
        worker.progress.connect(self.log)
        def failed(message):
            worker.had_error=True;self.error(message+'\n可点击刷新任务重新读取最新状态。')
        worker.failed.connect(failed);worker.result.connect(done)
        worker.finished.connect(lambda:self.finish_job(worker));self.refresh_table();worker.start()
    def finish_job(self,worker):
        self.jobs.remove(worker);self.progress_bar.setRange(0,1);self.progress_bar.setValue(0 if worker.had_error else 1)
        self.log('操作失败，请查看上方错误日志' if worker.had_error else '本次操作已结束');worker.deleteLater()
        self.refresh_table()
    def closeEvent(self,event):
        if self.jobs:self.error('后台任务正在进行，请完成后退出');event.ignore()
        else:event.accept()
    def build_hall(self):
        page=QWidget();v=QVBoxLayout(page);v.setContentsMargins(16,10,16,10);v.setSpacing(8)
        self.hall_controls=QWidget();bar=QHBoxLayout(self.hall_controls);bar.setContentsMargins(0,0,0,0);bar.setSpacing(8);self.top_controls.addWidget(self.hall_controls,1);self.top_controls.addStretch(0)
        self.search=QLineEdit();self.search.setPlaceholderText('搜索文案、人物…');self.search.setMinimumWidth(120);self.search.setMaximumWidth(240);self.search.textChanged.connect(self.refresh_table)
        self.requester=QComboBox();self.requester.addItem('全部需求者','');self.requester.currentIndexChanged.connect(self.refresh_table)
        self.state=QComboBox();self.state.addItems(['全部状态','可领取','已分配','已完成']);self.state.currentIndexChanged.connect(self.refresh_table)
        self.requester.setFixedWidth(120);self.state.setFixedWidth(105)
        for w in [self.search,self.requester,self.state]:bar.addWidget(w)
        bar.addWidget(button('全部人物',self.clear_group));bar.addStretch();bar.addWidget(button('刷新任务',self.reload,True))
        self.cards=QHBoxLayout();self.cards.setContentsMargins(0,0,0,4);self.cards.setSpacing(12);card_widget=QWidget();card_widget.setLayout(self.cards);area=QScrollArea();area.setWidgetResizable(True);area.setWidget(card_widget);area.setFixedHeight(190);self.card_area=area;v.addWidget(area)
        modes=QHBoxLayout();modes.addWidget(button('人物卡片',lambda:area.setVisible(True),True));modes.addWidget(button('完整列表',lambda:area.setVisible(False)));self.count=QLabel('尚未加载任务');modes.addWidget(self.count,1);v.addLayout(modes)
        self.task_table=table(['选择','序号','需求者 / 人物','需求日期','中文文案','葡语文案','图片','制作人','进度','自动命名','成品链接']);self.task_table.setColumnWidth(4,250);self.task_table.setColumnWidth(9,250);self.task_table.setColumnWidth(6,72);v.addWidget(self.task_table,1)
        actions=QHBoxLayout();self.select_all=QCheckBox('全选当前可领取');self.select_all.clicked.connect(self.toggle_all);actions.addWidget(self.select_all);actions.addWidget(button('领取勾选任务',self.claim,True));actions.addWidget(button('下载 / 重试选中行素材',self.download));actions.addStretch();v.addLayout(actions);self.pages.addWidget(page)
    def clear_group(self):self.group_filter=None;self.refresh_table()
    def reload(self):
        cfg=self.cfg.model_copy(deep=True)
        self.run_job(lambda p:desktop_service.query(cfg,p),self.loaded)
    def loaded(self,items):
        self.tasks=items;self.group_filter=None;self.group_cards={};self.requester.blockSignals(True);self.requester.clear();self.requester.addItem('全部需求者','')
        for name in sorted({t.requester for t in items}):self.requester.addItem(name,name)
        self.requester.blockSignals(False)
        while self.cards.count():
            item=self.cards.takeAt(0)
            if item.widget():item.widget().deleteLater()
        groups={}
        for t in items:groups.setdefault((t.source_id,t.sheet,t.start_col),[]).append(t)
        for key,ts in groups.items():
            self.cards.addWidget(self.person_card(key,ts))
        self.cards.addStretch();self.refresh_table();self.statusBar().showMessage(f'已读取 {len(items)} 个任务')
    def person_card(self,key,tasks):
        t=tasks[0];card=QFrame();card.setObjectName('personCard');card.setFixedWidth(156);v=QVBoxLayout(card);v.setContentsMargins(7,7,7,9);v.setSpacing(5)
        url=next((task.image for task in tasks if task.image),'') or t.avatar
        avatar=Thumbnail(self.thumbnails,url,140,86,zoom=False,on_click=lambda:self.select_group(key));v.addWidget(avatar)
        b=button(t.person,lambda:self.select_group(key));b.setStyleSheet('border:0;text-align:left;padding:2px;font-weight:700;font-size:14px');v.addWidget(b)
        who=QLabel(t.requester);who.setObjectName('muted');v.addWidget(who)
        metrics=QLabel(f'总数 {len(tasks)}   可领取 {sum(t.available for t in tasks)}   完成 {sum(bool(t.output) for t in tasks)}');metrics.setStyleSheet('font-size:11px;color:#6b87a9');v.addWidget(metrics)
        self.group_cards[key]=card
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.mousePressEvent=lambda event:self.select_group(key)
        return card
    def select_group(self,key):self.group_filter=key;self.refresh_table()
    def refresh_table(self):
        if not hasattr(self,'task_table'):return
        q=self.search.text().lower();s=self.state.currentIndex();who=self.requester.currentData()
        self.visible=[t for t in self.tasks if (not self.mine or t.owner==self.cfg.producer) and (not who or t.requester==who) and (not self.group_filter or (t.source_id,t.sheet,t.start_col)==self.group_filter) and (not q or q in ' '.join([t.chinese,t.portuguese,t.filename,t.label]).lower()) and (s==0 or s==1 and t.available or s==2 and t.owner and not t.output or s==3 and t.output)]
        nums={t.identity:n for t,n in allocate_numbers(self.tasks,[t.identity for t in self.tasks])}
        fill(self.task_table,[['',t.number or nums[t.identity],t.label,t.deadline,t.chinese,t.portuguese,'',t.owner,'已完成' if t.output else '已分配' if t.owner else '可领取',t.filename,t.output] for t in self.visible])
        for r,t in enumerate(self.visible):
            item=self.task_table.item(r,0)
            self.task_table.setCellWidget(r,6,Thumbnail(self.thumbnails,t.image));status=self.task_table.item(r,8);status.setForeground(QColor('#0fa66d' if t.output else '#e68b22' if t.owner else '#1677ed'))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            if t.available and not t.output:item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Unchecked)
            if not t.output and (t.available or t.owner==self.cfg.producer):
                action=button('可领取' if t.available else '已分配 · 放弃',lambda task=t:self.task_action(task));action.setEnabled(not self.jobs);action.setObjectName('soft');self.task_table.setCellWidget(r,8,action)
        self.select_all.blockSignals(True);self.select_all.setChecked(False);self.select_all.blockSignals(False)
        self.count.setObjectName('muted')
        group_task=next((t for t in self.tasks if (t.source_id,t.sheet,t.start_col)==self.group_filter),None)
        scope=group_task.label if group_task else ('我的制作 · 全部人物' if self.mine else '全部人物')
        self.count.setText(f'{scope}  ·  共 {len(self.visible)} 个任务  ·  可领取 {sum(t.available and not t.output for t in self.visible)}  ·  已领取 {sum(bool(t.owner) for t in self.visible)}  ·  已完成 {sum(bool(t.output) for t in self.visible)}')
        for key,card in self.group_cards.items():
            card.setProperty('selected',key==self.group_filter);card.style().unpolish(card);card.style().polish(card)
    def toggle_all(self,checked):
        for r,t in enumerate(self.visible):
            if t.available and not t.output:self.task_table.item(r,0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
    def task_action(self,t):
        if self.jobs:return
        if t.available and not t.output:self.start_claim([t.identity]);return
        if t.owner!=self.cfg.producer or t.output:return
        answer=QMessageBox.question(self,'放弃任务',f'确定放弃「{t.label}」的任务 {t.number}？\n来源任务将恢复可领取，制作记录保留并标记已放弃。')
        if answer==QMessageBox.StandardButton.Yes:
            self.run_job(lambda p:desktop_service.abandon(self.cfg,t.identity,t.filename,p),self.released)
    def released(self,identity):
        for t in self.tasks:
            if t.identity==identity:t.owner='';t.filename='';t.number='';t.progress='可领取'
        self.sync_views();self.log('任务已放弃，来源任务已恢复可领取')
    def sync_views(self):
        key=self.group_filter;self.loaded(self.tasks);self.group_filter=key;self.refresh_table();self.refresh_stats()
    def start_claim(self,ids):
        self.run_job(lambda p:desktop_service.claim_tasks(self.cfg,ids,p),self.claimed)
    def claim(self):
        ids=[t.identity for r,t in enumerate(self.visible) if self.task_table.item(r,0).checkState()==Qt.CheckState.Checked]
        if not ids:self.error('请勾选可领取任务');return
        self.start_claim(ids)
    def claimed(self,result):
        items=result['claimed'];ids={x['id']:x for x in items}
        for t in self.tasks:
            if t.identity in ids:t.owner=self.cfg.producer;t.filename=ids[t.identity]['filename'];t.number=ids[t.identity]['number']
        self.sync_views();self.announce('下载完成' if not result['failed_downloads'] else '领取完成，部分图片下载失败');self.log(f'已领取 {len(items)} 条；图片成功 {len(items)-len(result["failed_downloads"])}，失败 {len(result["failed_downloads"])}。失败图片可选中行后重试。')
    def download(self):
        row=self.task_table.currentRow()
        if row<0:return
        t=self.visible[row]
        if t.owner!=self.cfg.producer or not t.filename:self.error('请选择自己已领取的任务');return
        self.run_job(lambda p:desktop_service.download_claim_image(self.cfg,{'id':t.identity,'filename':t.filename,'deadline':t.deadline,'image':t.image,'date':t.filename.rsplit('-',1)[-1],'folder':t.label,'number':t.number},p),lambda path:(self.log('已保存：'+path),self.announce('下载完成')))
    def build_upload(self):
        page=QWidget();v=QVBoxLayout(page);v.addWidget(QLabel('拖入视频文件，或选择文件 / 文件夹。上传前检查整个队列，失败即停止。'))
        bar=QHBoxLayout();bar.addWidget(button('选择视频',self.pick_videos));bar.addWidget(button('选择文件夹',self.pick_folder));bar.addWidget(button('清空队列',self.clear_upload));bar.addWidget(button('开始上传',self.upload,True));v.addLayout(bar)
        self.upload_table=table(['视频路径']);v.addWidget(self.upload_table);v.addWidget(QLabel('当前支持逐文件进度；跨进程断点续传待实现。'));self.pages.addWidget(page)
    def add_paths(self,paths):
        if self.jobs:return
        self.paths.extend(str(p) for p in paths);fill(self.upload_table,[[p] for p in self.paths]);self.pages.setCurrentIndex(1)
    def pick_videos(self):self.add_paths(QFileDialog.getOpenFileNames(self,'选择视频','','视频 (*.mp4 *.mov *.mkv *.webm)')[0])
    def pick_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'选择视频文件夹')
        if folder:self.add_paths(p for p in Path(folder).rglob('*') if p.is_file() and p.suffix.lower() in ('.mp4','.mov','.mkv','.webm'))
    def clear_upload(self):
        if not self.jobs:self.paths=[];fill(self.upload_table,[])
    def upload(self):
        if self.paths:
            def work(progress):
                n=desktop_service.upload_files(self.cfg,list(self.paths),progress)
                progress(f'{n} 个视频上传回填完成；正在刷新任务…')
                return desktop_service.query(self.cfg)
            self.run_job(work,lambda tasks:(self.loaded(tasks),self.refresh_stats(),self.log('上传回填完成，任务状态已刷新')))
    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls():event.acceptProposedAction()
    def dropEvent(self,event):self.add_paths(u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile())
    def build_stats(self):
        page=QWidget();v=QVBoxLayout(page);v.setContentsMargins(24,20,24,20)
        bar=QHBoxLayout();today=QDate.currentDate();self.stats_from=QDateEdit(QDate(today.year(),today.month(),1));self.stats_to=QDateEdit(today)
        for widget in (self.stats_from,self.stats_to):widget.setCalendarPopup(True);widget.setDisplayFormat('yyyy-MM-dd')
        bar.addWidget(QLabel('日期范围'));bar.addWidget(self.stats_from);bar.addWidget(self.stats_to);bar.addWidget(button('统计',self.refresh_stats));bar.addWidget(button('本月',self.stats_month));bar.addWidget(button('查看操作日志',self.show_history));bar.addStretch();v.addLayout(bar)
        note=QLabel('表格：按需求日期筛选当前状态。曲线：按本机操作日志的发生日期统计领取、放弃、完成事件；不推算历史未领取数量。无年份日期按所选开始年份计算。');note.setWordWrap(True);note.setObjectName('muted');v.addWidget(note)
        self.chart=QChart();self.chart_view=QChartView(self.chart);self.chart_view.setMinimumHeight(220);v.addWidget(self.chart_view)
        self.stats=table(['需求者 / 人物','总任务','未领取','已领取¹','已完成','放弃次数']);self.stats.setObjectName('compactStats');self.stats.horizontalHeader().setStretchLastSection(False);self.stats.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter);self.stats.setColumnWidth(0,240)
        self.stats.horizontalHeaderItem(3).setToolTip('已领取包含已完成任务');self.stats.verticalHeader().setDefaultSectionSize(36)
        for c in range(1,6):self.stats.setColumnWidth(c,76)
        v.addWidget(self.stats);self.pages.addWidget(page)
    def stats_month(self):
        now=QDate.currentDate();self.stats_from.setDate(QDate(now.year(),now.month(),1));self.stats_to.setDate(now);self.refresh_stats()
    def show_history(self):
        self.navigate(4)
        try:
            from .journal import read_activity
            self.activity.setPlainText(read_activity())
            for op in reversed(list_operations(100)):
                self.log(f'{op["updated"]}  {op["kind"]} / {op["state"]}  日志 {op["id"]}')
                payload=op['payload']
                if payload.get('error'):self.log('错误：'+payload['error'])
                if payload.get('path'):self.log('文件：'+payload['path'])
                if payload.get('source_updates'):self.log('需求表单元格：'+', '.join(u['range'] for u in payload['source_updates']))
        except Exception as e:self.error(str(e))
    def refresh_stats(self):
        if not hasattr(self,'stats'):return
        start=self.stats_from.date().toPython();end=self.stats_to.date().toPython()
        if end<start or (end-start).days>366:self.error('请选择不超过367天的有效日期范围');return
        data=report(self.tasks,list_operations(None),start,end);fill(self.stats,data['rows'])
        for r in range(self.stats.rowCount()):
            for c in range(self.stats.columnCount()):self.stats.item(r,c).setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chart.removeAllSeries()
        for axis in self.chart.axes():self.chart.removeAxis(axis);axis.deleteLater()
        for kind,label,color in [('claim','领取','#0879ff'),('release','放弃','#f29b38'),('upload','完成','#21b57b')]:
            series=QLineSeries();series.setName(label);series.setColor(QColor(color))
            for i,day in enumerate(data['days'].values()):series.append(i,day[kind])
            self.chart.addSeries(series)
        self.chart.createDefaultAxes();self.chart.setTitle(f'{start.isoformat()} — {end.isoformat()} · 每日操作次数（本机日志）')
        for axis in self.chart.axes(Qt.Orientation.Horizontal):axis.setTitleText('距开始日期天数');axis.setLabelFormat('%d')
        maximum=max((max(day.values()) for day in data['days'].values()),default=0)
        for axis in self.chart.axes(Qt.Orientation.Vertical):axis.setLabelFormat('%d');axis.setRange(0,max(1,maximum));axis.setTickCount(min(6,max(1,maximum)+1))
    def build_settings(self):
        page=QWidget();outer=QVBoxLayout(page);outer.setContentsMargins(26,24,26,24);outer.setSpacing(12)
        title=QLabel('系统设置');title.setObjectName('title');outer.addWidget(title)
        description=QLabel('连接任务来源，定义你的制作流程。');description.setObjectName('muted');outer.addWidget(description)
        tabs=QTabWidget();outer.addWidget(tabs,1)
        def panel(tabname,title,description):
            area=QScrollArea();area.setWidgetResizable(True);content=QWidget();content.setObjectName('settingsContent');body=QVBoxLayout(content);body.setContentsMargins(0,18,0,0)
            card=QWidget();card.setObjectName('panel');v=QVBoxLayout(card);v.setContentsMargins(24,22,24,22);v.setSpacing(16)
            label=QLabel(title);label.setObjectName('sectionTitle');v.addWidget(label)
            desc=QLabel(description);desc.setWordWrap(True);desc.setObjectName('muted');v.addWidget(desc)
            body.addWidget(card);body.addStretch();area.setWidget(content);tabs.addTab(area,tabname);return v
        self.fields={}
        def field(v,key,label):
            form=QFormLayout();form.setSpacing(14);edit=QLineEdit(getattr(self.cfg,key));self.fields[key]=edit;form.addRow(label,edit);v.addLayout(form);return edit
        v=panel('任务来源','需求工作表','填写 Spreadsheet ID 后自动读取全部 Sheet。勾选需要的工作表，别名会根据名称开头自动填写，也可以直接修改。')
        doc=field(v,'source_spreadsheet_id','Spreadsheet ID');doc.setPlaceholderText('Google 表格网址 /d/ 与 /edit 之间的 ID')
        doc.editingFinished.connect(self.auto_discover_sources)
        actions=QHBoxLayout();self.discover_button=button('读取 / 刷新工作表',self.pick_source_sheet,True);actions.addWidget(self.discover_button)
        actions.addWidget(button('全选',lambda:self.select_sources(True)));actions.addWidget(button('取消全选',lambda:self.select_sources(False)));actions.addStretch();v.addLayout(actions)
        self.source_summary=QLabel('尚未读取工作表');self.source_summary.setObjectName('muted');v.addWidget(self.source_summary)
        self.sources=table(['实际 Sheet 名称','需求者别名','启用']);self.sources.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked|QAbstractItemView.EditTrigger.EditKeyPressed|QAbstractItemView.EditTrigger.SelectedClicked)
        self.sources.horizontalHeader().setStretchLastSection(False);self.sources.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch);self.sources.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch);self.sources.setColumnWidth(2,80);self.sources.setMinimumHeight(310)
        self.source_doc=self.cfg.source_spreadsheet_id;self.requested_source_doc=None
        if self.cfg.source_catalog:
            for row in self.cfg.source_catalog:self.add_source(row.name,row.alias,row.enabled,row.sheet_id)
        else:
            for name in self.cfg.source_sheets:self.add_source(name,self.cfg.requester_names.get(name) or suggest_alias(name),True)
        self.sources.itemChanged.connect(self.update_source_summary);self.update_source_summary();v.addWidget(self.sources)
        notice=QLabel('例如：需求者-制作人-业务分类 → 需求者。只读取勾选项；再次刷新会保留手动别名。');notice.setObjectName('notice');notice.setWordWrap(True);v.addWidget(notice)
        v=panel('制作与文件','个人制作配置','配置制作人及唯一制作工作表，指定素材和成品的存放位置。')
        for key,label in [('producer','制作人姓名'),('production_sheet','制作 Sheet 名称'),('production_spreadsheet_id','制作表 Spreadsheet ID'),('prefix','命名前缀'),('download_path','素材下载根目录'),('drive_parent_folder_id','Drive 父文件夹 ID')]:field(v,key,label)
        self.production_layout=QComboBox();self.production_layout.addItem('按人物分组追加','grouped');self.production_layout.addItem('左侧第一组（自动识别列宽） 顶部插入（最新领取在上）','left_al');self.production_layout.setCurrentIndex(self.production_layout.findData(self.cfg.production_layout));v.addWidget(QLabel('制作表写入方式'));v.addWidget(self.production_layout)
        v.addWidget(button('选择素材文件夹',self.pick_download))
        self.voice_enabled=QCheckBox('下载完成后语音提醒（关闭后静默）');self.voice_enabled.setChecked(self.cfg.voice_enabled);v.addWidget(self.voice_enabled)
        v=panel('Google 授权','Google 账号连接','导入桌面应用 OAuth JSON，在系统浏览器中完成账号授权。')
        self.auth_label=QLabel('尚未检查授权状态');self.auth_label.setObjectName('notice');v.addWidget(self.auth_label);bar=QHBoxLayout()
        for text,fn in [('导入授权文件',self.import_auth),('Google 授权',self.authorize),('检查授权',self.auth_status),('清除本机登录',self.disconnect)]:bar.addWidget(button(text,fn))
        v.addLayout(bar)
        v=panel('组件与更新','运行环境','检查 GitHub Release。更新包下载后先校验 SHA-256，再启动对应系统的安装流程。')
        self.components=table(['组件','版本','状态']);self.components.setMinimumHeight(350);self.components.setColumnWidth(0,260);self.components.setColumnWidth(1,240);v.addWidget(self.components)
        bar=QHBoxLayout();bar.addWidget(button('检查组件',self.check_components));bar.addWidget(button('安装 / 修复组件',self.repair));bar.addWidget(button('检查更新',self.update_info));v.addLayout(bar)
        footer=QHBoxLayout();hint=QLabel('保存后生效 · 不会修改已领取任务的命名');hint.setObjectName('muted');footer.addWidget(hint);footer.addStretch();footer.addWidget(button('保存设置',self.save,True));outer.addLayout(footer)
        self.pages.addWidget(page);self.check_components()
    def source_rows(self):
        return [{'name':self.sources.item(r,0).text(),'alias':self.sources.item(r,1).text().strip(),
                 'enabled':self.sources.item(r,2).checkState()==Qt.CheckState.Checked,
                 'sheet_id':self.sources.item(r,0).data(Qt.ItemDataRole.UserRole)} for r in range(self.sources.rowCount())]
    def update_source_summary(self,*args):
        rows=self.source_rows();self.source_summary.setText(f'共 {len(rows)} 个工作表  ·  已勾选 {sum(r["enabled"] for r in rows)} 个  ·  双击别名修改')
    def select_sources(self,enabled):
        for r in range(self.sources.rowCount()):self.sources.item(r,2).setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)
    def auto_discover_sources(self):
        doc=self.fields['source_spreadsheet_id'].text().strip()
        if doc and doc!=self.source_doc and not self.jobs:self.pick_source_sheet()
    def pick_source_sheet(self):
        if self.jobs:self.error('请等待当前操作完成');return
        doc=self.fields['source_spreadsheet_id'].text().strip()
        if not doc:self.error('请先填写 Spreadsheet ID');return
        self.requested_source_doc=doc;self.discover_button.setEnabled(False);self.source_summary.setText('正在读取 Google 工作表…')
        def fetch(progress):
            from .workflow import list_sheet_metadata
            sheets,_=google_client.services()
            return list_sheet_metadata(sheets,doc)
        self.run_job(fetch,self.choose_source_sheet)
        if self.jobs:
            self.jobs[-1].finished.connect(lambda:self.discover_button.setEnabled(True))
            self.jobs[-1].failed.connect(lambda message:self.source_summary.setText('读取失败，原配置已保留；请检查账号和表格 ID 后重试'))
    def choose_source_sheet(self,tabs):
        doc=self.requested_source_doc or self.fields['source_spreadsheet_id'].text().strip()
        if doc!=self.fields['source_spreadsheet_id'].text().strip():
            self.source_summary.setText('表格 ID 已改变，请重新读取');return
        previous=self.source_rows() if doc==self.source_doc else []
        rows=merge_sources(tabs,previous)
        missing=[r['name'] for r in previous if r['enabled'] and not any(r['sheet_id']==t['sheetId'] if r['sheet_id'] is not None else r['name']==t['title'] for t in tabs)]
        self.sources.blockSignals(True);self.sources.setRowCount(0)
        for r in rows:self.add_source(r['name'],r['alias'],r['enabled'],r['sheet_id'])
        self.sources.blockSignals(False);self.source_doc=doc;self.update_source_summary()
        if missing:self.source_summary.setText(self.source_summary.text()+'；已移除不存在的工作表：'+'、'.join(missing))
        self.statusBar().showMessage('工作表已读取，请勾选保留项、检查别名并保存')
    def add_source(self,name='',alias='',enabled=True,sheet_id=None):
        blocked=self.sources.blockSignals(True);r=self.sources.rowCount();self.sources.insertRow(r)
        title=QTableWidgetItem(name);title.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);title.setData(Qt.ItemDataRole.UserRole,sheet_id);self.sources.setItem(r,0,title)
        self.sources.setItem(r,1,QTableWidgetItem(alias or suggest_alias(name)))
        check=QTableWidgetItem();check.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable|Qt.ItemFlag.ItemIsSelectable);check.setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked);self.sources.setItem(r,2,check);self.sources.blockSignals(blocked)
    def pick_download(self):
        folder=QFileDialog.getExistingDirectory(self,'素材目录',self.fields['download_path'].text())
        if folder:self.fields['download_path'].setText(folder)
    def save(self):
        if self.jobs:self.error('请等待后台操作结束后保存设置');return
        try:
            values={k:w.text().strip() for k,w in self.fields.items()};values['production_layout']=self.production_layout.currentData();values['voice_enabled']=self.voice_enabled.isChecked()
            if values['source_spreadsheet_id']!=self.source_doc:raise ValueError('表格 ID 已改变，请先读取工作表再保存')
            rows=self.source_rows();mapping={}
            for row in rows:
                if row['enabled']:
                    if not row['alias']:raise ValueError('已勾选的工作表必须填写别名')
                    if row['name'] in mapping:raise ValueError('工作表名称不能重复')
                    mapping[row['name']]=row['alias']
            values.update(source_sheets=list(mapping),requester_names=mapping,source_catalog=rows)
            cfg=type(self.cfg).model_validate(self.cfg.model_dump()|values);save_settings(cfg);self.cfg=cfg;self.loaded([]);self.statusBar().showMessage('设置已保存，请刷新任务')
        except Exception as e:self.error(str(e))
    def import_auth(self):
        path=QFileDialog.getOpenFileName(self,'选择桌面 OAuth JSON','','JSON (*.json)')[0]
        if path:
            def read(p):
                with open(path,'rb') as f:return google_client.import_client(f.read(65537))
            self.run_job(read,self.show_auth)
    def show_auth(self,data):
        detail='需要重新授权文件夹读取权限' if data.get('needs_reauth') else '系统凭据库不可用，请解锁' if data.get('credential_store_unavailable') else '已保存到系统凭据库' if data['connected'] else '未授权'
        self.auth_label.setText(f'客户端：{"已配置" if data["configured"] else "未配置"} · 登录：{detail}')

    def authorize(self):self.run_job(lambda p:google_client.authorize(),self.show_auth)
    def auth_status(self):self.run_job(lambda p:google_client.auth_status(),self.show_auth)
    def disconnect(self):self.run_job(lambda p:google_client.disconnect(),self.show_auth)
    def check_components(self):fill(self.components,inspect_components())
    def repair(self):
        self.check_components();QMessageBox.information(self,'组件修复','当前为开发预览版。发布仓库与签名校验尚未配置，自动安装暂不可用。\n正式版本通过重新安装完整软件包修复内置组件。')
    def update_info(self):
        self.run_job(lambda progress:updater.check_for_update(),self.show_update)
    def show_update(self,info):
        if not info['available']:
            QMessageBox.information(self,'检查更新',f'当前版本：V{info["current"]}\n已是最新版本。')
            return
        if not info['installer'] or not info['checksums']:
            QMessageBox.warning(self,'发现新版本',f'发现 V{info["latest"]}，但该发布缺少当前系统安装包或 SHA-256 校验清单。\n请前往发布页手动下载：\n{info["release_url"]}')
            return
        answer=QMessageBox.question(self,'发现新版本',f'当前版本：V{info["current"]}\n最新版本：V{info["latest"]}\n\n现在下载、校验并安装更新吗？')
        if answer==QMessageBox.StandardButton.Yes:
            self.start_update_download(info)
    def start_update_download(self,info):
        # The release-check worker emits its result just before its finished
        # signal.  Wait for it to leave self.jobs instead of treating the
        # user's affirmative click as a competing operation.
        if self.jobs:
            QTimer.singleShot(50,lambda:self.start_update_download(info));return
        self.run_job(lambda progress:updater.download_update(info,progress),self.start_update_install)
    def start_update_install(self,path):
        if self.jobs:
            QTimer.singleShot(50,lambda:self.start_update_install(path));return
        self.run_job(lambda progress:updater.install_update(Path(path)),self.installed_update)
    def installed_update(self,message):
        try:
            self.log(message)
            QMessageBox.information(self,'开始安装更新',message)
            if sys.platform in ('win32','darwin') or sys.platform.startswith('linux'):
                QApplication.instance().quit()
        except Exception as e:self.error('无法安装更新：'+str(e))

def main():
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE);window=Window();window.show()
    if '--smoke-test' in sys.argv:QTimer.singleShot(500,app.quit)
    return app.exec()

if __name__=='__main__':sys.exit(main())

