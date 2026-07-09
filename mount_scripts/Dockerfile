# =============================================================================
# Example: R + Python Container for PBI-Scope
# =============================================================================
# This Dockerfile creates a container with both R and Python, ready to connect
# to the PBI-Scope database via the shared Docker volume.
#
# Build and run:
#   docker build -t pbi-custom-r .
#   docker compose -f docker-compose.custom.yml up custom-jupyter
#   OR
#   docker compose -f docker-compose.custom.yml up custom-scripts
#
# See docs/guides/custom-containers.md for full documentation.
# =============================================================================

# --- Base Image ---------------------------------------------------------------
# rocker/r-ver provides R 4.3+ with common system libraries.
# We add Python on top for dual-language support.
#
# Alternative base images:
#   - python:3.10-slim  → Python-first, add R via r-base
#   - rocker/rstudio    → R + RStudio Server (port 8787)
#   - jupyter/r-notebook → Jupyter with R kernel pre-installed
#   - ubuntu:22.04      → Minimal, install everything yourself
FROM rocker/r-ver:4.3.2

# --- System Dependencies ------------------------------------------------------
# Install Python and system libraries needed by R packages and Python.
# The lib* packages are required by popular R packages like ggplot2 and sf.
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    libcurl4-openssl-dev \
    libssl-dev \
    libxml2-dev \
    libfontconfig1-dev \
    libharfbuzz-dev \
    libfribidi-dev \
    libfreetype6-dev \
    libpng-dev \
    libtiff5-dev \
    libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*

# --- R Packages ---------------------------------------------------------------
# Install R packages for data analysis and visualization.
#
# Key packages:
#   - DBI, duckdb    → Connect to the DuckDB database
#   - dplyr, tidyr   → Data manipulation
#   - ggplot2        → Visualization
#   - scales         → Axis formatting (comma labels, etc.)
#   - writexl        → Export to Excel (optional)
#   - IRkernel       → Jupyter kernel for R (required for R in Jupyter)
#
# To add more R packages, add them to the install.packages() vector.
RUN R -e 'install.packages(c(
    "DBI", "duckdb",
    "dplyr", "tidyr",
    "ggplot2", "scales",
    "writexl",
    "IRkernel"
), repos = "https://cloud.r-project.org")'

# Register IRkernel with Jupyter
RUN R -e 'IRkernel::installspec(user = FALSE)'

# --- Python Packages ----------------------------------------------------------
# Install the pbi package and common scientific libraries.
#
# To add more Python packages, add them to this pip install command.
RUN pip3 install --no-cache-dir \
    pbi \
    duckdb \
    pandas \
    matplotlib \
    seaborn \
    jupyterlab

# --- Working Directory ---------------------------------------------------------
# This is where your scripts and notebooks will be mounted.
WORKDIR /workspace

# --- Entrypoint Script --------------------------------------------------------
# The entrypoint script handles:
#   1. /etc/passwd patching for arbitrary UID support
#   2. Switching between Jupyter and script mode
#
# We COPY it from the build context (mount_scripts/ directory).
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# --- Expose Ports -------------------------------------------------------------
# Jupyter Lab runs on port 8888 by default.
EXPOSE 8888

# --- Default Command ----------------------------------------------------------
# The entrypoint script decides what to run based on the COMMAND argument:
#   "jupyter"  → Start Jupyter Lab with R and Python kernels
#   "script"   → Run explore_phages.R
#   "bash"     → Open a shell (for debugging)
#
# You can override this in docker-compose or at runtime:
#   docker run pbi-custom-r bash
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["jupyter"]
