import rtoml
from pathlib import Path

TARGET_DIR = Path("modules/base/data/countries/economy")
files = list(TARGET_DIR.glob("*.toml"))
found = False
for f_path in files:
    try:
        data = rtoml.load(f_path)
        resources = data.get("resources", {})
        if not resources:
            print(f"{f_path.name}: Empty or missing resources")
            found = True
            continue
        
        total = sum(v for v in resources.values() if isinstance(v, (int, float)))
        if abs(total - 1.0) > 1e-9:
            print(f"{f_path.name}: Sum is {total}")
            found = True
            
        for k, v in resources.items():
            if v < 0.00001:
                print(f"{f_path.name}: {k} is {v}")
                found = True
    except Exception as e:
        print(f"{f_path.name}: Error {e}")

if not found:
    print("All files look good (sum=1.0, no zeros).")
