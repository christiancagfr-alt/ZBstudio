"""Native Qt desktop. Business work runs off the GUI thread."""
import sys
import csv
import io
from html import escape
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer, QDate, QLocale
from PySide6.QtGui import QDesktopServices,QPixmap,QColor,QIcon
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QPushButton,QLabel,QLineEdit,QComboBox,QTableWidget,QTableWidgetItem,QHeaderView,QStackedWidget,QFormLayout,QFileDialog,QMessageBox,QScrollArea,QAbstractItemView,QInputDialog,QTabWidget,QFrame,QCheckBox,QProgressBar,QPlainTextEdit,QDateEdit,QSpinBox,QDialog,QDialogButtonBox)
from PySide6.QtNetwork import QNetworkAccessManager,QNetworkRequest
from .config import load_settings,save_settings,source_documents
from . import google_client,desktop_service
from .components import inspect_components
from .domain import ALIASES, normalize
from .journal import list_operations
from .reporting import report
from PySide6.QtCharts import QChart,QChartView,QLineSeries,QValueAxis
from .assets import save_image
from .thumbnails import Thumbnails,Thumbnail

from .theme import STYLE,DARK_STYLE
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
    for r in range(t.rowCount()):
        for c in range(t.columnCount()):
            if t.cellWidget(r,c):t.removeCellWidget(r,c)
    t.clearContents()
    t.setRowCount(len(rows))
    for r,row in enumerate(rows):
        for c,value in enumerate(row):
            item=QTableWidgetItem(str(value));item.setToolTip(str(value));t.setItem(r,c,item)

class Window(QMainWindow):
    def __init__(self,cfg=None):
        super().__init__();self.cfg=cfg or load_settings();self.tasks=[];self.jobs=[];self.paths=[];self.stale_claims=set();self.mine=False;self.group_filter=None;self.group_cards={}
        self.network=QNetworkAccessManager(self);self.thumbnails=Thumbnails(self)
        self.setWindowTitle(f'ZB Studio · V{APP_VERSION}');self.resize(1280,800);self.setMinimumSize(920,600);self.setAcceptDrops(True)
        root=QWidget();root.setObjectName('workspace');self.setCentralWidget(root);layout=QVBoxLayout(root);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        logo_path=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))/'zb_workflow_logo.svg'
        self.setWindowIcon(QIcon(str(logo_path)))
        header=QWidget();header.setObjectName('topbar');top=QHBoxLayout(header);top.setContentsMargins(14,10,14,10);top.setSpacing(8);self.top_controls=top
        logo=QLabel();logo.setFixedSize(32,32);logo.setPixmap(QIcon(str(logo_path)).pixmap(32,32));top.addWidget(logo)
        title=QLabel('ZB Studio');title.setMinimumWidth(100);title.setMaximumWidth(130);title.setToolTip('视频制作工作台');title.setObjectName('brand');top.addWidget(title)
        top.addSpacing(10);self.sheet_links=[]
        for text,fn in [('打开需求表 ↗',self.open_source_sheets),('打开制作表 ↗',lambda:self.open_sheet(self.cfg.production_spreadsheet_id))]:
            b=button(text,fn);b.setObjectName('soft');self.sheet_links.append(b)
        layout.addWidget(header)
        body=QHBoxLayout();body.setSpacing(0);sidebar=QWidget();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(156);nav=QVBoxLayout(sidebar);nav.setContentsMargins(12,18,12,20);nav.setSpacing(9);body.addWidget(sidebar)
        self.pages=QStackedWidget();body.addWidget(self.pages,1);layout.addLayout(body,1)
        self.build_hall();self.build_upload();self.build_stats();self.build_settings();self.build_activity();self.nav_buttons=[]
        for name,idx,mine,art in [('任务大厅',0,False,'home'),('我的制作',0,True,'work'),('成品上传',1,False,'upload'),('任务统计',2,False,'stats'),('系统设置',3,False,'settings'),('操作记录',4,False,'work')]:
            b=button(name,lambda i=idx,m=mine:self.navigate(i,m));b.setObjectName('nav');b.setIcon(icon(art));b.setProperty('art',art);b.setCheckable(True);nav.addWidget(b);self.nav_buttons.append((b,idx,mine))
        self.nav_buttons[0][0].setChecked(True);self.nav_buttons[0][0].setIcon(icon('home','#ffffff'))
        update_button=button('检查更新',self.update_info);update_button.setObjectName('nav');nav.addWidget(update_button)
        nav.addStretch()
        for link in self.sheet_links:nav.addWidget(link)
        foot=QLabel(f'ZB STUDIO\n桌面工作台 · V{APP_VERSION}');foot.setObjectName('muted');nav.addWidget(foot)
        self.apply_theme(self.cfg.dark_mode)
        self.statusBar().showMessage('先在系统设置导入 Google 桌面授权文件并配置工作表。')
    def apply_theme(self,dark):
        self.current_dark=dark
        self.setStyleSheet(DARK_STYLE if dark else STYLE)
        if hasattr(self,'chart'):
            self.chart.setTheme(QChart.ChartTheme.ChartThemeDark if dark else QChart.ChartTheme.ChartThemeLight)
            self.chart.setBackgroundBrush(QColor('#202c3d' if dark else '#ffffff'))
            self.chart.setPlotAreaBackgroundVisible(False)
        if hasattr(self,'task_table'):self.refresh_table()
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
    def open_source_sheets(self):
        for doc in source_documents(self.cfg):
            if any(sheet.enabled for sheet in doc.sheets):self.open_sheet(doc.spreadsheet_id)
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
        self.source_filter=QComboBox();self.source_filter.setMinimumWidth(125);self.source_filter.currentIndexChanged.connect(self.source_filter_changed);bar.addWidget(self.source_filter);bar.addWidget(button('管理来源',self.manage_sources))
        self.search=QLineEdit();self.search.setPlaceholderText('搜索文案、人物…');self.search.setMinimumWidth(120);self.search.setMaximumWidth(240);self.search.textChanged.connect(self.refresh_table)
        self.requester=QComboBox();self.requester.addItem('全部需求者','');self.requester.currentIndexChanged.connect(self.refresh_table)
        self.state=QComboBox();self.state.addItems(['全部状态','可领取','已分配','已完成']);self.state.currentIndexChanged.connect(self.refresh_table)
        self.viral_filter=QComboBox();self.viral_filter.addItems(['全部爆帖状态','爆帖','非爆帖']);self.viral_filter.currentIndexChanged.connect(self.refresh_table);self.viral_filter.setFixedWidth(120)
        self.requester.setFixedWidth(120);self.state.setFixedWidth(105)
        for w in [self.search,self.requester,self.state,self.viral_filter]:bar.addWidget(w)
        bar.addWidget(button('全部人物',self.clear_group));bar.addStretch();bar.addWidget(button('刷新任务',self.reload,True))
        self.cards=QHBoxLayout();self.cards.setContentsMargins(0,0,0,4);self.cards.setSpacing(12);card_widget=QWidget();card_widget.setObjectName('cardShelf');card_widget.setLayout(self.cards);area=QScrollArea();area.setObjectName('cardArea');area.setWidgetResizable(True);area.setWidget(card_widget);area.setFixedHeight(190);self.card_area=area;v.addWidget(area)
        self.full_list_mode=False
        modes=QHBoxLayout();modes.addWidget(button('人物卡片',lambda:self.set_list_mode(False),True));modes.addWidget(button('完整列表',lambda:self.set_list_mode(True)));modes.addWidget(button('填写成品',self.batch_completion_dialog));self.count=QLabel('尚未加载任务');modes.addWidget(self.count,1);v.addLayout(modes)
        self.task_table=table(['选择','序号','需求者 / 人物','需求日期','中文文案','外语文案','图片','制作人','进度','自动命名','成品链接','播放量','爆帖状态']);self.task_table.setColumnWidth(4,250);self.task_table.setColumnWidth(9,250);self.task_table.setColumnWidth(6,72);self.task_table.setColumnWidth(8,128);v.addWidget(self.task_table,1)
        self.task_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter);self.task_table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked|QAbstractItemView.EditTrigger.EditKeyPressed);self.task_table.itemChanged.connect(self.hall_item_changed)
        actions=QHBoxLayout();self.select_all=QCheckBox('全选当前可领取');self.select_all.clicked.connect(self.toggle_all);actions.addWidget(self.select_all);actions.addWidget(button('领取勾选任务',self.claim,True));self.download_image_sources=QCheckBox('图片需求也下载素材');self.download_image_sources.setToolTip('视频需求仍自动下载；图片需求默认不下载。');actions.addWidget(self.download_image_sources);actions.addWidget(button('下载 / 重试选中行素材',self.download));actions.addStretch();v.addLayout(actions)
        number_bar=QHBoxLayout();self.override_number=QCheckBox('本次指定起始号');number_bar.addWidget(self.override_number);self.claim_start=QSpinBox();self.claim_start.setRange(1,999999);self.claim_start.setValue(self.cfg.sequence_start);self.claim_start.setEnabled(False);self.override_number.toggled.connect(self.claim_start.setEnabled);self.claim_start.setMaximumWidth(90);number_bar.addWidget(self.claim_start);hint=QLabel('勾选后本次从指定号码开始；冲突时停止');hint.setObjectName('muted');number_bar.addWidget(hint);number_bar.addStretch();v.addLayout(number_bar);self.pages.addWidget(page)
    def batch_completion_dialog(self):
        tasks=[t for t in self.visible if t.owner==self.cfg.producer and t.filename and not t.output]
        if not tasks:self.error('当前列表没有本制作人已领取、未回填成品的任务');return
        # Hall completion only updates the source and production sheets.
        cfg=self.cfg.model_copy(update={'register_spreadsheet_id':'','register_sheet':''},deep=True)
        class CompletionDialog(QDialog):
            busy=False
            def reject(self):
                if not self.busy:super().reject()
            def closeEvent(self,event):
                if self.busy:event.ignore()
                else:super().closeEvent(event)
        dialog=CompletionDialog(self);dialog.setWindowTitle('填写成品 · 批量校对');dialog.resize(1050,660)
        layout=QVBoxLayout(dialog);label=QLabel('左侧为当前列表中本人的未完成任务；粘贴多个 Drive 文件链接后读取，按行校对。文件名不同显示红色，确认后仍可回填。');label.setWordWrap(True);layout.addWidget(label)
        pasted=QPlainTextEdit();pasted.setPlaceholderText('一次粘贴多个 Google Drive 文件链接，每行一个');pasted.setMaximumHeight(100);layout.addWidget(pasted)
        state={'files':[],'confirmed':False};status=QLabel('等待粘贴并读取云端文件');layout.addWidget(status)
        compare=table(['任务自动命名','云端文件名','成品链接','核对']);compare.horizontalHeader().setStretchLastSection(False)
        for i in (0,1,2):compare.horizontalHeader().setSectionResizeMode(i,QHeaderView.ResizeMode.Stretch)
        compare.setColumnWidth(3,90);layout.addWidget(compare,1)
        def render():
            files=state['files'];rows=[]
            for i in range(max(len(tasks),len(files))):
                t=tasks[i] if i<len(tasks) else None;f=files[i] if i<len(files) else None
                same=bool(t and f and Path(f['name']).stem==t.filename)
                rows.append([t.filename if t else '（无对应任务）',f['name'] if f else '（缺少文件）',f['url'] if f else '', '✓ 一致' if same else '✗ 待核对'])
            fill(compare,rows)
            for r in range(len(rows)):compare.item(r,3).setForeground(QColor('#19a864' if rows[r][3].startswith('✓') else '#e44b4b'))
            status.setText(f'任务 {len(tasks)} 条，文件 {len(files)} 个；将本次任务移到前面，与文件逐行对应')
        def invalidate_links():
            if state['files']:
                state['files']=[];render();status.setText('粘贴内容已改变，请重新读取并校对')
        pasted.textChanged.connect(invalidate_links)
        def read_links():
            if self.jobs:status.setText('请等待当前操作完成');return
            text=pasted.toPlainText();status.setText('正在读取文件名…');state['files']=[];render()
            def done(items):
                import shiboken6
                if shiboken6.isValid(dialog) and dialog.isVisible():
                    if pasted.toPlainText()!=text:status.setText('粘贴内容已改变，请重新读取');return
                    state['files']=items;render()
            self.run_job(lambda p:desktop_service.inspect_completion_links(text,p),done)
        def move(delta):
            row=compare.currentRow();other=row+delta;files=state['files']
            if 0<=row<len(files) and 0<=other<len(files):files[row],files[other]=files[other],files[row];render();compare.selectRow(other)
        def move_task(delta):
            row=compare.currentRow();other=row+delta
            if 0<=row<len(tasks) and 0<=other<len(tasks):tasks[row],tasks[other]=tasks[other],tasks[row];render();compare.selectRow(other)
        def change_link():
            row=compare.currentRow();files=state['files']
            if row<0 or row>=len(files):status.setText('请先选中需要修改的文件行');return
            link,ok=QInputDialog.getText(dialog,'修改文件链接','粘贴新的 Google Drive 文件链接：',text=files[row]['url'])
            if not ok:return
            if self.jobs:status.setText('请等待当前操作完成');return
            def done(items):
                import shiboken6
                if not shiboken6.isValid(dialog) or not dialog.isVisible():return
                if len(items)!=1:status.setText('每行只能设置一个文件链接');return
                files[row]=items[0];render();compare.selectRow(row)
            self.run_job(lambda p:desktop_service.inspect_completion_links(link,p),done)
        controls=QHBoxLayout();controls.addWidget(button('读取并校对',read_links,True));controls.addWidget(button('文件上移',lambda:move(-1)));controls.addWidget(button('文件下移',lambda:move(1)));controls.addWidget(button('任务上移',lambda:move_task(-1)));controls.addWidget(button('任务下移',lambda:move_task(1)));controls.addWidget(button('修改链接',change_link));controls.addStretch();layout.addLayout(controls)
        def confirm():
            if self.jobs:status.setText('请等待当前操作完成');return
            files=state['files']
            if not files or len(files)>len(tasks):status.setText('请确保文件数量不超过任务数量，并调整任务顺序');return
            pairs=list(zip(tasks,files));status.setText('正在检查并回填，请勿关闭窗口…');dialog.busy=True
            def done(count):
                import shiboken6
                if shiboken6.isValid(dialog):dialog.busy=False;state['confirmed']=True;dialog.accept()
                self.log(f'已回填 {count} 条成品');QTimer.singleShot(50,self.reload_when_idle)
            self.run_job(lambda p:desktop_service.confirm_completion_pairs(cfg,pairs,p),done)
            if self.jobs:
                def unblock():
                    import shiboken6
                    if shiboken6.isValid(dialog):dialog.busy=False
                self.jobs[-1].finished.connect(unblock)
        controls.addWidget(button('确认回填',confirm,True));render();dialog.exec()
    def reload_when_idle(self):
        if self.jobs:QTimer.singleShot(100,self.reload_when_idle)
        else:self.reload()
    def manage_sources(self):
        dialog=QDialog(self);dialog.setWindowTitle('管理任务来源');dialog.resize(780,600)
        layout=QVBoxLayout(dialog);layout.addWidget(QLabel('选择已有来源编辑，或填写新的表格 ID / 链接。读取后勾选要保留的工作表。'))
        docs={d.spreadsheet_id:d.model_copy(deep=True) for d in source_documents(self.cfg)};loaded_id={'value':''};changed={'value':False}
        selector=QComboBox();selector.addItem('添加新来源','')
        for d in docs.values():selector.addItem(d.display_name or d.spreadsheet_id,d.spreadsheet_id)
        layout.addWidget(selector)
        form=QFormLayout();doc_id=QLineEdit();doc_name=QLineEdit();form.addRow('表格 ID 或链接',doc_id);form.addRow('来源名称',doc_name);layout.addLayout(form)
        source_table=table(['Sheet 名称','需求者别名','启用','需求类型']);source_table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked|QAbstractItemView.EditTrigger.EditKeyPressed|QAbstractItemView.EditTrigger.SelectedClicked);source_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch);source_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch);source_table.setColumnWidth(2,70);source_table.setColumnWidth(3,100)
        layout.addWidget(source_table,1)
        def rows():
            return [{'name':source_table.item(r,0).text(),'alias':source_table.item(r,1).text().strip(),'sheet_id':source_table.item(r,0).data(Qt.ItemDataRole.UserRole),'enabled':source_table.item(r,2).checkState()==Qt.CheckState.Checked,'task_type':source_table.cellWidget(r,3).currentData()} for r in range(source_table.rowCount())]
        def fill_rows(items):
            source_table.setRowCount(0)
            for row in items:
                r=source_table.rowCount();source_table.insertRow(r)
                name=QTableWidgetItem(row['name']);name.setFlags(name.flags() & ~Qt.ItemFlag.ItemIsEditable);name.setData(Qt.ItemDataRole.UserRole,row.get('sheet_id'));source_table.setItem(r,0,name)
                source_table.setItem(r,1,QTableWidgetItem(row.get('alias','')))
                check=QTableWidgetItem();check.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable|Qt.ItemFlag.ItemIsUserCheckable);check.setCheckState(Qt.CheckState.Checked if row.get('enabled') else Qt.CheckState.Unchecked);source_table.setItem(r,2,check)
                source_table.setCellWidget(r,3,self.source_type_combo(row.get('task_type','video')))
        def choose():
            sid=selector.currentData() or '';loaded_id['value']=sid;doc=docs.get(sid);doc_id.setText(sid);doc_name.setText(doc.display_name if doc else '');fill_rows([x.model_dump() for x in doc.sheets] if doc else [])
        selector.currentIndexChanged.connect(choose)
        status=QLabel('');status.setWordWrap(True);layout.addWidget(status)
        read_button=button('读取工作表',lambda:read());layout.addWidget(read_button)
        def read():
            sid=self.normalize_source_id(doc_id.text())
            if not sid:status.setText('请填写表格 ID 或链接');return
            if self.jobs:status.setText('请等待当前操作完成');return
            previous=rows() if selector.currentData()==sid else ([x.model_dump() for x in docs[sid].sheets] if sid in docs else [])
            read_button.setEnabled(False);status.setText('正在读取工作表…')
            def fetch(progress):
                from .workflow import list_sheet_metadata
                sheets,_=google_client.services();return list_sheet_metadata(sheets,sid)
            def receive(tabs):
                import shiboken6
                if not shiboken6.isValid(dialog) or not dialog.isVisible():return
                if self.normalize_source_id(doc_id.text())!=sid:status.setText('表格 ID 已改变，请重新读取');return
                doc_id.setText(sid)
                if selector.currentData()!=sid:selector.blockSignals(True);selector.setCurrentIndex(0);selector.blockSignals(False)
                loaded_id['value']=sid;fill_rows(merge_sources(tabs,previous));status.setText('勾选工作表并填写别名，然后点击保存来源')
            self.run_job(fetch,receive)
            if self.jobs:
                def done_read():
                    import shiboken6
                    if shiboken6.isValid(read_button):read_button.setEnabled(True)
                self.jobs[-1].finished.connect(done_read)
        def save_one():
            from .config import SourceDocument
            if self.jobs:status.setText('请等待读取完成');return
            sid=self.normalize_source_id(doc_id.text());entries=rows()
            if not sid or not entries:status.setText('请先读取工作表');return
            if any(x['enabled'] and not x['alias'] for x in entries):status.setText('启用的工作表必须填写需求者别名');return
            if loaded_id['value']!=sid:status.setText('ID 已更改，请重新读取新表格');return
            docs[sid]=SourceDocument(spreadsheet_id=sid,display_name=doc_name.text().strip(),sheets=entries)
            cfg=self.cfg.model_copy(update={'source_documents':list(docs.values()),'source_spreadsheet_id':next(iter(docs))},deep=True)
            primary=docs[cfg.source_spreadsheet_id];cfg.source_catalog=primary.sheets;cfg.source_sheets=[x.name for x in primary.sheets if x.enabled];cfg.requester_names={x.name:x.alias for x in primary.sheets if x.enabled}
            save_settings(cfg);self.cfg=cfg;changed['value']=True;self.reload_source_controls();self.loaded([])
            selector.blockSignals(True);selector.clear();selector.addItem('添加新来源','')
            for doc in docs.values():selector.addItem(doc.display_name or doc.spreadsheet_id,doc.spreadsheet_id)
            selector.setCurrentIndex(selector.findData(sid));selector.blockSignals(False);status.setText('已保存来源，请刷新任务')
        def remove_one():
            sid=selector.currentData()
            if not sid or sid not in docs:status.setText('请先选择要移除的来源');return
            if self.jobs:status.setText('请等待读取完成');return
            docs.pop(sid);primary=next(iter(docs),None)
            from .config import SourceDocument
            cfg=self.cfg.model_copy(update={'source_documents':list(docs.values()),'source_spreadsheet_id':primary or ''},deep=True)
            first=docs[primary] if primary else SourceDocument(spreadsheet_id='')
            cfg.source_catalog=first.sheets;cfg.source_sheets=[x.name for x in first.sheets if x.enabled];cfg.requester_names={x.name:x.alias for x in first.sheets if x.enabled}
            save_settings(cfg);self.cfg=cfg;changed['value']=True;self.reload_source_controls();self.loaded([])
            selector.blockSignals(True);selector.clear();selector.addItem('添加新来源','')
            for doc in docs.values():selector.addItem(doc.display_name or doc.spreadsheet_id,doc.spreadsheet_id)
            selector.blockSignals(False);choose();status.setText('已移除来源，未修改 Google 表格')
        actions=QHBoxLayout();actions.addWidget(button('保存来源',save_one,True));actions.addWidget(button('移除所选来源',remove_one));layout.addLayout(actions)
        close=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);close.rejected.connect(dialog.reject);layout.addWidget(close);dialog.exec()
        if changed['value'] and not self.jobs and any(s.enabled for d in source_documents(self.cfg) for s in d.sheets):self.reload()
    def reload_source_controls(self):
        self.fields['source_spreadsheet_id'].setText(self.cfg.source_spreadsheet_id);self.source_doc=self.cfg.source_spreadsheet_id
        self.sources.blockSignals(True);self.sources.setRowCount(0)
        for row in self.cfg.source_catalog:self.add_source(row.name,row.alias,row.enabled,row.sheet_id,row.task_type)
        self.sources.blockSignals(False);self.update_source_summary();self.extra_sources.setRowCount(0)
        for doc in source_documents(self.cfg):
            if doc.spreadsheet_id!=self.cfg.source_spreadsheet_id:
                for row in doc.sheets:self.add_extra_source(doc.spreadsheet_id,row.name,row.alias,row.enabled,row.sheet_id,row.task_type)
        self.refresh_extra_groups();self.apply_extra_visibility()
    def source_filter_changed(self):
        self.group_filter=None;self.refresh_table()
    def set_list_mode(self,full):
        self.full_list_mode=full;self.card_area.setVisible(not full)
        if full:self.group_filter=None
        self.refresh_table()
    def clear_group(self):self.group_filter=None;self.refresh_table()
    def reload(self):
        cfg=self.cfg.model_copy(deep=True)
        self.run_job(lambda p:desktop_service.query(cfg,p),self.loaded)
    def loaded(self,items):
        current_source=self.source_filter.currentData() or '';self.source_filter.blockSignals(True);self.source_filter.clear();self.source_filter.addItem('全部来源','')
        for doc in source_documents(self.cfg):
            if any(s.enabled for s in doc.sheets):self.source_filter.addItem(doc.display_name or doc.spreadsheet_id,doc.spreadsheet_id)
        self.source_filter.setCurrentIndex(max(0,self.source_filter.findData(current_source)));self.source_filter.blockSignals(False)
        self.tasks=items;self.stale_claims.clear();self.group_filter=None;self.group_cards={};self.requester.blockSignals(True);self.requester.clear();self.requester.addItem('全部需求者','')
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
        q=self.search.text().lower();s=self.state.currentIndex();who=self.requester.currentData();viral=self.viral_filter.currentIndex();source=self.source_filter.currentData()
        self.visible=[t for t in self.tasks if (not source or t.source_id==source) and (not self.mine or t.owner==self.cfg.producer) and (not who or t.requester==who) and (not self.group_filter or (t.source_id,t.sheet,t.start_col)==self.group_filter) and (not q or q in ' '.join([t.chinese,t.portuguese,t.filename,t.label]).lower()) and (s==0 or s==1 and t.available or s==2 and t.owner and not t.output or s==3 and t.output) and (viral==0 or viral==1 and t.viral and t.output or viral==2 and not t.viral and t.output)]
        self.task_table.horizontalHeaderItem(1).setText('列表序号' if self.full_list_mode else '任务序号')
        self.task_table.blockSignals(True)
        fill(self.task_table,[['',str(i+1).zfill(2) if self.full_list_mode else t.number or '—',t.label,t.deadline,t.chinese,t.portuguese,'','待刷新' if t.identity in self.stale_claims else t.owner,'待刷新' if t.identity in self.stale_claims else t.progress or ('已完成' if t.output else '已分配' if t.owner else '可领取'),t.filename,t.output,t.views,'爆帖' if t.output and t.viral else '未标记' if t.output else '—'] for i,t in enumerate(self.visible)])
        language_labels={t.language_header for t in self.visible if t.language_header}
        self.task_table.horizontalHeaderItem(5).setText(next(iter(language_labels)) if len(language_labels)==1 else '外语文案')
        for r,t in enumerate(self.visible):
            if self.full_list_mode:self.task_table.item(r,1).setToolTip('列表位置；领取后的任务序号：'+(t.number or '尚未领取'))
            if t.language_header:self.task_table.item(r,5).setToolTip(t.language_header+'：'+t.portuguese)
            item=self.task_table.item(r,0)
            self.task_table.setCellWidget(r,6,Thumbnail(self.thumbnails,t.image));status=self.task_table.item(r,8);status.setForeground(QColor('#0fa66d' if t.output else '#e68b22' if t.owner else '#1677ed'))
            if t.views_note:self.task_table.item(r,11).setToolTip(t.views_note)
            for col in (10,11,12):self.task_table.item(r,col).setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if t.views and t.views_url:
                link=QLabel(f'<a href="{escape(t.views_url,quote=True)}">{escape(t.views)}</a>')
                link.setTextFormat(Qt.TextFormat.RichText);link.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse|Qt.TextInteractionFlag.LinksAccessibleByKeyboard)
                link.setAlignment(Qt.AlignmentFlag.AlignCenter);link.setStyleSheet('background:#202c3d; font-size:13px;' if getattr(self,'current_dark',False) else 'background:#ffffff; font-size:13px;')
                link.setToolTip(t.views_note or t.views_url);link.linkActivated.connect(lambda url:QDesktopServices.openUrl(QUrl(url)))
                self.task_table.item(r,11).setText('')
                self.task_table.setCellWidget(r,11,link)
            if t.output and t.viral:self.task_table.item(r,12).setForeground(QColor('#0fa66d'))
            owner=self.task_table.item(r,7)
            for col in range(self.task_table.columnCount()):
                cell=self.task_table.item(r,col)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if t.identity not in self.stale_claims and not self.jobs:
                owner.setFlags(owner.flags() | Qt.ItemFlag.ItemIsEditable);owner.setToolTip('双击直接修改制作人')
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            if t.identity not in self.stale_claims and t.available and not t.output:item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Unchecked)
            if t.identity not in self.stale_claims and t.available and not t.output:
                action=button('领取',lambda task=t:self.task_action(task));action.setEnabled(not self.jobs);action.setObjectName('soft');self.task_table.setCellWidget(r,8,action)
            elif t.identity not in self.stale_claims and (t.owner or t.output):
                progress=QComboBox();progress.setObjectName('taskProgress');current=t.progress or ('已完成' if t.output else '制作中')
                if current in ('已分配','分配'):current='制作中'
                options=['制作中','已完成','暂停']
                if current not in options:options.append(current)
                for value in options:progress.addItem(value)
                progress.setCurrentText(current);progress.setEnabled(not self.jobs)
                progress.activated.connect(lambda index,task=t,box=progress:self.set_task_progress(task,box.currentText()))
                self.task_table.setCellWidget(r,8,progress)
        self.task_table.blockSignals(False)
        self.select_all.blockSignals(True);self.select_all.setChecked(False);self.select_all.blockSignals(False)
        self.count.setObjectName('muted')
        group_task=next((t for t in self.tasks if (t.source_id,t.sheet,t.start_col)==self.group_filter),None)
        scope=group_task.label if group_task else ('我的制作 · 全部人物' if self.mine else '全部人物')
        self.count.setText(f'{scope}  ·  共 {len(self.visible)} 个任务  ·  可领取 {sum(t.available and not t.output for t in self.visible)}  ·  已领取 {sum(bool(t.owner) for t in self.visible)}  ·  已完成 {sum(bool(t.output) for t in self.visible)}')
        for key,card in self.group_cards.items():
            card.setVisible(not source or key[0]==source);card.setProperty('selected',key==self.group_filter);card.style().unpolish(card);card.style().polish(card)
    def hall_item_changed(self,item):
        if item.column()!=7 or self.jobs or item.row()>=len(self.visible):return
        task=self.visible[item.row()];value=item.text().strip()
        if value==task.owner:return
        cfg=self.cfg.model_copy(deep=True);self.run_job(lambda p:desktop_service.edit_task(cfg,task,'owner',value,p),self.loaded)
    def set_task_progress(self,task,value):
        if self.jobs:return
        if value=='可领取':
            self.refresh_table();self.error('如需释放已领取任务，请先清理或通过放弃任务流程处理，避免两表记录不一致');return
        if value==task.progress:return
        cfg=self.cfg.model_copy(deep=True);self.run_job(lambda p:desktop_service.edit_task(cfg,task,'progress',value,p),self.loaded)
    def toggle_all(self,checked):
        for r,t in enumerate(self.visible):
            if t.identity not in self.stale_claims and t.available and not t.output:self.task_table.item(r,0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
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
        download_images=self.download_image_sources.isChecked();cfg=self.cfg.model_copy(update={'sequence_override':self.claim_start.value() if self.override_number.isChecked() else None},deep=True)
        self.run_job(lambda p:desktop_service.claim_tasks(cfg,ids,p,download_images),self.claimed)
    def claim(self):
        ids=[t.identity for r,t in enumerate(self.visible) if self.task_table.item(r,0).checkState()==Qt.CheckState.Checked]
        if not ids:self.error('请勾选可领取任务');return
        self.start_claim(ids)
    def claimed(self,result):
        self.override_number.setChecked(False)
        items=result['claimed'];fresh=result.get('fresh_tasks')
        if fresh is not None:
            key=self.group_filter;self.loaded(fresh);self.group_filter=key;self.refresh_table();self.refresh_stats()
        else:
            # Cached names may be stale: do not invent an owner after a failed refresh.
            self.stale_claims.update(item['id'] for item in items);self.refresh_table()
            self.log('领取已完成，但制作人状态未刷新，请点击刷新任务')
        failed=len(result['failed_downloads']);skipped=len(result.get('skipped_downloads',[]));downloaded=len(items)-failed-skipped
        self.announce('领取完成' if skipped or failed else '下载完成')
        self.log(f'已领取 {len(items)} 条；素材成功 {downloaded}，跳过 {skipped}，失败 {failed}。')
    def download(self):
        row=self.task_table.currentRow()
        if row<0:return
        t=self.visible[row]
        if t.owner!=self.cfg.producer or not t.filename:self.error('请选择自己已领取的任务');return
        self.run_job(lambda p:desktop_service.download_claim_image(self.cfg,{'id':t.identity,'source_id':t.source_id,'filename':t.filename,'deadline':t.deadline,'image':t.image,'date':t.filename.rsplit('-',1)[-1],'folder':t.label,'number':t.number},p),lambda path:(self.log('已保存：'+path),self.announce('下载完成')))
    def build_upload(self):
        page=QWidget();page.setObjectName('uploadContent');v=QVBoxLayout(page);v.setContentsMargins(16,12,16,16);v.setSpacing(8);v.addWidget(QLabel('拖入成品文件，或选择文件 / 文件夹。上传前检查整个队列，失败即停止。'))
        choices=QGridLayout();choices.setHorizontalSpacing(12);choices.setVerticalSpacing(8);self.upload_choices={}
        for i,(key,label) in enumerate([('type','类型'),('difficulty','难易程度'),('material','素材来源'),('software','软件')]):
            column=(i%2)*2;row=i//2;choices.addWidget(QLabel(label),row,column);box=QComboBox();box.setMinimumWidth(160);box.setMinimumHeight(40);box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);box.setMinimumContentsLength(10);choices.addWidget(box,row,column+1);self.upload_choices[key]=box
            box.currentTextChanged.connect(box.setToolTip)
        choices.setColumnStretch(1,1);choices.setColumnStretch(3,1);v.addLayout(choices)
        dates=QHBoxLayout();dates.addWidget(QLabel('登记日期'))
        self.upload_date=QDateEdit(QDate.currentDate());self.upload_date.setCalendarPopup(True);self.upload_date.setDisplayFormat('yyyy-MM-dd');dates.addWidget(self.upload_date)
        self.auto_date=True;self.date_hint=QLabel('未选择文件夹，默认当天');self.date_hint.setObjectName('muted');self.date_hint.setWordWrap(True)
        self.upload_date.dateChanged.connect(self.manual_date_changed)
        dates.addWidget(button('重新识别',self.redetect_date));dates.addWidget(button('恢复自动',self.restore_auto_date))
        dates.addStretch();v.addLayout(dates);v.addWidget(self.date_hint)
        category_bar=QHBoxLayout();category_bar.addWidget(button('刷新分类选项',self.refresh_upload_categories));category_bar.addStretch();v.addLayout(category_bar)
        self.populate_upload_choices(self.cfg.register_category_options)
        bar=QHBoxLayout();bar.addWidget(button('选择文件',self.pick_videos));bar.addWidget(button('选择文件夹',self.pick_folder));bar.addWidget(button('清空队列',self.clear_upload));bar.addWidget(button('开始上传',self.upload,True));v.addLayout(bar)
        self.upload_table=table(['成品文件路径']);v.addWidget(self.upload_table)
        v.addWidget(QLabel('或粘贴 Google Drive 文件 / 文件夹链接（每行一个），读取文件名匹配后回填。'))
        self.cloud_links=QPlainTextEdit();self.cloud_links.setPlaceholderText('https://drive.google.com/file/d/...\nhttps://drive.google.com/drive/folders/...');self.cloud_links.setMaximumHeight(110);v.addWidget(self.cloud_links)
        self.cloud_date_timer=QTimer(self);self.cloud_date_timer.setSingleShot(True);self.cloud_date_timer.setInterval(900);self.cloud_date_timer.timeout.connect(self.detect_cloud_date)
        self.cloud_links.textChanged.connect(lambda:self.cloud_date_timer.start() if self.auto_date else None)
        v.addWidget(button('匹配云端链接并回填',self.complete_links,True));v.addWidget(QLabel('当前支持逐文件进度；跨进程断点续传待实现。'))
        area=QScrollArea();area.setWidgetResizable(True);area.setWidget(page);self.pages.addWidget(area)
    def complete_links(self):
        links=[line.strip() for line in self.cloud_links.toPlainText().splitlines() if line.strip()]
        if not links:self.error('请先粘贴 Google Drive 文件或文件夹链接');return
        try:cfg=self.upload_settings()
        except ValueError as e:self.error(str(e));return
        def work(progress):
            count=desktop_service.complete_drive_links(cfg,links,progress)
            progress(f'{count} 个云端成品回填完成，正在刷新任务…')
            return desktop_service.query(self.cfg)
        self.run_job(work,lambda tasks:(self.loaded(tasks),self.refresh_stats(),self.log('云端成品回填完成')))
    def add_paths(self,paths):
        if self.jobs:return
        self.paths.extend(str(p) for p in paths);fill(self.upload_table,[[p] for p in self.paths]);self.pages.setCurrentIndex(1)
        if self.auto_date:self.detect_local_date()
    def pick_videos(self):self.add_paths(QFileDialog.getOpenFileNames(self,'选择成品文件','','所有文件 (*)')[0])
    def pick_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'选择成品文件夹')
        if folder:self.add_paths(p for p in Path(folder).rglob('*') if p.is_file())
    def clear_upload(self):
        if not self.jobs:
            self.paths=[];fill(self.upload_table,[])
            if self.auto_date:self.set_detected_date(None,'未选择文件夹，默认当天')
    def upload(self):
        if self.paths:
            try:cfg=self.upload_settings()
            except ValueError as e:self.error(str(e));return
            def work(progress):
                n=desktop_service.upload_files(cfg,list(self.paths),progress)
                progress(f'{n} 个成品上传回填完成；正在刷新任务…')
                return desktop_service.query(self.cfg)
            self.run_job(work,lambda tasks:(self.loaded(tasks),self.refresh_stats(),self.log('上传回填完成，任务状态已刷新')))
    def populate_upload_choices(self,options):
        for key,box in self.upload_choices.items():
            current=box.currentData() or self.cfg.register_defaults.get(key,'');box.clear();box.addItem('请选择','')
            for value in options.get(key,[]):box.addItem(value,value)
            index=box.findData(current);box.setCurrentIndex(max(index,0))
    def refresh_upload_categories(self):
        doc=self.cfg.register_spreadsheet_id
        if not doc:self.error('请先在系统设置中保存登记表 ID');return
        def fetch(progress):
            from .registration import read_categories
            sheets,_=google_client.services();return read_categories(sheets,doc)
        self.run_job(fetch,lambda options:(self.populate_upload_choices(options),self.statusBar().showMessage('分类选项已刷新',8000)))
    def upload_settings(self):
        values={key:box.currentData() or '' for key,box in self.upload_choices.items()}
        if self.cfg.register_spreadsheet_id:
            required=[key for key,value in values.items() if key in self.cfg.register_columns and not value]
            if required:raise ValueError('请在成品上传中选择类型、难易程度、素材来源和软件（已关闭的字段除外）')
        return self.cfg.model_copy(update={'register_defaults':self.cfg.register_defaults|values,'register_date_mode':'manual','register_date':self.upload_date.date().toString('yyyy-MM-dd')},deep=True)
    def manual_date_changed(self,*args):
        self.auto_date=False;self.date_hint.setText('已手动选择日期')
    def set_detected_date(self,value,message):
        if not self.auto_date:return
        self.upload_date.blockSignals(True);self.upload_date.setDate(QDate.fromString(value,'yyyy-MM-dd') if value else QDate.currentDate());self.upload_date.blockSignals(False);self.date_hint.setText(message)
    def detect_local_date(self):
        dates=set();missing=False
        cfg=self.cfg.model_copy(update={'register_date_mode':'folder'})
        for raw in self.paths:
            try:dates.add(desktop_service.completion_date(cfg,[p.name for p in reversed(Path(raw).parents)]))
            except ValueError:missing=True
        if len(dates)==1 and not missing:self.set_detected_date(next(iter(dates)),'已从文件夹识别日期')
        elif len(dates)>1 or dates and missing:self.set_detected_date(None,'文件夹日期不一致或部分未识别，默认当天；可手动选择')
        else:self.set_detected_date(None,'未识别到文件夹日期，默认当天')
    def restore_auto_date(self):self.auto_date=True;self.redetect_date()
    def redetect_date(self):
        self.auto_date=True
        if self.cloud_links.toPlainText().strip():self.detect_cloud_date()
        elif self.paths:self.detect_local_date()
        else:self.set_detected_date(None,'未选择文件夹，默认当天')
    def detect_cloud_date(self):
        if not self.auto_date:return
        links=[line.strip() for line in self.cloud_links.toPlainText().splitlines() if line.strip()]
        if not links:self.set_detected_date(None,'未选择文件夹，默认当天');return
        if any(not link.startswith('https://drive.google.com/') for link in links):self.set_detected_date(None,'等待有效的 Google Drive 链接');return
        if self.jobs:self.date_hint.setText('正在执行其他任务，稍后可点击重新识别');return
        self.date_hint.setText('正在读取云端文件夹日期…')
        def fetch(progress):
            _,drive=google_client.services();cfg=self.cfg.model_copy(update={'register_date_mode':'folder'});found=set();missing=False
            for link in links:
                item=desktop_service.resolve_drive_link(drive,link)
                if item.get('mimeType')!='application/vnd.google-apps.folder':missing=True;continue
                try:found.add(desktop_service.completion_date(cfg,[item['name']]))
                except ValueError:missing=True
            return found,missing
        def done(result):
            if self.cloud_links.toPlainText().strip()!='\n'.join(links):return
            found,missing=result
            if len(found)==1 and not missing:self.set_detected_date(next(iter(found)),'已从云端文件夹名称识别日期')
            elif len(found)>1 or found and missing:self.set_detected_date(None,'文件夹日期不一致或部分未识别，默认当天；可手动选择')
            else:self.set_detected_date(None,'未识别到文件夹日期，默认当天')
        worker=Worker(fetch);self.jobs.append(worker)
        worker.result.connect(done)
        worker.failed.connect(lambda _:self.set_detected_date(None,'识别失败，默认当天；可手动选择'))
        def finished():
            self.jobs.remove(worker);worker.deleteLater()
            if self.auto_date and self.cloud_links.toPlainText().strip()!='\n'.join(links):self.cloud_date_timer.start()
        worker.finished.connect(finished);worker.start()
    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls():event.acceptProposedAction()
    def dropEvent(self,event):self.add_paths(u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile())
    def build_stats(self):
        page=QWidget();v=QVBoxLayout(page);v.setContentsMargins(24,20,24,20)
        bar=QHBoxLayout();today=QDate.currentDate();self.stats_from=QDateEdit(QDate(today.year(),today.month(),1));self.stats_to=QDateEdit(today)
        for widget in (self.stats_from,self.stats_to):widget.setCalendarPopup(True);widget.setDisplayFormat('yyyy-MM-dd')
        bar.addWidget(QLabel('日期范围'));bar.addWidget(self.stats_from);bar.addWidget(self.stats_to);bar.addWidget(button('统计',self.refresh_stats));bar.addWidget(button('本月',self.stats_month));bar.addWidget(button('复制统计表',self.copy_stats));bar.addWidget(button('查看操作日志',self.show_history));bar.addStretch();v.addLayout(bar)
        note=QLabel('表格按需求日期统计；爆帖数量以有成品链接且单元格背景为绿色的任务数为准。曲线按本机日志统计操作次数。');note.setWordWrap(True);note.setObjectName('muted');v.addWidget(note)
        self.chart=QChart();self.chart_view=QChartView(self.chart);self.chart_view.setMinimumHeight(220);v.addWidget(self.chart_view)
        self.stats=table(['需求表','需求者 / 人物','总任务','未领取','已领取¹','已完成','爆帖数量','放弃次数']);self.stats.setObjectName('compactStats');self.stats.horizontalHeader().setStretchLastSection(False);self.stats.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter);self.stats.setColumnWidth(0,180);self.stats.setColumnWidth(1,220)
        self.stats.horizontalHeaderItem(4).setToolTip('已领取包含已完成任务');self.stats.verticalHeader().setDefaultSectionSize(36)
        for c in range(2,8):self.stats.setColumnWidth(c,76)
        v.addWidget(self.stats);self.pages.addWidget(page)
    def stats_month(self):
        now=QDate.currentDate();self.stats_from.setDate(QDate(now.year(),now.month(),1));self.stats_to.setDate(now);self.refresh_stats()
    def copy_stats(self):
        def safe(value):
            value=str(value or '')
            if value.lstrip().startswith(('=','+','-','@')):return "'"+value
            return value
        buffer=io.StringIO(newline='');writer=csv.writer(buffer,delimiter='\t',lineterminator='\r\n')
        writer.writerow([safe(self.stats.horizontalHeaderItem(c).text()) for c in range(self.stats.columnCount())])
        for row in range(self.stats.rowCount()):
            writer.writerow([safe(self.stats.item(row,c).text() if self.stats.item(row,c) else '') for c in range(self.stats.columnCount())])
        QApplication.clipboard().setText(buffer.getvalue())
        self.statusBar().showMessage(f'已复制 {self.stats.rowCount()} 行统计数据，可直接粘贴到 Google 表格',8000)
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
        actions.addWidget(button('全选',lambda:self.select_sources(True)));actions.addWidget(button('取消全选',lambda:self.select_sources(False)));actions.addWidget(button('删除选中工作表',self.remove_primary_sources));actions.addWidget(button('折叠 / 展开',self.toggle_primary_sources));actions.addStretch();v.addLayout(actions)
        self.source_summary=QLabel('尚未读取工作表');self.source_summary.setObjectName('muted');v.addWidget(self.source_summary)
        self.sources=table(['实际 Sheet 名称','需求者别名','启用','需求类型']);self.sources.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked|QAbstractItemView.EditTrigger.EditKeyPressed|QAbstractItemView.EditTrigger.SelectedClicked)
        self.sources.horizontalHeader().setStretchLastSection(False);self.sources.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch);self.sources.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch);self.sources.setColumnWidth(2,80);self.sources.setColumnWidth(3,120);self.sources.setMinimumHeight(310)
        self.source_doc=self.cfg.source_spreadsheet_id;self.requested_source_doc=None
        if self.cfg.source_catalog:
            for row in self.cfg.source_catalog:self.add_source(row.name,row.alias,row.enabled,row.sheet_id,row.task_type)
        else:
            for name in self.cfg.source_sheets:self.add_source(name,self.cfg.requester_names.get(name) or suggest_alias(name),True)
        self.sources.itemChanged.connect(self.update_source_summary);self.update_source_summary();v.addWidget(self.sources);self.sources.setVisible(not self.cfg.primary_source_collapsed)
        notice=QLabel('例如：需求者-制作人-业务分类 → 需求者。只读取勾选项；再次刷新会保留手动别名。');notice.setObjectName('notice');notice.setWordWrap(True);v.addWidget(notice)
        extra_title=QLabel('其他需求来源');extra_title.setObjectName('sectionTitle');v.addWidget(extra_title)
        self.extra_id=QLineEdit();self.extra_id.setPlaceholderText('填写其他 Spreadsheet ID，点击读取并勾选工作表');v.addWidget(self.extra_id)
        extra_actions=QHBoxLayout();extra_actions.addWidget(button('读取其他来源工作表',self.discover_extra_sources));extra_actions.addWidget(button('删除选中工作表',self.remove_extra_sources));extra_actions.addWidget(button('删除所选来源',self.remove_extra_document));extra_actions.addWidget(button('折叠 / 展开来源',self.toggle_extra_sources));self.extra_group=QComboBox();self.extra_group.addItem('全部其他来源','');extra_actions.addWidget(self.extra_group,1);v.addLayout(extra_actions)
        self.extra_collapsed=set(self.cfg.collapsed_source_ids)
        self.extra_sources=table(['Spreadsheet ID','实际 Sheet 名称','需求者别名','启用','需求类型']);self.extra_sources.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked|QAbstractItemView.EditTrigger.EditKeyPressed|QAbstractItemView.EditTrigger.SelectedClicked);self.extra_sources.setMinimumHeight(0);self.extra_sources.setMaximumHeight(360)
        self.extra_sources.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch);self.extra_sources.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch);self.extra_sources.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch);self.extra_sources.setColumnWidth(3,70)
        for doc in source_documents(self.cfg):
            if doc.spreadsheet_id!=self.cfg.source_spreadsheet_id:
                for row in doc.sheets:self.add_extra_source(doc.spreadsheet_id,row.name,row.alias,row.enabled,row.sheet_id,row.task_type)
        v.addWidget(self.extra_sources);self.apply_extra_visibility()
        v=panel('表头别名','任务表字段识别','填写表格实际使用的字段名称，多个名称用中文或英文逗号隔开。适用于需求表和制作表；原有标准表头仍可使用。请避免将同一名称分配给不同字段。')
        self.header_mapping=QTableWidget(len(ALIASES),2);self.header_mapping.setObjectName('headerMapping');self.header_mapping.setHorizontalHeaderLabels(['标准字段','自定义表头名称（双击编辑）']);self.header_mapping.verticalHeader().hide();self.header_mapping.verticalHeader().setDefaultSectionSize(46);self.header_mapping.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);self.header_mapping.setShowGrid(False);self.header_mapping.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.header_mapping.setFixedHeight(len(ALIASES)*46+58)
        for row,(key,names) in enumerate(ALIASES.items()):
            item=QTableWidgetItem('语言' if key=='portuguese' else names[0]);item.setData(Qt.ItemDataRole.UserRole,key);item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable);self.header_mapping.setItem(row,0,item)
            self.header_mapping.setItem(row,1,QTableWidgetItem('，'.join(self.cfg.header_aliases.get(key,[]))))
        v.addWidget(self.header_mapping)
        v=panel('制作与文件','个人制作配置','配置制作人及唯一制作工作表，指定素材和成品的存放位置。')
        for key,label in [('producer','制作人姓名'),('production_sheet','制作 Sheet 名称'),('production_spreadsheet_id','制作表 Spreadsheet ID'),('prefix','命名前缀'),('download_path','素材下载根目录'),('drive_parent_folder_id','Drive 父文件夹 ID')]:field(v,key,label)
        self.production_layout=QComboBox();self.production_layout.addItem('按人物分组追加','grouped');self.production_layout.addItem('左侧第一组（自动识别列宽） 顶部插入（最新领取在上）','left_al');self.production_layout.setCurrentIndex(self.production_layout.findData(self.cfg.production_layout));v.addWidget(QLabel('制作表写入方式'));v.addWidget(self.production_layout)
        sequence_form=QFormLayout();self.sequence_start=QSpinBox();self.sequence_start.setRange(1,999999);self.sequence_start.setValue(self.cfg.sequence_start);sequence_form.addRow('默认起始序号',self.sequence_start)
        self.sequence_mode=QComboBox();self.sequence_mode.addItem('全部来源连续编号','combined');self.sequence_mode.addItem('每个表格独立编号','per_source');self.sequence_mode.setCurrentIndex(max(0,self.sequence_mode.findData(self.cfg.sequence_mode)));sequence_form.addRow('多表格编号方式',self.sequence_mode);v.addLayout(sequence_form)
        v.addWidget(button('选择素材文件夹',self.pick_download))
        self.voice_enabled=QCheckBox('下载完成后语音提醒（关闭后静默）');self.voice_enabled.setChecked(self.cfg.voice_enabled);v.addWidget(self.voice_enabled)
        self.dark_mode=QCheckBox('启用暗黑模式');self.dark_mode.setChecked(self.cfg.dark_mode);self.dark_mode.toggled.connect(self.apply_theme);v.addWidget(self.dark_mode)
        from .registration import LABELS
        v=panel('成品登记表','附加成品登记表','可选：成品回填后追加一行。列字母可修改，留空代表不写入。类型、素材来源、软件和难易程度从登记表中的“分类”工作表读取。')
        register_doc=field(v,'register_spreadsheet_id','登记表 Spreadsheet ID');field(v,'register_sheet','登记 Sheet 名称')
        v.addWidget(button('读取分类选项',self.load_register_categories))
        self.category_status=QLabel('填写登记表 ID 后读取“分类”工作表');self.category_status.setObjectName('muted');v.addWidget(self.category_status)
        self.category_options={};self.category_source=None
        register_doc.editingFinished.connect(lambda:self.load_register_categories() if register_doc.text().strip() and register_doc.text().strip()!=self.category_source and not self.jobs else None)
        self.register_mapping=QTableWidget(len(LABELS),3);self.register_mapping.setHorizontalHeaderLabels(['字段','目标列（留空不写入）','默认值']);self.register_mapping.verticalHeader().hide();self.register_mapping.verticalHeader().setDefaultSectionSize(46);self.register_mapping.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);self.register_mapping.setMinimumHeight(520)
        for row,(key,label) in enumerate(LABELS.items()):
            item=QTableWidgetItem(label);item.setData(Qt.ItemDataRole.UserRole,key);item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable);self.register_mapping.setItem(row,0,item)
            self.register_mapping.setItem(row,1,QTableWidgetItem(self.cfg.register_columns.get(key,'')))
            default=QTableWidgetItem(self.cfg.register_defaults.get(key,''));
            if key!='group':default.setFlags(default.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.register_mapping.setItem(row,2,default)
            if key in ('type','material','software','difficulty'):default.setText('在成品上传中选择')
        v.addWidget(self.register_mapping)
        self.duration_choices={}
        for key,label in [('short','≤59 秒对应分类'),('long','≥60 秒对应分类')]:
            box=QComboBox();box.addItem('','');value=self.cfg.register_duration_labels.get(key,'')
            if value:box.addItem(value,value);box.setCurrentIndex(1)
            self.duration_choices[key]=box;form=QFormLayout();form.addRow(label,box);v.addLayout(form)
        tip=QLabel('日期使用回填当天；制作人自动读取；视频时长由 Drive 提供（秒）。未取得时长则留空。请从分类表 E 列选择两个时长对应值。')
        tip.setWordWrap(True);tip.setObjectName('muted');v.addWidget(tip)
        v=panel('Google 授权','Google 账号连接','导入桌面应用 OAuth JSON，在系统浏览器中完成账号授权。')
        self.auth_label=QLabel('尚未检查授权状态');self.auth_label.setObjectName('notice');v.addWidget(self.auth_label);bar=QHBoxLayout()
        for text,fn in [('导入授权文件',self.import_auth),('Google 授权',self.authorize),('检查授权',self.auth_status),('清除本机登录',self.disconnect)]:bar.addWidget(button(text,fn))
        v.addLayout(bar)
        v=panel('组件与更新','运行环境','检查 GitHub Release。更新包下载后先校验 SHA-256，再启动对应系统的安装流程。')
        self.components=table(['组件','版本','状态']);self.components.setMinimumHeight(350);self.components.setColumnWidth(0,260);self.components.setColumnWidth(1,240);v.addWidget(self.components)
        bar=QHBoxLayout();bar.addWidget(button('检查组件',self.check_components));bar.addWidget(button('安装 / 修复组件',self.repair));v.addLayout(bar)
        footer=QHBoxLayout();hint=QLabel('保存后生效 · 不会修改已领取任务的命名');hint.setObjectName('muted');footer.addWidget(hint);footer.addStretch();footer.addWidget(button('保存设置',self.save,True));outer.addLayout(footer)
        tabs.removeTab(0)  # source configuration lives in the task hall dialog
        self.pages.addWidget(page);self.check_components()
    @staticmethod
    def normalize_source_id(value):
        import re
        text=value.strip();match=re.search(r'^https://docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]+)(?:/|$)',text)
        return match.group(1) if match else text
    def remove_primary_sources(self):
        rows=sorted({index.row() for index in self.sources.selectedIndexes()},reverse=True)
        for row in rows:self.sources.removeRow(row)
        self.update_source_summary()
    def toggle_primary_sources(self):
        self.sources.setVisible(self.sources.isHidden())
    def refresh_extra_groups(self):
        current=self.extra_group.currentData() or '';docs=sorted({self.extra_sources.item(r,0).text() for r in range(self.extra_sources.rowCount()) if self.extra_sources.item(r,0)})
        self.extra_group.blockSignals(True);self.extra_group.clear();self.extra_group.addItem('全部其他来源','')
        for doc in docs:self.extra_group.addItem(('▶ ' if doc in self.extra_collapsed else '▼ ')+doc,doc)
        index=self.extra_group.findData(current);self.extra_group.setCurrentIndex(max(0,index));self.extra_group.blockSignals(False)
    def apply_extra_visibility(self):
        for r in range(self.extra_sources.rowCount()):self.extra_sources.setRowHidden(r,self.extra_sources.item(r,0).text() in self.extra_collapsed)
        visible=sum(not self.extra_sources.isRowHidden(r) for r in range(self.extra_sources.rowCount()))
        self.extra_sources.setMaximumHeight(max(55,min(360,visible*52+55)))
    def toggle_extra_sources(self):
        doc=self.extra_group.currentData()
        docs={self.extra_sources.item(r,0).text() for r in range(self.extra_sources.rowCount())}
        if not doc:
            self.extra_collapsed=set() if docs and docs<=self.extra_collapsed else docs
        elif doc in self.extra_collapsed:self.extra_collapsed.remove(doc)
        else:self.extra_collapsed.add(doc)
        self.extra_sources.clearSelection();self.apply_extra_visibility();self.refresh_extra_groups()
    def remove_extra_sources(self):
        rows=sorted({index.row() for index in self.extra_sources.selectedIndexes()},reverse=True)
        if not rows:self.statusBar().showMessage('请先在表格中选中要删除的工作表');return
        for row in rows:self.extra_sources.removeRow(row)
        self.refresh_extra_groups();self.apply_extra_visibility()
    def remove_extra_document(self):
        doc=self.extra_group.currentData()
        if not doc:self.statusBar().showMessage('请先选择要删除的来源 ID');return
        for row in reversed(range(self.extra_sources.rowCount())):
            if self.extra_sources.item(row,0).text()==doc:self.extra_sources.removeRow(row)
        self.extra_collapsed.discard(doc);self.refresh_extra_groups();self.apply_extra_visibility()
    def add_extra_source(self,doc,name,alias,enabled,sheet_id=None,task_type='video'):
        r=self.extra_sources.rowCount();self.extra_sources.insertRow(r)
        for c,value in enumerate((doc,name,alias)):
            item=QTableWidgetItem(value)
            if c<2:item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if c==1:item.setData(Qt.ItemDataRole.UserRole,sheet_id)
            self.extra_sources.setItem(r,c,item)
        check=QTableWidgetItem();check.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable|Qt.ItemFlag.ItemIsSelectable);check.setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked);self.extra_sources.setItem(r,3,check);self.extra_sources.setCellWidget(r,4,self.source_type_combo(task_type));self.refresh_extra_groups()
    def discover_extra_sources(self):
        doc=self.extra_id.text().strip()
        doc=self.normalize_source_id(doc);self.extra_id.setText(doc)
        if not doc or doc==self.source_doc:self.error('请填写与主来源不同的 Spreadsheet ID');return
        def fetch(progress):
            from .workflow import list_sheet_metadata
            sheets,_=google_client.services();return list_sheet_metadata(sheets,doc)
        self.run_job(fetch,lambda tabs:self.show_extra_sources(doc,tabs))
    def show_extra_sources(self,doc,tabs):
        if self.normalize_source_id(self.extra_id.text())!=doc:
            self.statusBar().showMessage('来源 ID 已改变，请重新读取工作表');return
        previous=[]
        for r in range(self.extra_sources.rowCount()):
            if self.extra_sources.item(r,0).text()==doc:
                previous.append({'name':self.extra_sources.item(r,1).text(),'alias':self.extra_sources.item(r,2).text(),'enabled':self.extra_sources.item(r,3).checkState()==Qt.CheckState.Checked,'sheet_id':self.extra_sources.item(r,1).data(Qt.ItemDataRole.UserRole),'task_type':self.extra_sources.cellWidget(r,4).currentData()})
        rows=merge_sources(tabs,previous)
        for r in reversed(range(self.extra_sources.rowCount())):
            if self.extra_sources.item(r,0).text()==doc:self.extra_sources.removeRow(r)
        for row in rows:self.add_extra_source(doc,row['name'],row['alias'],row['enabled'],row['sheet_id'],row['task_type'])
        self.extra_collapsed.discard(doc);self.refresh_extra_groups();self.extra_group.setCurrentIndex(max(0,self.extra_group.findData(doc)));self.apply_extra_visibility()
        for r in range(self.extra_sources.rowCount()):
            if self.extra_sources.item(r,0).text()==doc:self.extra_sources.scrollToItem(self.extra_sources.item(r,0));break
        self.statusBar().showMessage('已读取来源 '+doc+'，请勾选工作表并保存设置')
    def load_register_categories(self):
        doc=self.fields['register_spreadsheet_id'].text().strip()
        if not doc:self.error('请先填写登记表 Spreadsheet ID');return
        self.category_status.setText('正在读取“分类”工作表…')
        def fetch(progress):
            from .registration import read_categories
            sheets,_=google_client.services()
            return read_categories(sheets,doc)
        self.run_job(fetch,lambda options:self.show_register_categories(doc,options))
        if self.jobs:self.jobs[-1].failed.connect(lambda _:self.category_status.setText('分类读取失败，原有选择未修改；请检查 ID、授权及“分类”工作表'))
    def show_register_categories(self,doc,options):
        if self.fields['register_spreadsheet_id'].text().strip()!=doc:
            self.category_status.setText('登记表 ID 已改变，请重新读取分类');return
        self.category_source=doc;self.category_options=options
        self.populate_upload_choices(options)
        for row in range(self.register_mapping.rowCount()):
            key=self.register_mapping.item(row,0).data(Qt.ItemDataRole.UserRole)
            box=self.register_mapping.cellWidget(row,2)
            if box is None:continue
            current=box.currentData();box.clear();box.addItem('','')
            for value in options.get(key,[]):box.addItem(value,value)
            index=box.findData(current)
            if index<0 and current:box.addItem(current+'（不在分类表中，请重新选择）',current);index=box.count()-1
            box.setCurrentIndex(max(index,0))
        for key,box in self.duration_choices.items():
            current=box.currentData();box.clear();box.addItem('','')
            for value in options.get('duration_class',[]):box.addItem(value,value)
            index=box.findData(current)
            if index<0 and current:box.addItem(current+'（不在分类表中，请重新选择）',current);index=box.count()-1
            box.setCurrentIndex(max(index,0))
        self.category_status.setText('已读取分类选项，请选择默认值和时长分类后保存')
    def source_rows(self):
        return [{'name':self.sources.item(r,0).text(),'alias':self.sources.item(r,1).text().strip(),
                 'enabled':self.sources.item(r,2).checkState()==Qt.CheckState.Checked,
                 'sheet_id':self.sources.item(r,0).data(Qt.ItemDataRole.UserRole),'task_type':self.sources.cellWidget(r,3).currentData()} for r in range(self.sources.rowCount())]
    def update_source_summary(self,*args):
        rows=self.source_rows();self.source_summary.setText(f'共 {len(rows)} 个工作表  ·  已勾选 {sum(r["enabled"] for r in rows)} 个  ·  双击别名修改')
    def select_sources(self,enabled):
        for r in range(self.sources.rowCount()):self.sources.item(r,2).setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)
    def auto_discover_sources(self):
        doc=self.fields['source_spreadsheet_id'].text().strip()
        if doc and doc!=self.source_doc and not self.jobs:self.pick_source_sheet()
    def pick_source_sheet(self):
        if self.jobs:self.error('请等待当前操作完成');return
        doc=self.normalize_source_id(self.fields['source_spreadsheet_id'].text());self.fields['source_spreadsheet_id'].setText(doc)
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
        for r in rows:self.add_source(r['name'],r['alias'],r['enabled'],r['sheet_id'],r['task_type'])
        self.sources.blockSignals(False);self.source_doc=doc;self.update_source_summary()
        if missing:self.source_summary.setText(self.source_summary.text()+'；已移除不存在的工作表：'+'、'.join(missing))
        self.statusBar().showMessage('工作表已读取，请勾选保留项、检查别名并保存')
    def source_type_combo(self,value):
        box=QComboBox();box.addItem('视频','video');box.addItem('图片','image');box.setCurrentIndex(max(0,box.findData(value)));return box
    def add_source(self,name='',alias='',enabled=True,sheet_id=None,task_type='video'):
        blocked=self.sources.blockSignals(True);r=self.sources.rowCount();self.sources.insertRow(r)
        title=QTableWidgetItem(name);title.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable);title.setData(Qt.ItemDataRole.UserRole,sheet_id);self.sources.setItem(r,0,title)
        self.sources.setItem(r,1,QTableWidgetItem(alias or suggest_alias(name)))
        check=QTableWidgetItem();check.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable|Qt.ItemFlag.ItemIsSelectable);check.setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked);self.sources.setItem(r,2,check);self.sources.setCellWidget(r,3,self.source_type_combo(task_type));self.sources.blockSignals(blocked)
    def pick_download(self):
        folder=QFileDialog.getExistingDirectory(self,'素材目录',self.fields['download_path'].text())
        if folder:self.fields['download_path'].setText(folder)
    def save(self):
        if self.jobs:self.error('请等待后台操作结束后保存设置');return
        try:
            values={k:w.text().strip() for k,w in self.fields.items()};values['production_layout']=self.production_layout.currentData();values['voice_enabled']=self.voice_enabled.isChecked();values['dark_mode']=self.dark_mode.isChecked();values['sequence_start']=self.sequence_start.value();values['sequence_mode']=self.sequence_mode.currentData();values['sequence_override']=None;values['collapsed_source_ids']=sorted(self.extra_collapsed);values['primary_source_collapsed']=self.sources.isHidden()
            import re
            aliases={};used={normalize(name):key for key,names in ALIASES.items() for name in names}
            for r in range(self.header_mapping.rowCount()):
                key=self.header_mapping.item(r,0).data(Qt.ItemDataRole.UserRole)
                names=[name.strip() for name in re.split('[,，]',self.header_mapping.item(r,1).text()) if name.strip()]
                for name in names:
                    normalized=normalize(name)
                    if normalized in used and used[normalized]!=key:raise ValueError(f'表头名称“{name}”已用于其他字段，请修改以避免写错列')
                    used[normalized]=key
                if names:aliases[key]=names
            values['header_aliases']=aliases
            values['register_columns']={self.register_mapping.item(r,0).data(Qt.ItemDataRole.UserRole):self.register_mapping.item(r,1).text().strip().upper() for r in range(self.register_mapping.rowCount()) if self.register_mapping.item(r,1).text().strip()}
            values['register_defaults']={k:v for k,v in self.cfg.register_defaults.items() if k in ('type','material','software','difficulty')}
            for r in range(self.register_mapping.rowCount()):
                key=self.register_mapping.item(r,0).data(Qt.ItemDataRole.UserRole);box=self.register_mapping.cellWidget(r,2)
                if key=='group':values['register_defaults'][key]=self.register_mapping.item(r,2).text().strip()
                elif box is not None:values['register_defaults'][key]=box.currentData() or ''
            values['register_duration_labels']={key:box.currentData() or '' for key,box in self.duration_choices.items()}
            values['register_category_options']=self.category_options if self.category_source==values['register_spreadsheet_id'] else self.cfg.register_category_options
            if values['register_spreadsheet_id'] and values['register_spreadsheet_id']!=self.cfg.register_spreadsheet_id and self.category_source!=values['register_spreadsheet_id']:
                raise ValueError('登记表 ID 已改变，请先读取分类选项再保存')
            if self.category_source==values['register_spreadsheet_id']:
                for key in ('type','material','software','difficulty'):
                    if values['register_defaults'].get(key) and values['register_defaults'][key] not in self.category_options.get(key,[]):raise ValueError('默认'+key+'不在分类表中，请重新选择')
                if any(value and value not in self.category_options.get('duration_class',[]) for value in values['register_duration_labels'].values()):raise ValueError('时长分类不在分类表中，请重新选择')
            if values['source_spreadsheet_id']!=self.source_doc:raise ValueError('表格 ID 已改变，请先读取工作表再保存')
            rows=self.source_rows();mapping={}
            for row in rows:
                if row['enabled']:
                    if not row['alias']:raise ValueError('已勾选的工作表必须填写别名')
                    if row['name'] in mapping:raise ValueError('工作表名称不能重复')
                    mapping[row['name']]=row['alias']
            values.update(source_sheets=list(mapping),requester_names=mapping,source_catalog=rows)
            names={d.spreadsheet_id:d.display_name for d in source_documents(self.cfg)}
            documents=[{'spreadsheet_id':values['source_spreadsheet_id'],'display_name':names.get(values['source_spreadsheet_id'],''),'sheets':rows}] if values['source_spreadsheet_id'] else []
            extras={}
            for r in range(self.extra_sources.rowCount()):
                doc=self.extra_sources.item(r,0).text().strip();name=self.extra_sources.item(r,1).text().strip();alias=self.extra_sources.item(r,2).text().strip();enabled=self.extra_sources.item(r,3).checkState()==Qt.CheckState.Checked
                if doc==values['source_spreadsheet_id']:raise ValueError('主来源与其他来源的 Spreadsheet ID 重复，请删除重复来源后保存')
                if enabled and not alias:raise ValueError('已启用工作表必须填写需求者别名')
                extras.setdefault(doc,[]).append({'name':name,'alias':alias,'enabled':enabled,'sheet_id':self.extra_sources.item(r,1).data(Qt.ItemDataRole.UserRole),'task_type':self.extra_sources.cellWidget(r,4).currentData()})
            documents.extend({'spreadsheet_id':doc,'display_name':names.get(doc,''),'sheets':entries} for doc,entries in extras.items())
            values['source_documents']=documents
            cfg=type(self.cfg).model_validate(self.cfg.model_dump()|values)
            from .registration import validate
            validate(cfg);save_settings(cfg);self.cfg=cfg;self.claim_start.setValue(cfg.sequence_start);self.loaded([]);self.statusBar().showMessage('设置已保存，请刷新任务')
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

