import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import os
import sys

# Import your script
# Note: Ensure mapgen.py is in utils/mapgen/ or your PYTHONPATH
try:
    from utils.mapgen import mapgen
except ImportError:
    # If it's in the same folder, just use: import mapgen
    import mapgen

class StreamToTkinter:
    """Redirects stdout/stderr to a Tkinter text widget."""
    def __init__(self, log_func):
        self.log_func = log_func

    def write(self, str):
        if str.strip(): # Avoid logging empty newlines
            self.log_func(str.strip())

    def flush(self):
        pass

class MapGenApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Map Generator GUI")
        self.root.geometry("700x600")
        
        style = ttk.Style()
        style.theme_use('clam')
        
        self.use_reuse_tsv = tk.BooleanVar(value=False)
        self.reuse_tsv_path = tk.StringVar()
        self.is_running = False

        self._init_ui()

    def _init_ui(self):
        # === 1. Configuration ===
        config_frame = ttk.LabelFrame(self.root, text="Settings", padding=10)
        config_frame.pack(fill="x", padx=10, pady=5)

        cb = ttk.Checkbutton(config_frame, text="Reuse Existing Database (TSV)", 
                             variable=self.use_reuse_tsv, command=self.toggle_tsv_input)
        cb.grid(row=0, column=0, sticky="w", columnspan=3)

        self.lbl_tsv = ttk.Label(config_frame, text="TSV Path:", state="disabled")
        self.lbl_tsv.grid(row=1, column=0, sticky="w", pady=5)
        
        self.ent_tsv = ttk.Entry(config_frame, textvariable=self.reuse_tsv_path, width=50, state="disabled")
        self.ent_tsv.grid(row=1, column=1, padx=5, pady=5)
        
        self.btn_tsv = ttk.Button(config_frame, text="Browse", command=self.browse_tsv, state="disabled")
        self.btn_tsv.grid(row=1, column=2, pady=5)

        # === 2. Action Buttons ===
        btn_frame = ttk.Frame(self.root, padding=10)
        btn_frame.pack(fill="x")
        
        self.run_btn = ttk.Button(btn_frame, text="GENERATE MAP", command=self.start_processing)
        self.run_btn.pack(side="left", fill="x", expand=True, padx=5)
        
        ttk.Button(btn_frame, text="Clear Log", command=self.clear_log).pack(side="right", padx=5)

        # === 3. Console Output ===
        log_frame = ttk.LabelFrame(self.root, text="Process Output", padding=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, state='disabled', height=15, 
                                                 bg="#1e1e1e", fg="#00ff00", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)
        self.log_text.tag_config("INFO", foreground="#00ff00")
        self.log_text.tag_config("ERROR", foreground="#ff5555")

    def toggle_tsv_input(self):
        state = "normal" if self.use_reuse_tsv.get() else "disabled"
        self.lbl_tsv.config(state=state)
        self.ent_tsv.config(state=state)
        self.btn_tsv.config(state=state)

    def browse_tsv(self):
        f = filedialog.askopenfilename(filetypes=[("TSV Files", "*.tsv")])
        if f: self.reuse_tsv_path.set(f)

    def log(self, message, level="INFO"):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n", level)
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def clear_log(self):
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')

    def start_processing(self):
        if self.is_running: return
        self.is_running = True
        self.run_btn.config(state="disabled", text="Running...")
        self.clear_log()
        
        # Run in thread to keep GUI alive
        thread = threading.Thread(target=self.run_mapgen_logic)
        thread.daemon = True
        thread.start()

    def run_mapgen_logic(self):
        # 1. Redirect Stdout
        old_stdout = sys.stdout
        sys.stdout = StreamToTkinter(self.log)

        # 2. Setup Arguments for mapgen.main()
        original_argv = sys.argv
        sys.argv = ["mapgen.py"] # Fake the script name
        if self.use_reuse_tsv.get():
            sys.argv.extend(["--reuse-tsv", self.reuse_tsv_path.get()])

        try:
            # 3. Call the imported main function
            mapgen.main()
            self.root.after(0, lambda: messagebox.showinfo("Success", "Map generation completed!"))
        except Exception as e:
            self.log(f"CRITICAL ERROR: {str(e)}", "ERROR")
            self.root.after(0, lambda: messagebox.showerror("Error", f"Failed: {e}"))
        finally:
            # 4. Clean up
            sys.stdout = old_stdout
            sys.argv = original_argv
            self.is_running = False
            self.root.after(0, lambda: self.run_btn.config(state="normal", text="GENERATE MAP"))

if __name__ == "__main__":
    root = tk.Tk()
    app = MapGenApp(root)
    root.mainloop()