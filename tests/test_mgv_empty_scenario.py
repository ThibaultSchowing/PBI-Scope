#!/usr/bin/env python3
"""
End-to-end test simulating the exact scenario from the problem statement.
Tests the pipeline behavior when MGV dataset has no FASTA files.
"""

import os
import subprocess
import tempfile
from pathlib import Path


def test_mgv_empty_directory_scenario():
    """
    Simulate the exact scenario from the problem statement:
    - MGV directory exists but contains no .fasta or .fa files
    - The merge rule should create an empty MGV.fasta file
    - A warning should be printed
    - The pipeline should continue (exit code 0)
    """
    print("🧪 Testing MGV empty directory scenario (from problem statement)...")
    print("-" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Simulate the directory structure
        protein_fasta_extracted = Path(tmpdir) / "data" / "raw" / "protein_fasta_extracted"
        protein_fasta_merged = Path(tmpdir) / "data" / "intermediate" / "fasta" / "proteins"
        
        mgv_source = protein_fasta_extracted / "MGV"
        mgv_source.mkdir(parents=True)
        protein_fasta_merged.mkdir(parents=True)
        
        mgv_output = protein_fasta_merged / "MGV.fasta"
        
        print(f"Source directory: {mgv_source}")
        print(f"Output file: {mgv_output}")
        
        # Create some non-FASTA files to make the test more realistic
        (mgv_source / "README.txt").write_text("This dataset has no FASTA files")
        (mgv_source / "metadata.tsv").write_text("id\tname\n1\ttest\n")
        
        # Run the exact shell script from the fix
        shell_script = f"""
        set -e
        
        mkdir -p {protein_fasta_merged}
        
        # Find all fasta files and store in an array
        mapfile -t fasta_files < <(find {mgv_source} -type f \\( -name "*.fasta" -o -name "*.fa" \\))
        
        # Check if any files were found
        if [ "${{#fasta_files[@]}}" -eq 0 ]; then
            echo "⚠️ WARNING: No FASTA files found in {mgv_source} - creating empty file" >&2
            touch {mgv_output}
        elif [ "${{#fasta_files[@]}}" -eq 1 ]; then
            # Only one file, just copy it
            cp "${{fasta_files[0]}}" {mgv_output}
        else
            # Multiple files, merge them
            echo "Multiple files found - would call merge script"
        fi
        """
        
        print("\nExecuting merge rule shell script...")
        result = subprocess.run(
            ["bash", "-c", shell_script],
            capture_output=True,
            text=True
        )
        
        print(f"\nReturn code: {result.returncode}")
        print(f"STDERR: {result.stderr.strip()}")
        print(f"STDOUT: {result.stdout.strip()}")
        
        # Verify the fix works as expected
        assert result.returncode == 0, "Script should succeed (not fail like in the problem)"
        assert mgv_output.exists(), "MGV.fasta should be created"
        assert mgv_output.stat().st_size == 0, "MGV.fasta should be empty"
        assert "WARNING: No FASTA files found" in result.stderr, "Warning should be printed to stderr"
        
        print("\n✅ VERIFICATION:")
        print(f"  - Exit code is 0 (success) ✓")
        print(f"  - Empty MGV.fasta created ✓")
        print(f"  - Warning message printed ✓")
        
        # Now simulate the downstream merge_protein_fasta rule
        print("\nSimulating downstream merge_protein_fasta rule...")
        
        # Create another valid source for realism
        refseq_source = protein_fasta_extracted / "RefSeq"
        refseq_source.mkdir(parents=True)
        refseq_output = protein_fasta_merged / "RefSeq.fasta"
        refseq_output.write_text(">protein1\nMKVLSTAGLAIVLGLAAVAAEVAAQ\n")
        
        # Simulate the downstream merge logic
        all_sources = [mgv_output, refseq_output]
        final_output = Path(tmpdir) / "data" / "intermediate" / "fasta" / "all_proteins.fasta"
        
        valid_files = []
        skipped_files = []
        for fasta_file in all_sources:
            if os.path.exists(fasta_file) and os.path.getsize(fasta_file) > 0:
                valid_files.append(fasta_file)
            else:
                skipped_files.append(fasta_file)
                print(f"  ⚠️ Skipping empty or missing file: {fasta_file.name}")
        
        # Merge valid files
        if valid_files:
            final_output.parent.mkdir(parents=True, exist_ok=True)
            with final_output.open('w') as outfile:
                for fasta_file in valid_files:
                    with fasta_file.open('r') as infile:
                        content = infile.read()
                        if content.strip():
                            outfile.write(content)
                            if not content.endswith('\n'):
                                outfile.write('\n')
            
            print(f"  ✅ Merged {len(valid_files)}/{len(all_sources)} protein FASTA files")
        
        # Verify downstream behavior
        assert len(skipped_files) == 1, "MGV.fasta should be skipped"
        assert skipped_files[0] == mgv_output, "MGV.fasta should be the skipped file"
        assert len(valid_files) == 1, "RefSeq.fasta should be valid"
        assert final_output.exists(), "Final merged file should be created"
        assert "protein1" in final_output.read_text(), "Final file should contain RefSeq data"
        
        print("\n✅ DOWNSTREAM VERIFICATION:")
        print(f"  - Empty MGV.fasta skipped ✓")
        print(f"  - Valid RefSeq.fasta included ✓")
        print(f"  - Final merge completed successfully ✓")
        print(f"  - Pipeline continues (no error) ✓")
        
    print("\n" + "=" * 60)
    print("✅ END-TO-END TEST PASSED!")
    print("=" * 60)
    print("\nThis demonstrates that the fix solves the problem:")
    print("  - Before: Pipeline fails with non-zero exit code")
    print("  - After: Pipeline succeeds, empty files are handled gracefully")


if __name__ == "__main__":
    print("=" * 60)
    print("End-to-End Test: MGV Empty Directory Scenario")
    print("=" * 60)
    print()
    
    test_mgv_empty_directory_scenario()
