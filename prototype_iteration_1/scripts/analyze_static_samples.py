from __future__ import annotations

import json
import math
import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio
import seaborn as sns
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "reports" / "figures"
REPORT = ROOT / "reports" / "static_dataset_eda.md"

MODEL_CRS = "EPSG:3978"
INTERMEDIATE_RESOLUTION_M = 100
CELL_SIZE_M = 2_500
CELLS_PER_SIDE = 12
PIXELS_PER_CELL = CELL_SIZE_M // INTERMEDIATE_RESOLUTION_M

FBP_CODE_NAMES = {
    1: "C-1 Spruce-Lichen Woodland",
    2: "C-2 Boreal Spruce",
    3: "C-3 Mature Jack or Lodgepole Pine",
    4: "C-4 Immature Jack or Lodgepole Pine",
    5: "C-5 Red and White Pine",
    7: "C-7 Ponderosa Pine / Douglas Fir",
    11: "D-1 Leafless Aspen",
    13: "D-1/D-2 Aspen",
    31: "O-1a Matted Grass",
    101: "Non-fuel",
    102: "Water",
    105: "Vegetated Non-Fuel",
    415: "M-1 Boreal Mixedwood Leafless (15% Conifer)",
    625: "M-1/M-2 Boreal Mixedwood (25% Conifer)",
    650: "M-1/M-2 Boreal Mixedwood (50% Conifer)",
    675: "M-1/M-2 Boreal Mixedwood (75% Conifer)",
}

FUEL_GROUP_CODES = {
    "conifer": {1, 2, 3, 4, 5, 7},
    "deciduous": {11, 13},
    "open": {31},
    "mixedwood": {415, 625, 650, 675},
    "nonfuel": {101, 105},
    "water": {102},
}

SPECIES_LAYERS = {
    "balsam_fir_pct": "scanfi_balsam_fir_2020.tif",
    "black_spruce_pct": "scanfi_black_spruce_2020.tif",
    "broadleaf_pct": "scanfi_broadleaf_2020.tif",
    "jack_pine_pct": "scanfi_jack_pine_2020.tif",
    "other_conifer_pct": "scanfi_other_conifer_2020.tif",
    "tamarack_pct": "scanfi_tamarack_2020.tif",
    "white_red_pine_pct": "scanfi_white_red_pine_2020.tif",
}

GROUP_COLORS = {
    "conifer": "#31572c",
    "deciduous": "#90a955",
    "open": "#e9c46a",
    "mixedwood": "#6a994e",
    "nonfuel": "#9e9e9e",
    "water": "#457b9d",
    "unknown": "#ffffff",
}


def grid_from_bounds(
    bounds: tuple[float, float, float, float], resolution: int
) -> tuple[rasterio.Affine, int, int]:
    left, bottom, right, top = bounds
    width = round((right - left) / resolution)
    height = round((top - bottom) / resolution)
    return from_origin(left, top, resolution, resolution), width, height


def reproject_file(
    path: Path,
    bounds: tuple[float, float, float, float],
    resampling: Resampling,
) -> np.ndarray:
    transform, width, height = grid_from_bounds(bounds, INTERMEDIATE_RESOLUTION_M)
    destination = np.full((height, width), np.nan, dtype="float32")
    with rasterio.open(path) as source:
        reproject(
            source=rasterio.band(source, 1),
            destination=destination,
            src_transform=source.transform,
            src_crs=source.crs,
            src_nodata=source.nodata,
            dst_transform=transform,
            dst_crs=MODEL_CRS,
            dst_nodata=np.nan,
            resampling=resampling,
        )
    return destination


def reproject_array(
    source_array: np.ndarray,
    source_transform: rasterio.Affine,
    source_crs: rasterio.crs.CRS,
    bounds: tuple[float, float, float, float],
    resampling: Resampling,
) -> np.ndarray:
    transform, width, height = grid_from_bounds(bounds, INTERMEDIATE_RESOLUTION_M)
    destination = np.full((height, width), np.nan, dtype="float32")
    reproject(
        source=source_array.astype("float32"),
        destination=destination,
        src_transform=source_transform,
        src_crs=source_crs,
        src_nodata=np.nan,
        dst_transform=transform,
        dst_crs=MODEL_CRS,
        dst_nodata=np.nan,
        resampling=resampling,
    )
    return destination


def terrain_layers(
    path: Path, bounds: tuple[float, float, float, float]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    with rasterio.open(path) as source:
        elevation = source.read(1, masked=True).filled(np.nan).astype("float32")
        x_spacing = abs(source.transform.a)
        y_spacing = abs(source.transform.e)
        dz_dy, dz_dx = np.gradient(elevation, y_spacing, x_spacing)
        slope = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))
        aspect_radians = np.arctan2(dz_dx, -dz_dy)
        aspect_sin = np.sin(aspect_radians)
        aspect_cos = np.cos(aspect_radians)
        profile = source.transform, source.crs

    return (
        reproject_file(path, bounds, Resampling.average),
        reproject_array(slope, *profile, bounds, Resampling.average),
        reproject_array(aspect_sin, *profile, bounds, Resampling.average),
        reproject_array(aspect_cos, *profile, bounds, Resampling.average),
    )


def block_view(array: np.ndarray) -> np.ndarray:
    expected = CELLS_PER_SIDE * PIXELS_PER_CELL
    if array.shape != (expected, expected):
        raise ValueError(f"Expected {(expected, expected)}, received {array.shape}")
    return array.reshape(
        CELLS_PER_SIDE,
        PIXELS_PER_CELL,
        CELLS_PER_SIDE,
        PIXELS_PER_CELL,
    ).transpose(0, 2, 1, 3)


def block_mean(array: np.ndarray) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        return np.nanmean(block_view(array), axis=(2, 3))


def block_max(array: np.ndarray) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        return np.nanmax(block_view(array), axis=(2, 3))


def block_valid_fraction(array: np.ndarray) -> np.ndarray:
    return np.isfinite(block_view(array)).mean(axis=(2, 3))


def dominant_code(block: np.ndarray) -> int | None:
    values = block[np.isfinite(block)].astype(int)
    if not len(values):
        return None
    codes, counts = np.unique(values, return_counts=True)
    return int(codes[np.argmax(counts)])


def fuel_group(code: int | None) -> str:
    if code is None:
        return "unknown"
    for group, codes in FUEL_GROUP_CODES.items():
        if code in codes:
            return group
    return "unknown"


def fuel_cell_features(fbp: np.ndarray) -> list[dict[str, float | int | str | None]]:
    features: list[dict[str, float | int | str | None]] = []
    for row in block_view(fbp):
        for block in row:
            values = block[np.isfinite(block)].astype(int)
            code = dominant_code(block)
            record: dict[str, float | int | str | None] = {
                "fbp_dominant_code": code,
                "fbp_dominant_name": FBP_CODE_NAMES.get(code, "Unknown"),
                "fuel_dominant_group": fuel_group(code),
                "fbp_valid_fraction": len(values) / block.size,
            }
            denominator = len(values)
            for group, codes in FUEL_GROUP_CODES.items():
                record[f"fuel_{group}_share"] = (
                    float(np.isin(values, list(codes)).sum() / denominator)
                    if denominator
                    else math.nan
                )
            features.append(record)
    return features


def analyze_place(
    place: str,
    bounds: tuple[float, float, float, float],
) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    place_root = RAW / "samples" / place
    fbp = reproject_file(place_root / "fbp_2024.tif", bounds, Resampling.nearest)
    layers = {
        "closure_1985_pct": reproject_file(
            place_root / "scanfi_closure_1985.tif", bounds, Resampling.average
        ),
        "closure_2020_pct": reproject_file(
            place_root / "scanfi_closure_2020.tif", bounds, Resampling.average
        ),
        "closure_2025_pct": reproject_file(
            place_root / "scanfi_closure_2025.tif", bounds, Resampling.average
        ),
        "height_2020_m": reproject_file(
            place_root / "scanfi_height_2020.tif", bounds, Resampling.average
        ),
    }
    for column, filename in SPECIES_LAYERS.items():
        layers[column] = reproject_file(
            place_root / filename, bounds, Resampling.average
        )

    conifer_columns = [column for column in SPECIES_LAYERS if column != "broadleaf_pct"]
    conifer_stack = np.stack([layers[column] for column in conifer_columns])
    layers["conifer_crown_closure_pct"] = np.nansum(conifer_stack, axis=0)
    all_species = layers["conifer_crown_closure_pct"] + layers["broadleaf_pct"]
    layers["conifer_share_pct"] = np.divide(
        layers["conifer_crown_closure_pct"] * 100,
        all_species,
        out=np.full_like(all_species, np.nan),
        where=all_species > 0,
    )

    elevation, slope, aspect_sin, aspect_cos = terrain_layers(
        place_root / "mrdem_dtm.tif", bounds
    )
    layers.update(
        {
            "elevation_m": elevation,
            "slope_degrees": slope,
            "aspect_sin": aspect_sin,
            "aspect_cos": aspect_cos,
        }
    )

    fuel_records = fuel_cell_features(fbp)
    continuous = {name: block_mean(array).ravel() for name, array in layers.items()}
    continuous["slope_max_degrees"] = block_max(slope).ravel()
    continuous["scanfi_valid_fraction"] = block_valid_fraction(
        layers["closure_2020_pct"]
    ).ravel()
    continuous["mrdem_valid_fraction"] = block_valid_fraction(elevation).ravel()

    left, bottom, _, top = bounds
    rows: list[dict[str, object]] = []
    to_lon_lat = Transformer.from_crs(MODEL_CRS, "EPSG:4326", always_xy=True)
    for row_index in range(CELLS_PER_SIDE):
        for column_index in range(CELLS_PER_SIDE):
            index = row_index * CELLS_PER_SIDE + column_index
            x = left + (column_index + 0.5) * CELL_SIZE_M
            y = top - (row_index + 0.5) * CELL_SIZE_M
            longitude, latitude = to_lon_lat.transform(x, y)
            record: dict[str, object] = {
                "cell_id": f"{place}_{row_index:02d}_{column_index:02d}",
                "place": place,
                "grid_row": row_index,
                "grid_column": column_index,
                "x_epsg3978": x,
                "y_epsg3978": y,
                "longitude": longitude,
                "latitude": latitude,
            }
            record.update(fuel_records[index])
            record.update({name: values[index] for name, values in continuous.items()})
            rows.append(record)

    frame = pd.DataFrame(rows)
    frame["closure_change_1985_2020_pct_points"] = (
        frame["closure_2020_pct"] - frame["closure_1985_pct"]
    )
    frame["closure_change_2020_2025_pct_points"] = (
        frame["closure_2025_pct"] - frame["closure_2020_pct"]
    )
    aspect_radians = np.arctan2(frame["aspect_sin"], frame["aspect_cos"])
    frame["aspect_degrees"] = np.degrees(aspect_radians) % 360
    return frame, {"fbp": fbp, **layers}


def fuel_distribution(places: list[str]) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for place in places:
        with rasterio.open(RAW / "samples" / place / "fbp_2024.tif") as source:
            values = source.read(1, masked=True).compressed().astype(int)
        codes, counts = np.unique(values, return_counts=True)
        for code, count in zip(codes, counts, strict=True):
            records.append(
                {
                    "place": place,
                    "fbp_code": int(code),
                    "fbp_name": FBP_CODE_NAMES.get(int(code), "Unknown"),
                    "fuel_group": fuel_group(int(code)),
                    "pixel_count": int(count),
                    "area_km2": float(count * 30 * 30 / 1_000_000),
                    "share": float(count / len(values)),
                }
            )
    return pd.DataFrame(records)


def analyze_boundary() -> tuple[pd.DataFrame, dict[str, float | int | str]]:
    zones = gpd.read_file(RAW / "boundaries" / "fire_management_zones.geojson")
    projected = zones.to_crs(MODEL_CRS)
    projected["area_km2"] = projected.geometry.area / 1_000_000
    designation = (
        projected.groupby("FMZ_DESIGNATION", as_index=False)
        .agg(feature_count=("OGF_ID", "size"), summed_area_km2=("area_km2", "sum"))
        .sort_values("summed_area_km2", ascending=False)
    )
    union = projected.geometry.union_all()
    summed_area = projected["area_km2"].sum()
    union_area = union.area / 1_000_000
    business_dates = pd.to_datetime(
        zones["BUSINESS_EFFECTIVE_DATE"], unit="ms", errors="coerce"
    )
    metrics: dict[str, float | int | str] = {
        "feature_count": len(zones),
        "unique_ogf_ids": int(zones["OGF_ID"].nunique()),
        "invalid_geometry_count": int((~zones.geometry.is_valid).sum()),
        "duplicate_geometry_count": int(zones.geometry.to_wkb().duplicated().sum()),
        "summed_feature_area_km2": float(summed_area),
        "union_area_km2": float(union_area),
        "overlap_area_km2": float(summed_area - union_area),
        "business_effective_date_min": str(business_dates.min().date()),
        "business_effective_date_max": str(business_dates.max().date()),
        "geometry_update_non_null": int(zones["GEOMETRY_UPDATE_DATETIME"].notna().sum()),
    }
    return designation, metrics


def save_figures(
    features: pd.DataFrame,
    arrays_by_place: dict[str, dict[str, np.ndarray]],
    fuel: pd.DataFrame,
) -> None:
    sns.set_theme(style="whitegrid")
    places = list(arrays_by_place)
    group_order = list(FUEL_GROUP_CODES)
    group_to_number = {group: index for index, group in enumerate(group_order)}
    cmap = ListedColormap([GROUP_COLORS[group] for group in group_order])

    figure, axes = plt.subplots(len(places), 4, figsize=(16, 11), constrained_layout=True)
    for row, place in enumerate(places):
        frame = features[features["place"] == place]
        fuel_grid = np.array(
            [group_to_number.get(value, np.nan) for value in frame["fuel_dominant_group"]]
        ).reshape(CELLS_PER_SIDE, CELLS_PER_SIDE)
        panels = [
            (fuel_grid, "Dominant fuel group", cmap, -0.5, len(group_order) - 0.5),
            (block_mean(arrays_by_place[place]["closure_2020_pct"]), "Canopy closure 2020 (%)", "YlGn", 0, 100),
            (block_mean(arrays_by_place[place]["elevation_m"]), "Elevation (m)", "terrain", None, None),
            (block_mean(arrays_by_place[place]["slope_degrees"]), "Slope (degrees)", "magma", 0, None),
        ]
        for column, (array, title, panel_cmap, vmin, vmax) in enumerate(panels):
            image = axes[row, column].imshow(array, cmap=panel_cmap, vmin=vmin, vmax=vmax)
            axes[row, column].set_title(f"{place.replace('_', ' ').title()} — {title}")
            axes[row, column].set_xticks([])
            axes[row, column].set_yticks([])
            if column > 0:
                figure.colorbar(image, ax=axes[row, column], shrink=0.72)
    figure.suptitle("Static predictor pilot samples (2.5 km cells)", fontsize=16)
    figure.legend(
        handles=[Patch(color=GROUP_COLORS[group], label=group.title()) for group in group_order],
        loc="outside lower center",
        ncol=len(group_order),
        title="Dominant fuel group",
    )
    figure.savefig(FIGURES / "static_predictor_maps.png", dpi=180)
    plt.close(figure)

    grouped = fuel.groupby(["place", "fuel_group"], as_index=False)["area_km2"].sum()
    pivot = grouped.pivot(index="place", columns="fuel_group", values="area_km2").fillna(0)
    pivot = pivot.reindex(columns=group_order, fill_value=0)
    axes = pivot.plot(
        kind="bar",
        stacked=True,
        color=[GROUP_COLORS[group] for group in group_order],
        figsize=(10, 6),
    )
    axes.set_ylabel("Mapped area (km²)")
    axes.set_xlabel("")
    axes.set_xticklabels([label.get_text().replace("_", " ").title() for label in axes.get_xticklabels()])
    axes.set_title("FBP 2024 fuel composition in pilot samples")
    axes.legend(title="Fuel group", bbox_to_anchor=(1.02, 1), loc="upper left")
    axes.figure.tight_layout()
    axes.figure.savefig(FIGURES / "fuel_composition.png", dpi=180)
    plt.close(axes.figure)

    closure = features.melt(
        id_vars="place",
        value_vars=["closure_1985_pct", "closure_2020_pct", "closure_2025_pct"],
        var_name="year",
        value_name="canopy_closure_pct",
    )
    closure["year"] = closure["year"].str.extract(r"(\d{4})").astype(int)
    closure["place"] = closure["place"].str.replace("_", " ").str.title()
    figure, axis = plt.subplots(figsize=(9, 5))
    sns.pointplot(
        data=closure,
        x="year",
        y="canopy_closure_pct",
        hue="place",
        errorbar=("ci", 95),
        ax=axis,
    )
    axis.set_title("Descriptive SCANFI canopy-closure comparison")
    axis.set_ylabel("Mean canopy closure (%)")
    axis.set_xlabel("SCANFI reference year")
    figure.tight_layout()
    figure.savefig(FIGURES / "closure_comparison.png", dpi=180)
    plt.close(figure)

    zones = gpd.read_file(RAW / "boundaries" / "fire_management_zones.geojson").to_crs(MODEL_CRS)
    figure, axis = plt.subplots(figsize=(9, 10))
    zones.plot(column="FMZ_DESIGNATION", categorical=True, legend=True, ax=axis, linewidth=0.2)
    axis.set_axis_off()
    axis.set_title("Historical Ontario Fire Management Zones")
    figure.tight_layout()
    figure.savefig(FIGURES / "historical_fire_management_zones.png", dpi=180)
    plt.close(figure)


def build_report(
    features: pd.DataFrame,
    fuel: pd.DataFrame,
    designation: pd.DataFrame,
    boundary_metrics: dict[str, float | int | str],
) -> str:
    summary = features.groupby("place").agg(
        cells=("cell_id", "size"),
        canopy_2020_mean_pct=("closure_2020_pct", "mean"),
        canopy_change_1985_2020_pp=("closure_change_1985_2020_pct_points", "mean"),
        canopy_change_2020_2025_pp=("closure_change_2020_2025_pct_points", "mean"),
        height_2020_mean_m=("height_2020_m", "mean"),
        conifer_share_mean_pct=("conifer_share_pct", "mean"),
        elevation_mean_m=("elevation_m", "mean"),
        slope_mean_degrees=("slope_degrees", "mean"),
        slope_peak_100m_degrees=("slope_max_degrees", "max"),
    )
    summary = summary.round(2)

    group_area = fuel.groupby(["place", "fuel_group"])["area_km2"].sum()
    dominant_groups = group_area.groupby(level=0).idxmax().map(lambda value: value[1])
    dominant_shares = (
        group_area.groupby(level=0).max() / group_area.groupby(level=0).sum() * 100
    )

    numeric_for_correlation = features[
        [
            "closure_2020_pct",
            "height_2020_m",
            "conifer_share_pct",
            "elevation_m",
            "slope_degrees",
        ]
    ]
    correlations = numeric_for_correlation.corr().round(3)
    strongest_pairs = (
        correlations.where(np.triu(np.ones(correlations.shape), k=1).astype(bool))
        .stack()
        .sort_values(key=np.abs, ascending=False)
    )
    strongest_text = ", ".join(
        f"{left} vs {right}: r={value:.2f}"
        for (left, right), value in strongest_pairs.head(3).items()
    )

    fuel_findings = "\n".join(
        f"- {place.replace('_', ' ').title()}: {dominant_groups[place]} is the largest mapped group ({dominant_shares[place]:.1f}% of valid sampled map pixels)."
        for place in summary.index
    )
    completeness = features[
        ["fbp_valid_fraction", "scanfi_valid_fraction", "mrdem_valid_fraction"]
    ].mean().mul(100)
    share_sum = features[[f"fuel_{group}_share" for group in FUEL_GROUP_CODES]].sum(axis=1)

    return f"""# Static dataset exploratory analysis

## Scope

This is a reproducible pilot analysis of three 30 km × 30 km samples centred near Red Lake, Thunder Bay, and Timmins. It produces {len(features):,} model-ready 2.5 km cells covering 2,700 km². It does **not** estimate province-wide prevalence and it does not train a fire model because no fire-outcome labels are joined yet.

## Main findings

{fuel_findings}
- Mean 2020 canopy closure ranges from {summary['canopy_2020_mean_pct'].min():.1f}% to {summary['canopy_2020_mean_pct'].max():.1f}% across the three samples.
- Mean elevation ranges from {summary['elevation_mean_m'].min():.1f} m to {summary['elevation_mean_m'].max():.1f} m; the steepest derived 100 m slope in the pilot is {summary['slope_peak_100m_degrees'].max():.1f}°.
- Strongest pooled descriptive relationships at 2.5 km are {strongest_text}. These are associations among predictors, not relationships with wildfire occurrence.
- SCANFI canopy differences are descriptive only. The product documentation warns that the time series is not designed for fine local trend validation; 2025 layers would also leak future information into models trained for earlier fire years.

## Place summary

{summary.to_markdown()}

## Data quality and engineering conclusions

- Mean valid coverage: FBP {completeness['fbp_valid_fraction']:.2f}%, SCANFI {completeness['scanfi_valid_fraction']:.2f}%, MRDEM {completeness['mrdem_valid_fraction']:.2f}%.
- Fuel-group shares sum to 1 within floating-point tolerance for {int(np.isclose(share_sum, 1, atol=1e-6).sum())} of {len(features)} cells.
- SCANFI v2 uses a custom NAD83 Canada Lambert definition with latitude of origin 0°. It must be reprojected; assigning EPSG:3978 without reprojection would displace the data by thousands of kilometres.
- MRDEM provides elevation, not ready-made slope/aspect. This pipeline derives slope and circular aspect features before 2.5 km aggregation.
- The FBP map is categorical, so nearest-neighbour resampling is used. Continuous SCANFI and MRDEM layers use area-average resampling.

## Historical boundary audit

- Features: {boundary_metrics['feature_count']}; unique OGF IDs: {boundary_metrics['unique_ogf_ids']}; invalid geometries: {boundary_metrics['invalid_geometry_count']}; duplicate geometries: {boundary_metrics['duplicate_geometry_count']}.
- Summed feature area: {boundary_metrics['summed_feature_area_km2']:,.0f} km²; dissolved union: {boundary_metrics['union_area_km2']:,.0f} km²; overlap: {boundary_metrics['overlap_area_km2']:,.0f} km².
- Business-effective dates: {boundary_metrics['business_effective_date_min']} to {boundary_metrics['business_effective_date_max']}; non-null geometry update timestamps: {boundary_metrics['geometry_update_non_null']}.
- This layer is explicitly historical and was replaced by Ontario's response-based strategy in 2014. It is acceptable as a reproducible coarse study mask only after dissolving overlaps; it should not be described as the current operational fire-management boundary.

{designation.round(1).to_markdown(index=False)}

## Correlations among candidate static predictors

{correlations.to_markdown()}

## Recommended LightGBM use

Join these static features to a space-time table keyed by 2.5 km cell and date. The target `y` should be a clearly defined future event, such as `fire_start_next_24h`. Keep FBP, terrain, and era-appropriate SCANFI values as predictors; add lagged weather, FWI, lightning, roads, and historical fire labels. Split by both year and geographic blocks, then compare LightGBM against a simple logistic-regression baseline using PR-AUC, recall at an operational alert budget, calibration, and spatial holdout performance.

Do not use final fire size, final perimeter, future hotspots, suppression outcomes, or any raster vintage published after the prediction date as features.

## Produced artifacts

- `data/processed/static_features_2500m.parquet` and `.csv`: one row per pilot grid cell.
- `data/processed/fuel_distribution.csv`: native 30 m FBP composition.
- `data/processed/fire_management_zone_summary.csv`: boundary designation audit.
- `data/processed/validation_summary.json`: machine-readable QA metrics.
- `reports/figures/`: fuel, canopy, terrain, and boundary figures.
"""


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((RAW / "samples" / "manifest.json").read_text())
    places = list(manifest["places"])

    feature_frames: list[pd.DataFrame] = []
    arrays_by_place: dict[str, dict[str, np.ndarray]] = {}
    for place in places:
        bounds = tuple(manifest["places"][place]["bounds_model_crs"])
        frame, arrays = analyze_place(place, bounds)
        feature_frames.append(frame)
        arrays_by_place[place] = arrays
        print(f"Analyzed {place}: {len(frame)} cells", flush=True)

    features = pd.concat(feature_frames, ignore_index=True)
    fuel = fuel_distribution(places)
    designation, boundary_metrics = analyze_boundary()

    features.to_csv(PROCESSED / "static_features_2500m.csv", index=False)
    features.to_parquet(PROCESSED / "static_features_2500m.parquet", index=False)
    fuel.to_csv(PROCESSED / "fuel_distribution.csv", index=False)
    designation.to_csv(PROCESSED / "fire_management_zone_summary.csv", index=False)

    validation = {
        "rows": len(features),
        "unique_cell_ids": int(features["cell_id"].nunique()),
        "places": places,
        "fuel_share_sum_failures": int(
            (~np.isclose(
                features[[f"fuel_{group}_share" for group in FUEL_GROUP_CODES]].sum(axis=1),
                1,
                atol=1e-6,
            )).sum()
        ),
        "closure_out_of_range": int(
            ((features["closure_2020_pct"] < 0) | (features["closure_2020_pct"] > 100)).sum()
        ),
        "negative_height_count": int((features["height_2020_m"] < 0).sum()),
        "negative_slope_count": int((features["slope_degrees"] < 0).sum()),
        "boundary": boundary_metrics,
    }
    (PROCESSED / "validation_summary.json").write_text(
        json.dumps(validation, indent=2) + "\n"
    )
    save_figures(features, arrays_by_place, fuel)
    REPORT.write_text(build_report(features, fuel, designation, boundary_metrics))
    print(f"Wrote {len(features)} rows and report {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
