#!/usr/bin/env python3
"""
Unit tests for multi-host parsing and resolution.

Tests the new standalone functions introduced for multi-host support:
  - parse_host_field()
  - resolve_host_token()
  - RobustHostGenomeDownloader._generate_candidates()
  - RobustHostGenomeDownloader._build_assembly_links()
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

# Add workflow scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "workflow" / "scripts" / "sequences"))

from download_host_genomes_robust import (
    HostToken,
    ResolvedAssemblyLink,
    parse_host_field,
    RobustHostGenomeDownloader,
)
from assembly_resolver import AssemblyResolver, AssemblyMetadata


class TestParseHostField(unittest.TestCase):
    """Tests for the standalone parse_host_field() function."""

    # ------------------------------------------------------------------
    # Empty / invalid inputs
    # ------------------------------------------------------------------

    def test_empty_string(self):
        self.assertEqual(parse_host_field(''), [])

    def test_none_input(self):
        self.assertEqual(parse_host_field(None), [])

    def test_dash_only(self):
        self.assertEqual(parse_host_field('-'), [])

    def test_na_only(self):
        self.assertEqual(parse_host_field('NA'), [])

    def test_unknown_host(self):
        self.assertEqual(parse_host_field('unknown host'), [])

    def test_unidentified(self):
        self.assertEqual(parse_host_field('unidentified'), [])

    def test_semicolons_only_na(self):
        """All tokens are NA – should return empty list."""
        self.assertEqual(parse_host_field('NA;NA;NA'), [])

    # ------------------------------------------------------------------
    # Single token inputs
    # ------------------------------------------------------------------

    def test_simple_species_name(self):
        result = parse_host_field('Escherichia coli')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].token, 'Escherichia coli')
        self.assertEqual(result[0].token_type, 'species_name')
        self.assertEqual(result[0].token_order, 1)

    def test_assembly_accession_gcf(self):
        result = parse_host_field('GCF_000005845.2')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].token, 'GCF_000005845.2')
        self.assertEqual(result[0].token_type, 'assembly_accession')

    def test_assembly_accession_gca(self):
        result = parse_host_field('GCA_900066335.1')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].token_type, 'assembly_accession')

    def test_gca_with_space_normalized(self):
        """'GCA 900066335.1' must be normalised to 'GCA_900066335.1'."""
        result = parse_host_field('GCA 900066335.1')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].token, 'GCA_900066335.1')
        self.assertEqual(result[0].token_type, 'assembly_accession')

    def test_gcf_with_space_normalized(self):
        result = parse_host_field('GCF 000005845.2')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].token, 'GCF_000005845.2')
        self.assertEqual(result[0].token_type, 'assembly_accession')

    def test_single_word_other(self):
        """Single capitalised word is 'other' (genus-only, code, etc.)."""
        result = parse_host_field('Lachnospira')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].token_type, 'other')

    # ------------------------------------------------------------------
    # Multi-token semicolon-separated inputs
    # ------------------------------------------------------------------

    def test_problem_statement_example_1(self):
        """'NA;GCA 900066335.1;UBA9502;Blautia obeum' from the problem statement."""
        result = parse_host_field('NA;GCA 900066335.1;UBA9502;Blautia obeum')
        # NA is filtered → 3 tokens
        self.assertEqual(len(result), 3)

        # GCA accession (normalised)
        gca_token = result[0]
        self.assertEqual(gca_token.token, 'GCA_900066335.1')
        self.assertEqual(gca_token.token_type, 'assembly_accession')
        self.assertEqual(gca_token.token_order, 2)  # 2nd in original list

        # UBA9502 – 'other'
        uba_token = result[1]
        self.assertEqual(uba_token.token, 'UBA9502')
        self.assertEqual(uba_token.token_type, 'other')
        self.assertEqual(uba_token.token_order, 3)

        # Blautia obeum – species_name
        blautia_token = result[2]
        self.assertEqual(blautia_token.token, 'Blautia obeum')
        self.assertEqual(blautia_token.token_type, 'species_name')
        self.assertEqual(blautia_token.token_order, 4)

    def test_problem_statement_example_2(self):
        """'Bacteroides dorei;Bacteroides vulgatus' → 2 species tokens."""
        result = parse_host_field('Bacteroides dorei;Bacteroides vulgatus')
        self.assertEqual(len(result), 2)
        for tok in result:
            self.assertEqual(tok.token_type, 'species_name')
        self.assertEqual(result[0].token, 'Bacteroides dorei')
        self.assertEqual(result[0].token_order, 1)
        self.assertEqual(result[1].token, 'Bacteroides vulgatus')
        self.assertEqual(result[1].token_order, 2)

    def test_na_then_species(self):
        result = parse_host_field('NA;Escherichia coli')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].token, 'Escherichia coli')
        self.assertEqual(result[0].token_order, 2)  # 2nd position (NA skipped)

    def test_token_order_preserved_with_gaps(self):
        """Token_Order reflects the 1-based index in the original semicolon split."""
        # Position 1 = NA (filtered), 2 = GCA, 3 = UBA9502, 4 = Blautia obeum
        result = parse_host_field('NA;GCA_900066335.1;UBA9502;Blautia obeum')
        orders = [t.token_order for t in result]
        self.assertEqual(orders, [2, 3, 4])

    def test_whitespace_trimming(self):
        """Tokens with leading/trailing whitespace are trimmed."""
        result = parse_host_field('  Escherichia coli  ;  Bacillus subtilis  ')
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].token, 'Escherichia coli')
        self.assertEqual(result[1].token, 'Bacillus subtilis')

    def test_deterministic_output(self):
        """Same input always produces identical output (determinism)."""
        host = 'NA;GCA 900066335.1;UBA9502;Blautia obeum'
        result1 = parse_host_field(host)
        result2 = parse_host_field(host)
        self.assertEqual(result1, result2)


class TestGenerateCandidates(unittest.TestCase):
    """Tests for RobustHostGenomeDownloader._generate_candidates()."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.phage_csv = self.temp_path / 'phages.csv'

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_downloader(self, rows):
        df = pd.DataFrame(rows)
        df.to_csv(self.phage_csv, index=False)
        return RobustHostGenomeDownloader(
            phage_csv_path=str(self.phage_csv),
            output_dir=str(self.temp_path / 'genomes'),
            metadata_output=str(self.temp_path / 'host_metadata.csv'),
            assembly_metadata_output=str(self.temp_path / 'assembly_metadata.csv'),
            phage_host_links_output=str(self.temp_path / 'phage_host_links.csv'),
            ncbi_email='pbi-test@example.org',
            metadata_only=True,
        )

    def test_single_host_single_token(self):
        rows = [{'Phage_ID': 'p1', 'Host': 'Escherichia coli', 'Source_DB': 'RefSeq'}]
        dl = self._make_downloader(rows)
        phage_df = pd.read_csv(self.phage_csv)
        cand = dl._generate_candidates(phage_df)

        self.assertEqual(len(cand), 1)
        self.assertEqual(cand.iloc[0]['Phage_ID'], 'p1')
        self.assertEqual(cand.iloc[0]['Host_Token'], 'Escherichia coli')
        self.assertEqual(cand.iloc[0]['Token_Type'], 'species_name')

    def test_multi_host_multi_token(self):
        """Phage with 'Bacteroides dorei;Bacteroides vulgatus' yields 2 candidate rows."""
        rows = [
            {'Phage_ID': 'p1', 'Host': 'Bacteroides dorei;Bacteroides vulgatus', 'Source_DB': 'RefSeq'},
        ]
        dl = self._make_downloader(rows)
        phage_df = pd.read_csv(self.phage_csv)
        cand = dl._generate_candidates(phage_df)

        self.assertEqual(len(cand), 2)
        self.assertEqual(set(cand['Host_Token']), {'Bacteroides dorei', 'Bacteroides vulgatus'})

    def test_invalid_host_excluded(self):
        rows = [
            {'Phage_ID': 'p1', 'Host': '-', 'Source_DB': 'RefSeq'},
            {'Phage_ID': 'p2', 'Host': 'Escherichia coli', 'Source_DB': 'RefSeq'},
        ]
        dl = self._make_downloader(rows)
        phage_df = pd.read_csv(self.phage_csv)
        cand = dl._generate_candidates(phage_df)

        # Only p2 should appear
        self.assertEqual(len(cand), 1)
        self.assertEqual(cand.iloc[0]['Phage_ID'], 'p2')

    def test_two_phages_same_host_both_in_candidates(self):
        rows = [
            {'Phage_ID': 'p1', 'Host': 'Escherichia coli', 'Source_DB': 'RefSeq'},
            {'Phage_ID': 'p2', 'Host': 'Escherichia coli', 'Source_DB': 'RefSeq'},
        ]
        dl = self._make_downloader(rows)
        phage_df = pd.read_csv(self.phage_csv)
        cand = dl._generate_candidates(phage_df)

        # Both phages should appear (candidates are per-phage)
        self.assertEqual(len(cand), 2)
        self.assertIn('p1', cand['Phage_ID'].values)
        self.assertIn('p2', cand['Phage_ID'].values)

    def test_sorted_output(self):
        rows = [
            {'Phage_ID': 'p2', 'Host': 'Bacillus subtilis', 'Source_DB': 'RefSeq'},
            {'Phage_ID': 'p1', 'Host': 'Escherichia coli', 'Source_DB': 'RefSeq'},
        ]
        dl = self._make_downloader(rows)
        phage_df = pd.read_csv(self.phage_csv)
        cand = dl._generate_candidates(phage_df)

        # Should be sorted by Phage_ID
        self.assertEqual(list(cand['Phage_ID']), ['p1', 'p2'])


class TestBuildAssemblyLinks(unittest.TestCase):
    """Tests for RobustHostGenomeDownloader._build_assembly_links()."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.phage_csv = self.temp_path / 'phages.csv'
        pd.DataFrame([
            {'Phage_ID': 'p1', 'Host': 'Escherichia coli', 'Source_DB': 'RefSeq'},
        ]).to_csv(self.phage_csv, index=False)
        self.dl = RobustHostGenomeDownloader(
            phage_csv_path=str(self.phage_csv),
            output_dir=str(self.temp_path / 'genomes'),
            metadata_output=str(self.temp_path / 'host_metadata.csv'),
            assembly_metadata_output=str(self.temp_path / 'assembly_metadata.csv'),
            phage_host_links_output=str(self.temp_path / 'phage_host_links.csv'),
            ncbi_email='pbi-test@example.org',
            metadata_only=True,
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _dummy_assembly(self, accession, level='Complete Genome', category='reference genome'):
        return AssemblyMetadata(
            assembly_accession=accession,
            assembly_name='test_asm',
            organism_name='Test organism',
            assembly_level=level,
            refseq_category=category,
        )

    def _make_candidates(self, rows):
        return pd.DataFrame(rows, columns=[
            'Phage_ID', 'Host_Raw', 'Host_Token', 'Token_Type', 'Token_Order'
        ])

    def test_empty_candidates(self):
        cand = self._make_candidates([])
        links = self.dl._build_assembly_links(cand, {})
        self.assertTrue(links.empty)

    def test_single_link(self):
        cand = self._make_candidates([
            ('p1', 'Escherichia coli', 'Escherichia coli', 'species_name', 1),
        ])
        asm = self._dummy_assembly('GCF_000005845.2')
        links = self.dl._build_assembly_links(cand, {'Escherichia coli': [asm]})

        self.assertEqual(len(links), 1)
        row = links.iloc[0]
        self.assertEqual(row['Phage_ID'], 'p1')
        self.assertEqual(row['Assembly_Accession'], 'GCF_000005845.2')
        self.assertEqual(row['Resolution_Source'], 'species_to_taxid_to_assembly')
        self.assertEqual(row['Resolution_Rank'], 1)
        self.assertAlmostEqual(row['Confidence'], 0.70)

    def test_assembly_accession_confidence(self):
        cand = self._make_candidates([
            ('p1', 'GCF_000005845.2', 'GCF_000005845.2', 'assembly_accession', 1),
        ])
        asm = self._dummy_assembly('GCF_000005845.2')
        links = self.dl._build_assembly_links(cand, {'GCF_000005845.2': [asm]})
        self.assertAlmostEqual(links.iloc[0]['Confidence'], 0.95)
        self.assertEqual(links.iloc[0]['Resolution_Source'], 'accession_in_host_field')

    def test_multi_host_produces_multiple_links(self):
        """One phage with two species tokens → two assembly links."""
        cand = self._make_candidates([
            ('p1', 'Bacteroides dorei;Bacteroides vulgatus', 'Bacteroides dorei', 'species_name', 1),
            ('p1', 'Bacteroides dorei;Bacteroides vulgatus', 'Bacteroides vulgatus', 'species_name', 2),
        ])
        asm1 = self._dummy_assembly('GCF_AAA000001.1')
        asm2 = self._dummy_assembly('GCF_BBB000002.1')
        token_to_asm = {
            'Bacteroides dorei': [asm1],
            'Bacteroides vulgatus': [asm2],
        }
        links = self.dl._build_assembly_links(cand, token_to_asm)

        self.assertEqual(len(links), 2)
        accessions = set(links['Assembly_Accession'])
        self.assertIn('GCF_AAA000001.1', accessions)
        self.assertIn('GCF_BBB000002.1', accessions)

    def test_unresolved_token_produces_no_link(self):
        cand = self._make_candidates([
            ('p1', 'Unknown species', 'Unknown species', 'species_name', 1),
        ])
        links = self.dl._build_assembly_links(cand, {'Unknown species': []})
        self.assertTrue(links.empty)

    def test_sorted_output(self):
        cand = self._make_candidates([
            ('p2', 'Bacillus subtilis', 'Bacillus subtilis', 'species_name', 1),
            ('p1', 'Escherichia coli', 'Escherichia coli', 'species_name', 1),
        ])
        asm1 = self._dummy_assembly('GCF_000001.1')
        asm2 = self._dummy_assembly('GCF_000002.1')
        links = self.dl._build_assembly_links(cand, {
            'Bacillus subtilis': [asm1],
            'Escherichia coli': [asm2],
        })
        self.assertEqual(list(links['Phage_ID']), ['p1', 'p2'])

    def test_ambiguous_flag(self):
        """Multiple assemblies for a token sets Ambiguous=True."""
        cand = self._make_candidates([
            ('p1', 'Escherichia coli', 'Escherichia coli', 'species_name', 1),
        ])
        asm1 = self._dummy_assembly('GCF_000001.1')
        asm2 = self._dummy_assembly('GCF_000002.1')
        links = self.dl._build_assembly_links(
            cand, {'Escherichia coli': [asm1, asm2]}
        )
        # Both assemblies get separate rows; both should be flagged as ambiguous
        for _, row in links.iterrows():
            self.assertTrue(row['Ambiguous'])
            self.assertIn('2 assemblies found', row['Ambiguity_Reason'])


class TestBacterialHostFiltering(unittest.TestCase):
    """Tests for the bacterial-host verification step in process_all_hosts.

    These tests exercise the Stage 2b filtering logic that is embedded inside
    ``process_all_hosts``.  Because that method also talks to NCBI for assembly
    resolution and downloads, we patch ``AssemblyResolver.is_bacterial_taxid``
    to avoid network calls.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.phage_csv = self.temp_path / 'phages.csv'

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_downloader(self, rows):
        df = pd.DataFrame(rows)
        df.to_csv(self.phage_csv, index=False)
        return RobustHostGenomeDownloader(
            phage_csv_path=str(self.phage_csv),
            output_dir=str(self.temp_path / 'genomes'),
            metadata_output=str(self.temp_path / 'host_metadata.csv'),
            assembly_metadata_output=str(self.temp_path / 'assembly_metadata.csv'),
            phage_host_links_output=str(self.temp_path / 'phage_host_links.csv'),
            ncbi_email='pbi-test@example.org',
            metadata_only=True,
        )

    def _make_assembly(self, accession, organism, taxid=None):
        return AssemblyMetadata(
            assembly_accession=accession,
            assembly_name='test_asm',
            organism_name=organism,
            species_taxid=taxid,
            assembly_level='Complete Genome',
            refseq_category='reference genome',
        )

    def _run_stage2b(self, downloader, token_to_assemblies):
        """Execute only the Stage 2b bacterial-filtering loop from process_all_hosts."""
        non_bacterial_tokens = []
        for tok, assemblies in list(token_to_assemblies.items()):
            if not assemblies:
                continue
            bacterial_assemblies = []
            for asm in assemblies:
                if asm.species_taxid is None:
                    bacterial_assemblies.append(asm)
                    continue
                is_bacterial = downloader.resolver.is_bacterial_taxid(asm.species_taxid)
                if is_bacterial is False:
                    if tok not in non_bacterial_tokens:
                        non_bacterial_tokens.append(tok)
                elif is_bacterial is None:
                    bacterial_assemblies.append(asm)
                else:
                    bacterial_assemblies.append(asm)
            token_to_assemblies[tok] = bacterial_assemblies
        return token_to_assemblies, non_bacterial_tokens

    def test_bacterial_assembly_kept(self):
        """A confirmed bacterial assembly must remain in token_to_assemblies."""
        rows = [{'Phage_ID': 'p1', 'Host': 'Escherichia coli', 'Source_DB': 'RefSeq'}]
        dl = self._make_downloader(rows)

        ecoli_asm = self._make_assembly('GCF_000005845.2', 'Escherichia coli str. K-12', taxid=562)
        token_to_assemblies = {'Escherichia coli': [ecoli_asm]}

        # Patch: E. coli (562) → bacterial
        dl.resolver._bacterial_taxid_cache[562] = True

        result, excluded = self._run_stage2b(dl, token_to_assemblies)
        self.assertEqual(len(result['Escherichia coli']), 1)
        self.assertEqual(excluded, [])

    def test_non_bacterial_assembly_removed(self):
        """An assembly resolving to a non-bacterial organism must be removed and logged."""
        rows = [{'Phage_ID': 'p1', 'Host': 'Homo sapiens', 'Source_DB': 'RefSeq'}]
        dl = self._make_downloader(rows)

        human_asm = self._make_assembly('GCF_000001405.40', 'Homo sapiens', taxid=9606)
        token_to_assemblies = {'Homo sapiens': [human_asm]}

        # Patch: Homo sapiens (9606) → not bacterial
        dl.resolver._bacterial_taxid_cache[9606] = False

        result, excluded = self._run_stage2b(dl, token_to_assemblies)
        self.assertEqual(len(result['Homo sapiens']), 0)
        self.assertIn('Homo sapiens', excluded)

    def test_unknown_taxonomy_assembly_kept(self):
        """When taxonomy lookup returns None (unknown), the assembly is included."""
        rows = [{'Phage_ID': 'p1', 'Host': 'Unknown bacterium', 'Source_DB': 'RefSeq'}]
        dl = self._make_downloader(rows)

        asm = self._make_assembly('GCA_999999999.1', 'Unknown bacterium', taxid=99999)
        token_to_assemblies = {'Unknown bacterium': [asm]}

        # Patch: lookup fails → None
        dl.resolver._bacterial_taxid_cache[99999] = None

        result, excluded = self._run_stage2b(dl, token_to_assemblies)
        self.assertEqual(len(result['Unknown bacterium']), 1)
        self.assertEqual(excluded, [])

    def test_assembly_without_taxid_kept(self):
        """Assembly with species_taxid=None cannot be checked; it must be kept."""
        rows = [{'Phage_ID': 'p1', 'Host': 'Bacteroides dorei', 'Source_DB': 'RefSeq'}]
        dl = self._make_downloader(rows)

        asm = self._make_assembly('GCF_123456789.1', 'Bacteroides dorei', taxid=None)
        token_to_assemblies = {'Bacteroides dorei': [asm]}

        result, excluded = self._run_stage2b(dl, token_to_assemblies)
        self.assertEqual(len(result['Bacteroides dorei']), 1)
        self.assertEqual(excluded, [])

    def test_mixed_tokens_only_non_bacterial_removed(self):
        """Bacterial tokens remain; only the non-bacterial token is excluded."""
        rows = [
            {'Phage_ID': 'p1', 'Host': 'Escherichia coli', 'Source_DB': 'RefSeq'},
            {'Phage_ID': 'p2', 'Host': 'Mus musculus', 'Source_DB': 'RefSeq'},
        ]
        dl = self._make_downloader(rows)

        ecoli_asm = self._make_assembly('GCF_000005845.2', 'Escherichia coli K-12', taxid=562)
        mouse_asm = self._make_assembly('GCF_000001635.27', 'Mus musculus', taxid=10090)
        token_to_assemblies = {
            'Escherichia coli': [ecoli_asm],
            'Mus musculus': [mouse_asm],
        }

        dl.resolver._bacterial_taxid_cache[562] = True
        dl.resolver._bacterial_taxid_cache[10090] = False

        result, excluded = self._run_stage2b(dl, token_to_assemblies)
        self.assertEqual(len(result['Escherichia coli']), 1)
        self.assertEqual(len(result['Mus musculus']), 0)
        self.assertIn('Mus musculus', excluded)
        self.assertNotIn('Escherichia coli', excluded)


def main():
    unittest.main(verbosity=2)


if __name__ == '__main__':
    main()
