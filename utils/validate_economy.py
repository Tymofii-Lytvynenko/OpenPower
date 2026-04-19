import os
import rtoml
import csv
from pathlib import Path

# Path to the directory containing country economy TOML files
TARGET_DIR = Path("modules/base/data/countries/economy")
# Path to the master GDP file
GDP_FILE = Path("modules/base/data/countries/countries_eco.tsv")

# Complete list of resources as defined in src/shared/economy_meta.py
ALL_RESOURCES = [
    "cereals", "vegetables_and_fruits", "meat_and_fish", "dairy", "tobacco", 
    "drugs_and_raw_plants", "other_food_and_beverages", "wood_and_paper", 
    "minerals", "fossil_fuels", "electricity", "iron_and_steel", 
    "non_ferrous_metals", "precious_stones", "fabrics_and_leather", 
    "plastics_and_rubber", "chemicals", "construction_materials", 
    "pharmaceuticals", "appliances", "vehicles", "machinery_and_instruments", 
    "commodities", "luxury_commodities", "arms_and_ammunition", 
    "transport_services", "tourism_services", "construction_services", 
    "financial_services", "it_and_telecom_services", "business_services", 
    "recreational_services", "health_services", "education_services", 
    "government_services", "industrial_services"
]

def load_gdp_data():
    """
    Loads GDP data from countries_eco.tsv and returns a dict mapping country ID to GDP.
    """
    gdp_map = {}
    if not GDP_FILE.exists():
        print(f"Warning: GDP file not found at {GDP_FILE}")
        return gdp_map
    
    try:
        with open(GDP_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                gdp_map[row['id']] = float(row['gdp'])
    except Exception as e:
        print(f"Error loading GDP data: {e}")
    
    return gdp_map

def validate_file(file_path: Path, target_gdp: float):
    """
    Validates a TOML file:
    - Checks for [resources] section.
    - Checks for all 3 category presence.
    - Checks for zero values.
    - Checks if sum matches target_gdp.
    """
    errors = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            # Check for empty file manually first
            content = f.read()
            if not content.strip():
                return ["File is empty"]
            data = rtoml.loads(content)
    except Exception as e:
        return [f"RToml Load Error: {e}"]

    if "resources" not in data:
        return ["Missing [resources] section"]
    
    resources = data["resources"]
    
    # 1. Check for missing categories
    missing = [res for res in ALL_RESOURCES if res not in resources]
    if missing:
        errors.append(f"Missing categories: {', '.join(missing)}")
    
    # 2. Check for zero or negative values
    zeros = [k for k, v in resources.items() if isinstance(v, (int, float)) and v <= 0]
    if zeros:
        # Note: If target_gdp is 0 (like ATA), zeros might be acceptable, but usually we want at least $1
        if target_gdp > 0:
            errors.append(f"Zero/Negative values found: {', '.join(zeros)}")
    
    # 3. Check for non-numeric values
    non_numeric = [k for k, v in resources.items() if not isinstance(v, (int, float))]
    if non_numeric:
        errors.append(f"Non-numeric values found: {', '.join(non_numeric)}")

    # 4. Check sum if target_gdp is provided
    total_sum = sum(v for v in resources.values() if isinstance(v, (int, float)))
    if target_gdp is not None:
        diff = abs(total_sum - target_gdp)
        # Allow small rounding threshold (e.g. $1000)
        if diff > 1000:
            errors.append(f"Sum mismatch: Found {total_sum:,.0f}, Expected {target_gdp:,.0f} (Diff: {diff:,.0f})")
    
    # 5. Check for extra categories not in the master list
    extra = [k for k in resources.keys() if k not in ALL_RESOURCES]
    if extra:
        errors.append(f"Extra categories found: {', '.join(extra)}")

    return errors

def main():
    """
    Main entry point for the validation script.
    """
    if not TARGET_DIR.exists():
        print(f"Directory not found: {TARGET_DIR}")
        return

    gdp_data = load_gdp_data()
    files = sorted(list(TARGET_DIR.glob("*.toml")))
    
    print(f"Validating {len(files)} files in {TARGET_DIR} against USD GDP master list...")
    
    error_count = 0
    clean_count = 0
    
    for file_path in files:
        country_id = file_path.stem
        target_gdp = gdp_data.get(country_id)
        
        errors = validate_file(file_path, target_gdp)
        
        if errors:
            print(f"\n[!] {file_path.name}:")
            for err in errors:
                print(f"    - {err}")
            error_count += 1
        else:
            clean_count += 1

    print(f"\nValidation Result:")
    print(f"------------------")
    print(f"Clean files: {clean_count}")
    print(f"Files with errors: {error_count}")
    print(f"Total files checked: {len(files)}")

if __name__ == "__main__":
    main()
