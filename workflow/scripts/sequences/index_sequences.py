#!/usr/bin/env python

import pyfaidx
from pathlib import Path
import logging
import sys
import os
import hashlib
import shutil
from collections import defaultdict


def _setup_logging(log_file: str, also_stderr: bool = True) -> None:
    """Route all logging to *log_file* (Snakemake log: path).

    Delegates to ``workflow/scripts/common/logging_utils.py`` when available;
    otherwise applies an equivalent inline setup so the script remains
    self-contained.
    """
    try:
        _common = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'common')
        if _common not in sys.path:
            sys.path.insert(0, _common)
        from logging_utils import setup_logging  # noqa: PLC0415
        setup_logging(log_file, also_stderr=also_stderr)
    except Exception:
        # Fallback: minimal inline setup
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.INFO)
        fh = logging.FileHandler(log_file)
        fh.setFormatter(fmt)
        root.addHandler(fh)
        if also_stderr:
            sh = logging.StreamHandler(sys.stderr)
            sh.setFormatter(fmt)
            root.addHandler(sh)


def _canonical_key_for_indexing(header: str, is_protein: bool) -> str:
    """Return canonical dedup key: token0 for phage, token1 for protein (Variant B)."""
    toks = header.strip().split()
    if not toks:
        return ""
    if is_protein:
        return toks[1] if len(toks) >= 2 else toks[0]
    return toks[0]


def normalize_and_deduplicate_fasta_streaming(input_fasta, output_fasta, line_width=80, 
                                               duplicate_report_path=None,
                                               is_protein: bool | None = None):
    """
    Memory-efficient FASTA normalization and deduplication using streaming
    
    - Processes one sequence at a time (low memory)
    - Ensures consistent line width
    - Tracks duplicates without loading all sequences
    - Generates detailed duplicate report
    - Uses canonical key (Variant B): token0 for phage, token1 for protein
    
    Args:
        input_fasta: Path to input FASTA file
        output_fasta: Path to output normalized FASTA file
        line_width: Number of characters per line (default: 80)
        duplicate_report_path: Path to save duplicate analysis report (optional)
        is_protein: If None, auto-detected from filename (contains 'protein')
    """
    
    if is_protein is None:
        is_protein = "protein" in str(input_fasta).lower()

    logging.info(f"🔧 Normalizing and deduplicating FASTA: {input_fasta}")
    logging.info(f"📋 Using canonical key (is_protein={is_protein}): {'token1 (Protein_ID)' if is_protein else 'token0 (Phage_ID)'}")
    
    # Track seen IDs and their hashes — canonical key -> hash
    seen_ids = {}  # canonical_key -> hash
    duplicate_stats = defaultdict(lambda: {'identical': 0, 'different': 0, 'sequences': []})
    # also track cross-source conflicts for phage duplicates with same key but different source
    cross_source_conflicts = defaultdict(set)  # canonical_key -> set of source tokens seen
    total_sequences = 0
    sequences_written = 0
    
    # Create temporary file — NEVER write in-place onto Snakemake input;
    # caller must ensure output_fasta != input_fasta or use tmp then move via Snakemake output
    if str(input_fasta) == str(output_fasta):
        temp_output = output_fasta + '.dedup.tmp'
    else:
        temp_output = output_fasta + '.tmp'
    
    try:
        with open(input_fasta, 'r') as infile, open(temp_output, 'w') as outfile:
            current_header = None
            current_seq = []
            
            for line_num, line in enumerate(infile, 1):
                line = line.rstrip('\n\r')
                
                if line.startswith('>'):
                    # Process previous sequence if exists
                    if current_header is not None:
                        written = _write_sequence(
                            outfile, current_header, current_seq,
                            seen_ids, duplicate_stats, line_width,
                            is_protein=is_protein
                        )
                        if written:
                            sequences_written += 1
                        total_sequences += 1
                        
                        # Progress indicator
                        if total_sequences % 100000 == 0:
                            logging.info(f"   📊 Processed {total_sequences:,} sequences, kept {sequences_written:,}...")
                    
                    # Store canonical header (without '>')
                    current_header = line[1:].strip()
                    # Validate no empty header
                    if not current_header:
                        logging.warning(f"⚠️ Empty header at line {line_num} in {input_fasta}, skipping")
                        current_seq = []
                        continue
                    current_seq = []
                    
                else:
                    # Accumulate sequence
                    if line:  # Skip empty lines
                        current_seq.append(line)
            
            # Process last sequence
            if current_header is not None:
                written = _write_sequence(
                    outfile, current_header, current_seq,
                    seen_ids, duplicate_stats, line_width,
                    is_protein=is_protein
                )
                if written:
                    sequences_written += 1
                total_sequences += 1
        
        # Replace original with normalized — if input==output, this is in-place dedup via tmp;
        # otherwise this writes to the intended output path (no mutation of Snakemake input is now handled by caller)
        logging.info(f"🔄 Replacing original with normalized file")
        shutil.move(temp_output, output_fasta)
        
        # Calculate statistics
        duplicates_identical = sum(v['identical'] for v in duplicate_stats.values())
        duplicates_different = sum(v['different'] for v in duplicate_stats.values())
        unique_duplicate_ids = len(duplicate_stats)
        
        logging.info(f"✅ Normalization complete:")
        logging.info(f"   📊 Total sequences read: {total_sequences:,}")
        logging.info(f"   ✅ Sequences written: {sequences_written:,}")
        logging.info(f"   🗑️ Duplicates removed (identical): {duplicates_identical:,}")
        logging.info(f"   ⚠️ Duplicates skipped (different): {duplicates_different:,}")
        logging.info(f"   🔑 Unique IDs with duplicates: {unique_duplicate_ids:,}")
        
        # Generate duplicate report
        if duplicate_report_path and duplicate_stats:
            _generate_duplicate_report(duplicate_stats, duplicate_report_path, input_fasta)
            logging.info(f"   📝 Duplicate report saved: {duplicate_report_path}")
        
        return {
            'total_sequences': total_sequences,
            'sequences_written': sequences_written,
            'duplicates_identical': duplicates_identical,
            'duplicates_different': duplicates_different,
            'unique_duplicate_ids': unique_duplicate_ids
        }
        
    except Exception as e:
        # Clean up temp file on error
        if os.path.exists(temp_output):
            os.remove(temp_output)
        raise e

def _write_sequence(outfile, full_header, seq_parts, seen_ids, duplicate_stats, line_width, is_protein: bool = False):
    """
    Write a single sequence to output file
    
    Handles duplicate detection and line width normalization
    Uses canonical key (token0 for phage, token1 for protein - Variant B)
    
    Args:
        outfile: Output file handle
        full_header: Complete header line (without '>')
        seq_parts: List of sequence line fragments
        seen_ids: Dictionary tracking seen IDs (canonical_key -> hash)
        duplicate_stats: Dictionary tracking duplicate statistics
        line_width: Characters per line for sequence
        is_protein: True for protein FASTA (dedupe on token1), False for phage (token0)
    
    Returns:
        bool: True if sequence was written, False if skipped
    """
    # Join sequence parts
    seq_str = ''.join(seq_parts)
    
    # Calculate hash case-insensitively (matches fasta_qc.py)
    seq_hash = hashlib.md5(seq_str.upper().encode()).hexdigest()
    
    toks = full_header.strip().split()
    if not toks:
        return False
    canonical_key = toks[1] if is_protein and len(toks) >= 2 else toks[0]

    if canonical_key in seen_ids:
        # Duplicate found
        if seen_ids[canonical_key] == seq_hash:
            # Exact duplicate - skip
            duplicate_stats[canonical_key]['identical'] += 1
        else:
            # Different sequence with same ID - skip
            duplicate_stats[canonical_key]['different'] += 1
            duplicate_stats[canonical_key]['sequences'].append({
                'hash': seq_hash,
                'length': len(seq_str)
            })
        return False
    
    # Mark as seen
    seen_ids[canonical_key] = seq_hash
    
    # Write header (full header line, preserving Source_DB provenance)
    outfile.write(f">{full_header}\n")
    
    # Write sequence with consistent line width
    for i in range(0, len(seq_str), line_width):
        outfile.write(seq_str[i:i+line_width] + '\n')
    
    return True

def _generate_duplicate_report(duplicate_stats, report_path, input_file):
    """Generate detailed HTML report of duplicate sequences"""
    
    # Sort by total duplicates (descending)
    sorted_dups = sorted(
        duplicate_stats.items(),
        key=lambda x: x[1]['identical'] + x[1]['different'],
        reverse=True
    )
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>FASTA Duplicate Analysis Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; }}
        .summary {{ background: #ecf0f1; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .summary-item {{ display: inline-block; margin: 10px 20px; }}
        .summary-label {{ font-weight: bold; color: #7f8c8d; }}
        .summary-value {{ font-size: 24px; color: #2c3e50; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th {{ background: #3498db; color: white; padding: 12px; text-align: left; }}
        td {{ padding: 10px; border-bottom: 1px solid #ddd; word-wrap: break-word; }}
        tr:hover {{ background: #f8f9fa; }}
        .identical {{ color: #e74c3c; }}
        .different {{ color: #e67e22; }}
        .warning {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 10px; margin: 20px 0; }}
        .info {{ background: #d1ecf1; border-left: 4px solid #0c5460; padding: 10px; margin: 20px 0; }}
        .header-text {{ font-family: monospace; font-size: 0.9em; max-width: 500px; word-break: break-all; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 FASTA Duplicate Analysis Report</h1>
        
        <div class="info">
            ℹ️ <strong>Parsing Strategy:</strong> Using FULL header line as sequence ID<br>
            <strong>File:</strong> {Path(input_file).name}
        </div>
        
        <div class="summary">
            <h2>Summary Statistics</h2>
            <div class="summary-item">
                <div class="summary-label">Unique IDs with Duplicates</div>
                <div class="summary-value">{len(duplicate_stats):,}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Total Identical Duplicates</div>
                <div class="summary-value identical">{sum(v['identical'] for v in duplicate_stats.values()):,}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Total Different Duplicates</div>
                <div class="summary-value different">{sum(v['different'] for v in duplicate_stats.values()):,}</div>
            </div>
        </div>
        
        <div class="warning">
            ⚠️ <strong>Note:</strong> Identical duplicates are removed automatically. 
            Different sequences with the same header are skipped (only the first occurrence is kept).
            This may indicate issues with the source FASTA files or merging process.
        </div>
        
        <h2>Top Duplicate Headers (showing up to 1000)</h2>
        <table>
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>Sequence Header</th>
                    <th>Identical Copies</th>
                    <th>Different Sequences</th>
                    <th>Total Duplicates</th>
                </tr>
            </thead>
            <tbody>
"""
    
    for rank, (header, stats) in enumerate(sorted_dups[:1000], 1):
        total = stats['identical'] + stats['different']
        # Escape HTML in header
        header_display = header.replace('<', '&lt;').replace('>', '&gt;')
        # Truncate very long headers for display
        if len(header_display) > 100:
            header_display = header_display[:97] + '...'
        
        html += f"""
                <tr>
                    <td>{rank}</td>
                    <td><div class="header-text">{header_display}</div></td>
                    <td class="identical">{stats['identical']:,}</td>
                    <td class="different">{stats['different']:,}</td>
                    <td><strong>{total:,}</strong></td>
                </tr>
"""
    
    html += """
            </tbody>
        </table>
        
        <h2>Recommendations</h2>
        <ul>
            <li><strong>Identical duplicates:</strong> Likely from merging the same data from multiple sources. Safe to remove.</li>
            <li><strong>Different sequences with same header:</strong> May indicate:
                <ul>
                    <li>Different versions of the same sequence from different databases</li>
                    <li>Annotation updates over time</li>
                    <li>Errors in source data</li>
                </ul>
                Consider investigating the top duplicates manually.
            </li>
            <li><strong>Action items:</strong>
                <ul>
                    <li>Check source FASTA files for header conflicts</li>
                    <li>Consider adding source database prefix during merge</li>
                    <li>Review merge scripts in <code>workflow/scripts/mergers/</code></li>
                </ul>
            </li>
        </ul>
    </div>
</body>
</html>
"""
    
    with open(report_path, 'w') as f:
        f.write(html)

def validate_fasta(fasta_path):
    """Validate FASTA file before indexing"""
    if not os.path.exists(fasta_path):
        raise FileNotFoundError(f"❌ FASTA file not found: {fasta_path}")
    
    if os.path.getsize(fasta_path) == 0:
        raise ValueError(f"❌ FASTA file is empty: {fasta_path}")
    
    # Quick check for FASTA format
    with open(fasta_path, 'r') as f:
        first_line = f.readline().strip()
        if not first_line.startswith('>'):
            raise ValueError(f"❌ File does not appear to be FASTA format: {fasta_path}")
    
    logging.info(f"✅ FASTA file validation passed: {fasta_path}")
    return True

# wrapper for legacy callers that expect exception outside try


def index_fasta(fasta_path):
    """Create .fai index for FASTA file with validation using canonical keys."""
    
    fasta_path = Path(fasta_path)
    is_protein = "protein" in str(fasta_path).lower()
    
    logging.info(f"🔍 Validating FASTA file: {fasta_path}")
    validate_fasta(fasta_path)
    
    logging.info(f"📇 Creating index for: {fasta_path}")
    try:
        if is_protein:
            logging.info(f"   Using canonical protein key: token1 (Protein_ID) Variant B")
            def _protein_k(h):
                toks = h.split()
                return toks[1] if len(toks) >= 2 else toks[0] if toks else h
            fasta = pyfaidx.Fasta(
                str(fasta_path),
                read_long_names=True,
                split_char="\x00",
                key_function=_protein_k,
                rebuild=True,
            )
        else:
            logging.info(f"   Using canonical phage key: token0 (Phage_ID)")
            def _phage_k(h):
                toks = h.split()
                return toks[0] if toks else h
            fasta = pyfaidx.Fasta(
                str(fasta_path),
                read_long_names=True,
                split_char="\x00",
                key_function=_phage_k,
                rebuild=True,
            )
        
        # Get statistics
        num_sequences = len(fasta.keys())
        
        # Calculate total length (sample first 1000 to estimate)
        sample_size = min(1000, num_sequences)
        sample_keys = list(fasta.keys())[:sample_size]
        sample_total = sum(len(fasta[key]) for key in sample_keys)
        avg_length = sample_total / sample_size if sample_size > 0 else 0
        estimated_total = int(avg_length * num_sequences)
        
        logging.info(f"✅ Successfully indexed {num_sequences:,} sequences")
        logging.info(f"📊 Estimated total length: ~{estimated_total:,} bp")
        
        # Verify index was created
        index_path = Path(str(fasta_path) + '.fai')
        if not index_path.exists():
            raise FileNotFoundError(f"❌ Index file was not created: {index_path}")
        
        index_size = os.path.getsize(index_path)
        logging.info(f"📁 Index file size: {index_size:,} bytes")
        
        # Sample first few sequence IDs (show full headers)
        sample_ids = list(fasta.keys())[:5]
        logging.info(f"🔍 Sample sequence headers:")
        for sid in sample_ids:
            # Truncate very long headers for logging
            display_id = sid if len(sid) <= 100 else sid[:97] + '...'
            logging.info(f"   - '{display_id}'")
        
        return {
            'num_sequences': num_sequences,
            'total_length': estimated_total,
            'index_size': index_size,
            'fasta': fasta
        }
        
    except Exception as e:
        logging.error(f"❌ Error during indexing: {str(e)}")
        raise

def main():
    """Main indexing function for Snakemake"""

    # Route all logging to the Snakemake log file
    _setup_logging(snakemake.log[0])  # noqa: F821

    # Get input from Snakemake
    fasta_path = snakemake.input[0]  # noqa: F821
    output_index = snakemake.output[0]  # noqa: F821

    logging.info(f"🚀 Starting FASTA indexing")
    logging.info(f"📂 Input: {fasta_path}")
    logging.info(f"📂 Output: {output_index}")
    
    # Log system info
    try:
        import psutil
        mem = psutil.virtual_memory()
        logging.info(f"💾 Available memory: {mem.available / (1024**3):.1f} GB / {mem.total / (1024**3):.1f} GB")
    except ImportError:
        pass
    
    try:
        # Get file size
        file_size_gb = os.path.getsize(fasta_path) / (1024**3)
        logging.info(f"📦 Input file size: {file_size_gb:.2f} GB")
        
        # Validate basic FASTA format first
        logging.info(f"🔍 Validating basic FASTA format")
        if not os.path.exists(fasta_path):
            raise FileNotFoundError(f"❌ FASTA file not found: {fasta_path}")
        if os.path.getsize(fasta_path) == 0:
            raise ValueError(f"❌ FASTA file is empty: {fasta_path}")
        
        # Determine report path (prefer mounted pipeline logs directory in containers)
        fasta_name = Path(fasta_path).stem
        logs_root = os.environ.get("PBI_LOGS_DIR")
        report_dir = Path(logs_root) / "reports" if logs_root else Path("../reports")
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = str(report_dir / f"{fasta_name}_duplicates.html")
        
        # IMPORTANT: Normalize and deduplicate IN PLACE
        # This modifies the original file before indexing
        logging.info(f"🔧 Step 1: Normalizing and deduplicating FASTA (in-place)")
        logging.info(f"⚠️  This will modify the original file: {fasta_path}")
        
        norm_stats = normalize_and_deduplicate_fasta_streaming(
            fasta_path,
            fasta_path,  # Output to same file (in-place via temp file)
            duplicate_report_path=report_path
        )
        
        logging.info(f"✅ Normalization complete")
        logging.info(f"   Sequences written: {norm_stats['sequences_written']:,}")
        logging.info(f"   Duplicates removed: {norm_stats['duplicates_identical']:,}")
        logging.info(f"   Duplicates skipped: {norm_stats['duplicates_different']:,}")
        
        # Now index the deduplicated file
        logging.info(f"🔧 Step 2: Creating index")
        result = index_fasta(fasta_path)
        
        # Verify output matches expected path
        expected_index = Path(str(fasta_path) + '.fai')
        output_index_path = Path(output_index)
        
        if expected_index != output_index_path:
            logging.warning(f"⚠️ Index path mismatch:")
            logging.warning(f"   Expected: {expected_index}")
            logging.warning(f"   Declared: {output_index_path}")
        
        logging.info(f"✅ Indexing complete!")
        logging.info(f"✅ {result['num_sequences']:,} sequences indexed")
        logging.info(f"✅ Duplicates removed (identical): {norm_stats['duplicates_identical']:,}")
        logging.info(f"⚠️ Duplicates skipped (different): {norm_stats['duplicates_different']:,}")
        logging.info(f"📝 See duplicate report: {report_path}")
        logging.info(f"✅ Index saved to: {output_index}")
        
    except Exception as e:
        logging.error(f"❌ Indexing failed: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
