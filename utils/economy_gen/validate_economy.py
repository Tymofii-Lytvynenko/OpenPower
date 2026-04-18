import os
import rtoml
from pathlib import Path

# Minimum value for any resource: 0.001% = 0.00001
MIN_VALUE = 0.00001
# Path to the directory containing country economy TOML files
TARGET_DIR = Path("modules/base/data/countries/economy")

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

def validate_and_correct_file(file_path: Path) -> bool:
    """
    Loads a TOML file, ensures all resources are present, enforces a minimum value, 
    and normalizes the total sum to 1.0.
    Returns True if the file was modified and saved.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = rtoml.load(f)
    except Exception as e:
        print(f"Error loading {file_path.name}: {e}")
        return False

    if "resources" not in data:
        data["resources"] = {}
    
    resources = data["resources"]
    modified = False

    # 1. Ensure all resources from the master list are present
    for res_id in ALL_RESOURCES:
        if res_id not in resources:
            resources[res_id] = MIN_VALUE
            modified = True

    # 2. Enforce minimum value (0.001%) for existing entries
    for key, value in resources.items():
        if not isinstance(value, (int, float)):
            continue
        if value < MIN_VALUE:
            resources[key] = MIN_VALUE
            modified = True

    # 3. Normalize sum to 1.0
    total_sum = sum(v for v in resources.values() if isinstance(v, (int, float)))
    if total_sum <= 0:
        print(f"Warning: {file_path.name} has zero or negative total sum. Cannot normalize.")
        return False

    # Check if sum is already approximately 1.0 and no values were enforced/added
    if abs(total_sum - 1.0) > 1e-9 or modified:
        # Normalize all values so they sum to 1.0
        for key, value in resources.items():
            if isinstance(value, (int, float)):
                # We use 8 decimal places for reasonable precision
                resources[key] = round(value / total_sum, 8)
        
        # After rounding, the sum might slightly deviate from 1.0 due to float precision
        new_sum = sum(resources.values())
        if abs(new_sum - 1.0) > 1e-9:
            # Adjust the largest value to absorb the rounding error
            max_key = max(resources, key=resources.get)
            resources[max_key] = round(resources[max_key] + (1.0 - new_sum), 8)
            
        modified = True

    if modified:
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                rtoml.dump(data, f)
            return True
        except Exception as e:
            print(f"Error saving {file_path.name}: {e}")
            return False

    return False

def main():
    """
    Main entry point for the validation script.
    """
    if not TARGET_DIR.exists():
        print(f"Directory not found: {TARGET_DIR}")
        return

    files = list(TARGET_DIR.glob("*.toml"))
    print(f"Validating {len(files)} files in {TARGET_DIR}...")
    
    updated_count = 0
    skipped_count = 0
    for file_path in files:
        # Load and check manually for debugging
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                if not content.strip():
                    print(f"Empty file: {file_path.name}")
                    skipped_count += 1
                    continue
        except Exception:
            pass

        if validate_and_correct_file(file_path):
            print(f"Modified: {file_path.name}")
            updated_count += 1
        else:
            # Check if it was skipped due to missing resources section
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = rtoml.load(f)
                    if "resources" not in data:
                        print(f"Missing [resources] section: {file_path.name}")
                        skipped_count += 1
            except Exception:
                pass

    print(f"\nValidation complete.")
    print(f"Updated: {updated_count} files.")
    print(f"Skipped: {skipped_count} files.")
    print(f"Total:   {len(files)} files.")

if __name__ == "__main__":
    main()
