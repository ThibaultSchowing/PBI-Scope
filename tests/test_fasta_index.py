"""
Unit tests for fasta_index.py — FASTA loading and caching utilities.
"""

import tempfile
from pathlib import Path

import pytest

from pbi.fasta_index import (
    HostFastaCache,
    PrivatePhageFastaCache,
    _fasta_key_function,
    _protein_key_function,
    _should_rebuild_fai,
    load_phage_fasta,
    load_protein_fasta,
)


class TestKeyFunctions:
    """Tests for FASTA key extraction functions."""

    def test_phage_key_simple(self):
        assert _fasta_key_function(">NC_000866.4") == "NC_000866.4"

    def test_phage_key_with_description(self):
        assert _fasta_key_function(">NC_000866.4 some description") == "NC_000866.4"

    def test_phage_key_pipe_separated(self):
        assert _fasta_key_function(">IMGVR_UViG_2020627000_000021|2020627000|VrWwEF_contig52410") == \
            "IMGVR_UViG_2020627000_000021|2020627000|VrWwEF_contig52410"

    def test_protein_key_simple(self):
        assert _protein_key_function(">NC_000866.4 NP_049616.1") == "NP_049616.1"

    def test_protein_key_with_source(self):
        assert _protein_key_function(">NC_000866.4 NP_049616.1 RefSeq") == "NP_049616.1"

    def test_protein_key_prodigal_hash(self):
        assert _protein_key_function(">3300006028.a:Ga0070717_10000169_1 # 2 # 685") == \
            "3300006028.a:Ga0070717_10000169_1"

    def test_protein_key_single_token(self):
        assert _protein_key_function(">NP_049616.1") == "NP_049616.1"


class TestShouldRebuildFai:
    """Tests for _should_rebuild_fai()."""

    def test_missing_index(self, tmp_path):
        fasta = tmp_path / "test.fasta"
        fasta.write_text(">seq1\nATGC\n")
        assert _should_rebuild_fai(fasta) is True

    def test_existing_fresh_index(self, tmp_path):
        fasta = tmp_path / "test.fasta"
        fasta.write_text(">seq1\nATGC\n")
        fai = tmp_path / "test.fasta.fai"
        fai.write_text("seq1\t4\t6\t60\t61\n")
        # Make fai newer than fasta
        import os
        os.utime(fai, (fasta.stat().st_mtime + 10, fasta.stat().st_mtime + 10))
        assert _should_rebuild_fai(fasta) is False

    def test_stale_index(self, tmp_path):
        fasta = tmp_path / "test.fasta"
        fasta.write_text(">seq1\nATGC\n")
        fai = tmp_path / "test.fasta.fai"
        fai.write_text("seq1\t4\t6\t60\t61\n")
        # Make fai older than fasta
        import os
        os.utime(fai, (fasta.stat().st_mtime - 10, fasta.stat().st_mtime - 10))
        assert _should_rebuild_fai(fasta) is True


class TestHostFastaCache:
    """Tests for HostFastaCache."""

    def test_cache_get_and_retrieve(self, tmp_path):
        host_file = tmp_path / "host1.fasta"
        host_file.write_text(">contig1\nATGC\n")
        fai = tmp_path / "host1.fasta.fai"
        fai.write_text("contig1\t4\t11\t60\t61\n")

        cache = HostFastaCache(max_size=2)
        fasta1 = cache.get("host1", str(host_file))
        fasta2 = cache.get("host1", str(host_file))
        assert fasta1 is fasta2  # Same object from cache

    def test_cache_eviction(self, tmp_path):
        files = []
        for i in range(3):
            f = tmp_path / f"host{i}.fasta"
            f.write_text(f">contig{i}\nATGC\n")
            fai = tmp_path / f"host{i}.fasta.fai"
            fai.write_text(f"contig{i}\t4\t11\t60\t61\n")
            files.append(str(f))

        cache = HostFastaCache(max_size=2)
        cache.get("host0", files[0])
        cache.get("host1", files[1])
        cache.get("host2", files[2])  # Should evict host0

        assert len(cache._cache) == 2
        assert "host0" not in cache._cache
        assert "host1" in cache._cache
        assert "host2" in cache._cache

    def test_close_all(self, tmp_path):
        host_file = tmp_path / "host1.fasta"
        host_file.write_text(">contig1\nATGC\n")
        fai = tmp_path / "host1.fasta.fai"
        fai.write_text("contig1\t4\t11\t60\t61\n")

        cache = HostFastaCache()
        cache.get("host1", str(host_file))
        cache.close_all()
        assert len(cache._cache) == 0


class TestPrivatePhageFastaCache:
    """Tests for PrivatePhageFastaCache."""

    def test_cache_get_and_retrieve(self, tmp_path):
        phage_file = tmp_path / "phage.fasta"
        phage_file.write_text(">phage1\nATGC\n")
        fai = tmp_path / "phage.fasta.fai"
        fai.write_text("phage1\t4\t11\t60\t61\n")

        cache = PrivatePhageFastaCache(max_size=2)
        fasta1 = cache.get("test_source", str(phage_file))
        fasta2 = cache.get("test_source", str(phage_file))
        assert fasta1 is fasta2

    def test_cache_eviction(self, tmp_path):
        files = []
        for i in range(3):
            f = tmp_path / f"phage{i}.fasta"
            f.write_text(f">phage{i}\nATGC\n")
            fai = tmp_path / f"phage{i}.fasta.fai"
            fai.write_text(f"phage{i}\t4\t11\t60\t61\n")
            files.append(str(f))

        cache = PrivatePhageFastaCache(max_size=2)
        cache.get("source0", files[0])
        cache.get("source1", files[1])
        cache.get("source2", files[2])

        assert len(cache._cache) == 2
        assert "source0" not in cache._cache
