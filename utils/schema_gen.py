import polars as pl
import rtoml
from pathlib import Path
from typing import List, Dict, Any

# Paths are resolved relative to the script's parent to ensure 
# portability regardless of where the python process is invoked.
PROJECT_ROOT = Path(__file__).parent.parent
MODULES_DIR = PROJECT_ROOT / "modules"
OUTPUT_FILE = PROJECT_ROOT / "DATA_SCHEMA.md"

def get_polars_type_name(dtype: Any) -> str:
    """
    Converts a Polars DataType object into a clean, readable string 
    for the Markdown report.
    """
    return str(dtype).replace("DataType(", "").replace(")", "")

def get_tsv_schema(file_path: Path) -> pl.Schema:
    """
    Reads only the header of a TSV to extract the schema efficiently.
    """
    return pl.read_csv(
        file_path,
        separator="\t",
        n_rows=0,
        schema_overrides={"hex": pl.String}
    ).schema

def format_preview(val: Any) -> str:
    """
    Helper function to intelligently format a value for the Markdown preview.
    If it's a dictionary, it displays multiple inner keys instead of truncating immediately.
    """
    if isinstance(val, dict):
        items = list(val.items())
        # Show up to 3 key-value pairs inline so we can see other values (not just production)
        parts = [f"'{k}': {v}" for k, v in items[:3]]
        preview = "{" + ", ".join(parts)
        if len(items) > 3:
            preview += ", ..."
        preview += "}"
        return preview
    else:
        # Standard string truncation for long lists or strings
        res = str(val)
        if len(res) > 60:
            return res[:57] + "..."
        return res

def get_toml_signature(file_path: Path) -> str:
    """
    Extracts the structural 'skeleton' of a TOML file. 
    This allows us to compare if multiple TOML files share the same schema,
    ignoring the actual values or specific dynamic dictionary keys inside.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = rtoml.load(f)
            
        if not data:
            return "_Empty file_"

        lines = []
        for key, value in data.items():
            if isinstance(value, list) and len(value) > 0:
                first_item = value[0]
                if isinstance(first_item, dict):
                    lines.append(f"[[{key}]]")
                    for sub_k in sorted(first_item.keys()):
                        lines.append(f"  {sub_k} = {type(first_item[sub_k]).__name__}")
                else:
                    lines.append(f"{key} = List[{type(first_item).__name__}]")
            elif isinstance(value, dict):
                 lines.append(f"[{key}]")
                 lines.append(f"  <dynamic_keys>")
            else:
                lines.append(f"{key} = {type(value).__name__}")
        
        return "\n".join(lines)
    except Exception:
        return "_Error parsing file_"

def generate_toml_example(file_path: Path) -> str:
    """
    Generates a readable example from a TOML file showing actual keys, 
    types, and intelligently formatted sample values.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = rtoml.load(f)
        
        if not data:
            return "_Empty file_"
            
        lines = []
        for key, value in data.items():
            if isinstance(value, list) and len(value) > 0:
                first_item = value[0]
                if isinstance(first_item, dict):
                    lines.append(f"[[{key}]] # List of Objects")
                    for sub_k, sub_v in first_item.items():
                        lines.append(f"  {sub_k} = {type(sub_v).__name__} (e.g. {format_preview(sub_v)})")
                else:
                    lines.append(f"{key} = List[{type(first_item).__name__}] (e.g. {format_preview(first_item)})")
            elif isinstance(value, dict):
                 lines.append(f"[{key}] # Dictionary/Matrix")
                 count = 0
                 for sub_k, sub_v in value.items():
                     # Limit to showing 5 items so massive matrices don't span pages
                     if count >= 5:
                         lines.append(f"  ... (+ {len(value) - 5} more keys)")
                         break
                     lines.append(f"  {sub_k} = {type(sub_v).__name__} (e.g. {format_preview(sub_v)})")
                     count += 1
            else:
                lines.append(f"{key} = {type(value).__name__} (e.g. {format_preview(value)})")
        
        return "\n".join(lines)
    except Exception:
        return "_Error parsing file_"

def analyze_tsv_group(file_paths: List[Path]) -> str:
    """
    Analyzes a group of TSV files. If all files share the same schema,
    it returns a single consolidated Markdown report.
    """
    if not file_paths:
        return ""

    try:
        baseline_path = file_paths[0]
        baseline_schema = get_tsv_schema(baseline_path)
        
        is_uniform = True
        for other_file in file_paths[1:]:
            if get_tsv_schema(other_file) != baseline_schema:
                is_uniform = False
                break
        
        if is_uniform:
            df_sample = pl.read_csv(
                baseline_path, 
                separator="\t", 
                n_rows=1, 
                schema_overrides={"hex": pl.String}
            )
            row = df_sample.row(0, named=True) if not df_sample.is_empty() else {}
            
            parent_dir = baseline_path.parent.relative_to(PROJECT_ROOT)
            output = [f"### 📂 TSV Group: `{parent_dir}/*.tsv` ({len(file_paths)} files)"]
            output.append(f"**Status:** ✅ Uniform Schema across all files.")
            output.append(f"**Columns:** {len(baseline_schema)}")
            output.append("\n| Column Name | Type | Example Value |")
            output.append("|---|---|---|")
            
            for col_name, dtype in baseline_schema.items():
                example = str(row.get(col_name, "N/A"))
                if len(example) > 50: example = example[:47] + "..."
                output.append(f"| `{col_name}` | {get_polars_type_name(dtype)} | `{example}` |")
            
            return "\n".join(output)
        else:
            return "\n\n".join([analyze_single_tsv(p) for p in file_paths])
            
    except Exception as e:
        return f"### ❌ Error analyzing group in `{file_paths[0].parent}`: {e}"

def analyze_single_tsv(file_path: Path) -> str:
    """
    Standard analysis for a single TSV file.
    """
    try:
        df = pl.read_csv(
            file_path, 
            separator="\t", 
            n_rows=5, 
            schema_overrides={"hex": pl.String}
        )
        output = [f"### 📄 TSV: `{file_path.relative_to(PROJECT_ROOT)}`"]
        output.append(f"**Columns:** {len(df.columns)}")
        output.append("\n| Column Name | Type | Example Value |")
        output.append("|---|---|---|")
        
        row = df.row(0, named=True) if not df.is_empty() else {}
        for col_name, dtype in df.schema.items():
            example = str(row.get(col_name, "N/A"))
            if len(example) > 50: example = example[:47] + "..."
            output.append(f"| `{col_name}` | {get_polars_type_name(dtype)} | `{example}` |")
        return "\n".join(output)
    except Exception as e:
        return f"### ❌ Error reading `{file_path.name}`: {e}"

def analyze_toml_group(file_paths: List[Path]) -> str:
    """
    Analyzes a group of TOML files. Groups them into a single entry 
    if their structural signatures match, showing values from the first file.
    """
    if not file_paths:
        return ""

    try:
        baseline_path = file_paths[0]
        baseline_sig = get_toml_signature(baseline_path)

        is_uniform = True
        for other_file in file_paths[1:]:
            if get_toml_signature(other_file) != baseline_sig:
                is_uniform = False
                break

        if is_uniform:
            parent_dir = baseline_path.parent.relative_to(PROJECT_ROOT)
            output = [f"### 📂 TOML Group: `{parent_dir}/*.toml` ({len(file_paths)} files)"]
            output.append(f"**Status:** ✅ Uniform Schema across all files.")
            
            if baseline_sig in ["_Empty file_", "_Error parsing file_"]:
                output.append(baseline_sig)
            else:
                output.append("```toml")
                output.append(generate_toml_example(baseline_path))
                output.append("```")
            return "\n".join(output)
        else:
            return "\n\n".join([analyze_single_toml(p) for p in file_paths])

    except Exception as e:
        return f"### ❌ Error analyzing TOML group in `{file_paths[0].parent}`: {e}"

def analyze_single_toml(file_path: Path) -> str:
    """
    Standard analysis for a single TOML file.
    """
    output = [f"### ⚙️ TOML: `{file_path.relative_to(PROJECT_ROOT)}`"]
    example = generate_toml_example(file_path)
    
    if example in ["_Empty file_", "_Error parsing file_"]:
        output.append(example)
    else:
        output.append("```toml")
        output.append(example)
        output.append("```")
        
    return "\n".join(output)

def generate_report():
    """
    Orchestrates the scanning process. Groups files by directory to detect 
    bulk data structures and generates a consolidated report.
    """
    print(f"Scanning modules in: {MODULES_DIR}...")
    
    report_lines = [
        "# 🗃️ OpenPower Data Schema Report", 
        "",
        "> Auto-generated snapshot of data structures. Identical files in folders are grouped.",
        ""
    ]
    
    all_files = list(MODULES_DIR.rglob("*"))
    groups: Dict[tuple, List[Path]] = {}
    
    for p in all_files:
        if p.is_dir() or p.suffix not in [".tsv", ".toml"] or p.name == "mod.toml":
            continue
        
        mod_name = p.relative_to(MODULES_DIR).parts[0]
        group_key = (mod_name, p.parent, p.suffix)
        
        if group_key not in groups:
            groups[group_key] = []
        groups[group_key].append(p)

    current_mod = ""
    sorted_group_keys = sorted(groups.keys(), key=lambda x: (x[0], str(x[1])))

    for group_key in sorted_group_keys:
        mod_name, parent_path, suffix = group_key
        file_list = sorted(groups[group_key])
        
        if mod_name != current_mod:
            current_mod = mod_name
            report_lines.append(f"\n## 📦 Module: `{mod_name}`\n---")

        if suffix == ".tsv":
            if len(file_list) > 1:
                report_lines.append(analyze_tsv_group(file_list))
            else:
                report_lines.append(analyze_single_tsv(file_list[0]))
            report_lines.append("")
            
        elif suffix == ".toml":
            if len(file_list) > 1:
                report_lines.append(analyze_toml_group(file_list))
            else:
                report_lines.append(analyze_single_toml(file_list[0]))
            report_lines.append("")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    
    print(f"✅ Schema generated at: {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_report()