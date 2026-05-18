from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from geo_matching import StreamlitGeoMatcher, compare_geo_coverage


DEFAULT_DATA_ROOT = Path(r"D:\Tencent\Data analysis\anzdata-worktree\projects\anz-bi-platform")
DEFAULT_STAGING_GEO = Path(r"D:\Tencent\Data analysis\ANZ_Data_Warehouse\data\Geo_warehouse_streamlit_staging")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare current BI geography coverage with Streamlit staging rules.")
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    parser.add_argument("--staging-geo-dir", default=str(DEFAULT_STAGING_GEO))
    parser.add_argument("--sample", type=int, default=0, help="Optional sample size for faster development checks.")
    parser.add_argument("--output-json", help="Optional path for the comparison summary JSON.")
    args = parser.parse_args()

    data_root = Path(args.data_root).expanduser()
    staging_dir = Path(args.staging_geo_dir).expanduser()
    matcher = StreamlitGeoMatcher(staging_dir)

    new_intake = _load_rows(data_root / "processed" / "new_intake" / "new_intake_rows.csv", args.sample)
    activation = _load_rows(
        data_root / "processed" / "activation_low_activity" / "activation_candidates.csv",
        args.sample,
    )

    summary = {
        "data_root": str(data_root),
        "staging_geo_dir": str(staging_dir),
        "new_intake": compare_geo_coverage(new_intake, matcher),
        "activation_low_activity": compare_geo_coverage(activation, matcher),
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
    print(payload)
    return 0


def _load_rows(path: Path, sample: int) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str).fillna("")
    if sample > 0 and sample < len(df):
        return df.sample(sample, random_state=31).reset_index(drop=True)
    return df


if __name__ == "__main__":
    raise SystemExit(main())

