# Dockerfile for running the PBI Snakemake pipeline
FROM condaforge/mambaforge:latest

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Pixi
RUN curl -fsSL https://pixi.sh/install.sh | bash
ENV PATH="/root/.pixi/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy pixi configuration
COPY pixi.toml /app/

# Copy workflow files
COPY workflow /app/workflow
COPY src /app/src
COPY setup.py /app/

# Install PBI package dependencies
RUN pip install duckdb>=0.9.0 pyfaidx>=0.7.0 pandas>=2.0.0

# Create data directory structure
RUN mkdir -p /data/processed/databases /data/processed/sequences /data/intermediate

# Set the working directory to workflow for Snakemake
WORKDIR /app/workflow

# Default command to run the pipeline
CMD ["snakemake", "--cores", "all", "--use-conda", "--printshellcmds", "--directory", "/app/workflow", "--snakefile", "/app/workflow/Snakefile"]
