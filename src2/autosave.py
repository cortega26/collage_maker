# === Module: autosave.py ===
"""
Automatic state saving.
"""
import os, json, glob
import logging
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
