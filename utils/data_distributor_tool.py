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
# 1. Logic & Strategy
# ==========================================

class DistributionStrategy:
    def calculate_weights(self, region_data, total_pop, total_area, country_hdi, count):
        raise NotImplementedError

class EvenStrategy(DistributionStrategy):
    def calculate_weights(self, region_data, total_pop, total_area, country_hdi, count):
        return 1.0 / count if count > 0 else 0

class PopulationStrategy(DistributionStrategy):
    def calculate_weights(self, region_data, total_pop, total_area, country_hdi, count):
        return region_data['pop'] / total_pop if total_pop > 0 else (1.0 / count)

class AreaStrategy(DistributionStrategy):
    def calculate_weights(self, region_data, total_pop, total_area, country_hdi, count):
        return region_data['area'] / total_area if total_area > 0 else (1.0 / count)

class HybridStrategy(DistributionStrategy):
    def calculate_weights(self, region_data, total_pop, total_area, country_hdi, count):
        w_pop = (region_data['pop'] / total_pop) if total_pop > 0 else (1.0 / count)
        w_area = (region_data['area'] / total_area) if total_area > 0 else (1.0 / count)
        hdi_normalized = max(0.1, min(1.0, country_hdi / 100.0))
        pop_bias = 1.0 - (hdi_normalized * 0.5) 
        return (w_pop * pop_bias) + (w_area * (1.0 - pop_bias))

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
                    # Pad row if short
                    while len(row) < len(headers): row.append('')
                    data.append(dict(zip(headers, row)))
            return data

class WorldRegistry:
    def __init__(self):
        self.countries = {}
        self.all_regions = []

    def build(self, reg_path, pop_path, dem_path):
        self.countries.clear(); self.all_regions.clear()
        
        # HDI
        hdi_map = {}
        for row in SafeTSV.read(dem_path):
            if 'id' in row: hdi_map[row['id']] = float(row.get('human_dev', 50))

        # Pop
        pop_map = {}
        for row in SafeTSV.read(pop_path):
            if 'hex' in row:
                pop_map[row['hex']] = sum([float(row.get(k,0) or 0) for k in ['pop_14','pop_15_64','pop_65']])

        # Regions
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
# 2. UI Components
# ==========================================

class ColumnConfigRow(tk.Frame):
    def __init__(self, parent, col_name, strategies):
        super().__init__(parent)
        tk.Label(self, text=col_name, width=20, anchor='w', font=('Consolas', 10)).pack(side='left')
        self.var_mode = tk.StringVar(value="Hybrid")
        ttk.Combobox(self, textvariable=self.var_mode, values=list(strategies.keys()), state="readonly", width=15).pack(side='left', padx=5)
        self.pack(fill='x', pady=2)

class MainWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("OpenPower Distributor v3.1")
        self.root.geometry("800x750")
        
        self.registry = WorldRegistry()
        self.strategies = {
            "Even": EvenStrategy(),
            "Population": PopulationStrategy(),
            "Area": AreaStrategy(),
            "Hybrid (Smart)": HybridStrategy()
        }
        self.configs = {}
        self._setup_ui()

    def _setup_ui(self):
        # 1. Base Data
        lf1 = tk.LabelFrame(self.root, text="1. Base Data Setup", font=('Arial', 10, 'bold'))
        lf1.pack(fill='x', padx=10, pady=5)
        self.ent_reg = self._path_row(lf1, "Regions:")
        self.ent_pop = self._path_row(lf1, "Pop Data:")
        self.ent_dem = self._path_row(lf1, "Demographics:")
        tk.Button(lf1, text="Initialize World Data", bg="#dddddd", command=self.load_world).pack(pady=5)

        # 2. Source/Target
        lf2 = tk.LabelFrame(self.root, text="2. File Selection", font=('Arial', 10, 'bold'))
        lf2.pack(fill='x', padx=10, pady=5)
        
        # Source Row with explicit Load Button
        f_src = tk.Frame(lf2)
        f_src.pack(fill='x', pady=2)
        tk.Label(f_src, text="Source (Country):", width=15, anchor='w').pack(side='left')
        self.ent_src = tk.Entry(f_src)
        self.ent_src.pack(side='left', fill='x', expand=True, padx=5)
        tk.Button(f_src, text="...", width=3, command=lambda: self._browse(self.ent_src)).pack(side='left')
        # THIS IS THE NEW BUTTON
        tk.Button(f_src, text="LOAD COLUMNS", bg="#3498db", fg="white", command=self.load_columns).pack(side='left', padx=5)

        self.ent_tgt = self._path_row(lf2, "Target (Region):")

        # 3. Config Area
        tk.Label(self.root, text="3. Distribution Configuration", font=('Arial', 10, 'bold')).pack(pady=(10,0))
        
        # Scrollable Canvas
        container = tk.Frame(self.root, bd=1, relief="sunken")
        container.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.canvas = tk.Canvas(container)
        sb = tk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = tk.Frame(self.canvas)

        self.scroll_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=sb.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # 4. Action
        tk.Button(self.root, text="🚀 EXECUTE DISTRIBUTION", bg="#27ae60", fg="white", font=('Arial', 12, 'bold'), height=2, command=self.run).pack(fill='x', padx=10, pady=10)

        # Log
        self.log_widget = tk.Text(self.root, height=8, bg="#2c3e50", fg="#ecf0f1", state='disabled')
        self.log_widget.pack(fill='x', padx=10, pady=(0, 10))

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
        if p:
            entry.delete(0, tk.END)
            entry.insert(0, p)

    def log(self, m):
        self.log_widget.config(state='normal')
        self.log_widget.insert(tk.END, f"> {m}\n")
        self.log_widget.see(tk.END)
        self.log_widget.config(state='disabled')

    def load_world(self):
        try:
            self.registry.build(self.ent_reg.get(), self.ent_pop.get(), self.ent_dem.get())
            self.log(f"World Loaded: {len(self.registry.countries)} countries, {len(self.registry.all_regions)} regions.")
        except Exception as e:
            messagebox.showerror("Init Error", str(e))
            self.log(f"Error: {e}")

    def load_columns(self):
        """
        Reads source file and lists ALL potential columns.
        removed strict numeric checking to prevent skipping valid columns.
        """
        p = self.ent_src.get()
        if not p or not os.path.exists(p):
            messagebox.showerror("Error", "Please select a valid Source file first.")
            return

        # Clear old UI
        for w in self.scroll_frame.winfo_children(): w.destroy()
        self.configs.clear()

        try:
            # Read just the header
            with open(p, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f, delimiter='\t')
                try:
                    headers = next(reader)
                except StopIteration:
                    self.log("Source file is empty.")
                    return

            # Clean headers
            cols = [h.strip() for h in headers if h.strip()]
            
            # Blocklist: Columns that definitely shouldn't be distributed
            ignored = ['id', 'un_member', 'is_playable', 'name', 'hex', 'owner', 'iso_region', 'type']
            
            # Allow everything else
            valid_cols = [c for c in cols if c.lower() not in ignored]

            self.log(f"Raw Headers Found: {cols}")
            
            if not valid_cols:
                self.log("No valid columns found. Check your TSV headers.")
                tk.Label(self.scroll_frame, text="No columns found (check log).", fg="red").pack()
                return

            self.log(f"Configurable Columns: {valid_cols}")
            
            for c in valid_cols:
                self.configs[c] = ColumnConfigRow(self.scroll_frame, c, self.strategies)
            
            # Update UI Layout
            self.scroll_frame.update_idletasks()
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        except Exception as e:
            self.log(f"Error reading source: {e}")
            traceback.print_exc()
            
    def run(self):
        if not self.registry.countries:
            messagebox.showerror("Error", "Please click 'Initialize World Data' first.")
            return
        if not self.configs:
            messagebox.showerror("Error", "Please click 'LOAD COLUMNS' first.")
            return

        try:
            # Load Data
            src_rows = SafeTSV.read(self.ent_src.get())
            
            # Prep Target
            tgt_path = self.ent_tgt.get()
            target_data = {}
            
            # Merge existing
            for r in SafeTSV.read(tgt_path):
                if 'hex' in r: target_data[r['hex']] = r
            
            # Ensure all regions present
            for h in self.registry.all_regions:
                if h not in target_data: target_data[h] = {'hex': h}

            # Distribute
            for col, config in self.configs.items():
                strat = self.strategies[config.var_mode.get()]
                self.log(f"Processing '{col}' via {config.var_mode.get()}...")

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
                        w = strat.calculate_weights(r, t_pop, t_area, c_info['hdi'], len(regs))
                        target_data[r['hex']][col] = f"{val * w:.4f}"

            # Save
            all_keys = set().union(*(d.keys() for d in target_data.values()))
            fieldnames = ['hex'] + sorted([k for k in all_keys if k != 'hex'])
            
            with open(tgt_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
                writer.writeheader()
                writer.writerows(target_data.values())

            self.log("✅ Distribution Complete!")
            messagebox.showinfo("Success", f"Updated {tgt_path}")

        except Exception as e:
            self.log(f"Run Error: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    root = tk.Tk()
    MainWindow(root)
    root.mainloop()