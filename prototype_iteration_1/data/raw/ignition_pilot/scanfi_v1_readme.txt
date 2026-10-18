SCANFI: the Spatialized CAnadian National Forest Inventory data product

  Please keep this “readme” file with the dataset for reference.

  Updated metadata and dataset updates can be found at this link: 
  https://doi.org/10.23687/18e6a919-53fd-41ce-b4e2-44a9707c52dc 

  If you use this data in your research or publication, please use these citations:
    
    Dataset
      Guindon L., Villemaire P., Correia D.L.P., Manka F., Lacarte S., Smiley B. 2023. SCANFI: Spatialized Canadian National Forest Inventory data product. Natural Resources Canada, Canadian Forest Service, Laurentian Forestry Centre, Quebec, Canada. https://doi.org/10.23687/18e6a919-53fd-41ce-b4e2-44a9707c52dc 

    Scientific publication  
      Guindon L., Manka F, Correia L.P. D., Villemaire P., Smiley B., Bernier P., Gauthier S., Beaudoin A., Boucher J., Boulanger Y. A new approach for Spatializing the Canadian National Forest Inventory (SCANFI) using Landsat dense time series. Canadian Journal of Forest Research 2024. [In Press]

--- SCANFI product V1.2, on Nov 19, 2024 ---
  
  The data type of the file SCANFI_att_biomass_SW_2020_v1.2.tif was changed from 8-bit to 16-bit in order to accommodate a wider range of values, exceeding 254 tons/ha.

--- SCANFI product V1.1, on May 20, 2024 ---

  An incremental adjustment, affecting less than 1% of the territory, was made to the biomass and land cover layers to rectify an anomaly stemming from a misclassification of water within recently scorched zones. Incorrectly categorized water classes were reassigned to the herbaceous class, while biomass values were adjusted from 0 to 2 tons/ha for these instances. This refinement shifts the Scanfi version from v1 to v1.1 across all layers. The upcoming SCANFI version will address this issue.


--- SCANFI product V1, on February 15, 2024 ---


- Description
  This repository contains a set of raster files predicting vegetation attributes and tree species distribution in Canada. The data was generated using machine learning algorithms applied to remote sensing data, climate data, and other environmental variables. The detailed methodology and data validation analyses are described in the scientific publication.

  The data consists of a set of raster files in GeoTIFF format, covering the entire non-arctic land mass of Canada. 
  
  The rasters have a spatial resolution of 30 meters and are provided in the following projection: https://www.spatialreference.org/ref/sr-org/8787/.


- The data is split into two sets of rasters:
  1)  Vegetation Attributes
  
      Biomass: tons/ha
      Crown closure: percentage of pixel covered by the tree canopy.
      Height: meters
      Tree species cover: percentage estimated as the proportion of the canopy covered by each tree species
      NFI land cover class values:
        1 = Bryoid
        2 = Herbs
        3 = Rock
        4 = Shrub
        5 = Tree cover is mainly “Treed broadleaf”
        6 = Tree cover is mainly “Treed conifer”
        7 = Tree cover is mainly “Treed mixed”
        8 = Water

  2)  Tree species cover proportion of total crown cover
    
      Note: For example, in a forest stand with 30% tree crown cover, a value of 100% balsam fir means that only balsam firs, which cover 30% of the pixel area, are present in this tree stand.
      
      Tree species:
      •  Balsam fir: Abies balsamea
      •  Black spruce: Picea mariana
      •  Douglas fir: Pseudotsuga menziesii
      •  Jack pine: Pinus banksiana
      •  Lodgepole pine: Pinus contorta
      •  Ponderosa pine: Pinus ponderosa
      •  Tamarack: Larix laricina
      •  White and red pine: Pinus strobus and Pinus resinosa
      •  PrcB: Broadleaf tree species
      •  PrcC other: Other coniferous tree species


- Data sources, methods and validation
  See Guindon et al., 2024 for a detailed description of the data sources, methods and validation analyses.
  
  Vegetation attributes in the arctic ecozones were predicted using a single random forest model, since these areas were outside of the NFI acquisition zone. As such, vegetation attributes in these areas were not properly validated. The raster "SCANFI_aux_arcticExtrapolationArea.tif" can be used to identify these areas.


- Data limitations
  1- The spectral disturbances of some areas disturbed by pests are not comprehensively represented in the training set, thus making it impossible to predict all defoliation cases. One such area, severely impacted by the recent eastern spruce budworm outbreak, is located on the North Shore of the St-Lawrence River. These forests are misrepresented in our training data, there is therefore an imprecision in our estimates.
  
  2- Attributes of open stand classes, namely shrub, herbs, rock and bryoid, are more difficult to estimate through the photointerpretation of aerial images. Therefore, these estimates could be less reliable than the forest attribute estimates. Therefore, these estimates are less reliable than the forest attribute estimates.
  
  3- As reported in the manuscript, the uncertainty of tree species cover predictions is relatively high. This is particularly true for less abundant tree species, such as ponderosa pine and tamarack. The tree species layers are therefore suitable for regional and coarser scale studies. These tree species layers are therefore suitable for regional and coarser scale studies. Also, the broadleaf proportion are slightly underestimated in this product version. 
  
  4- Our validation indicates that the areas in Yukon exhibit a notably lower R2 value. Consequently, estimates within these regions are less dependable.
  
  5- Urban areas and roads are classified as rock, according to the 2020 Agriculture and Agri-Food Canada land-use classification map. Even though those areas contain mostly buildings and infrastructure, they may also contain trees. Forested urban parks are usually classified as forested areas. Vegetation attributes are also predicted for forested areas in agricultural regions.


- Data Access and Usage
  The data is freely available for download and use. 
  
  You may use this data for research or commercial purposes, but you must cite the original source of the data. 
  
  The data is licensed under the Creative Commons Attribution 4.0 International license.
  
  To access and download the data, please navigate to https://doi.org/10.23687/18e6a919-53fd-41ce-b4e2-44a9707c52dc 


- Contact
  If you have any questions or feedback about this data, please contact the authors at luc.guindon@nrcan-rncan.gc.ca


