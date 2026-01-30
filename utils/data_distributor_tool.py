import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import csv
import os
import traceback

"""
OpenPower Data Distribution Utility

PURPOSE:
This script converts data between Country-level TSV files and Region-level TSV files.
It is primarily used to 'break down' national statistics (like resources, production, etc.) 
into granular regional data based on geographic or demographic weights.

DEPENDENCIES:
- Standard Python 3.x libraries (tkinter, csv, math, os).
- OpenPower 'base' module files: regions.tsv and regions_pop.tsv.

LOGIC:
It supports four distribution modes:
1. Even: Equal split across all regions.
2. Population: Weighted by (pop_14 + pop_15_64 + pop_65).
3. Area: Weighted by area_km2.
4. Hybrid: An average of population and area weights.
"""

# ==========================================
# 1. Strategy Layer
# ==========================================

class DistributionStrategy:
    def calculate_weights(self, region_data, total_pop, total_area, country_hdi, count, custom_ratio=0.5):
        raise NotImplementedError

class EvenStrategy(DistributionStrategy):
    def calculate_weights(self, region_data, total_pop, total_area, country_hdi, count, custom_ratio=0.5):
        return 1.0 / count if count > 0 else 0

class PopulationStrategy(DistributionStrategy):
    def calculate_weights(self, region_data, total_pop, total_area, country_hdi, count, custom_ratio=0.5):
        return region_data['pop'] / total_pop if total_pop > 0 else (1.0 / count)

class AreaStrategy(DistributionStrategy):
    def calculate_weights(self, region_data, total_pop, total_area, country_hdi, count, custom_ratio=0.5):
        return region_data['area'] / total_area if total_area > 0 else (1.0 / count)

class HybridStrategy(DistributionStrategy):
    def calculate_weights(self, region_data, total_pop, total_area, country_hdi, count, custom_ratio=0.5):
        w_pop = (region_data['pop'] / total_pop) if total_pop > 0 else (1.0 / count)
        w_area = (region_data['area'] / total_area) if total_area > 0 else (1.0 / count)
        hdi_normalized = max(0.1, min(1.0, country_hdi / 100.0))
        pop_bias = 1.0 - (hdi_normalized * 0.5) 
        return (w_pop * pop_bias) + (w_area * (1.0 - pop_bias))

class CustomStrategy(DistributionStrategy):
    def calculate_weights(self, region_data, total_pop, total_area, country_hdi, count, custom_ratio=0.5):
        w_pop = (region_data['pop'] / total_pop) if total_pop > 0 else (1.0 / count)
        w_area = (region_data['area'] / total_area) if total_area > 0 else (1.0 / count)
        return (w_pop * custom_ratio) + (w_area * (1.0 - custom_ratio))

# ==========================================
# 2. Data Helper
# ==========================================

class SafeTSV:
    @staticmethod
    def read(path):
        if not path or not os.path.exists(path): return []
        with open(path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.reader(f, delimiter='\t')
            try: headers = next(reader)
            except: return []
            headers = [h.strip() for h in headers]
            data = []
            for row in reader:
                if len(row) > 0:
                    while len(row) < len(headers): row.append('')
                    data.append(dict(zip(headers, row)))
            return data

class WorldRegistry:
    def __init__(self):
        self.countries = {}; self.all_regions = []

    def build(self, reg_path, pop_path, dem_path):
        self.countries.clear(); self.all_regions.clear()
        
        # Load HDI
        hdi_map = {}
        if os.path.exists(dem_path):
            for row in SafeTSV.read(dem_path):
                if 'id' in row: hdi_map[row['id']] = float(row.get('human_dev', 50))

        # Load Pop
        pop_map = {}
        if os.path.exists(pop_path):
            for row in SafeTSV.read(pop_path):
                if 'hex' in row:
                    pop_map[row['hex']] = sum([float(row.get(k,0) or 0) for k in ['pop_14','pop_15_64','pop_65']])

        # Load Regions
        reg_data = SafeTSV.read(reg_path)
        if not reg_data: raise ValueError("Regions file empty/invalid")
        if 'hex' not in reg_data[0]: raise KeyError("Missing 'hex' column in regions.tsv")

        for row in reg_data:
            r_hex = row['hex']
            owner = row.get('owner', 'Unknown')
            self.all_regions.append(r_hex)
            if owner not in self.countries:
                self.countries[owner] = {'hdi': hdi_map.get(owner, 50.0), 'regions': []}
            self.countries[owner]['regions'].append({
                'hex': r_hex,
                'area': float(row.get('area_km2', 1) or 1),
                'pop': pop_map.get(r_hex, 0)
            })

# ==========================================
# 3. UI Components
# ==========================================

class ColumnConfigRow(tk.Frame):
    def __init__(self, parent, col_name, strategies):
        super().__init__(parent, bd=1, relief="ridge", padx=5, pady=5, bg="#f0f0f0")
        
        self.top_frame = tk.Frame(self, bg="#f0f0f0")
        self.top_frame.pack(fill='x')
        
        tk.Label(self.top_frame, text=col_name, width=25, anchor='w', font=('Consolas', 10, 'bold'), bg="#f0f0f0").pack(side='left')
        
        self.var_mode = tk.StringVar(value="Hybrid (Smart)")
        self.combo = ttk.Combobox(self.top_frame, textvariable=self.var_mode, values=list(strategies.keys()), state="readonly", width=18)
        self.combo.pack(side='left', padx=5)
        self.combo.bind("<<ComboboxSelected>>", self._on_change)

        self.slider_frame = tk.Frame(self, bg="#f0f0f0")
        tk.Label(self.slider_frame, text="Area", font=('Arial', 8), bg="#f0f0f0").pack(side='left')
        self.slider = tk.Scale(self.slider_frame, from_=0.0, to=1.0, resolution=0.1, orient="horizontal", length=200, showvalue=0, bg="#f0f0f0")
        self.slider.set(0.5)
        self.slider.pack(side='left', padx=5, expand=True, fill='x')
        tk.Label(self.slider_frame, text="Pop", font=('Arial', 8), bg="#f0f0f0").pack(side='left')
        
        self.val_label = tk.Label(self.slider_frame, text="50%", width=4, font=('Arial', 8), bg="#f0f0f0")
        self.val_label.pack(side='left')
        self.slider.config(command=self._update_label)

    def _on_change(self, event=None):
        if self.var_mode.get() == "Custom":
            self.slider_frame.pack(fill='x', pady=(5,0))
        else:
            self.slider_frame.pack_forget()

    def _update_label(self, val):
        v = float(val)
        self.val_label.config(text=f"{int(v*100)}%")

    def get_custom_ratio(self):
        return self.slider.get()

class MainWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("OpenPower Distributor v4.1 (UI Fix)")
        self.root.geometry("850x800")
        
        self.registry = WorldRegistry()
        self.strategies = {
            "Even": EvenStrategy(),
            "Population": PopulationStrategy(),
            "Area": AreaStrategy(),
            "Hybrid (Smart)": HybridStrategy(),
            "Custom": CustomStrategy()
        }
        self.configs = {}
        self._setup_ui()

    def _setup_ui(self):
        # 1. Base Data
        lf1 = tk.LabelFrame(self.root, text="1. Base Data", font=('Arial', 10, 'bold'))
        lf1.pack(fill='x', padx=10, pady=5)
        self.ent_reg = self._path_row(lf1, "Regions:")
        self.ent_pop = self._path_row(lf1, "Pop Data:")
        self.ent_dem = self._path_row(lf1, "Demographics:")
        tk.Button(lf1, text="Initialize World Data", bg="#e0e0e0", command=self.load_world).pack(pady=5)

        # 2. Files
        lf2 = tk.LabelFrame(self.root, text="2. Source & Target", font=('Arial', 10, 'bold'))
        lf2.pack(fill='x', padx=10, pady=5)
        
        f_src = tk.Frame(lf2)
        f_src.pack(fill='x', pady=2)
        tk.Label(f_src, text="Source (Country):", width=15, anchor='w').pack(side='left')
        self.ent_src = tk.Entry(f_src); self.ent_src.pack(side='left', fill='x', expand=True, padx=5)
        tk.Button(f_src, text="...", width=3, command=lambda: self._browse(self.ent_src)).pack(side='left')
        tk.Button(f_src, text="LOAD COLUMNS", bg="#3498db", fg="white", command=self.load_columns).pack(side='left', padx=5)

        self.ent_tgt = self._path_row(lf2, "Target (Region):")

        # 3. Config (FIXED LAYOUT)
        tk.Label(self.root, text="3. Configuration", font=('Arial', 10, 'bold')).pack(pady=(10,0))
        
        # Container for Canvas
        container = tk.Frame(self.root, bd=2, relief="sunken")
        container.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.canvas = tk.Canvas(container, bg="white")
        sb = tk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        
        self.scroll_frame = tk.Frame(self.canvas, bg="white")
        
        # KEY FIX: Using 'create_window' with tags to bind width
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        
        self.canvas.configure(yscrollcommand=sb.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        
        # Bind events to ensure resizing works
        self.scroll_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # 4. Run
        tk.Button(self.root, text="🚀 EXECUTE DISTRIBUTION", bg="#27ae60", fg="white", font=('Arial', 12, 'bold'), height=2, command=self.run).pack(fill='x', padx=10, pady=10)
        
        self.log_widget = tk.Text(self.root, height=6, bg="#2c3e50", fg="#ecf0f1", state='disabled')
        self.log_widget.pack(fill='x', padx=10, pady=(0, 10))

    # --- UI Layout Helpers ---
    def _on_frame_configure(self, event):
        """Reset the scroll region to encompass the inner frame"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        """When canvas resizes, resize the inner frame to match"""
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _path_row(self, parent, label):
        f = tk.Frame(parent)
        f.pack(fill='x', pady=2)
        tk.Label(f, text=label, width=15, anchor='w').pack(side='left')
        e = tk.Entry(f)
        e.pack(side='left', fill='x', expand=True, padx=5)
        tk.Button(f, text="...", width=3, command=lambda: self._browse(e)).pack(side='left')
        return e

    def _browse(self, entry):
        p = filedialog.askopenfilename(filetypes=[("TSV", "*.tsv")])
        if p: entry.delete(0, tk.END); entry.insert(0, p)

    def log(self, m):
        self.log_widget.config(state='normal')
        self.log_widget.insert(tk.END, f"> {m}\n")
        self.log_widget.see(tk.END); self.log_widget.config(state='disabled')

    def load_world(self):
        try:
            self.registry.build(self.ent_reg.get(), self.ent_pop.get(), self.ent_dem.get())
            self.log(f"Indexed {len(self.registry.countries)} countries.")
        except Exception as e: self.log(f"Error: {e}")

    def load_columns(self):
        p = self.ent_src.get()
        if not p: return

        # CLEAR EXISTING
        for w in self.scroll_frame.winfo_children(): w.destroy()
        self.configs.clear()

        try:
            with open(p, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f, delimiter='\t')
                try: headers = next(reader)
                except: return

            cols = [h.strip() for h in headers if h.strip()]
            
            # Base file check
            if set(cols) == {'id', 'un_member', 'is_playable'}:
                messagebox.showwarning("Warning", "Selected 'countries.tsv'. Choose an economy/politics file.")
                return

            ignored = ['id', 'un_member', 'is_playable', 'name', 'hex', 'owner', 'iso_region', 'type']
            valid_cols = [c for c in cols if c.lower() not in ignored]

            if not valid_cols:
                self.log("No valid columns found.")
                tk.Label(self.scroll_frame, text="No numeric columns found.", fg="red", bg="white").pack(pady=10)
                return

            # ADD ROWS
            for c in valid_cols:
                row = ColumnConfigRow(self.scroll_frame, c, self.strategies)
                row.pack(fill='x', pady=2, padx=5)
                self.configs[c] = row

            self.log(f"Loaded {len(valid_cols)} columns.")
            
        except Exception as e:
            self.log(f"Load Error: {e}")
            traceback.print_exc()

    def run(self):
        if not self.registry.countries:
            messagebox.showerror("Error", "Init World Data first.")
            return

        try:
            src_rows = SafeTSV.read(self.ent_src.get())
            tgt_path = self.ent_tgt.get()
            target_data = {}

            if os.path.exists(tgt_path):
                for r in SafeTSV.read(tgt_path):
                    if 'hex' in r: target_data[r['hex']] = r
            
            for h in self.registry.all_regions:
                if h not in target_data: target_data[h] = {'hex': h}

            for col, config in self.configs.items():
                mode = config.var_mode.get()
                strat = self.strategies[mode]
                ratio = config.get_custom_ratio()

                self.log(f"Processing '{col}' ({mode})...")

                for c_row in src_rows:
                    c_id = c_row.get('id')
                    if c_id not in self.registry.countries: continue
                    try: val = float(c_row.get(col, 0) or 0)
                    except: val = 0.0

                    c_info = self.registry.countries[c_id]
                    regs = c_info['regions']
                    t_pop = sum(r['pop'] for r in regs)
                    t_area = sum(r['area'] for r in regs)

                    for r in regs:
                        w = strat.calculate_weights(r, t_pop, t_area, c_info['hdi'], len(regs), ratio)
                        target_data[r['hex']][col] = f"{val * w:.4f}"

            all_keys = set().union(*(d.keys() for d in target_data.values()))
            fieldnames = ['hex'] + sorted([k for k in all_keys if k != 'hex'])
            
            with open(tgt_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
                writer.writeheader()
                writer.writerows(target_data.values())

            self.log("✅ Done!")
            messagebox.showinfo("Success", "Files updated.")

        except Exception as e:
            self.log(f"Error: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    root = tk.Tk()
    MainWindow(root)
    root.mainloop()