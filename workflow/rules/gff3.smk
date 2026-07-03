# Rules for GFF3 download, indexing, and retrieval

GFF3_SOURCES = list(config["phage_GFF3_urls"].keys())


rule download_all_gff3:
    input:
        expand(
            config["phage_gff3_output"] + "/{source}.gff3",
            source=GFF3_SOURCES
        )


rule download_gff3:
    """
    Download a GFF3 file from PhageScope API.
    These are single .gff3 files per database (not tar.gz archives).
    Uses Python download with retry, HTTP status validation, and HTML
    error-page detection. On permanent failure an empty file is created
    so the index builder skips it gracefully.
    """
    output:
        gff3=config["phage_gff3_output"] + "/{source}.gff3"
    params:
        url=lambda wildcards: config["phage_GFF3_urls"][wildcards.source]
    cache: True
    conda:
        "../envs/base_env.yaml"
    script:
        "../scripts/gff3/download_gff3.py"


rule build_gff3_index:
    """
    Build a JSON index mapping phage_id -> (source_db, file_path, byte_offset, byte_length).
    Enables O(1) random access to GFF3 content by phage_id.
    """
    input:
        expand(
            config["phage_gff3_output"] + "/{source}.gff3",
            source=GFF3_SOURCES
        )
    output:
        index=config["phage_gff3_index_output"]
    conda:
        "../envs/base_env.yaml"
    script:
        "../scripts/gff3/build_gff3_index.py"
