# PBI-Scope
## Dockerized Phage Bacteria Interactions toolkit based on PhageScope

> A proof-of-concept dockerized bioinformatics pipeline that makes phage genomic data from [PhageScope](https://phagescope.deepomics.org/database) and their hosts available in an efficient, structured format for training neural networks and AI models for phage-host interaction prediction.

![PBI-Scope schema](https://github.com/ThibaultSchowing/PBI-Scope/blob/main/docs/img/PBI_Schema_Note.png)

**Install - Wait - Work** The pipeline takes care of everything within Docker !

[![Documentation](https://img.shields.io/badge/docs-github%20pages-blue)](https://thibaultschowing.github.io/PBI-Scope/)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.18961926-blue.svg)](https://doi.org/10.5281/zenodo.18961926)
[![CI Pipeline and DB Tests](https://github.com/ThibaultSchowing/PBI-Scope/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ThibaultSchowing/PBI-Scope/actions/workflows/ci.yml)
[![ExPASy SIB](https://img.shields.io/badge/ExPASy-SIB_Resource-E2001A)](https://www.expasy.org/resources/pbi-scope)
[![Publication](https://img.shields.io/badge/publication-Pending-orange)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Check the example notebooks on how to use PBI-Scope !

1. Preprocessing and integrating your private data
2. Run the pipeline to include these data into the PBI-Scope database
3. Use the _pbi_ Python package to generate datasets or stream data into your model training.
4. Use the included BLAST database to search for sequences, with the API or the Python package!
5. **For more than notebooks, checkout [the project's fork on CI4CB's page](https://github.com/CI4CB-lab/PBI-Scope-PERPHECT) to have a full working example on how to train a neural network with PBI-Scope.**

## 🎯 What is PBI-Scope?

PBI-Scope builds a unified data product from:

- Public phage metadata/sequences from PhageScope
- Optional private datasets from `private_data/` (validated and merged by source)
- Host genomes resolved from NCBI RefSeq

> **Note**: PBI-Scope is dependent on PhageScope as its primary data source. Regarding data such as Host range or lifestyle, unavailable data were predicted using various tools (e.g. DeepHost). Refer to [the publication](https://academic.oup.com/nar/article/52/D1/D756/7334092) for more information.

Outputs are stored in a shared Docker volume and exposed through:

- DuckDB metadata database
- Indexed FASTA files (phage/protein/host)
- `pbi` Python package (recommended access path)
- Analysis container (Jupyter Lab + VS Code Dev Containers)

> The REST API is now supported for database exploration ! For sequence-heavy usage, load the database's sequence retriever directly from the analysis container. **Check Notebook examples [in the notebooks folder !](https://github.com/ThibaultSchowing/PBI-Scope/tree/main/notebooks)**

## 📚 Documentation

For more details, check [the documentation](https://thibaultschowing.github.io/PBI-Scope/). It contains extensive information about:

- Quick start
- Workflow description
- Code snippets
- Debug and error handling
- And more !

Direct entry points:

- **Home**: https://thibaultschowing.github.io/PBI-Scope/
- **Installation**: https://thibaultschowing.github.io/PBI-Scope/guides/installation/
- **Story (one-read walkthrough)**: https://thibaultschowing.github.io/PBI-Scope/guides/storytelling/
- **Private data handling**: https://thibaultschowing.github.io/PBI-Scope/guides/private-data-ingestion/
- **Analysis container**: https://thibaultschowing.github.io/PBI-Scope/guides/analysis-guide/

**Check Notebook examples [in the notebooks folder !](https://github.com/ThibaultSchowing/PBI-Scope/tree/main/notebooks)**

## 🚀 Quick Start

```bash
git clone https://github.com/ThibaultSchowing/PBI-Scope.git
cd PBI-Scope

# Configure credentials and set your host UID/GID so containers
# write files as your user instead of root:
cp .env.example .env
echo "UID=$(id -u)" >> .env
echo "GID=$(id -g)" >> .env
# Then edit .env and fill in NCBI_EMAIL (and NCBI_API_KEY if you have one).

# Set up SSH port forwarding first (on your local machine):
# ssh -L 8888:localhost:8888 username@your-server

tmux new -s pbi

docker compose build pipeline
docker compose run --rm pipeline
# ~4 hours for PhageScope data, ~12-18 hours for host genomes retrieval

# analysis container
docker compose build analysis
docker compose up -d analysis


# api container (run in a dedicated terminal e.g. tmux session)
docker compose build api
docker compose up api

```

Open `http://localhost:8888` (with SSH tunnel: `ssh -L 8888:localhost:8888 user@server`).

## 🏗️ Infrastructure overview

```text
                  +--------------------------------------+
                  |         shared bind mounts           |
                  | ./private_data  -> /private-data     |
                  | ./pipeline_logs -> /pipeline-logs    |
                  | (pipeline: rw / analysis: ro)        |
                  +-------------------+------------------+
                                      |
         +----------------------------+----------------------------+
         |                                                         |
+--------v---------+      +-----------v-----------+      +--------v---------+
| pipeline         |----->|      pbi-data         |<-----| analysis         |
| (rw: /data,      |      | named volume (/data)  |      | (ro: /data)      |
|      /cache)     |      +-----------+-----------+      +---------+--------+
+--------+---------+                  |                            |
         |                    +-------v-------+          +---------v---------+
         |                    | api           |          | bind mounts       |
         |                    | (ro on /data) |          | [analysis only]   |
         |                    +---------------+          | ./notebooks       |
         |                                               |  -> /workspace(rw)|
+--------v---------+                                     | ./outputs         |
| named volume     |                                     |  -> /results (rw) |
| pbi-cache        |                                     | ./src             |
| -> /cache (rw)   |                                     |  -> /app/src (ro) |
| [pipeline only]  |                                     +-------------------+
+------------------+
```

Additional mounts/volumes currently used in `docker-compose.yml`:

- **Named volumes**
  - `pbi-data` → `/data` (pipeline: rw, analysis/api: ro)
  - `pbi-cache` → `/cache` (pipeline: rw)
- **Bind mounts**
  - `./private_data` → `/private-data` (pipeline: rw, analysis: ro)
  - `./pipeline_logs` → `/pipeline-logs` (pipeline: rw, analysis: ro)
  - `./notebooks` → `/workspace` (analysis: rw)
  - `./outputs` → `/results` (analysis: rw)
  - `./src` → `/app/src` (analysis: ro)

## Citation

If you use PBI-Scope, please cite it via Zenodo (all versions):

[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.18961926-blue.svg)](https://doi.org/10.5281/zenodo.18961926)

> Thibault Schowing. PBI-Scope. Zenodo. https://doi.org/10.5281/zenodo.18961926

See also [`CITATION.cff`](CITATION.cff).

## License

MIT — see [LICENSE](LICENSE).
