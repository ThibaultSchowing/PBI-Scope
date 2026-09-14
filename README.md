# PBI-Scope
## Dockerized Phage Bacteria Interactions toolkit based on PhageScope

> A proof-of-concept dockerized bioinformatics pipeline that makes phage genomic data from [PhageScope](https://phagescope.deepomics.org/database) and their hosts available in an efficient, structured format for training neural networks and AI models for phage-host interaction prediction.

![alt](https://github.com/ThibaultSchowing/PBI-Scope/blob/main/docs/img/PBI_Schema_Note.png)


**Install - Wait - Work** The pipeline takes care of everything within Docker !

[![Documentation](https://img.shields.io/badge/docs-github%20pages-blue)](https://thibaultschowing.github.io/PBI-Scope/)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo-blue.svg)](https://zenodo.org/records/22111305)
[![CI Pipeline and DB Tests](https://github.com/ThibaultSchowing/PBI-Scope/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ThibaultSchowing/PBI-Scope/actions/workflows/ci.yml)
[![ExPASy SIB](https://img.shields.io/badge/ExPASy-SIB_Resource-E2001A)](https://www.expasy.org/resources/pbi-scope)
[![Publication](https://img.shields.io/badge/publication-Pending-orange)]()

> Check the example notebooks on how to use PBI-Scope !  


1. Preprocessing and integrating your private data
2. Run the pipeline to include these data into the PBI-Scope database
3. Use the _pbi_ Python package to generate datasets or stream data into your model training.
4. Use the included BLAST database to search for sequences, with the API or the Python package!
5. **For more than notebooks, checkout [the project's fork on CI4CB's page](https://github.com/CI4CB-lab/PBI-Scope-PERPHECT) to have a full working example on how to train a neural network with PBI-Scope.** 

## Documentation 

For more details, check [the documentation](https://thibaultschowing.github.io/PBI-Scope/). It contains extensive information about: 
- Quick start
- Workflow description
- Code snippets
- Debug and error handling
- And more !

