import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
from pathlib import Path

from utils.validation import validate_image_path, validate_output_path
from utils.image_processor import ImageProcessor

ALLOWED_EXTENSIONS = ImageProcessor.VALID_EXTENSIONS

# Se intenta importar tkdnd para drag & drop desde el explorador.
# Si no está disponible, se usará la funcionalidad de doble clic para cargar imágenes.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    USE_DND = True
except ImportError:
    USE_DND = False


class CollageCell(tk.Canvas):
    def __init__(self, master, row, col, width, height, **kwargs):
        super().__init__(master, width=width, height=height, bg='lightgrey',
                         highlightthickness=1, highlightbackground='black', **kwargs)
        self.row = row
        self.col = col
        self.cell_width = width
        self.cell_height = height
        self.image_path = None
        self.original_image = None  # Imagen original (PIL.Image)
        self.processed_image = None  # Imagen ajustada a la celda (PIL.Image)
        self.tk_image = None  # Imagen para Tkinter (ImageTk.PhotoImage)
        # Mensaje por defecto
        self.create_text(self.cell_width/2, self.cell_height/2,
                         text="Drop image here", fill="black")
        # Si se hace doble clic se abre un diálogo para cargar la imagen
        self.bind("<Double-Button-1>", self.load_image_dialog)
        # Si está disponible el drag & drop desde el explorador se registra el widget como destino
        if USE_DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self.handle_drop)
        # Para rearranjar imágenes dentro del collage se implementa drag & drop interno
        self.bind("<ButtonPress-1>", self.on_drag_start)
        self.bind("<B1-Motion>", self.on_drag_motion)
        self.bind("<ButtonRelease-1>", self.on_drag_release)
        self.drag_data = {"x": 0, "y": 0, "item": None}

    def load_image_dialog(self, event=None):
        file_path = filedialog.askopenfilename(
            filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.webp;*.bmp")])
        if file_path:
            self.load_image(file_path)

    def handle_drop(self, event):
        # El valor event.data puede incluir llaves si el path contiene espacios.
        file_path = event.data
        if file_path.startswith("{") and file_path.endswith("}"):
            file_path = file_path[1:-1]
        self.load_image(file_path)
        return event.action

    def load_image(self, file_path):
        try:
            safe_path = validate_image_path(file_path, ALLOWED_EXTENSIONS)
            image = Image.open(safe_path)
            self.image_path = str(safe_path)
            self.original_image = image
            self.process_and_display_image()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cargar la imagen:\n{e}")

    def process_and_display_image(self):
        if not self.original_image:
            return
        img = self.original_image
        # Se desea que la imagen se ajuste a la celda sin stretching.
        # Se calcula el factor de escalado que permita encajar la imagen dentro de la celda.
        cell_w, cell_h = self.cell_width, self.cell_height
        ratio = min(cell_w / img.width, cell_h / img.height)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        # Use modern resampling for high-quality results
        resized_img = img.resize(new_size, Image.Resampling.LANCZOS)
        # Se crea una imagen en blanco del tamaño de la celda (letterboxing)
        new_img = Image.new("RGB", (cell_w, cell_h), (255, 255, 255))
        paste_x = (cell_w - new_size[0]) // 2
        paste_y = (cell_h - new_size[1]) // 2
        new_img.paste(resized_img, (paste_x, paste_y))
        self.processed_image = new_img
        # Se genera la imagen para mostrar en Tkinter
        self.tk_image = ImageTk.PhotoImage(new_img)
        self.delete("all")
        self.create_image(cell_w/2, cell_h/2, image=self.tk_image)

    # Métodos para drag & drop interno (rearranjo)
    def on_drag_start(self, event):
        if self.processed_image:
            self.drag_data["item"] = self
            self.drag_data["x"] = event.x
            self.drag_data["y"] = event.y

    def on_drag_motion(self, event):
        # Aquí se podría mostrar una imagen fantasma para feedback visual.
        pass

    def on_drag_release(self, event):
        # Se determina el widget sobre el cual se soltó la imagen.
        widget = self.master.winfo_containing(event.x_root, event.y_root)
        if widget and isinstance(widget, CollageCell) and widget != self:
            self.swap_with(widget)
        self.drag_data = {"x": 0, "y": 0, "item": None}

    def swap_with(self, other_cell):
        # Se intercambian las imágenes y datos asociados entre dos celdas.
        self.image_path, other_cell.image_path = other_cell.image_path, self.image_path
        self.original_image, other_cell.original_image = other_cell.original_image, self.original_image
        self.processed_image, other_cell.processed_image = other_cell.processed_image, self.processed_image
        self.tk_image, other_cell.tk_image = other_cell.tk_image, self.tk_image
        self.redraw()
        other_cell.redraw()

    def redraw(self):
        self.delete("all")
        if self.tk_image:
            self.create_image(self.cell_width/2,
                              self.cell_height/2, image=self.tk_image)
        else:
            self.create_text(self.cell_width/2, self.cell_height/2,
                             text="Drop image here", fill="black")


class CollageMakerApp(tk.Tk if not USE_DND else TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("Collage Maker")
        # Parámetros por defecto
        self.rows = 2
        self.cols = 2
        self.cell_width = 200
        self.cell_height = 200
        self.cells = []
        self.selected_format = tk.StringVar(value="PNG")
        self.create_widgets()

    def create_widgets(self):
        # Frame superior de controles
        control_frame = tk.Frame(self)
        control_frame.pack(side="top", fill="x", padx=5, pady=5)

        tk.Label(control_frame, text="Filas:").pack(side="left")
        self.rows_var = tk.IntVar(value=self.rows)
        tk.Spinbox(control_frame, from_=1, to=10, width=3,
                   textvariable=self.rows_var).pack(side="left")

        tk.Label(control_frame, text="Columnas:").pack(side="left")
        self.cols_var = tk.IntVar(value=self.cols)
        tk.Spinbox(control_frame, from_=1, to=10, width=3,
                   textvariable=self.cols_var).pack(side="left")

        tk.Label(control_frame, text="Ancho celda:").pack(side="left")
        self.cell_width_var = tk.IntVar(value=self.cell_width)
        tk.Spinbox(control_frame, from_=50, to=500, width=4,
                   textvariable=self.cell_width_var).pack(side="left")

        tk.Label(control_frame, text="Alto celda:").pack(side="left")
        self.cell_height_var = tk.IntVar(value=self.cell_height)
        tk.Spinbox(control_frame, from_=50, to=500, width=4,
                   textvariable=self.cell_height_var).pack(side="left")

        tk.Button(control_frame, text="Crear Collage",
                  command=self.build_collage_grid).pack(side="left", padx=5)

        tk.Label(control_frame, text="Formato salida:").pack(side="left")
        format_option = ttk.Combobox(control_frame, textvariable=self.selected_format,
                                     values=["PNG", "WEBP"], width=5, state="readonly")
        format_option.pack(side="left")

        tk.Button(control_frame, text="Guardar Collage",
                  command=self.save_collage).pack(side="left", padx=5)

        # Frame principal para el grid del collage
        self.grid_frame = tk.Frame(self)
        self.grid_frame.pack(side="top", fill="both",
                             expand=True, padx=5, pady=5)

        self.build_collage_grid()

    def build_collage_grid(self):
        # Se limpia el grid previo
        for widget in self.grid_frame.winfo_children():
            widget.destroy()
        self.cells = []
        self.rows = self.rows_var.get()
        self.cols = self.cols_var.get()
        self.cell_width = self.cell_width_var.get()
        self.cell_height = self.cell_height_var.get()
        for r in range(self.rows):
            row_cells = []
            for c in range(self.cols):
                cell = CollageCell(self.grid_frame, r, c,
                                   self.cell_width, self.cell_height)
                cell.grid(row=r, column=c, padx=2, pady=2)
                row_cells.append(cell)
            self.cells.append(row_cells)

    def save_collage(self):
        # Se genera la imagen final combinando las imágenes de cada celda
        collage_width = self.cols * self.cell_width
        collage_height = self.rows * self.cell_height
        collage_img = Image.new(
            "RGB", (collage_width, collage_height), (255, 255, 255))
        for r, row_cells in enumerate(self.cells):
            for c, cell in enumerate(row_cells):
                if cell.processed_image:
                    collage_img.paste(
                        cell.processed_image, (c * self.cell_width, r * self.cell_height))
        # Diálogo para guardar, permitiendo elegir PNG o webp
        filetypes = [("PNG", "*.png"), ("WebP", "*.webp")]
        # Prefer a stable, real filesystem path (avoids localized alias issues)
        pictures = Path.home() / "Pictures"
        initial_dir = str(pictures if pictures.exists() else Path.home())
        file_path = filedialog.asksaveasfilename(
            title="Guardar Collage",
            defaultextension="." + self.selected_format.get().lower(),
            filetypes=filetypes,
            initialdir=initial_dir
        )
        if file_path:
            try:
                safe_path = validate_output_path(file_path, {'.png', '.webp'})
                fmt = self.selected_format.get().upper()
                collage_img.save(str(safe_path), fmt)
                messagebox.showinfo(
                    "Guardado", "Collage guardado exitosamente.")
            except Exception as e:
                messagebox.showerror(
                    "Error", f"No se pudo guardar el collage:\n{e}")


if __name__ == "__main__":
    app = CollageMakerApp()
    app.mainloop()
