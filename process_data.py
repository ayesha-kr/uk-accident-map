import pandas as pd
import json
import os
import sys
import requests

DFT_BASE = "https://data.dft.gov.uk/road-accidents-safety-data"
SOURCES = [
    ("last-5-years",     f"{DFT_BASE}/dft-road-casualty-statistics-collision-last-5-years.csv"),
    ("provisional-2025", f"{DFT_BASE}/dft-road-casualty-statistics-collision-provisional-2025.csv"),
]
OUTPUT_PATH = "accidents.json"


def download(label, url):
    dest = f"stats19_{label}.csv"
    if os.path.exists(dest):
        print(f"  Already downloaded: {dest}, skipping.")
        return dest

    print(f"  Downloading {label}...")
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    print(f"    {downloaded / total * 100:.0f}%", end="\r")
    print(f"    Done — {downloaded / 1024 / 1024:.1f} MB")
    return dest


def process(csv_paths, output_path):
    frames = []
    for path in csv_paths:
        print(f"Reading {path}...")
        df = pd.read_csv(path, low_memory=False)
        df.columns = [c.lower() for c in df.columns]
        frames.append(df)

    df = pd.concat(frames, ignore_index=True)

    # Drop duplicates — provisional 2025 may overlap with last-5-years
    if "collision_index" in df.columns:
        before = len(df)
        df = df.drop_duplicates(subset=["collision_index"])
        print(f"Removed {before - len(df)} duplicate rows")

    severity_col = "collision_severity" if "collision_severity" in df.columns else "accident_severity"
    df = df[["latitude", "longitude", severity_col, "collision_year"]].dropna()

    years = sorted(df["collision_year"].unique().astype(int))
    print(f"\nYears in data: {years}")
    print(f"Total collisions: {len(df):,}")
    print("Severity breakdown:")
    for s, label in [(1, "Fatal"), (2, "Serious"), (3, "Slight")]:
        print(f"  {label}: {len(df[df[severity_col] == s]):,}")

    severity_weight = {1: 1.0, 2: 0.6, 3: 0.3}
    df["weight"]       = df[severity_col].map(severity_weight).fillna(0.3)
    df["severity_int"] = df[severity_col].astype(int)
    df["year"]         = df["collision_year"].astype(int)

    # [lat, lng, weight, severity, year]
    data = df[["latitude", "longitude", "weight", "severity_int", "year"]].values.tolist()

    years = [int(y) for y in years]
    data  = [[float(r[0]), float(r[1]), float(r[2]), int(r[3]), int(r[4])] for r in data]
    output = {"meta": {"years": years, "total": len(data)}, "data": data}

    with open(output_path, "w") as f:
        json.dump(output, f)

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"\nSaved → {output_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        process(sys.argv[1:], OUTPUT_PATH)
    else:
        print("Downloading DfT collision data (2020–2025)...")
        paths = [download(label, url) for label, url in SOURCES]
        process(paths, OUTPUT_PATH)

    print("Next: python3 -m http.server 8080 → open http://localhost:8080")
