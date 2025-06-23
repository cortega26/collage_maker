# === Module: workers.py ===
"""
Background workers and batch processing.
"""
from PySide6.QtCore import QRunnable, QObject, Signal, QThreadPool, QThread, Qt
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
