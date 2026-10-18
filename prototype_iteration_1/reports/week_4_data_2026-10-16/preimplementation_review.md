# Week 4 data preparation - implementation review

Reviewed October 16, 2026 before the new build. Preserve the existing v1 inputs, fitted experiments and reserved evaluation partitions. This increment produces a separate candidate weather layer for 2010-2017 development dates, not an automatic model/data promotion.

Replace the historical global four-station preselection with the four nearest stations actually reporting finite nonnegative FWI on each previous observation date, within a declared 200 km maximum. Use spherical distance (Earth radius 6371.0088 km), inverse squared distance with a 1 km floor, variable-specific finite/range checks and explicit missingness/quality flags. Report 100/200/300 km coverage sensitivity without choosing the radius from labels or validation performance. This is a pragmatic research support radius, not a meteorological validation or an operational interpolation standard. Seven-day rain requires seven consecutive valid daily values. Do not fill missing stations/weather with zero or use same/future-day observations.

The pinned archive contains a concatenated overlapping extract. Stable date/station deduplication will prefer the first finite nonnegative-FWI record in physical source order. Record duplicate counts and invalid measurements. This deliberately fixes the globally preselected inactive station problem without fabricating availability timestamps. It remains a historical hindcast.

Generate a separate full candidate grid using centroid coverage of the current downloaded non-OFR boundary, with no fire inputs. The old pinned boundary GeoJSON is absent locally. Therefore this is a current-boundary sensitivity scenario, not exact recovery of the old boundary or a claimed historically available 2010 mask. Retain differences and excluded development labels as audit evidence only; do not replace v1 labels or edit reserved selectors.

Verify all 11 provincial 2025 ERA5 input hashes and metadata, separately from the 2010-2017 weather correction. Do not backfill modern data into the historical benchmark. The provincial converter/join, selected static fractions, source eligibility and live HRDPS/FWI bridge remain separate Week 4 work.

Acceptance for this increment: synthetic tests for daily station availability, distance caps, finite/range checks, IDW and missing precipitation; complete development-weather keys/counts; strict previous-day timing; frozen input hashes unchanged; original partitions and models preserved. Geographic/domain and model performance need later sensitivity evaluation before candidate promotion.
