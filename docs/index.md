# PBI

Welcome to the documentation for the PBI repository. To get an overview of the project  [start here](getting-started/overview.md). For a detailed installation [go here](getting-started/installation.md). 


## Status

| Task | Status |
|------|--------|
|Integrate [PhageScope](https://phagescope.deepomics.org/workspace/) tables|✅ Complete|
|Installation manual and documentation|🔄 In Progress|
|Tests|🔄 In Progress|
|Python package and API to interrogate the database|🔄 In Progress|
|Review Snakemake pipeline logic |📆 Todo|
|Host (bacteria) genome retrieval tool from species name|📆 Todo|
|Plan external (other databases) data integration|📆 Todo|



## TODO's and broader goals

Gathering and merging the data from [PhageScope](https://phagescope.deepomics.org/workspace/) into a SQL database is mainly done. Now the goal is to make this database useable by preparing and testing an installation guide, filling the PBI python package with various functionnality allowing for data retrieval and usage and completing a standard API documentation. 

From a strong base, the project can be lead forward to integrate other more detailed Phage Bacteria Iteraction data. At this point various choices will have to be made about where the new data will be integrated. 

The preferred option for now is to create a new database, directly suited for our needs and populating it directly with the desired sequences. This database scheme can be inspired from older project such as [INPHINITY](https://www.ingenierie-sante.ch/fr/projects/84/INPHINITY). 


