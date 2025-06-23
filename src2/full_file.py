# === Module: cache.py ===
"""
Thread-safe LRU cache for QPixmap objects.
"""
import threading
from typing import Optional, Tuple, Dict, List
from PySide6.QtGui import QPixmap

class ImageCache:
    def __init__(self, max_size: int = 50, cleanup_threshold: float = 0.8):
        self._cache: Dict[str, Tuple[QPixmap, dict]] = {}
        self._order: List[str] = []
        self.max_size = max_size
        self.cleanup_threshold = cleanup_threshold
        self._lock = threading.Lock()

    def get(self, key: str) -> Tuple[Optional[QPixmap], Optional[dict]]:
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None, None
            # Move to most recently used
            self._order.remove(key)
            self._order.append(key)
            return entry

    def put(self, key: str, pixmap: QPixmap, metadata: dict) -> None:
        with self._lock:
            if key in self._cache:
                self._order.remove(key)
            elif len(self._cache) >= self.max_size * self.cleanup_threshold:
                self._cleanup()
            self._cache[key] = (pixmap, metadata)
            self._order.append(key)

    def _cleanup(self) -> None:
        # Evict oldest until size <= max_size/2
        target = max(self.max_size // 2, 1)
        while len(self._cache) > target:
            oldest = self._order.pop(0)
            del self._cache[oldest]

# Global instance
image_cache = ImageCache()


# === Module: optimizer.py ===
"""
Image optimization and metadata extraction.
"""
from PySide6.QtGui import QImageReader, QImage
from PySide6.QtCore import QSize, QFileInfo, Qt

class ImageOptimizer:
    @staticmethod
    def optimize_image(image: QImage, target_size: QSize) -> QImage:
        # Ensure ARGB32 for quality
        if image.format() != QImage.Format_ARGB32:
            image = image.convertToFormat(QImage.Format_ARGB32)
        # Scale if too large
        max_dim = max(target_size.width(), target_size.height())
        if max_dim > 2000:
            scale = 2000 / max_dim
            target_size = QSize(int(target_size.width() * scale), int(target_size.height() * scale))
        if image.size() != target_size:
            image = image.scaled(target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return image

    @staticmethod
    def extract_metadata(file_path: str) -> dict:
        reader = QImageReader(file_path)
        info = QFileInfo(file_path)
        size = reader.size()
        return {
            'size': (size.width(), size.height()),
            'format': reader.format().data().decode(),
            'supported': reader.canRead(),
            'modified': info.lastModified().toString()
        }


# === Module: cell.py ===
"""
Defines CollageCell: individual grid cell with drag-drop, image loading, caption.
"""
from PySide6.QtWidgets import QWidget, QMessageBox, QInputDialog
from PySide6.QtGui import QPixmap, QPainter, QColor, QDrag
from PySide6.QtCore import Qt, QMimeData, QByteArray, QDataStream, QIODevice, QRect, QSize, QPoint

from cache import image_cache
from optimizer import ImageOptimizer

class ImageMimeData(QMimeData):
    def __init__(self, pixmap: QPixmap, source_widget: "CollageCell"):
        super().__init__()
        self._pixmap = pixmap
        self.source_widget = source_widget
        ba = QByteArray()
        stream = QDataStream(ba, QIODevice.WriteOnly)
        stream << pixmap.toImage()
        self.setData("application/x-pixmap", ba)

    def image(self) -> QPixmap:
        return self._pixmap

class CollageCell(QWidget):
    def __init__(self, cell_id: int, cell_size: int, parent=None):
        super().__init__(parent)
        self.cell_id = cell_id
        self.setAcceptDrops(True)
        self.setFixedSize(cell_size, cell_size)
        self.pixmap: QPixmap = None
        self.original_pixmap: QPixmap = None
        self.caption: str = ""
        self.selected: bool = False

    def set_image(self, pixmap: QPixmap):
        self.original_pixmap = pixmap
        self.pixmap = pixmap
        self.update()

    def clear_image(self):
        self.pixmap = None
        self.original_pixmap = None
        self.caption = ""
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing
        )
        rect = self.rect()
        if self.selected:
            pen = painter.pen()
            pen.setColor(QColor(52, 152, 219))
            pen.setWidth(3)
            painter.setPen(pen)
            painter.drawRect(rect.adjusted(1,1,-1,-1))
        if self.pixmap:
            scaled = self.pixmap.scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (rect.width() - scaled.width()) // 2
            y = (rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            if self.caption:
                font = painter.font()
                font.setPointSize(12)
                painter.setFont(font)
                painter.setPen(Qt.white)
                painter.drawText(rect.adjusted(4,4,-4,-4), Qt.AlignBottom|Qt.AlignHCenter, self.caption)
        else:
            painter.fillRect(rect, QColor(245,245,245))
            painter.setPen(QColor(180,180,180))
            painter.drawText(rect, Qt.AlignCenter, "Drop Image Here")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.selected and event.modifiers() == Qt.ControlModifier:
                self.selected = False
                self.update()
                return
            if event.modifiers() == Qt.ControlModifier:
                self.selected = True
                self.update()
                return
            if self.pixmap:
                drag = QDrag(self)
                mime = ImageMimeData(self.pixmap, self)
                drag.setMimeData(mime)
                preview = self.pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                drag.setPixmap(preview)
                drag.exec(Qt.MoveAction)

    def mouseDoubleClickEvent(self, event):
        if self.pixmap:
            text, ok = QInputDialog.getText(self, "Edit Caption", "Caption:", text=self.caption)
            if ok:
                self.caption = text
                self.update()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-pixmap"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat("application/x-pixmap"):
            src = mime.source_widget
            if src and src is not self:
                # swap
                self.pixmap, src.pixmap = src.pixmap, self.pixmap
                self.original_pixmap, src.original_pixmap = src.original_pixmap, self.original_pixmap
                self.caption, src.caption = src.caption, self.caption
                self.update(); src.update()
                event.acceptProposedAction()
                return
        if mime.hasUrls():
            path = mime.urls()[0].toLocalFile()
            self._load_external(path)
            event.acceptProposedAction()
            return
        event.ignore()

    def _load_external(self, path: str):
        try:
            pix, _ = image_cache.get(path)
            if pix:
                self.set_image(pix)
                return
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            img = reader.read()
            if img.isNull():
                raise ValueError(reader.errorString())
            optimized = ImageOptimizer.optimize_image(img, self.size())
            pixmap = QPixmap.fromImage(optimized)
            self.set_image(pixmap)
            meta = ImageOptimizer.extract_metadata(path)
            image_cache.put(path, pixmap, meta)
        except Exception as e:
            QMessageBox.warning(self, "Load Error", str(e))

    def cleanup(self):
        self.pixmap = None
        self.original_pixmap = None

    def optimize_memory(self):
        # placeholder for memory reduce logic
        pass

    def batch_process_images(self, paths: list[str]):
        from workers import BatchProcessor
        BatchProcessor(self).process_files(paths, self.size())


# === Module: widget.py ===
"""
Defines CollageWidget: grid management, merging/splitting, animations.
"""
from PySide6.QtWidgets import QWidget, QGridLayout
from PySide6.QtCore import QSize, QRect, QPoint
from PySide6.QtGui import QPropertyAnimation, QParallelAnimationGroup, QEasingCurve

from cell import CollageCell

class CollageWidget(QWidget):
    def __init__(self, rows=2, cols=2, cell_size=260, parent=None):
        super().__init__(parent)
        self.rows = rows; self.cols = cols; self.cell_size = cell_size
        self.merged: dict[tuple[int,int], tuple[int,int]] = {}
        self.layout = QGridLayout(self)
        self.layout.setSpacing(2); self.layout.setContentsMargins(0,0,0,0)
        self.cells: list[CollageCell] = []
        self.populate_grid()

    def populate_grid(self):
        # clear existing
        for i in reversed(range(self.layout.count())):
            w = self.layout.itemAt(i).widget()
            if w:
                w.setParent(None)
        self.cells.clear()
        # create
        for r in range(self.rows):
            for c in range(self.cols):
                idx = r*self.cols + c + 1
                cell = CollageCell(idx, self.cell_size, self)
                self.layout.addWidget(cell, r, c)
                self.cells.append(cell)
        self.setFixedSize(self.sizeHint())

    def sizeHint(self) -> QSize:
        w = self.cols*self.cell_size + (self.cols-1)*self.layout.spacing()
        h = self.rows*self.cell_size + (self.rows-1)*self.layout.spacing()
        return QSize(w,h)

    def get_cell_position(self, cell: CollageCell) -> tuple[int,int] | None:
        idx = self.layout.indexOf(cell)
        if idx < 0: return None
        r,c,rs,cs = self.layout.getItemPosition(idx)
        return (r,c)

    def merge_cells(self, start_row: int, start_col: int, row_span: int, col_span: int) -> bool:
        # split overlapping
        for (mr,mc),(mrs,mcs) in list(self.merged.items()):
            if (mr < start_row+row_span and mr+mrs > start_row and
                mc < start_col+col_span and mc+mcs > start_col):
                self.split_merged_cell(mr,mc)
        # collect
        target = self.get_cell_at(start_row, start_col)
        if not target: return False
        to_merge = [self.get_cell_at(r,c) for r in range(start_row, start_row+row_span)
                    for c in range(start_col, start_col+col_span)
                    if not (r==start_row and c==start_col)]
        for cell in to_merge:
            self.layout.removeWidget(cell); cell.hide(); self.cells.remove(cell)
        self.layout.removeWidget(target)
        self.layout.addWidget(target, start_row, start_col, row_span, col_span)
        target.setFixedSize(
            self.cell_size*col_span + (col_span-1)*self.layout.spacing(),
            self.cell_size*row_span + (row_span-1)*self.layout.spacing()
        )
        self.merged[(start_row,start_col)] = (row_span, col_span)
        self.setFixedSize(self.sizeHint())
        return True

    def split_merged_cell(self, row: int, col: int) -> bool:
        if (row,col) not in self.merged: return False
        row_span, col_span = self.merged.pop((row,col))
        # find merged cell
        merged_cell = self.get_cell_at(row,col)
        pix = merged_cell.pixmap; cap = merged_cell.caption; sel = merged_cell.selected
        self.layout.removeWidget(merged_cell); merged_cell.hide(); self.cells.remove(merged_cell)
        # recreate
        for r in range(row, row+row_span):
            for c in range(col, col+col_span):
                cell = CollageCell(r*self.cols+c+1, self.cell_size, self)
                if r==row and c==col:
                    if pix: cell.set_image(pix)
                    cell.caption = cap; cell.selected = sel
                self.layout.addWidget(cell, r, c)
                self.cells.append(cell)
        self.setFixedSize(self.sizeHint())
        return True

    def get_cell_at(self, row: int, col: int) -> CollageCell | None:
        for i in range(self.layout.count()):
            item = self.layout.itemAt(i); w = item.widget()
            if w:
                r,c,rs,cs = self.layout.getItemPosition(i)
                if r==row and c==col:
                    return w
        return None

    def merge_selected(self):
        pos = [self.get_cell_position(c) for c in self.cells if c.selected]
        if len(pos)<2: return
        rows = [p[0] for p in pos]; cols=[p[1] for p in pos]
        minr,maxr = min(rows), max(rows); minc,maxc=min(cols),max(cols)
        if (maxr-minr+1)*(maxc-minc+1) != len(pos): return
        self.merge_cells(minr,minc,maxr-minr+1, maxc-minc+1)
        for c in self.cells: c.selected=False; c.update()

    def split_selected(self):
        for cell in self.cells:
            if cell.selected:
                pos = self.get_cell_position(cell)
                if pos and pos in self.merged:
                    self.split_merged_cell(*pos)
                    break

    def animate_swap(self, src: CollageCell, tgt: CollageCell):
        sp = src.mapTo(self, QPoint(0,0)); tp = tgt.mapTo(self, QPoint(0,0))
        lab1=src.pixmap and QLabel(self); lab2=tgt.pixmap and QLabel(self)
        if lab1: lab1.setPixmap(src.pixmap);
        if lab2: lab2.setPixmap(tgt.pixmap)
        # ... animation omitted for brevity

    def sanitize_positions(self):
        # ensure consistency
        pass


# === Module: undo.py ===
"""
Undo/Redo command pattern.
"""
from typing import List

class UndoCommand:
    def undo(self): pass
    def redo(self): pass

class ImageSwapCommand(UndoCommand):
    def __init__(self, src, tgt):
        self.src, self.tgt = src, tgt
        self.src_state=(src.pixmap, src.caption)
        self.tgt_state=(tgt.pixmap, tgt.caption)
    def undo(self):
        self.src.pixmap,self.src.caption=self.src_state
        self.tgt.pixmap,self.tgt.caption=self.tgt_state
        self.src.update(); self.tgt.update()
    def redo(self):
        self.src.pixmap,self.src.caption=self.tgt_state
        self.tgt.pixmap,self.tgt.caption=self.src_state
        self.src.update(); self.tgt.update()

class UndoStack:
    def __init__(self):
        self._undo: List[UndoCommand] = []
        self._redo: List[UndoCommand] = []
    def push(self, cmd: UndoCommand):
        cmd.redo(); self._undo.append(cmd); self._redo.clear()
    def undo(self):
        if self._undo: cmd=self._undo.pop(); cmd.undo(); self._redo.append(cmd)
    def redo(self):
        if self._redo: cmd=self._redo.pop(); cmd.redo(); self._undo.append(cmd)
    def clear(self): self._undo.clear(); self._redo.clear()


# === Module: workers.py ===
"""
Background workers and batch processing.
"""
from PySide6.QtCore import QRunnable, QObject, Signal, QThreadPool, QThread
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import QProgressDialog, QMessageBox
from optimizer import ImageOptimizer
from cache import image_cache

class WorkerSignals(QObject):
    started = Signal(); finished = Signal(); error = Signal(str)
    progress = Signal(int); result = Signal(object)

class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = WorkerSignals()
    def run(self):
        self.signals.started.emit()
        try:
            res = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(res)
        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()

class TaskQueue:
    def __init__(self, max_concurrent:int=4):
        self.pool = QThreadPool.globalInstance(); self.pool.setMaxThreadCount(max_concurrent)
        self.queue = []
    def add(self, task: QRunnable, priority:int=0):
        self.queue.append((priority,task)); self.queue.sort(key=lambda x: -x[0])
        self._process()
    def _process(self):
        if self.queue:
            _,task=self.queue.pop(0); self.pool.start(task)
    def clear(self): self.queue.clear()

class ImageLoadWorker(QThread):
    finished = Signal(QPixmap,str); error=Signal(str); progress=Signal(int)
    def __init__(self, paths, target_size=None):
        super().__init__(); self.paths=paths; self.target=target_size; self._cancel=False
    def run(self):
        total=len(self.paths)
        for i,p in enumerate(self.paths):
            if self._cancel: return
            self.progress.emit(int(i/total*100))
            reader=QImageReader(p); reader.setAutoTransform(True)
            if self.target: reader.setScaledSize(self.target)
            img=reader.read()
            if img.isNull(): self.error.emit(reader.errorString()); continue
            if self.target: img=ImageOptimizer.optimize_image(img,self.target)
            pm=QPixmap.fromImage(img)
            self.finished.emit(pm,p)
        self.progress.emit(100)
    def cancel(self): self._cancel=True

class BatchProcessor:
    def __init__(self, parent):
        self.parent=parent; self.worker=None
    def process_files(self, paths, target_size=None):
        dlg=QProgressDialog("Processing...","Cancel",0,len(paths),self.parent)
        dlg.setWindowModality(Qt.WindowModal)
        self.worker=ImageLoadWorker(paths,target_size)
        self.worker.progress.connect(dlg.setValue)
        self.worker.finished.connect(self._on_done)
        self.worker.error.connect(self._on_error)
        dlg.canceled.connect(self.worker.cancel)
        self.worker.start(); dlg.exec()
    def _on_done(self, pm, path):
        meta=ImageOptimizer.extract_metadata(path)
        image_cache.put(path,pm,meta)
    def _on_error(self,msg):
        QMessageBox.warning(self.parent, "Batch Error", msg)


# === Module: autosave.py ===
"""
Automatic state saving.
"""
import os, json, glob
from PySide6.QtCore import QTimer, QDateTime

class AutosaveManager:
    def __init__(self, parent, interval_ms=5*60*1000, keep=5):
        self.parent=parent; self.interval=interval_ms; self.keep=keep
        self.dir=os.path.join(os.getcwd(),"autosave"); os.makedirs(self.dir,exist_ok=True)
        self.timer=QTimer(self); self.timer.timeout.connect(self.save)
    def start(self): self.timer.start(self.interval)
    def stop(self): self.timer.stop()
    def save(self):
        try:
            state=self.parent.get_collage_state()
            ts=QDateTime.currentDateTime().toString("yyyyMMdd_HHmmss")
            fp=os.path.join(self.dir,f"autosave_{ts}.json")
            with open(fp,'w') as f: json.dump(state,f)
            # cleanup
            files=sorted(glob.glob(os.path.join(self.dir,"autosave_*.json")), reverse=True)
            for old in files[self.keep:]: os.remove(old)
        except Exception as e:
            logging.error(f"Autosave failed: {e}")
    def get_latest(self):
        files=glob.glob(os.path.join(self.dir,"autosave_*.json"))
        return max(files,key=os.path.getctime) if files else None


# === Module: recovery.py ===
"""
Error counting and recovery.
"""
import json, os, traceback
from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import QDateTime

class ErrorRecoveryManager:
    def __init__(self, parent, threshold=5, window_s=300):
        self.parent=parent; self.threshold=threshold; self.window=window_s
        self.count=0; self.last=QDateTime.currentDateTime()
    def handle(self, error:Exception, context:str):
        now=QDateTime.currentDateTime()
        if self.last.secsTo(now)>self.window: self.count=0
        self.count+=1; self.last=now
        logging.error(f"Error {context}: {error}\n{traceback.format_exc()}")
        if self.count>=self.threshold: self.recover()
    def recover(self):
        try:
            state=self.parent.get_collage_state()
            ts=QDateTime.currentDateTime().toString("yyyyMMdd_HHmmss")
            fp=os.path.join(self.parent.autosave.dir,f"recovery_{ts}.json")
            with open(fp,'w') as f: json.dump(state,f)
            self.parent.collage.populate_grid()
            image_cache._cache.clear(); image_cache._order.clear()
            QMessageBox.warning(self.parent, "Recovery", "Recovered from errors; state saved.")
        except Exception as e:
            QMessageBox.critical(self.parent, "Recovery Failed", str(e))


# === Module: performance.py ===
"""
Memory and resource monitoring.
"""
import gc
from cache import image_cache
try: import psutil; HAS_PSUTIL=True
except ImportError: HAS_PSUTIL=False

class PerformanceMonitor:
    def __init__(self, threshold=500*1024*1024, interval=300):
        self.threshold=threshold; self.interval=interval
        self.last=0
    def check(self):
        if not HAS_PSUTIL: return
        mem=psutil.Process().memory_info().rss
        if mem>self.threshold:
            gc.collect(); image_cache._cleanup(); logging.info("Memory optimized")


# === Module: main.py ===
"""
Main application integrating all components.
"""
import sys, os, json
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSpinBox, QPushButton, QCheckBox, QComboBox, QSlider,
    QDialog, QDialogButtonBox, QFileDialog, QMessageBox, QShortcut
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from widget import CollageWidget
from undo import UndoStack
from autosave import AutosaveManager
from recovery import ErrorRecoveryManager
from performance import PerformanceMonitor
from workers import BatchProcessor
from cache import image_cache

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Collage Maker - Refactored")
        self.undo_stack=UndoStack()
        self.performance=PerformanceMonitor()
        self.recovery=ErrorRecoveryManager(self)
        self.autosave=AutosaveManager(self)
        self._init_ui()
        self.autosave.start()
        self.batch=BatchProcessor(self)

    def _init_ui(self):
        men=self.menuBar().addMenu("File")
        save_act=men.addAction("Save Collage..."); save_act.triggered.connect(self.save_collage)
        save_orig=men.addAction("Save Original Collage..."); save_orig.triggered.connect(self.save_original_collage)
        QShortcut(QKeySequence.Save, self, self.save_collage)
        QShortcut("Ctrl+Shift+S", self, self.save_original_collage)

        w=QWidget(); self.setCentralWidget(w)
        v=QVBoxLayout(w)
        # controls
        ctr=QHBoxLayout()
        ctr.addWidget(QLabel("Rows:")); self.rows=QSpinBox(); self.rows.setValue(2)
        ctr.addWidget(self.rows)
        ctr.addWidget(QLabel("Cols:")); self.cols=QSpinBox(); self.cols.setValue(2)
        ctr.addWidget(self.cols)
        upd=QPushButton("Update Grid"); upd.clicked.connect(self.update_grid)
        ctr.addWidget(upd)
        merge=QPushButton("Merge"); merge.clicked.connect(self.collage.merge_selected)
        ctr.addWidget(merge)
        split=QPushButton("Split"); split.clicked.connect(self.collage.split_selected)
        ctr.addWidget(split)
        import_btn=QPushButton("Batch Import"); import_btn.clicked.connect(self.handle_batch)
        ctr.addWidget(import_btn)
        v.addLayout(ctr)
        # collage
        self.collage=CollageWidget(self.rows.value(), self.cols.value(), 260)
        v.addWidget(self.collage, alignment=Qt.AlignCenter)

    def update_grid(self):
        self.collage.rows=self.rows.value(); self.collage.cols=self.cols.value()
        self.collage.populate_grid()

    def handle_batch(self):
        files,_=QFileDialog.getOpenFileNames(self, "Select Images","","Images (*.png *.jpg *.bmp)")
        if files: self.batch.process_files(files, None)

    def save_collage(self):
        opts=self._show_save_dialog(default_orig=False)
        if not opts: return
        pm=self._generate_collage_pixmap(opts['res'])
        self._save_pixmap(pm, opts['fmt'], opts['quality'], opts['path'])
        if opts['original']: self._save_original(opts)

    def save_original_collage(self):
        opts=self._show_save_dialog(default_orig=True)
        if not opts: return
        self._save_original(opts)

    def _show_save_dialog(self, default_orig=False):
        dlg=QDialog(self); dlg.setWindowTitle("Save Options")
        lay=QVBoxLayout(dlg)
        chk=QCheckBox("Also save original-resolution collage"); chk.setChecked(default_orig)
        lay.addWidget(chk)
        fmt=QComboBox(); fmt.addItems(["png","jpg","webp"]); lay.addWidget(fmt)
        qsl=QSlider(Qt.Horizontal); qsl.setRange(1,100); qsl.setValue(95); lay.addWidget(qsl)
        res=QComboBox(); res.addItems(["1","2","4"]); lay.addWidget(res)
        bb=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); lay.addWidget(bb)
        if dlg.exec()!=QDialog.Accepted: return None
        path,_=FFileDialog.getSaveFileName(self, "Save To","", f"{fmt.currentText().upper()} Files (*.{fmt.currentText()})")
        if not path: return None
        return {'path':path, 'fmt':fmt.currentText(), 'quality':qsl.value(), 'res':int(res.currentText()), 'original':chk.isChecked()}

    def _generate_collage_pixmap(self, scale:int):
        size=self.collage.size(); out=size*scale
        pm=QPixmap(out); pm.fill(Qt.transparent)
        p=QPainter(pm); p.scale(scale,scale); self.collage.render(p); p.end()
        return pm

    def _generate_original_pixmap(self):
        # full original stitching
        cell_sz=self.collage.cell_size; sp=self.collage.layout.spacing()
        w=self.collage.cols*(cell_sz+sp)-sp; h=self.collage.rows*(cell_sz+sp)-sp
        pm=QPixmap(w,h); pm.fill(Qt.transparent)
        p=QPainter(pm)
        for idx,cell in enumerate(self.collage.cells):
            if cell.original_pixmap:
                r=idx//self.collage.cols; c=idx%self.collage.cols
                x=c*(cell_sz+sp); y=r*(cell_sz+sp)
                p.drawPixmap(x,y,cell.original_pixmap)
        p.end(); return pm

    def _save_pixmap(self, pix, fmt, quality, path):
        ext=fmt.lower();
        if not path.lower().endswith(f".{ext}"): path+=f".{ext}"
        if fmt in ['jpg','jpeg']: pix=self._convert_jpeg(pix)
        if not pix.save(path, fmt.upper(), quality): raise IOError(f"Failed to save {path}")
        QMessageBox.information(self, "Saved", f"Saved to {path}")

    def _convert_jpeg(self, pix):
        img=pix.toImage()
        if img.hasAlphaChannel():
            bg=QImage(img.size(),QImage.Format_RGB32); bg.fill(Qt.white)
            p=QPainter(bg); p.drawImage(0,0,img); p.end(); return QPixmap.fromImage(bg)
        return pix

    def _save_original(self, opts):
        pm=self._generate_original_pixmap()
        op=opts['path']; base,ext=os.path.splitext(op)
        out=base+"_original.png"
        pm.save(out, 'PNG'); QMessageBox.information(self, "Saved", f"Original saved to {out}")

    def get_collage_state(self):
        # serialize grid, cells, merges, settings
        state={'rows':self.collage.rows,'cols':self.collage.cols,'cells':[],'merged':self.collage.merged}
        for cell in self.collage.cells:
            c={'id':cell.cell_id,'caption':cell.caption,'selected':cell.selected}
            if cell.pixmap:
                # TODO: serialize images to temp files
                c['has_image']=True
            state['cells'].append(c)
        return state

if __name__=='__main__':
    app=QApplication(sys.argv); w=MainWindow(); w.show(); sys.exit(app.exec())
