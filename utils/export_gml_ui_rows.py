"""Export resolved source row definitions without treating them as windows."""
import json
from pathlib import Path

from utils.reference_paths import resolve_reference_file

ROOT = Path(__file__).resolve().parents[1]
ROW_TYPES = (
    "lstGoalItem",
    "lstInternalLawsGroups",
    "lstInternalLawsLawsItem",
    "lstCovertActionsItem",
    "lstTreatyEligibleCountryItem",
    "lstMailItem",
    "lstUnitDeployItem",
    "lstUnitProductionItem",
    "lstThematicLegendItem",
)


def export_rows(catalog):
    return {name: catalog["templates"][name] for name in ROW_TYPES}


if __name__ == "__main__":
    catalog_path = resolve_reference_file(ROOT, ".codex/reference_ui_catalog.json")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    output = ROOT / "src/client/ui/layouts/gml_rows.json"
    output.write_text(json.dumps(export_rows(catalog), indent=2) + "\n", encoding="utf-8")
    print(f"Exported {len(ROW_TYPES)} source row types")
