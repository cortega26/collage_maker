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
from PySide6.QtGui import QKeySequence, QPixmap, QPainter, QImage
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
        path,_=QFileDialog.getSaveFileName(self, "Save To","", f"{fmt.currentText().upper()} Files (*.{fmt.currentText()})")
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
