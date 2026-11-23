import rtoml
import csv
import math
from numbers import Real
from pathlib import Path

# Path to the directory containing country economy TOML files
TARGET_DIR = Path("modules/base/data/countries/countries_res")
# Path to the master GDP file
GDP_FILE = Path("modules/base/data/countries/countries_economic_historical.tsv")

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
    Loads GDP data from countries_economic_historical.tsv and returns a dict mapping country ID to GDP.
    """
    gdp_map = {}
    if not GDP_FILE.exists():
        print(f"Warning: GDP file not found at {GDP_FILE}")
        return gdp_map
    
    try:
        with open(GDP_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                if row["historical_gdp_current_usd_2001_available"].lower() == "true":
                    gdp_map[row["id"]] = round(float(row["historical_gdp_current_usd_2001"]))
    except Exception as e:
        print(f"Error loading GDP data: {e}")
    
    return gdp_map

def validate_file(file_path: Path, target_gdp: float):
    """
    Validates a TOML file:
    - Checks for [resources] section.
    - Checks resource policies and nonnegative regional production.
    - Checks if the regional sum matches the available 2001 GDP target.
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
    if not isinstance(resources, dict):
        return ["[resources] must contain a table"]
    
    regional = data.get("regional_resources", {})
    if not isinstance(regional, dict):
        return ["[regional_resources] must contain a table"]
    allowed = set(ALL_RESOURCES) | {
        "electronics", "textiles_and_leather", "wood_product_services",
        "sugar", "precous_stones", "minerals_alt", "tabacco",
    }
    extra = set(resources) - allowed
    if extra:
        errors.append(f"Extra categories found: {', '.join(sorted(extra))}")
    for name, policy in resources.items():
        if not isinstance(policy, dict) or "production" in policy:
            errors.append(f"{name}: production belongs in regional_resources")
            continue
        for field in ("is_legal", "is_gov_controlled", "tax_rate"):
            if field not in policy:
                errors.append(f"Resource {name} missing required field: {field}")

    amounts = []
    for region, entries in regional.items():
        if not isinstance(entries, dict):
            errors.append(f"Invalid regional table: {region}")
            continue
        for name, entry in entries.items():
            if name not in resources:
                errors.append(f"Missing categories: {name} has regional output without a policy")
            if isinstance(entry, dict):
                entry = entry.get("production", entry.get("domestic_production"))
            if isinstance(entry, bool) or not isinstance(entry, Real) or not math.isfinite(entry) or entry < 0:
                errors.append(f"Invalid production for {region}/{name}: expected a finite nonnegative number")
            else:
                amounts.append(entry)

    if target_gdp is not None:
        if isinstance(target_gdp, bool) or not isinstance(target_gdp, Real) or not math.isfinite(target_gdp):
            errors.append("Target GDP must be a finite number")
        elif (total := math.fsum(amounts)) != float(target_gdp):
            errors.append(f"Sum mismatch: Found {total:,.0f}, Expected {target_gdp:,.0f}")

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
