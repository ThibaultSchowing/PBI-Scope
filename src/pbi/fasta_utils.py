"""
fasta_utils.py
==============

Utility functions for assembling full genome sequences from multi-contig
pyfaidx FASTA objects.

Typical usage
-------------
>>> from pyfaidx import Fasta
>>> from pbi.fasta_utils import assemble_genome, get_genome_stats
>>> fasta = Fasta("host.fasta")
>>> full_seq = assemble_genome(fasta, mode="concat", gap=100, order="length_desc")
>>> stats = get_genome_stats(fasta)
>>> print(stats["contig_count"], stats["total_length"])
"""

from __future__ import annotations

from typing import Dict, List, Union

from pyfaidx import Fasta


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sorted_keys(fasta_obj: Fasta, order: str) -> List[str]:
    """Return contig keys in the requested deterministic order.

    Parameters
    ----------
    fasta_obj:
        An open :class:`pyfaidx.Fasta` object.
    order:
        ``"length_desc"`` – sort by sequence length descending, then by key
        name ascending as a tie-breaker.  This is the default and guarantees
        a fully deterministic ordering regardless of the FASTA file order.

        ``"file"`` – preserve the order in which contigs appear in the FASTA
        file.  pyfaidx iterates keys in file order when the index was built
        without ``key_function``; this is considered **best-effort** and may
        not be stable if the index was rebuilt with a different pyfaidx
        version.  Use ``"length_desc"`` when strict determinism is required.

    Returns
    -------
    list[str]
        Ordered list of contig keys.

    Raises
    ------
    ValueError
        If *order* is not one of the recognised values.
    """
    keys = list(fasta_obj.keys())
    if order == "file":
        return keys
    elif order == "length_desc":
        return sorted(keys, key=lambda k: (-len(fasta_obj[k]), k))
    else:
        raise ValueError(
            f"Unknown order '{order}'. "
            "Supported values: 'length_desc' (default), 'file'."
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def assemble_genome(
    fasta_obj: Fasta,
    mode: str = "concat",
    gap: int = 0,
    order: str = "length_desc",
) -> Union[str, List[str], Dict[str, str]]:
    """Assemble a genome from a multi-contig :class:`pyfaidx.Fasta` object.

    Parameters
    ----------
    fasta_obj:
        An open :class:`pyfaidx.Fasta` object that may contain one or more
        sequence records (contigs/chromosomes/scaffolds).
    mode:
        How to return the assembled genome.

        * ``"first"`` – return only the first contig as a string (legacy
          behaviour; order is determined by *order* parameter).
        * ``"concat"`` *(default)* – concatenate all contigs into a single
          string.  Optionally insert ``"N" * gap`` nucleotides between
          them.  Contig ordering follows the *order* parameter.
        * ``"list"`` – return a :class:`list` of per-contig sequence strings
          in the order specified by *order*.
        * ``"dict"`` – return an :class:`~collections.OrderedDict`-like
          :class:`dict` mapping ``{header: sequence}`` in the order specified
          by *order*.

    gap:
        Number of ``N`` characters to insert between contigs when
        *mode* is ``"concat"``.  Must be ≥ 0.  Ignored for all other modes.
        Default is ``0`` (contigs are concatenated directly).

    order:
        Determines the order in which contigs are processed.

        * ``"length_desc"`` *(default)* – sort by length descending, then by
          header/key ascending as a tie-breaker.  Fully deterministic.
        * ``"file"`` – preserve the order in which contigs appear in the
          FASTA file (best-effort; see :func:`_sorted_keys`).

    Returns
    -------
    str
        When *mode* is ``"first"`` or ``"concat"``.
    list[str]
        When *mode* is ``"list"``.
    dict[str, str]
        When *mode* is ``"dict"``.

    Raises
    ------
    KeyError
        If *fasta_obj* contains no sequences.
    ValueError
        If *mode*, *order*, or *gap* have invalid values.

    Examples
    --------
    >>> fasta = Fasta("multi_contig_host.fasta")

    # Single concatenated genome (default):
    >>> seq = assemble_genome(fasta)

    # With 100-N gap between contigs:
    >>> seq = assemble_genome(fasta, mode="concat", gap=100)

    # Keep file order:
    >>> seq = assemble_genome(fasta, mode="concat", order="file")

    # List of contig sequences:
    >>> contigs = assemble_genome(fasta, mode="list")

    # Dict mapping header -> sequence:
    >>> seqs = assemble_genome(fasta, mode="dict")

    # Just the largest contig:
    >>> first = assemble_genome(fasta, mode="first")
    """
    if gap < 0:
        raise ValueError(f"gap must be >= 0, got {gap}.")

    keys = _sorted_keys(fasta_obj, order)

    if not keys:
        raise KeyError("The FASTA object contains no sequences.")

    if mode == "first":
        return str(fasta_obj[keys[0]][:].seq)

    # Retrieve all sequences in order
    sequences: List[str] = [str(fasta_obj[k][:].seq) for k in keys]

    if mode == "concat":
        separator = "N" * gap
        return separator.join(sequences)

    if mode == "list":
        return sequences

    if mode == "dict":
        return {k: s for k, s in zip(keys, sequences)}

    raise ValueError(
        f"Unknown mode '{mode}'. "
        "Supported values: 'first', 'concat' (default), 'list', 'dict'."
    )


def get_genome_stats(
    fasta_obj: Fasta,
    order: str = "length_desc",
) -> Dict[str, object]:
    """Return summary statistics for a :class:`pyfaidx.Fasta` object.

    Parameters
    ----------
    fasta_obj:
        An open :class:`pyfaidx.Fasta` object.
    order:
        Contig ordering used for the *lengths* list in the returned dict.
        See :func:`assemble_genome` for details.  Default is
        ``"length_desc"``.

    Returns
    -------
    dict
        A dictionary with the following keys:

        * ``"contig_count"`` (:class:`int`) – number of records in the
          FASTA file.
        * ``"lengths"`` (:class:`list[int]`) – per-contig lengths in the
          requested order.
        * ``"total_length"`` (:class:`int`) – sum of all contig lengths.

    Examples
    --------
    >>> fasta = Fasta("multi_contig_host.fasta")
    >>> stats = get_genome_stats(fasta)
    >>> print(stats["contig_count"])   # e.g. 3
    >>> print(stats["total_length"])   # e.g. 4200000
    >>> print(stats["lengths"])        # e.g. [2500000, 1200000, 500000]
    """
    keys = _sorted_keys(fasta_obj, order)
    lengths = [len(fasta_obj[k]) for k in keys]
    return {
        "contig_count": len(keys),
        "lengths": lengths,
        "total_length": sum(lengths),
    }
