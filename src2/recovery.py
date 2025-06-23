# === Module: recovery.py ===
"""
Error counting and recovery.
"""
import json, os, traceback
import logging
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
