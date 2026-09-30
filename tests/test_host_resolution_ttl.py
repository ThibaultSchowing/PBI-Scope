import json, time, sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "workflow" / "scripts" / "sequences"))
from download_host_genomes_robust import RobustHostGenomeDownloader


def _make_downloader(tmp_path, ttl):
    # Minimal CSV to satisfy __init__ phage_csv_path existence
    phage_csv = tmp_path / "phage.csv"
    phage_csv.write_text("Phage_ID,Host\np1,Escherichia coli\n")
    out_dir = tmp_path / "hosts"
    out_dir.mkdir()
    meta = tmp_path / "host_metadata.csv"
    asm_meta = tmp_path / "assembly.csv"
    links = tmp_path / "links.csv"
    return RobustHostGenomeDownloader(
        phage_csv_path=str(phage_csv),
        output_dir=str(out_dir),
        metadata_output=str(meta),
        assembly_metadata_output=str(asm_meta),
        phage_host_links_output=str(links),
        ncbi_email="test@example.com",
        reuse_resolution_cache=True,
        host_resolution_cache_ttl_days=ttl,
    )


def test_ttl_fresh_cache_used(tmp_path):
    dl = _make_downloader(tmp_path, ttl=120)
    cache = dl.host_resolution_cache_output
    cache.write_text(json.dumps({"tok": [{"assembly_accession": "GCF_001", "organism_name": "E. coli"}]}))
    # mtime now = fresh
    loaded = dl._load_token_resolution_cache()
    assert "tok" in loaded


def test_ttl_stale_cache_ignored(tmp_path):
    dl = _make_downloader(tmp_path, ttl=1)
    cache = dl.host_resolution_cache_output
    cache.write_text(json.dumps({"tok": [{"assembly_accession": "GCF_001"}]}))
    # Make file 2 days old
    old = time.time() - 2 * 86400
    import os
    os.utime(cache, (old, old))
    loaded = dl._load_token_resolution_cache()
    assert loaded == {}


def test_ttl_zero_never_expires(tmp_path):
    dl = _make_downloader(tmp_path, ttl=0)
    cache = dl.host_resolution_cache_output
    cache.write_text(json.dumps({"tok": [{"assembly_accession": "GCF_001"}]}))
    old = time.time() - 200 * 86400
    import os
    os.utime(cache, (old, old))
    loaded = dl._load_token_resolution_cache()
    assert "tok" in loaded


def test_bacterial_cache_ttl(tmp_path):
    dl = _make_downloader(tmp_path, ttl=1)
    bcache = dl.bacterial_cache_output
    bcache.write_text(json.dumps({"123": True}))
    import os, time
    old = time.time() - 2 * 86400
    os.utime(bcache, (old, old))
    loaded = dl._load_bacterial_cache()
    assert loaded == {}


def test_disable_reuse_ignores_cache(tmp_path):
    dl = _make_downloader(tmp_path, ttl=120)
    dl.reuse_resolution_cache = False
    cache = dl.host_resolution_cache_output
    cache.write_text(json.dumps({"tok": [{"assembly_accession": "GCF_001"}]}))
    loaded = dl._load_token_resolution_cache()
    assert loaded == {}
