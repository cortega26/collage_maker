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