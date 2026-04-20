"""
PBI test suite — layout notes
==============================

tests/
  Unit / integration tests runnable with:  python -m pytest tests/

  Kept tests (no live dependencies required):
    test_docker_compose_private_data  – validates docker-compose.yml structure
    test_env_path_config              – pbi path resolution (env vars)
    test_fasta_merge_integration      – FASTA merge logic
    test_fasta_merge_shell_logic.sh   – shell-level FASTA merge
    test_fasta_qc                     – FASTA quality-control helpers
    test_fasta_utils                  – assemble_genome / get_genome_stats
    test_integration_genome_download  – workflow config + script presence checks
    test_mgv_empty_scenario           – empty-source handling (subprocess)
    test_resume_capability            – download resume logic (mocked)
    test_streaming_dataset            – streaming dataset shapes (mocked FASTA)

  Tests requiring full runtime (duckdb, pandas, pyfaidx, BioPython, etc.):
    test_assembly_resolver            – assembly_resolver workflow script
    test_chunked_merge                – pandas-heavy merge logic
    test_column_consistency           – duckdb column checks
    test_csv_quoting                  – pandas CSV parsing
    test_host_field_parsing           – host-name parser (workflow script)
    test_host_genome_download         – HostGenomeDownloader (mocked NCBI)
    test_multi_host_parsing           – multi-token host parsing
    test_optimized_genome_download    – OptimizedHostGenomeDownloader helpers
    test_private_data_ingestion       – pbi.private_data validation
    test_robust_genome_download       – RobustHostGenomeDownloader helpers
    test_schema_contracts             – YAML schema-contract loading
    test_sequence_retrieval           – SequenceRetriever (duckdb + pyfaidx)
    test_sequence_retrieval_private_paths – private-path wiring
    test_streaming_dataset            – full streaming/indexed datasets
    test_tokenization_fix_integration – CSV tokenization edge cases
    test_tsv_reading                  – TSV parsing

scripts/
  Standalone utility scripts (not pytest):
    validate_fasta_workflow.py  – end-to-end FASTA naming/format checks
    check_pbi_paths.py          – verify DATA_PATH resolution

cleanup_cache.sh  – Docker cache-volume cleanup (run manually)
"""
