import argparse
import io
from pathlib import Path

import requests
import pycountry
from PIL import Image

# --- CONFIGURATION ---
# The directory where processed flags will be stored
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "modules" / "base" / "assets" / "flags"
# Standardized dimensions for game UI (Width x Height)
TARGET_SIZE = (450, 300)  
# Source URL: FlagCDN provides high-quality SVG/PNG flags
CDN_URL_TEMPLATE = "https://flagcdn.com/w640/{iso2}.png"
# FlagCDN's XK flag asset maps to the game's KOS country code.
# Asset: https://flagcdn.com/w640/xk.png
# Design reference: Kosovo Law No. 03/L-038, Official Gazette.
# https://gzk.rks-gov.net/ActDocumentDetail.aspx?ActID=2517
SPECIAL_COUNTRY_CODES = {"KOS": "xk"}

class FlagProcessor:
    """
    A utility class to download world flags, resize them to a uniform 
    standard, and rename them using ISO 3166-1 alpha-3 codes.
    """
    
    def __init__(self, output_dir: Path = OUTPUT_DIR):
        """Initializes the output directory and fetches the country list."""
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Filter pycountry list to ensure every entry has both alpha_2 and alpha_3
        self.countries = [
            c for c in pycountry.countries 
            if hasattr(c, 'alpha_2') and hasattr(c, 'alpha_3')
        ]
        # Use a session for better performance with multiple requests
        self.session = requests.Session()

    def run(self):
        """Iterates through all countries and initiates the processing pipeline."""
        print(f"Starting processing for {len(self.countries)} countries...")
        print(f"Method: Forced Resize to {TARGET_SIZE[0]}x{TARGET_SIZE[1]}")
        print("The entire image will be preserved (no cropping).\n")

        success_count = 0
        for country in self.countries:
            iso2 = country.alpha_2.lower() # type: ignore (false positive)
            iso3 = country.alpha_3.upper() # type: ignore (false positive)
            
            if self.download_and_resize(iso2, iso3):
                print(f"[OK] {iso3}")
                success_count += 1
            else:
                print(f"[FAIL] {iso3}")

        processed_codes = {
            country.alpha_3.upper() for country in self.countries
        }
        for iso3, iso2 in SPECIAL_COUNTRY_CODES.items():
            if iso3 in processed_codes:
                continue
            if self.download_and_resize(iso2, iso3):
                print(f"[OK] {iso3}")
                success_count += 1
            else:
                print(f"[FAIL] {iso3}")

        print(f"\nTask Complete! Processed {success_count} flags.")

    def download_and_resize(self, iso2, iso3):
        """
        Downloads a specific flag, converts color modes if necessary,
        resizes it, and saves it with PNG optimization.
        """
        url = CDN_URL_TEMPLATE.format(iso2=iso2)
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code != 200:
                return False

            with Image.open(io.BytesIO(response.content)) as img:
                # Convert Paletted (P) or Grayscale (L) images to RGBA to ensure 
                # high-quality color space for resizing.
                if img.mode in ("P", "L"):
                    img = img.convert("RGBA")
                
                # We use .resize() instead of .fit() or .thumbnail() to ensure
                # every flag occupies the exact same dimensions in the game UI.
                # Note: This may slightly stretch/squash flags with non-3:2 ratios.
                final_img = img.resize(TARGET_SIZE, Image.Resampling.LANCZOS)
                
                save_path = self.output_dir / f"{iso3}.png"
                
                # Save with maximum compression to minimize game asset size.
                final_img.save(
                    save_path, 
                    "PNG", 
                    optimize=True, 
                    compress_level=9
                )
                return True
        except Exception as e:
            print(f"Error processing {iso3}: {e}")
            return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate OpenPower country flags.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Override the base game flags directory.")
    FlagProcessor(parser.parse_args().output_dir).run()
