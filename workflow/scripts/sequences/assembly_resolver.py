#!/usr/bin/env python
"""
Assembly Accession Resolver for NCBI Bacterial Genomes

This module provides robust resolution of heterogeneous identifiers to NCBI assembly accessions.
Supports:
- Assembly accessions (GCF_/GCA_)
- BioSample accessions
- BioProject accessions
- Species names (with ambiguity handling)
- Strain names

Follows best practices:
1. Uses NCBI Assembly database as authoritative source
2. Normalizes all inputs to assembly accessions (GCF_ preferred, GCA_ fallback)
3. Explicit ambiguity acknowledgment for names
4. Uses Taxonomy as helper, not guarantee
5. Filters by quality criteria (RefSeq > GenBank, latest versions, assembly level)
6. Prefers reference/representative genomes
"""

import re
import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from Bio import Entrez


class IdentifierType(Enum):
    """Types of identifiers that can be resolved"""
    ASSEMBLY_ACCESSION = "assembly_accession"  # GCF_ or GCA_
    BIOSAMPLE = "biosample"
    BIOPROJECT = "bioproject"
    SPECIES_NAME = "species_name"
    STRAIN_NAME = "strain_name"
    TAXID = "taxid"
    UNKNOWN = "unknown"


class AssemblyLevel(Enum):
    """Assembly completeness levels (in priority order)"""
    COMPLETE_GENOME = ("Complete Genome", 1000)
    CHROMOSOME = ("Chromosome", 500)
    SCAFFOLD = ("Scaffold", 100)
    CONTIG = ("Contig", 50)
    
    def __init__(self, display_name: str, priority: int):
        self.display_name = display_name
        self.priority = priority


class RefSeqCategory(Enum):
    """RefSeq category types (in priority order)"""
    REFERENCE = ("reference genome", 10000)
    REPRESENTATIVE = ("representative genome", 5000)
    NA = ("na", 0)
    
    def __init__(self, display_name: str, priority: int):
        self.display_name = display_name
        self.priority = priority


@dataclass
class AssemblyMetadata:
    """
    Comprehensive assembly metadata
    
    This class represents all metadata needed to make informed decisions about
    which assembly to use for a given bacterial genome.
    """
    # Primary identifiers
    assembly_accession: str  # GCF_xxxxxxxxx.x or GCA_xxxxxxxxx.x
    assembly_name: str
    
    # Organism information
    organism_name: str
    species_taxid: Optional[int] = None
    strain: Optional[str] = None
    
    # Assembly quality metrics
    assembly_level: str = "Contig"
    refseq_category: str = "na"
    
    # Version and status
    version: int = 1
    is_latest: bool = True
    
    # Additional identifiers
    biosample: Optional[str] = None
    bioproject: Optional[str] = None
    
    # Source information
    ftp_path: Optional[str] = None
    submission_date: Optional[str] = None
    
    def get_quality_score(self) -> int:
        """
        Calculate quality score for assembly ranking
        
        Higher score = better assembly
        Priority order:
        1. RefSeq category (reference > representative > na)
        2. Assembly level (complete > chromosome > scaffold > contig)
        3. Is latest version
        """
        score = 0
        
        # RefSeq category priority
        if self.refseq_category == "reference genome":
            score += 10000
        elif self.refseq_category == "representative genome":
            score += 5000
        
        # Assembly level priority
        if self.assembly_level == "Complete Genome":
            score += 1000
        elif self.assembly_level == "Chromosome":
            score += 500
        elif self.assembly_level == "Scaffold":
            score += 100
        elif self.assembly_level == "Contig":
            score += 50
        
        # Latest version bonus
        if self.is_latest:
            score += 10
        
        return score
    
    def is_refseq(self) -> bool:
        """Check if this is a RefSeq assembly (GCF_)"""
        return self.assembly_accession.startswith("GCF_")
    
    def is_genbank(self) -> bool:
        """Check if this is a GenBank assembly (GCA_)"""
        return self.assembly_accession.startswith("GCA_")


class AssemblyResolver:
    """
    Resolve heterogeneous identifiers to NCBI assembly accessions
    
    This class provides robust, reproducible resolution of various identifier types
    to canonical NCBI assembly accessions, with quality-based ranking and filtering.
    """
    
    # Priority ordering for identifier types (class-level constant)
    IDENTIFIER_PRIORITY = {
        IdentifierType.ASSEMBLY_ACCESSION: 0,
        IdentifierType.BIOSAMPLE: 1,
        IdentifierType.BIOPROJECT: 2,
        IdentifierType.TAXID: 3,
        IdentifierType.SPECIES_NAME: 4,
        IdentifierType.STRAIN_NAME: 5,
        IdentifierType.UNKNOWN: 6
    }
    
    def __init__(self, 
                 email: str,
                 api_key: Optional[str] = None,
                 delay: float = 0.34,
                 max_retries: int = 3):
        """
        Initialize AssemblyResolver
        
        Args:
            email: Email for NCBI Entrez (required)
            api_key: Optional NCBI API key for higher rate limits
            delay: Delay between requests (0.34s = ~3 req/s, 0.1s with API key)
            max_retries: Maximum retry attempts for failed requests
        """
        self.email = email
        self.api_key = api_key
        self.delay = delay if not api_key else 0.1
        self.max_retries = max_retries
        
        # Configure Entrez
        Entrez.email = email
        if api_key:
            Entrez.api_key = api_key
        
        # Compile regex patterns
        self.assembly_pattern = re.compile(r'^(GCF|GCA)_\d{9}\.\d+$')
        self.biosample_pattern = re.compile(r'^SAM(N|D|EA?)\d+$')
        self.bioproject_pattern = re.compile(r'^PRJ(NA|EA|DB)\d+$')
        self.taxid_pattern = re.compile(r'^\d+$')
        # Pattern to match GCA/GCF with space instead of underscore (e.g., "GCA 900066335.1")
        self.assembly_with_space_pattern = re.compile(r'\b(GCF|GCA)\s+(\d{9}\.\d+)\b')
        
        logging.info(f"✅ AssemblyResolver initialized")
        logging.info(f"   Email: {email}")
        logging.info(f"   API key: {'Yes' if api_key else 'No'}")
        logging.info(f"   Delay: {self.delay}s")
    
    def identify_type(self, identifier: str) -> IdentifierType:
        """
        Identify the type of identifier
        
        Args:
            identifier: Input identifier string
            
        Returns:
            IdentifierType enum value
        """
        identifier = identifier.strip()
        
        if self.assembly_pattern.match(identifier):
            return IdentifierType.ASSEMBLY_ACCESSION
        elif self.biosample_pattern.match(identifier):
            return IdentifierType.BIOSAMPLE
        elif self.bioproject_pattern.match(identifier):
            return IdentifierType.BIOPROJECT
        elif self.taxid_pattern.match(identifier):
            return IdentifierType.TAXID
        elif ' ' in identifier or identifier[0].isupper():
            # Heuristic: contains space or starts with capital = likely species/strain name
            return IdentifierType.SPECIES_NAME
        else:
            return IdentifierType.UNKNOWN
    
    def parse_host_field(self, host_field: str) -> List[Tuple[str, IdentifierType]]:
        """
        Parse a complex host field that may contain semicolon-separated values
        
        This method handles fields like "NA;GCA 900066335.1;UBA9502;Blautia..." by:
        1. Splitting on semicolons
        2. Fixing GCA/GCF accessions with spaces (e.g., "GCA 900066335.1" → "GCA_900066335.1")
        3. Filtering out "NA" and empty values
        4. Identifying the type of each component
        5. Returning them in priority order (accessions first, then names)
        
        Args:
            host_field: Raw host field value
            
        Returns:
            List of (identifier, type) tuples in priority order
        """
        if not host_field or host_field is None:
            return []
        
        # Handle various "null" representations
        host_field = str(host_field).strip()
        if host_field == '' or host_field.lower() in ('nan', 'none', 'null'):
            return []
        
        # First, try to fix GCA/GCF accessions with spaces anywhere in the field
        # This handles "GCA 900066335.1" → "GCA_900066335.1"
        host_field = self.assembly_with_space_pattern.sub(r'\1_\2', host_field)
        
        # Split on semicolons
        parts = [p.strip() for p in host_field.split(';')]
        
        # Parse each part and classify
        identifiers = []
        for part in parts:
            if not part or part.upper() == 'NA' or part == '-' or part == '':
                continue
            
            # Identify type
            id_type = self.identify_type(part)
            
            # Skip unknown types that are likely noise
            if id_type == IdentifierType.UNKNOWN:
                logging.debug(f"Skipping unknown identifier type: '{part}'")
                continue
            
            identifiers.append((part, id_type))
        
        # Sort by priority using class-level constant
        identifiers.sort(key=lambda x: self.IDENTIFIER_PRIORITY.get(x[1], 99))
        
        return identifiers
    
    def resolve_with_fallback(self,
                              identifier: str,
                              prefer_refseq: bool = True,
                              require_complete: bool = False,
                              max_results: int = 10) -> List[AssemblyMetadata]:
        """
        Resolve identifier with automatic fallback for complex fields
        
        This method first checks if the identifier is a complex semicolon-separated
        field and tries multiple resolution strategies:
        1. Try each component in priority order (accessions first)
        2. Return the first successful resolution
        
        Args:
            identifier: Input identifier (may be complex semicolon-separated)
            prefer_refseq: Prefer RefSeq (GCF_) over GenBank (GCA_)
            require_complete: Only return complete genomes
            max_results: Maximum number of results to return
            
        Returns:
            List of AssemblyMetadata objects, ranked by quality score
        """
        # Parse the field to extract potential identifiers
        parsed_identifiers = self.parse_host_field(identifier)
        
        if not parsed_identifiers:
            # Fall back to standard resolution
            return self.resolve(identifier, prefer_refseq, require_complete, max_results)
        
        # If we have multiple identifiers, try them in priority order
        if len(parsed_identifiers) > 1:
            logging.info(f"🔍 Parsed complex field '{identifier}' into {len(parsed_identifiers)} components")
            for i, (parsed_id, id_type) in enumerate(parsed_identifiers, 1):
                logging.info(f"   {i}. '{parsed_id}' (type: {id_type.value})")
        
        # Try each identifier until we get results
        for parsed_id, id_type in parsed_identifiers:
            try:
                results = self.resolve(parsed_id, prefer_refseq, require_complete, max_results)
                if results:
                    if len(parsed_identifiers) > 1:
                        logging.info(f"✅ Successfully resolved using: '{parsed_id}' ({id_type.value})")
                    return results
            except Exception as e:
                logging.debug(f"Failed to resolve '{parsed_id}': {e}")
                continue
        
        # No results from any component
        logging.warning(f"⚠️  Could not resolve any component of: {identifier}")
        return []
    
    def resolve(self, 
                identifier: str,
                prefer_refseq: bool = True,
                require_complete: bool = False,
                max_results: int = 10) -> List[AssemblyMetadata]:
        """
        Resolve identifier to assembly metadata
        
        Args:
            identifier: Input identifier (any supported type)
            prefer_refseq: Prefer RefSeq (GCF_) over GenBank (GCA_)
            require_complete: Only return complete genomes
            max_results: Maximum number of results to return
            
        Returns:
            List of AssemblyMetadata objects, ranked by quality score
        """
        id_type = self.identify_type(identifier)
        logging.info(f"🔍 Resolving '{identifier}' (type: {id_type.value})")
        
        if id_type == IdentifierType.ASSEMBLY_ACCESSION:
            return self._resolve_assembly_accession(identifier)
        elif id_type == IdentifierType.BIOSAMPLE:
            return self._resolve_biosample(identifier, prefer_refseq, require_complete, max_results)
        elif id_type == IdentifierType.BIOPROJECT:
            return self._resolve_bioproject(identifier, prefer_refseq, require_complete, max_results)
        elif id_type == IdentifierType.SPECIES_NAME:
            return self._resolve_species_name(identifier, prefer_refseq, require_complete, max_results)
        elif id_type == IdentifierType.TAXID:
            return self._resolve_taxid(identifier, prefer_refseq, require_complete, max_results)
        else:
            logging.warning(f"⚠️  Unknown identifier type: {identifier}")
            return []
    
    def _resolve_assembly_accession(self, accession: str) -> List[AssemblyMetadata]:
        """Resolve assembly accession directly"""
        try:
            time.sleep(self.delay)
            
            # Search for exact accession
            handle = Entrez.esearch(
                db="assembly",
                term=f"{accession}[Assembly Accession]",
                retmax=1
            )
            search_results = Entrez.read(handle)
            handle.close()
            
            if not search_results['IdList']:
                logging.warning(f"⚠️  Assembly not found: {accession}")
                return []
            
            # Get assembly summary
            time.sleep(self.delay)
            handle = Entrez.esummary(db="assembly", id=search_results['IdList'][0])
            summary = Entrez.read(handle, validate=False)
            handle.close()
            
            doc_sum = summary['DocumentSummarySet']['DocumentSummary'][0]
            metadata = self._parse_assembly_summary(doc_sum)
            
            return [metadata] if metadata else []
            
        except Exception as e:
            logging.error(f"❌ Error resolving assembly accession {accession}: {e}")
            return []
    
    def _resolve_biosample(self, 
                          biosample: str,
                          prefer_refseq: bool,
                          require_complete: bool,
                          max_results: int) -> List[AssemblyMetadata]:
        """Resolve BioSample to assemblies"""
        try:
            time.sleep(self.delay)
            
            # Search assemblies linked to BioSample
            search_term = f"{biosample}[BioSample]"
            if prefer_refseq:
                search_term += ' AND "latest refseq"[Filter]'
            
            handle = Entrez.esearch(
                db="assembly",
                term=search_term,
                retmax=max_results * 2  # Get more to filter
            )
            search_results = Entrez.read(handle)
            handle.close()
            
            if not search_results['IdList']:
                logging.warning(f"⚠️  No assemblies found for BioSample: {biosample}")
                return []
            
            return self._fetch_and_rank_assemblies(
                search_results['IdList'],
                prefer_refseq,
                require_complete,
                max_results
            )
            
        except Exception as e:
            logging.error(f"❌ Error resolving BioSample {biosample}: {e}")
            return []
    
    def _resolve_bioproject(self,
                           bioproject: str,
                           prefer_refseq: bool,
                           require_complete: bool,
                           max_results: int) -> List[AssemblyMetadata]:
        """Resolve BioProject to assemblies"""
        try:
            time.sleep(self.delay)
            
            # Search assemblies linked to BioProject
            search_term = f"{bioproject}[BioProject]"
            if prefer_refseq:
                search_term += ' AND "latest refseq"[Filter]'
            
            handle = Entrez.esearch(
                db="assembly",
                term=search_term,
                retmax=max_results * 2
            )
            search_results = Entrez.read(handle)
            handle.close()
            
            if not search_results['IdList']:
                logging.warning(f"⚠️  No assemblies found for BioProject: {bioproject}")
                return []
            
            return self._fetch_and_rank_assemblies(
                search_results['IdList'],
                prefer_refseq,
                require_complete,
                max_results
            )
            
        except Exception as e:
            logging.error(f"❌ Error resolving BioProject {bioproject}: {e}")
            return []
    
    def _resolve_species_name(self,
                             species_name: str,
                             prefer_refseq: bool,
                             require_complete: bool,
                             max_results: int) -> List[AssemblyMetadata]:
        """
        Resolve species name to assemblies
        
        Note: Explicitly acknowledges ambiguity. Multiple strains may exist for a species.
        Uses taxonomy as helper to validate, not as guarantee of assembly availability.
        """
        try:
            # First, try to get TaxID for validation
            taxid = self._get_taxid_for_species(species_name)
            if taxid:
                logging.info(f"   Found TaxID {taxid} for '{species_name}'")
            else:
                logging.warning(f"⚠️  Could not resolve TaxID for '{species_name}' (may be ambiguous)")
            
            time.sleep(self.delay)
            
            # Search assemblies for species
            search_term = f'"{species_name}"[Organism]'
            if prefer_refseq:
                search_term += ' AND "latest refseq"[Filter]'
            
            handle = Entrez.esearch(
                db="assembly",
                term=search_term,
                retmax=max_results * 3  # Get more since names can be ambiguous
            )
            search_results = Entrez.read(handle)
            handle.close()
            
            if not search_results['IdList']:
                logging.warning(f"⚠️  No assemblies found for species: {species_name}")
                logging.warning(f"   This may indicate:")
                logging.warning(f"   - Species name is misspelled or non-standard")
                logging.warning(f"   - No genome assemblies available for this species")
                logging.warning(f"   - Name is ambiguous (multiple taxa)")
                return []
            
            assemblies = self._fetch_and_rank_assemblies(
                search_results['IdList'],
                prefer_refseq,
                require_complete,
                max_results
            )
            
            if len(assemblies) > 1:
                logging.warning(f"⚠️  Ambiguity detected: {len(assemblies)} assemblies found for '{species_name}'")
                logging.warning(f"   Returning top {min(max_results, len(assemblies))} by quality ranking")
                logging.warning(f"   Consider using more specific identifier (strain, BioSample, etc.)")
            
            return assemblies
            
        except Exception as e:
            logging.error(f"❌ Error resolving species name '{species_name}': {e}")
            return []
    
    def _resolve_taxid(self,
                      taxid: str,
                      prefer_refseq: bool,
                      require_complete: bool,
                      max_results: int) -> List[AssemblyMetadata]:
        """Resolve TaxID to assemblies"""
        try:
            time.sleep(self.delay)
            
            # Search assemblies for TaxID
            search_term = f"txid{taxid}[Organism]"
            if prefer_refseq:
                search_term += ' AND "latest refseq"[Filter]'
            
            handle = Entrez.esearch(
                db="assembly",
                term=search_term,
                retmax=max_results * 2
            )
            search_results = Entrez.read(handle)
            handle.close()
            
            if not search_results['IdList']:
                logging.warning(f"⚠️  No assemblies found for TaxID: {taxid}")
                return []
            
            return self._fetch_and_rank_assemblies(
                search_results['IdList'],
                prefer_refseq,
                require_complete,
                max_results
            )
            
        except Exception as e:
            logging.error(f"❌ Error resolving TaxID {taxid}: {e}")
            return []
    
    def _get_taxid_for_species(self, species_name: str) -> Optional[int]:
        """Get TaxID for species name (helper, not guarantee)"""
        try:
            time.sleep(self.delay)
            
            handle = Entrez.esearch(db="taxonomy", term=f'"{species_name}"[Scientific Name]')
            search_results = Entrez.read(handle)
            handle.close()
            
            if search_results['IdList']:
                return int(search_results['IdList'][0])
            return None
            
        except Exception as e:
            logging.debug(f"Could not get TaxID for {species_name}: {e}")
            return None
    
    def _fetch_and_rank_assemblies(self,
                                   assembly_ids: List[str],
                                   prefer_refseq: bool,
                                   require_complete: bool,
                                   max_results: int) -> List[AssemblyMetadata]:
        """Fetch assembly summaries and rank by quality"""
        try:
            time.sleep(self.delay)
            
            # Fetch summaries in batches
            assemblies = []
            batch_size = 100
            
            for i in range(0, len(assembly_ids), batch_size):
                batch_ids = assembly_ids[i:i + batch_size]
                
                handle = Entrez.esummary(db="assembly", id=",".join(batch_ids))
                summaries = Entrez.read(handle, validate=False)
                handle.close()
                
                for doc_sum in summaries['DocumentSummarySet']['DocumentSummary']:
                    metadata = self._parse_assembly_summary(doc_sum)
                    if metadata:
                        assemblies.append(metadata)
                
                if i + batch_size < len(assembly_ids):
                    time.sleep(self.delay)
            
            # Filter assemblies
            filtered = []
            for asm in assemblies:
                # Filter by completeness if required
                if require_complete and asm.assembly_level != "Complete Genome":
                    continue
                
                # Prefer RefSeq if requested
                if prefer_refseq and not asm.is_refseq():
                    # Only include GenBank if no RefSeq alternative
                    refseq_exists = any(a.is_refseq() for a in assemblies)
                    if refseq_exists:
                        continue
                
                filtered.append(asm)
            
            # Rank by quality score
            ranked = sorted(filtered, key=lambda x: x.get_quality_score(), reverse=True)
            
            return ranked[:max_results]
            
        except Exception as e:
            logging.error(f"❌ Error fetching/ranking assemblies: {e}")
            return []
    
    def _parse_assembly_summary(self, doc_sum) -> Optional[AssemblyMetadata]:
        """Parse Entrez assembly summary to AssemblyMetadata"""
        try:
            # Extract FTP path
            ftp_path = None
            if 'FtpPath_RefSeq' in doc_sum and doc_sum['FtpPath_RefSeq']:
                ftp_path = doc_sum['FtpPath_RefSeq']
            elif 'FtpPath_GenBank' in doc_sum and doc_sum['FtpPath_GenBank']:
                ftp_path = doc_sum['FtpPath_GenBank']
            
            # Extract strain field with proper None handling
            strain = doc_sum.get('Biosource', {}).get('InfraspecificNames', {}).get('Strain', '')
            if not strain or strain.strip() == '':
                strain = None
            
            return AssemblyMetadata(
                assembly_accession=doc_sum.get('AssemblyAccession', ''),
                assembly_name=doc_sum.get('AssemblyName', ''),
                organism_name=doc_sum.get('SpeciesName', ''),
                species_taxid=int(doc_sum['SpeciesTaxid']) if 'SpeciesTaxid' in doc_sum else None,
                strain=strain,
                assembly_level=doc_sum.get('AssemblyStatus', 'Contig'),
                refseq_category=doc_sum.get('RefSeq_category', 'na'),
                biosample=doc_sum.get('BioSampleAccn', '') or None,
                bioproject=doc_sum.get('BioprojectAccn', '') or None,
                ftp_path=ftp_path,
                submission_date=doc_sum.get('SubmissionDate', ''),
                is_latest='latest' in doc_sum.get('PropertyList', [])
            )
            
        except Exception as e:
            logging.error(f"Error parsing assembly summary: {e}")
            return None
    
    def get_best_assembly(self,
                         identifier: str,
                         prefer_refseq: bool = True,
                         require_complete: bool = False) -> Optional[AssemblyMetadata]:
        """
        Get single best assembly for an identifier
        
        Convenience method that returns only the top-ranked assembly.
        Automatically handles complex semicolon-separated fields.
        
        Args:
            identifier: Input identifier (may be complex semicolon-separated)
            prefer_refseq: Prefer RefSeq over GenBank
            require_complete: Only consider complete genomes
            
        Returns:
            Top-ranked AssemblyMetadata or None
        """
        assemblies = self.resolve_with_fallback(
            identifier,
            prefer_refseq=prefer_refseq,
            require_complete=require_complete,
            max_results=1
        )
        
        return assemblies[0] if assemblies else None
