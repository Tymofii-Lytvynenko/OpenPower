import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import csv
import os
import math

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
# 1. Data & Logic Layer (Model)
# ==========================================

class TSVManager:
    """
    Handles reading and writing TSV files using standard csv library.
    Focuses on the 'how' of file I/O.
    """
    def read_tsv(self, filepath):
        """Reads a TSV file and returns a list of dictionaries."""
        if not filepath or not os.path.exists(filepath):
            return []
        
        with open(filepath, mode='r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f, delimiter='\t')
            return list(reader)

    def write_tsv(self, filepath, fieldnames, data):
        """Writes a list of dictionaries to a TSV file."""
        with open(filepath, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
            writer.writeheader()
            writer.writerows(data)

    def get_columns(self, filepath):
        """Returns the list of column names from a TSV file."""
        if not filepath or not os.path.exists(filepath):
            return []
        
        with open(filepath, mode='r', encoding='utf-8', newline='') as f:
            # Read only the first line to get headers
            line = f.readline()
            if not line:
                return []
            return line.strip().split('\t')


class WorldDataManager:
    """
    Manages the relationships between Countries and Regions (Pop, Area, Owner).
    Serves as the 'Database' for the operation.
    """
    def __init__(self, tsv_manager):
        self.tsv = tsv_manager
        # Mapping: country_id -> list of region objects (dict)
        self.country_to_regions = {}
        # Mapping: region_hex -> region data (area, pop, owner)
        self.region_registry = {}

    def load_world_data(self, regions_path, pop_path):
        """
        Parses regions.tsv and regions_pop.tsv to build the world state.
        
        Why: We need to join data from two files (geo and pop) to perform 
        proportional math.
        """
        self.country_to_regions.clear()
        self.region_registry.clear()

        # 1. Load Geo Data (Area, Owner, Hex)
        raw_regions = self.tsv.read_tsv(regions_path)
        for row in raw_regions:
            r_hex = row.get('hex')
            owner = row.get('owner')
            try:
                area = float(row.get('area_km2', 0))
            except ValueError:
                area = 0.0

            if r_hex and owner:
                data = {
                    'hex': r_hex,
                    'owner': owner,
                    'area': area,
                    'pop': 0.0 # Will be filled next
                }
                self.region_registry[r_hex] = data
                
                if owner not in self.country_to_regions:
                    self.country_to_regions[owner] = []
                self.country_to_regions[owner].append(data)

        # 2. Load Pop Data (Populations)
        raw_pop = self.tsv.read_tsv(pop_path)
        for row in raw_pop:
            r_hex = row.get('hex')
            if r_hex in self.region_registry:
                # Summing all age groups for total population
                try:
                    p14 = float(row.get('pop_14', 0))
                    p15 = float(row.get('pop_15_64', 0))
                    p65 = float(row.get('pop_65', 0))
                    self.region_registry[r_hex]['pop'] = p14 + p15 + p65
                except ValueError:
                    continue


class DistributionLogic:
    """
    Pure logic class for calculating distributions.
    Adheres to the single responsibility principle.
    """
    
    MODES = {
        "Even": "even",
        "Population (Per Capita)": "pop",
        "Area (Per km²)": "area",
        "Hybrid (Pop & Area)": "hybrid"
    }

    def calculate_distribution(self, total_value, regions_data, mode):
        """
        Distributes a total_value across a list of regions based on the mode.
        
        Args:
            total_value (float): The value to distribute.
            regions_data (list): List of dicts {'hex', 'pop', 'area'}.
            mode (str): Key from MODES.
            
        Returns:
            dict: { region_hex: calculated_value }
        """
        results = {}
        count = len(regions_data)
        if count == 0:
            return results

        # Strategy 1: Even
        if mode == "even":
            val_per_region = total_value / count
            for r in regions_data:
                results[r['hex']] = val_per_region
            return results

        # Strategy 2, 3, 4: Proportional
        # We need total weights first
        total_pop = sum(r['pop'] for r in regions_data)
        total_area = sum(r['area'] for r in regions_data)

        for r in regions_data:
            weight = 0.0
            
            if mode == "pop":
                if total_pop > 0:
                    weight = r['pop'] / total_pop
                else:
                    weight = 1.0 / count # Fallback to even
            
            elif mode == "area":
                if total_area > 0:
                    weight = r['area'] / total_area
                else:
                    weight = 1.0 / count

            elif mode == "hybrid":
                # Average of the two proportions
                w_pop = (r['pop'] / total_pop) if total_pop > 0 else (1.0/count)
                w_area = (r['area'] / total_area) if total_area > 0 else (1.0/count)
                weight = (w_pop + w_area) / 2.0

            results[r['hex']] = total_value * weight

        return results


# ==========================================
# 2. UI Layer (View/Controller)
# ==========================================

class FileSelector(tk.Frame):
    """Reusable component for selecting a file."""
    def __init__(self, parent, label_text, file_type="tsv", command=None):
        super().__init__(parent)
        self.pack(fill='x', pady=2)
        
        lbl = tk.Label(self, text=label_text, width=20, anchor='w')
        lbl.pack(side='left')
        
        self.entry = tk.Entry(self)
        self.entry.pack(side='left', fill='x', expand=True, padx=5)
        
        btn = tk.Button(self, text="Browse", command=self._browse)
        btn.pack(side='left')

        self.custom_callback = command
        self.file_type = file_type

    def _browse(self):
        filename = filedialog.askopenfilename(filetypes=[("TSV Files", "*.tsv")])
        if filename:
            self.entry.delete(0, tk.END)
            self.entry.insert(0, filename)
            if self.custom_callback:
                self.custom_callback(filename)

    def get(self):
        return self.entry.get()


class MainWindow:
    """
    Main Application Window.
    Binds the Logic (DataManager) to the User Interactions.
    """
    def __init__(self, root):
        self.root = root
        self.root.title("OpenPower Data Distributor Tool")
        self.root.geometry("700x600")

        # Logic Composition
        self.tsv_manager = TSVManager()
        self.world_manager = WorldDataManager(self.tsv_manager)
        self.logic = DistributionLogic()

        self.source_columns = []
        
        self._setup_ui()

    def _setup_ui(self):
        # --- Section 1: Base Data ---
        lf_base = tk.LabelFrame(self.root, text="1. Load World Data (Base Modules)")
        lf_base.pack(fill='x', padx=10, pady=5)
        
        self.fs_regions = FileSelector(lf_base, "regions.tsv:")
        self.fs_pop = FileSelector(lf_base, "regions_pop.tsv:")
        
        btn_load_world = tk.Button(lf_base, text="Load World Data", command=self.load_world_data)
        btn_load_world.pack(pady=5)

        # --- Section 2: Source & Target ---
        lf_files = tk.LabelFrame(self.root, text="2. Select Data Files")
        lf_files.pack(fill='x', padx=10, pady=5)

        self.fs_source = FileSelector(lf_files, "Source (Country):", command=self.update_source_columns)
        self.fs_target = FileSelector(lf_files, "Target (Regions):")

        # --- Section 3: Configuration ---
        lf_config = tk.LabelFrame(self.root, text="3. Distribution Configuration")
        lf_config.pack(fill='x', padx=10, pady=5)

        # Column Selector
        frame_col = tk.Frame(lf_config)
        frame_col.pack(fill='x', pady=2)
        tk.Label(frame_col, text="Column to Distribute:", width=20, anchor='w').pack(side='left')
        self.combo_col = ttk.Combobox(frame_col, state="readonly")
        self.combo_col.pack(side='left', fill='x', expand=True)

        # Mode Selector
        frame_mode = tk.Frame(lf_config)
        frame_mode.pack(fill='x', pady=5)
        tk.Label(frame_mode, text="Distribution Mode:", width=20, anchor='w').pack(side='left')
        
        self.var_mode = tk.StringVar(value="even")
        for text, val in self.logic.MODES.items():
            rb = tk.Radiobutton(frame_mode, text=text, variable=self.var_mode, value=val)
            rb.pack(side='left')

        # --- Section 4: Action ---
        btn_run = tk.Button(self.root, text="🚀 RUN DISTRIBUTION", command=self.run_process, bg="#dddddd", height=2)
        btn_run.pack(fill='x', padx=10, pady=10)

        # --- Log ---
        self.log_text = tk.Text(self.root, height=10, state='disabled')
        self.log_text.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        
        self.log("Welcome to the OpenPower Data Tool.")
        self.log("Please select regions.tsv and regions_pop.tsv first.")

    def log(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"> {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def load_world_data(self):
        """Loads the base mapping files."""
        r_path = self.fs_regions.get()
        p_path = self.fs_pop.get()
        
        if not r_path or not p_path:
            messagebox.showerror("Error", "Please select both regions.tsv and regions_pop.tsv")
            return

        try:
            self.world_manager.load_world_data(r_path, p_path)
            count = len(self.world_manager.country_to_regions)
            self.log(f"Successfully loaded world data. Found {count} countries.")
        except Exception as e:
            self.log(f"Error loading world data: {e}")

    def update_source_columns(self, filepath):
        """Callback when source file changes to populate dropdown."""
        try:
            cols = self.tsv_manager.get_columns(filepath)
            self.combo_col['values'] = cols
            if cols:
                self.combo_col.current(1) # Default to 2nd column usually (1st is ID)
                self.log(f"Loaded columns from source: {cols}")
        except Exception as e:
            self.log(f"Error reading source columns: {e}")

    def run_process(self):
        """Main execution flow."""
        # 1. Validation
        if not self.world_manager.country_to_regions:
            messagebox.showerror("Error", "World data not loaded. Please complete Step 1.")
            return

        src_path = self.fs_source.get()
        tgt_path = self.fs_target.get()
        col_name = self.combo_col.get()
        mode = self.var_mode.get()

        if not src_path or not tgt_path or not col_name:
            messagebox.showerror("Error", "Please select Source, Target, and Column.")
            return

        try:
            # 2. Read Source Country Data
            country_data = self.tsv_manager.read_tsv(src_path)
            
            # 3. Read (or Init) Target Region Data
            # Note: If target exists, we read it to preserve other columns. 
            # If not, we create basic structure.
            target_rows = []
            target_fieldnames = []
            
            if os.path.exists(tgt_path):
                target_rows = self.tsv_manager.read_tsv(tgt_path)
                target_fieldnames = self.tsv_manager.get_columns(tgt_path)
            
            # If the column doesn't exist in target, add it
            if col_name not in target_fieldnames:
                target_fieldnames.append(col_name)
            
            # Ensure 'hex' is in fieldnames if creating new file
            if 'hex' not in target_fieldnames:
                target_fieldnames.insert(0, 'hex')

            # Create a lookup for existing target rows to update them efficiently
            # Mapping: hex -> row_dict
            target_map = {row['hex']: row for row in target_rows if 'hex' in row}

            processed_count = 0

            # 4. Processing Loop
            for c_row in country_data:
                c_id = c_row.get('id') # Assuming 'id' is standard country key
                if not c_id: continue

                # Get value to distribute
                try:
                    val_str = c_row.get(col_name)
                    # Handle empty strings or None
                    if val_str in [None, '']:
                        total_val = 0.0
                    else:
                        total_val = float(val_str)
                except ValueError:
                    self.log(f"Skipping country {c_id}: value '{c_row.get(col_name)}' is not a number.")
                    continue

                # Get regions for this country
                regions = self.world_manager.country_to_regions.get(c_id, [])
                if not regions:
                    continue

                # Calculate
                distribution = self.logic.calculate_distribution(total_val, regions, mode)

                # Update Target Map
                for r_hex, new_val in distribution.items():
                    if r_hex not in target_map:
                        # Create new row if it didn't exist in target file
                        target_map[r_hex] = {'hex': r_hex}
                    
                    # Store as integer if it was an integer input, else float
                    # Here we stick to formatting as string for TSV
                    target_map[r_hex][col_name] = f"{new_val:.4f}"
                
                processed_count += 1

            # 5. Write Result
            final_rows = list(target_map.values())
            self.tsv_manager.write_tsv(tgt_path, target_fieldnames, final_rows)
            
            self.log(f"Done! Distributed '{col_name}' from {processed_count} countries to regions.")
            self.log(f"Saved to: {tgt_path}")
            messagebox.showinfo("Success", "Distribution Complete!")

        except Exception as e:
            self.log(f"Critical Error: {e}")
            import traceback
            traceback.print_exc()


# ==========================================
# 3. Entry Point
# ==========================================

if __name__ == "__main__":
    root = tk.Tk()
    app = MainWindow(root)
    root.mainloop()