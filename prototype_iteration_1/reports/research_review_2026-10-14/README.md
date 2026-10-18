# Wildfire research and tool review

Reviewed October 14–15, 2026 for COMP 385. This is a local research attachment and development assessment; it records source findings separately from recommendations and experiments still to run.

## What the slide actually contains

The slide has **11 entries**. Ten can be connected to identifiable publications: **7 journal articles, 1 main-conference paper, 1 workshop paper and 1 government technical report**. Several publications also describe software or datasets. The remaining entry, **burn-probability maps**, names an output rather than a particular paper. A more accurate slide title would be **“Research and tools supporting the wildfire workflow.”**

The earlier count of one paper described references verified in the previously inspected repository/deck, not this research slide. That count was incomplete for the team's full research list.

| Slide entry | Verified identity | Classification | Review depth |
| --- | --- | --- | --- |
| Cell2Fire (2021) | Pais et al.; DOI 10.3389/ffgc.2021.692706 | Journal research paper + simulator | Full text available; methods, validation, assumptions and conclusions reviewed. |
| C2F-K (Chile) | C2FK; developer-linked Carrasco-Barra et al. paper, **2026**, DOI 10.1016/j.envsoft.2026.107009 | Simulator + journal research paper | Institutional full-text HTML reviewed: methods, results, Tables 3–4, limitations and software availability; developer interfaces also inspected. |
| Prometheus (2010) | Tymstra et al.; report NOR-X-417 | Government technical report describing a simulator | Relevant report sections reviewed through the government-hosted PDF; local PDF download unsuccessful. |
| Kim et al. (2025) | Kim, Pais and Gonzalez; DOI 10.1038/s41598-025-05706-6 | Journal research paper + accompanying code | Full text available; experiments, optimization and operational limits reviewed. |
| PyTorchFire (2025) | Xia and Cheng; DOI 10.1016/j.envsoft.2025.106401 | Journal research paper + software | Full text, README, package requirements, model and trainer source inspected. |
| JaxWildfire (2025) | Çakır et al.; NeurIPS ML4PS workshop; arXiv 2512.06102 | Workshop research paper + proposed software | Workshop paper reviewed; public repository has no simulator implementation at the inspected commit. |
| Downstream Protection Value (2021) | Pais, Carrasco, Elimbi Moudio and Shen; DOI 10.1016/j.cor.2021.105252 | Journal research paper / prioritization method | Institutional full text obtained and critically reviewed; local HTML archive and searchable text saved. |
| Burn-probability maps | Frequency of burning across a specified simulation ensemble | Output / method category | Reviewed in Cell2Fire and simulator documentation; exact separate citation unspecified. |
| Next Day Spread (2022) | Huot et al.; DOI 10.1109/TGRS.2022.3192974 | Journal dataset/benchmark paper + data/code | Journal identity verified; accessible author preprint reviewed, with its own page numbering. |
| WildfireSpreadTS (2023) | Gerard, Zhao and Sullivan; NeurIPS Datasets and Benchmarks | Peer-reviewed main-conference paper + dataset/code | Proceedings paper and current developer notes reviewed. |
| Jain review (2020) | Jain et al.; DOI 10.1139/er-2020-0019 | Peer-reviewed journal review article | Author manuscript's occurrence, data, evaluation and interpretation sections reviewed. |

For the course's two-peer-reviewed-paper requirement, use **Cell2Fire and Kim** as two original studies. Jain provides additional support for ignition modelling. The workshop paper and technical report are useful supplementary references; neither is needed to establish the minimum. Identification does not mean all publications were read cover to cover or that their results were reproduced.

## Literature review: findings, limitations and use

The following briefs, synthesis and project comparison form the completed local literature-review attachment. Page references are PDF pages in the accessible versions, not necessarily journal page numbers.

### 1. Cell2Fire: a reference for our spread engine

Pais et al. (2021) describe a modular grid simulator that uses fuel, terrain, ignition and weather/FWI information. Canadian FBP head, flank and back spread rates define directional growth between eight adjacent cells. Repeated scenarios support landscape planning.

The validation primarily tests agreement with Prometheus. Section 3.1 explicitly distinguishes that experiment from quantitative evaluation against actual fire scars. Suppression is outside the model, and spotting is discussed as future work. Thus, agreement with a reference simulator is useful implementation evidence, but not sufficient evidence of forecast skill.

**Our use:** an independent Canadian-FBP comparator for the existing 90 m spread prototype and a reference for ensemble outputs. Our shortest-travel-time algorithm and sixteen neighbours differ; calling it Cell2Fire would be inaccurate. Its adjacent-cell design also provides a useful contrast for investigating our reproduced water-barrier crossing defect. This is a project inference, not a demonstrated fix.

Evidence: [paper](https://doi.org/10.3389/ffgc.2021.692706), §§2.2–2.2.3, 3.1 and 4; PDF pp. 4–7, 11–12, 17. [Local PDF](sources/cell2fire_2021.pdf).

### 2. Kim: calibration must be separated from forecasting

Kim et al. (2025) compare Cell2Fire implementations with established simulators and historical burns. They optimize directional spread and ellipse parameters and examine weather/parameter sensitivity. For the Dogrib example, reported F1 against the observed scar increases from 0.74 to 0.83 after optimization.

That improvement is a **calibration result**, not an untouched Ontario forecast score. The authors explicitly note that real-time use can lack the burn perimeter required for optimization. Prior-fire calibration is suggested, with transferability still needing investigation.

**Our use:** motivate bounded calibration of the existing spread engine on development fires, followed by frozen-parameter testing on separate incidents. Do not optimize against the future perimeter of the incident being forecast. Our current final-perimeter-assisted fuel repair must be isolated as retrospective reconstruction. Do not copy the published adjustment values or interpret their reported score as our expected performance.

Evidence: [paper](https://doi.org/10.1038/s41598-025-05706-6), real-landscape results, discussion and optimization methods; PDF pp. 4, 7 and 9. [Local PDF](sources/kim_2025.pdf).

### 3. Jain: the strongest connection to ignition modelling

Jain et al. (2020) review 298 publications across wildfire research domains, including occurrence prediction, behaviour and management. They discuss data alignment, representative samples, model choice, spatial dependence, class imbalance and interpretation. The review does not establish one universally superior algorithm.

**Our use:** justify a simple, explainable baseline before a more complex candidate, with explicit spatial/time evaluation and uncertainty. Our historical-rate/logistic/boosting comparison remains a project experiment to conduct. The paper supports the methodology, not a claim that LightGBM has already won.

**Difference:** our target is a recorded new start in an Ontario 10 km cell on a local calendar day; a susceptibility map or existing-fire propagation model answers a different question. Keep final size/perimeters and future detections out of ignition predictors.

Evidence: [journal](https://doi.org/10.1139/er-2020-0019), §§4.3 and 5.1–5.4; accessible manuscript PDF pp. 18–19 and 30–33. [Local author manuscript](sources/jain_2020_author_manuscript.pdf).

### 4. PyTorchFire: a future differentiable spread experiment

Xia and Cheng (2025) implement a differentiable cellular automaton in PyTorch so gradients can adjust spread parameters. Experiments include synthetic targets and two real-fire cases. They explicitly describe a proof of concept rather than an operational model. The paper identifies limits in variable growth speed and missing processes such as spotting.

**Our use:** later compare gradient-based spread calibration with our current parameter search. This requires an Ontario input adapter and a physical time-step contract. A differentiable model can fit observations efficiently without producing reliable forecasts on unseen fires. Published NVIDIA timings are not measurements on this Mac.

Evidence: [paper](https://doi.org/10.1016/j.envsoft.2025.106401), §§2.3, 3 and 4; PDF pp. 5–6, 9–11 and 14. [Local PDF](sources/pytorchfire_2025.pdf). Tool-specific integration findings appear below.

### 5. JaxWildfire: future simulation and reinforcement learning

Çakır et al. (2025) use JAX to batch probabilistic cellular-automaton simulations and differentiate parameters. The workshop paper reports speed comparisons on an A100 GPU, calibration on Bear 2020, and a synthetic 20 × 20 fire-suppression learning task. Humidity and temperature effects remain proposed extensions.

**Our use:** a later research option for many-scenario simulation or intervention-policy experiments. It does not provide evidence that an operational suppression policy works in Ontario. The [public repository](https://github.com/ori-goals/JaxWildfire) currently contains a README and gitignore, with implementation release still pending. We cannot reproduce its software results from that repository today.

Evidence: [accepted workshop paper](https://ml4physicalsciences.github.io/2025/files/NeurIPS_ML4PS_2025_80.pdf), pp. 2–5 and 8; [workshop listing](https://ml4physicalsciences.github.io/2025/); [arXiv record](https://arxiv.org/abs/2512.06102). [Local workshop PDF](sources/jaxwildfire_2025.pdf).

### 6. Next Day Spread: a benchmark design, not our ignition labels

Huot et al. (2022) predict next-day active fire from an existing fire mask and environmental features. Their US data use 1 km cells and 2012–2020 observations. The accessible manuscript compares persistence, logistic regression, random forest and a convolutional network, using precision-recall evaluation and training-only normalization statistics.

**Our use:** adopt the baseline-comparison discipline and explicit handling of unknown satellite labels. A persistence baseline is appropriate for next-day active-fire masks, but differs from the project's current even-growth baseline and first-seen-cell replay target.

**Limits:** satellite detections are imperfect observations; a missing detection is not proof of no fire. Their random-week partition is not our strict forward-time deployment test. Neither their daily labels nor their scores validate our 1-/3-/6-hour outputs. US benchmark data would be a separate experiment, not an eighth selected Ontario source.

Evidence: [Google Research journal record](https://research.google/pubs/next-day-wildfire-spread-a-machine-learning-dataset-to-predict-wildfire-spreading-from-remote-sensing-data/); [author preprint](https://arxiv.org/abs/2112.02447), §§II–V and Appendix A, PDF pp. 4–8 and Table II p. 10. [Local preprint](sources/next_day_spread_2022_preprint.pdf).

### 7. WildfireSpreadTS: temporal context and careful benchmarks

Gerard et al. (2023) provide 607 US fire-event sequences, 13,607 images and 23 channels, with 375 m active-fire maps and daily targets. They compare persistence, logistic regression, U-Net, ConvLSTM and temporal attention. More inputs do not consistently improve results, supporting controlled feature/time-window ablations.

**Our use:** a later multi-day spread benchmark, retaining whole incidents and clear observation masks. Their all-permutations year evaluation is not equivalent to training only on the past. Satellite-observed active fire also differs from complete burned area and our first-detection target.

Evidence: [proceedings](https://proceedings.neurips.cc/paper_files/paper/2023/hash/ebd545176bdaa9cd5d45954947bd74b7-Abstract-Datasets_and_Benchmarks.html), §§2, 5 and 7; PDF pp. 2–4 and 7–10. [Local PDF](sources/wildfirespreadts_2023.pdf).

The [current developer README](https://github.com/SebastianGer/WildfireSpreadTS) records a corrected dataset-class bug and an unresolved angle-encoding issue: sine alone loses information, so both sine and cosine are needed. Any future reproduction must pin and review the loader version rather than blindly reproduce old code.

### 8. C2FK: useful software, Chilean fuel rules

Carrasco-Barra et al. (2026) adapt Cell2Fire to Chilean KITRAL fuels, fitting elliptical spread relationships and adding crown-fire calculations. Their study compares synthetic/heterogeneous landscapes with KITRAL and three real fires with observed scars. Table 3 reports real-fire F1 scores of **86.40%, 68.10% and 47.62%**, mean **67.37%**; mean precision is **54.96%**, recall **90.32%**. Those three runs disable crown fire and assume free burning. Therefore the high simulation-to-simulation agreement is not an operational accuracy estimate, and the real-fire experiments do not validate crown-fire predictions. The conclusion explicitly requests more empirical crown validation. The ensemble demonstration uses 1,000 scenarios on a 30 m, 250,000-cell landscape; its frequencies depend on scenario sampling and boundary extent.

**Our use:** retain the ensemble/output design as a reference for the separate 90 m spread capability. Compare precision and recall alongside overlap to expose overgrowth, and test domain boundaries. Do not transfer KITRAL fuel codes/equations to Ontario FBP or manufacture canopy bulk density, crown-base height or foliar moisture from closure alone. An Ontario adapter and held-out experiment would be separate implementation work.

**Access and provenance:** full publisher HTML accessed through Centennial Library on October 15, §§2.3–2.6, §§3.1–3.4, Table 3 and conclusions. This is a full-text reading, not a downloaded publisher PDF or a local reproduction. [Article](https://doi.org/10.1016/j.envsoft.2026.107009); [developer repository](https://github.com/fire2a/C2FK). The paper declares BSD-3-Clause but the pinned repository snapshot declares GPL-3.0; verify the exact reused version before redistribution.

### 9. Downstream Protection Value: deciding where to treat

Pais et al. (2021) construct directed propagation networks from Cell2Fire simulations, combine paths across scenarios and rank cells by downstream protection value. They formulate connected treatment selection as a mixed-integer optimization problem, with a greedy warm start. Their 65,500 simulation experiments vary landscape, weather, ignition, replications and treatment fraction. Reported reductions of **53% in spread rate and 57% in expected burned area** are relative to their closest comparator, betweenness centrality, under these experimental conditions. They are simulated treatment effects, not Ontario forecast accuracy or proven field benefits. Simulated horizons differ: 12 hours in Alberta and 24 hours in British Columbia. The model also depends on scenario credibility and treatment assumptions; changing fuels can change the network being ranked.

**Our use:** a future treatment-prioritization experiment after spread evaluation is credible. It needs explicit values at risk, candidate treatments, costs/budget and propagation scenarios. Those decision inputs are outside the seven-source predictor contract. High ignition probability does not automatically identify the best treatment location. DPV is a later optional decision layer, not a prerequisite for training our first ignition classifier.

**Access and provenance:** full publisher HTML obtained through Centennial Library on October 15; methods §§2.5–2.6, results §3 and conclusions §4 reviewed. [Article](https://doi.org/10.1016/j.cor.2021.105252); [local full-text archive](sources/dpv_2021_fulltext.mhtml); [searchable extract](sources/dpv_2021_fulltext.txt). Section references apply to the HTML edition, not invented PDF page numbers. No optimizer was installed or experiment reproduced.

### 10. Prometheus: a Canadian reference model

Tymstra et al. (2010) document a vector fire-growth simulator using Huygens-style propagation and Canadian FBP rates. The report covers fuels, topography, hourly weather/FWI, validation and calibration. It distinguishes model, user and data error and discusses sensitivity to wind and landscape representation.

**Our use:** reference Canadian input semantics and synthetic-case expectations, with an optional later simulator comparison. The report is technical literature, not a journal article. A model's output time interval does not establish the accuracy of that horizon.

Evidence: [Government of Canada record](https://publications.gc.ca/site/eng/9.568367/publication.html) and [report](https://publications.gc.ca/collections/collection_2010/nrcan/Fo133-1-417-eng.pdf), printed pp. 18–32 and 54–57 (PDF pp. 31–45 and 67–70). Relevant report sections were available in the browser; local download attempts returned archive/host errors. The report was not installed or benchmarked as software.

### 11. Burn-probability maps: an ensemble output

Cell2Fire documents per-cell burn grids across scenarios. Counting how often a cell burns yields an ensemble burn frequency **conditional on the selected ignition, weather, fuel, parameter and time-horizon assumptions**. A confidence band or probability interpretation requires a defensible ensemble, not arbitrary repetitions.

**Our use:** later uncertainty displays for the separate spread capability. Our current deterministic replay does not supply them. Do not label a scenario burn-frequency map as daily new-ignition probability. The slide supplies no author/title/year identifying an additional paper, so this entry is resolved as a method/output and excluded from the publication count. Its explicit supporting references are Cell2Fire §2.2.2 and C2FK §2.6, equation 23: number of scenarios burning a cell divided by the total scenario count. No additional unnamed paper is required to finish classifying this entry.

## Synthesis and comparison with our project

The sources support complementary questions: occurrence research asks where a new fire starts; spread simulators ask how an existing fire grows; benchmark datasets test observational predictions; DPV asks where an intervention has value. They are not ten sequential software dependencies.

The key progression between the two core studies is from matching another simulator (Pais et al., 2021) to improving agreement with real burn scars through calibration (Kim et al., 2025). Both are useful research contributions, but neither establishes our unseen-incident forecast performance. Jain et al. (2020) supplies the wider reason to align modelling units, data quality and evaluation with the actual task. The satellite benchmarks add a further distinction: the target can be the observation process, rather than complete physical fire progression.

Our contribution is a separately evaluated Ontario workflow: **10 km daily recorded-ignition risk**, alongside the existing **90 m incident-conditioned spread prototype**, using explicit issue times, source vintages, uncertainty and baseline comparisons. This is a project-specific design and evaluation contribution; it is not a claim of a novel fire-spread algorithm. The current historical ignition baseline uses NFDB/CDEM/CWFIS; modern FBP/SCANFI layers cannot silently become historical predictors. The selected seven-source scope remains separate from optional US benchmark experiments.

Immediate consequences are to reserve chronological/geographic ignition partitions, retain missingness, train the existing simple baselines, correct the spread barrier defect, isolate final-perimeter-assisted reconstruction and rerun the common spread evaluation. Additional calibration can follow on development fires. Importing a more sophisticated simulator before those checks would not resolve their underlying data/evaluation problems.

## Tool assessment and future integration

These are source/documentation assessments, **not installed-tool smoke tests or local performance benchmarks**. The exact inspected repository commits and licences are in [the repository snapshot](tool_repository_snapshot.json).

| Tool/resource | Requirements, support and cost | Proposed place in our project | Recommendation |
| --- | --- | --- | --- |
| Cell2Fire | Python/C++ core; compiler, Boost/Eigen and dependencies. GPL-3.0 repository. Documentation and example landscapes exist. Build/adaptation effort and compute are the main costs. | Export the existing spread fuel/terrain/weather/ignition inputs to its schema, then compare on the same held-out incidents. | First external simulator candidate after existing defects and evaluation contracts are resolved. No local runtime result yet. |
| C2FK | C++ build; documented macOS makefiles, GCC/OpenMP, Boost and TIFF dependencies. GPL-3.0. Chile-specific KITRAL fuel mapping. | Learn scenario repetition, raster output and propagation-message design; optional cross-engine research. | Retain as reference; Ontario fuel/equation compatibility must be demonstrated before use. |
| PyTorchFire | MIT; Python, PyTorch and tensor inputs. Inspected main requires Python >=3.12; the 2025 paper used an older environment, so pin a release. GPU compute is optional for a small feasibility trial, but published GPU speedups are not Mac guarantees. | Future differentiable spread calibration with an explicit Ontario adapter and observation losses. | Promising experiment, not a direct replacement for the current FBP model. |
| JaxWildfire | JAX/Gymnax concepts in paper; inspected public repository has no simulator code or declared software licence. | Future batched simulations/RL only if a usable release becomes available. | Defer implementation; availability is the current blocker. |
| Prometheus | Canadian FBP reference and detailed report; installer/version/platform/licence not established in this review. | Input conventions and optional comparator. | Use the report now; confirm software distribution before planning a runtime dependency. |
| WildfireSpreadTS | MIT code; CC-BY-4.0 data; paper describes roughly 50 GB, with additional storage for converted data. Training/reproduction can require substantial compute. Developer loader issues need review. | Optional US temporal-spread baseline, separate from Ontario development data. | Borrow experiment structure now; defer full dataset/model reproduction. |
| Next Day Spread | Published US data/aggregation and baseline workflow. Reproduction needs data storage and a compatible ML environment; no local costs/timing measured. | Optional next-day active-fire benchmark. | Use methodology now, not its fire masks as Ontario ignition labels. |
| DPV | An algorithm/framework requiring graphs, meaningful asset values, treatment constraints and scenarios; no independently evaluated implementation obtained here. | Future treatment-prioritization layer. | Full-text review complete; defer implementation until spread validation and decision-input requirements are satisfied. |

PyTorchFire source inspection found two concrete integration requirements:

1. Its model expects vegetation/density modifiers, per-neighbour slope, an initial fire mask, wind speed in m/s and a **towards** angle measured counter-clockwise from east. Our meteorological/grid bearings require a tested conversion; integer FBP codes are not those modifiers. Define how a model step corresponds to elapsed hours before comparing outputs.
2. At the inspected commit, `BaseTrainer.train()` is explicitly a template: it randomizes the initial mask and assigns its output as its own target. `evaluate()` is also a template. The quick-start training call is therefore not a valid Ontario calibration experiment. A real observation-target/time-mask implementation is required. Source: [pinned model](https://github.com/xiazeyu/PyTorchFire/blob/591e8c3cda44b7d6d68ab6bed71eb945cdc67832/pytorchfire/model.py) and [pinned trainer](https://github.com/xiazeyu/PyTorchFire/blob/591e8c3cda44b7d6d68ab6bed71eb945cdc67832/pytorchfire/trainer.py).

Future tool-trial acceptance evidence: pin source/environment; run a small synthetic ignition; check north/east wind, zero-fuel and full-width water cases; preserve seed and physical time; fit on development observations only; compare identical held-out targets and baseline definitions; record runtime on the actual hardware. Test spotting separately only if explicitly modelled. These trials remain unperformed.

## Where each part belongs

```text
TRACK A: NEW IGNITION (10 km cells, daily recorded-start target)
Eligible past inputs -> common time-safe feature table
                    -> historical-rate / logistic / chosen boosting comparison
                    -> held-out evaluation -> risk map
Research support: Jain; benchmark evaluation principles

TRACK B: EXISTING FIRE (separate 90 m spread prototype)
Observed fire state + eligible weather/fuel/terrain
                    -> correct barrier / reconstruction issues
                    -> calibration on development fires
                    -> frozen tests against a common baseline
                    -> spread viewer, with validated horizon limits
Research support: Cell2Fire, Kim, Prometheus
Later experiment: PyTorchFire; optional US observational benchmarks

AFTER RELIABLE SPREAD EVALUATION
Defensible scenario ensemble -> burn-frequency / uncertainty maps
                             -> optional DPV treatment study
                             -> possible future JAX/RL research
```

## Checklist effect and remaining work

- [x] Identify and classify all eleven slide entries, with source links and publication types.
- [x] Review two original peer-reviewed studies, summarize methods/limits, synthesize them and compare our project.
- [x] Record additional ignition, satellite-benchmark and tool research.
- [x] Assess tool interfaces, requirements, availability, cost drivers and future uses.
- [x] Store seven accessible paper PDFs, extracted text, metadata and pinned documentation/source snapshots locally.
- [x] Obtain and critically read full journal texts for **DPV and C2FK** through Centennial Library; methods, numerical results, validation boundaries and future use recorded above.
- [x] Resolve “burn-probability maps” as an output/method, supported by Cell2Fire and C2FK §2.6; do not invent a separate publication identity.
- [ ] Run tool feasibility/compatibility experiments and formal architecture review before integration.
- [ ] Implement and evaluate models/calibration/uncertainty; none is completed by this literature review.

The Week 2 **minimum two-paper literature review** can now be marked complete locally. The separately linked Week 2 package records data investigation, requirements, plan and evaluation reservation. No application code was modified, external simulator installed, model trained, Git branch merged/pushed or presentation edited.

## References

The links below are publication identifiers; accessible source versions and their differences are recorded above. APA-style author/year citations are used in the review.

- Carrasco-Barra, J., González-Olabarria, J. R., Matus-Olivares, C., Ulloa-Fierro, F., Soto, F., Palacios, D., Mahaluf, R., de la Barra, F., Espinoza, C., Vilches, M., Rivas, M., Badilla, F., Gilabert, H., Castillo, M., Saavedra, J., Lisón, F., Garcia-Gonzalo, J., & Weintraub, A. (2026). New extensions of Cell2Fire software for fire risk analysis and evaluation in Chilean forests. *Environmental Modelling & Software, 203*, 107009. https://doi.org/10.1016/j.envsoft.2026.107009
- Çakır, U., Darvariu, V.-A., Lacerda, B., & Hawes, N. (2025). JaxWildfire: A GPU-accelerated wildfire simulator for reinforcement learning. *NeurIPS Workshop on Machine Learning and the Physical Sciences*. https://arxiv.org/abs/2512.06102
- Gerard, S., Zhao, Y., & Sullivan, J. (2023). WildfireSpreadTS: A dataset of multi-modal time series for wildfire spread prediction. *Advances in Neural Information Processing Systems, 36*, Datasets and Benchmarks Track. https://doi.org/10.52202/075280-3258
- Huot, F., Hu, R. L., Goyal, N., Sankar, T., Ihme, M., & Chen, Y.-F. (2022). Next Day Wildfire Spread: A machine learning dataset to predict wildfire spreading from remote-sensing data. *IEEE Transactions on Geoscience and Remote Sensing, 60*, 1–13. https://doi.org/10.1109/TGRS.2022.3192974
- Jain, P., Coogan, S. C. P., Subramanian, S. G., Crowley, M., Taylor, S., & Flannigan, M. D. (2020). A review of machine learning applications in wildfire science and management. *Environmental Reviews, 28*(4), 478–505. https://doi.org/10.1139/er-2020-0019
- Kim, M., Pais, C., & Gonzalez, M. C. (2025). Fire spread simulations using Cell2Fire on synthetic and real landscapes. *Scientific Reports, 15*, 25173. https://doi.org/10.1038/s41598-025-05706-6
- Pais, C., Carrasco, J., Elimbi Moudio, P., & Shen, Z.-J. M. (2021). Downstream protection value: Detecting critical zones for effective fuel-treatment under wildfire risk. *Computers & Operations Research, 131*, 105252. https://doi.org/10.1016/j.cor.2021.105252
- Pais, C., Carrasco, J., Martell, D. L., Weintraub, A., & Woodruff, D. L. (2021). Cell2Fire: A cell-based forest fire growth model to support strategic landscape management planning. *Frontiers in Forests and Global Change, 4*, 692706. https://doi.org/10.3389/ffgc.2021.692706
- Tymstra, C., Bryce, R. W., Wotton, B. M., Taylor, S. W., & Armitage, O. B. (2010). *Development and structure of Prometheus: The Canadian Wildland Fire Growth Simulation Model* (Information Report NOR-X-417). Natural Resources Canada, Canadian Forest Service, Northern Forestry Centre. https://publications.gc.ca/site/eng/9.568367/publication.html
- Xia, Z., & Cheng, S. (2025). PyTorchFire: A GPU-accelerated wildfire simulator with differentiable cellular automata. *Environmental Modelling & Software, 188*, 106401. https://doi.org/10.1016/j.envsoft.2025.106401

## Evidence files

- [Source download manifest](source_download_manifest.json): successful downloads, source URLs, hashes and unsuccessful attempts.
- [Additional access attempts](additional_access_manifest.json): unresolved publisher/archive access, not silently counted as downloads.
- [Publication metadata](publication_metadata.json): retrieved DOI metadata; rate-limited entries are supplemented by the primary papers/records above.
- [Repository snapshot](tool_repository_snapshot.json): commits, licences and path inventories for five tool/code repositories; this does not claim every code file was reviewed.
- `sources/`: seven paper PDFs and searchable extracts, the private DPV full-text HTML archive, pinned README/API/build documentation and the inspected PyTorchFire model/trainer source. These are reference snapshots, not vendored application dependencies.

The extended slide review and minimum two-original-paper synthesis are complete locally. Tool execution, Ontario adapters and model validation remain implementation work, not literature-review completion criteria.
