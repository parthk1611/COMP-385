"""Collect fixed public Ontario services with pagination and retrieval provenance."""

from pathlib import Path
import json
import hashlib
import tempfile
import zipfile
import geopandas as gpd
from datetime import datetime, timezone
import requests

SOURCES = {
    "fires": "https://ws.lioservices.lrc.gov.on.ca/arcgis3/rest/services/FFIM/Forest_Fire_Info_Map/MapServer/1",
    "districts": "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open03/MapServer/6",
}


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=path.parent,
            prefix=path.name + ".",
            suffix=".partial",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, allow_nan=False, indent=2)
            handle.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def arcgis_json(session, url, params):
    response = session.get(url, params=params, timeout=(10, 60))
    response.raise_for_status()
    result = response.json()
    if "error" in result:
        raise ValueError(
            "ArcGIS returned an error: " + str(result["error"].get("code", "unknown"))
        )
    return result


def collect_layer(kind, directory, session):
    url = SOURCES[kind]
    metadata = arcgis_json(session, url, {"f": "json"})
    oid = next(
        (
            f["name"]
            for f in metadata.get("fields", [])
            if f["type"] == "esriFieldTypeOID"
        ),
        None,
    )
    if oid is None:
        raise ValueError("Missing object-id field")
    ids = arcgis_json(
        session, url + "/query", {"f": "json", "where": "1=1", "returnIdsOnly": "true"}
    )
    if "objectIds" not in ids:
        raise ValueError("Object-id response is incomplete")
    identifiers = sorted(ids["objectIds"] or [])
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Duplicate source identifiers")
    if len(identifiers) > 20000:
        raise ValueError("Unexpected source size; review the service contract")
    features = []
    for start in range(0, len(identifiers), 500):
        data = arcgis_json(
            session,
            url + "/query",
            {
                "f": "geojson",
                "where": "1=1",
                "objectIds": ",".join(map(str, identifiers[start : start + 500])),
                "outFields": (
                    "*"
                    if kind == "fires"
                    else "OBJECTID,DISTRICT_NAME,REGION_NAME,GEOMETRY_UPDATE_DATETIME"
                ),
                "outSR": 4326,
                "returnGeometry": "true",
                "geometryPrecision": 6,
            },
        )
        if data.get("exceededTransferLimit") or data.get("type") != "FeatureCollection":
            raise ValueError("Truncated or unexpected feature response")
        features.extend(data["features"])
    found = [f.get("properties", {}).get(oid, f.get("id")) for f in features]
    if sorted(found) != identifiers:
        raise ValueError(
            "Source changed or query did not return the exact requested identifiers"
        )
    result = {"type": "FeatureCollection", "features": features}
    for name, document in [
        (kind + "_metadata.json", metadata),
        (kind + ".geojson", result),
    ]:
        atomic_json(directory / name, document)
    path = directory / (kind + ".geojson")
    record = {
        "url": url,
        "retrieved_at_utc": now_utc(),
        "features": len(features),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "geometry_type": metadata.get("geometryType"),
        "service_last_edit": metadata.get("editingInfo", {}).get("lastEditDate"),
        "retrieval_is_not_incident_observation_time": True,
    }
    return result, record


ARCHIVE_URL = "https://ws.gisetl.lrc.gov.on.ca/fmedatadownload/Packages/MNRDIST.zip"


def district_archive(cache, session):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / "MNRDIST.zip"
    manifest = cache / "manifest.json"
    if manifest.exists():
        record = json.loads(manifest.read_text())
        if hashlib.sha256(archive.read_bytes()).hexdigest() != record["archive_sha256"]:
            raise ValueError("Pinned district archive changed")
        return archive, record
    response = session.get(ARCHIVE_URL, timeout=(10, 60))
    response.raise_for_status()
    if len(response.content) > 100_000_000:
        raise ValueError("Unexpected district archive size")
    archive.write_bytes(response.content)
    with zipfile.ZipFile(archive) as z:
        packages = sorted(
            {str(Path(n).parent) for n in z.namelist() if n.endswith(".shp")}
        )
    record = {
        "url": ARCHIVE_URL,
        "retrieved_at_utc": now_utc(),
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "package_directories": packages,
        "role": "Dated administrative reference; not verified evacuation boundaries",
    }
    atomic_json(manifest, record)
    return archive, record


def load_district_archive(archive, directory):
    folder = directory / "district_shape"
    folder.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        wanted = [
            n
            for n in z.namelist()
            if Path(n).suffix.lower() in (".shp", ".shx", ".dbf", ".prj")
        ]
        if sum(z.getinfo(n).file_size for n in wanted) > 300_000_000:
            raise ValueError("Unexpected extracted boundary size")
        for name in wanted:
            (folder / Path(name).name).write_bytes(z.read(name))
    paths = list(folder.glob("*.shp"))
    if len(paths) != 1:
        raise ValueError("Expected one district layer")
    frame = gpd.read_file(paths[0])
    if frame.crs is None or frame.OGF_ID.duplicated().any():
        raise ValueError("Invalid district CRS or identities")
    frame = frame.rename(
        columns={
            "OGF_ID": "OBJECTID",
            "DIST_NAME": "DISTRICT_NAME",
            "REG_NAME": "REGION_NAME",
        }
    )
    result = json.loads(frame.to_crs(4326).to_json(drop_id=True))
    atomic_json(directory / "districts.geojson", result)
    return result, {
        "features": len(frame),
        "geometry_record_dates": sorted(frame.GEO_UPD_DT.unique().tolist()),
        "sha256": hashlib.sha256(
            (directory / "districts.geojson").read_bytes()
        ).hexdigest(),
    }


def collect(directory, boundary_cache):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    with requests.Session() as session:
        fires, fire_record = collect_layer("fires", directory, session)
        archive, archive_record = district_archive(boundary_cache, session)
        districts, district_record = load_district_archive(archive, directory)
    records = {"fires": fire_record, "districts": {**archive_record, **district_record}}
    atomic_json(directory / "sources.json", records)
    return {"fires": fires, "districts": districts}, records
