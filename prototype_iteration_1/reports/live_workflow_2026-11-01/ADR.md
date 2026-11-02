# ADR: Connect live observations, research spread and regional notices

Status: Accepted for local research implementation; no operational qualification.
Date: 2026-11-01

Keep 10 km ignition and 90 m spread separate. Add a fixed-URL Ontario ArcGIS collector, current HRDPS weather collection using the existing adapter, and indexed intersections with the dated 2023 MNR administrative districts. Match source times explicitly. Report active-fire points as observations; do not invent active perimeters or apply historical models to new weather.

Use existing saved reconstruction footprints for a labelled end-to-end demonstration of area intersections and local draft alerts. Actual live model outputs remain unavailable under the existing qualification decision. Source labels/causes remain reported attributes, not model predictions.

Store local notices/drafts in SQLite with deterministic identity and revision hashes. Publish a complete snapshot atomically after successful collection. Keep failed refresh evidence separate; a stale prior snapshot is visibly stale. Expose a read-only local API/page; no outbound message delivery. No paid service, LLM, new frontend framework, production deployment or scheduling automation is needed.

Alternatives: a new streaming service adds infrastructure without correcting model/source limitations; relabelling replay as live would invalidate evidence. A plain static report would not exercise region intersections or idempotent notice handling.

Measure existing request latency before optimizing. Cache keyed Parquet reads and indexed explanation JSON only while the local file identity is unchanged; preserve response values and invalidate on file changes. Review language for unsupported claims, vague risk bands and emergency instructions. Test source failures, truncation, geometry/time handling, stale snapshots, deduplication and the unavailable live response.
