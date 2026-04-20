![alt](https://github.com/ThibaultSchowing/PBI/blob/main/docs/img/github-header-banner%20(1).png)

# PBI - Phage Bacteria Interactions

> A dockerized pipeline that builds a queryable phage-host resource for machine learning and analysis.

[![Documentation](https://img.shields.io/badge/docs-github%20pages-blue)](https://thibaultschowing.github.io/PBI/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.18961927.svg)](https://doi.org/10.5281/zenodo.18961927)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19232887.svg)](https://doi.org/10.5281/zenodo.19232887)

## 🎯 What is PBI?

PBI builds a unified data product from:

- Public phage metadata/sequences from PhageScope
- Optional private datasets from `private_data/` (validated and merged by source)
- Host genomes resolved from NCBI RefSeq

Outputs are stored in a shared Docker volume and exposed through:

- DuckDB metadata database
- Indexed FASTA files (phage/protein/host)
- `pbi` Python package (recommended access path)
- Analysis container (Jupyter Lab + VS Code Dev Containers)

> The REST API is currently not supported for sequence-heavy usage because it is too slow for large retrieval workloads. It will be redesigned later for database exploration-first access.

## 📚 Documentation

- **Home**: https://thibaultschowing.github.io/PBI/
- **Installation**: https://thibaultschowing.github.io/PBI/guides/installation/
- **Story (one-read walkthrough)**: https://thibaultschowing.github.io/PBI/guides/storytelling/
- **Private data handling**: https://thibaultschowing.github.io/PBI/guides/private-data-ingestion/
- **Analysis container**: https://thibaultschowing.github.io/PBI/guides/analysis-guide/

## 🚀 Quick Start

```bash
git clone https://github.com/ThibaultSchowing/PBI.git
cd PBI

export NCBI_EMAIL="you@domain.org"
export NCBI_API_KEY="..."

docker compose build pipeline
docker compose run --rm pipeline

# analysis container
docker compose build analysis
docker compose up -d analysis
```

Open `http://localhost:8888` (or with SSH tunnel: `ssh -L 8888:localhost:8888 user@server`).

## 🏗️ Infrastructure overview

```text
                         +-------------------------+
                         |   bind mount            |
                         | ./private_data          |
                         | -> /private-data        |
                         +------------+------------+
                                      |
+------------------+      +-----------v-----------+      +------------------+
| pipeline         |----->|      pbi-data         |<-----| analysis         |
| (rw on /data)    |      | named volume (/data)  |      | (ro on /data)    |
+--------+---------+      +-----------+-----------+      +---------+--------+
         |                            |                            |
         |                    +-------v-------+                    |
         |                    | api (legacy)  |                    |
         |                    | (ro on /data) |                    |
         |                    +---------------+                    |
         |
+--------v---------+
| bind mount       |
| ./pipeline_logs  |
| -> /pipeline-logs|
+------------------+
```

## License

MIT
