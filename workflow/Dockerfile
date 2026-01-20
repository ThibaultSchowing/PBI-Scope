# Dockerfile for running the PBI Snakemake pipeline
FROM condaforge/mambaforge:latest

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy workflow files
COPY workflow /app/workflow
COPY src /app/src
COPY setup.py /app/

# Copy environment file and create conda environment
COPY workflow/envs/base_environment.yaml /tmp/base_environment.yaml

# Install snakemake and core dependencies using conda env
# NOTE: SSL verification is temporarily disabled due to self-signed certificates in
# the GitHub Actions CI environment. In production, ensure proper CA certificates are
# configured or use a trusted mirror. Re-enable with: conda config --set ssl_verify true
# Update the base environment instead of creating a new one
RUN conda config --set ssl_verify false && \
    conda env update -n base -f /tmp/base_environment.yaml && \
    conda clean -a -y && \
    conda config --set ssl_verify true

# Create data directory structure
RUN mkdir -p /data/processed/databases /data/processed/sequences /data/intermediate /data/raw /cache

# Set the working directory to workflow for Snakemake
WORKDIR /app/workflow

# Default command to run the pipeline
CMD ["snakemake", "--cores", "1", "--use-conda", "--printshellcmds", "--cache", "--conda-prefix", "/cache/conda", "--directory", "/app/workflow", "--snakefile", "/app/workflow/Snakefile"]
