# Welcome to PBI Documentation

**Phage-Bacteria Interaction Database Pipeline**

PBI is a comprehensive bioinformatics pipeline and API for aggregating, processing, and querying phage genomic data from multiple public databases. It creates a unified, optimized database from diverse phage data sources including GenBank, RefSeq, PhagesDB, and many more via [PhageScope](https://phagescope.deepomics.org/workspace/).

## 🚀 Quick Start

Choose your preferred method:

- **🐳 Docker (Recommended)**: Get started quickly → [Docker Guide](guides/docker-guide.md)
- **💻 Local Installation**: For development and customization → [Installation Guide](guides/installation.md)
- **📊 Database Overview**: Explore the data structure → [Database Documentation](database/overview.md)

## 📋 Development Status

| Component | Status | Description |
|-----------|--------|-------------|
| **Database Integration** | ✅ Complete | All 9 PhageScope tables integrated into DuckDB |
| **Database Optimization** | ✅ Complete | Star schema with indexes and materialized views |
| **Sequence Processing** | ✅ Complete | FASTA indexing with pyfaidx for fast retrieval |
| **Data Validation** | ✅ Complete | Comprehensive quality checks and HTML reports |
| **Docker Support** | ✅ Complete | Pipeline and API containers with volume management |
| **API Development** | 🔄 In Progress | Basic endpoints functional, expanding features |
| **Python Package** | 🔄 In Progress | Core functionality available, adding features |
| **Documentation** | 🔄 In Progress | Improving clarity and completeness |
| **Testing Suite** | 🔄 In Progress | Adding unit and integration tests |
| **Pipeline Review** | 📆 Planned | Code review and optimization |
| **Host Genome Retrieval** | 📆 Planned | Bacterial genome fetching from species names |
| **External Data Integration** | 📆 Planned | Additional databases beyond PhageScope |

## 🎯 Project Goals & Roadmap

### Current Focus
The PhageScope data integration is complete. Current efforts focus on:
- **API Enhancement**: Expanding endpoints and adding authentication
- **Python Package**: Developing user-friendly functions for data retrieval and analysis
- **Documentation**: Creating comprehensive guides and examples
- **Testing**: Ensuring reliability and correctness

### Future Directions
From this solid foundation, we plan to:
1. **Expand Data Sources**: Integrate additional specialized databases
2. **Host Genome Integration**: Automated retrieval of bacterial genomes matching phages
3. **Custom Database Schema**: Optimized structure inspired by projects like [INPHINITY](https://www.ingenierie-sante.ch/fr/projects/84/INPHINITY)
4. **Advanced Analytics**: Built-in analysis tools and machine learning integration

## 📊 Current Database

The pipeline has successfully integrated data from **14 major phage databases**:

- **~873,000 phage genomes** with complete metadata
- **~43 million protein annotations** with functional predictions
- **~6.5 million transcription terminators**
- **~702,000 tRNA/tmRNA features**
- **~4 million transmembrane protein predictions**
- Plus CRISPR systems, virulence factors, and antimicrobial resistance genes

**Database Size**: ~15 GB optimized DuckDB  
**Sequence Files**: ~100 GB indexed FASTA files  
**Reports**: Comprehensive HTML validation and metadata reports

📊 [View Database Validation Report](reports/database_validation.html)

## 📚 Documentation Structure

- **[Guides](guides/overview.md)**: Installation, Docker, and usage guides
- **[Database](database/overview.md)**: Schema, tables, and data sources
- **[API Reference](api/overview.md)**: REST API endpoints and examples  
- **[Command Reference](reference/commands.md)**: Useful commands and snippets
- **[Developer Guide](developer/code-structure.md)**: Architecture and contributing

## 🆘 Support & Contributing

- **Issues**: Report bugs or request features via [GitHub Issues](https://github.com/ThibaultSchowing/PBI/issues)
- **Documentation**: Browse these docs or check inline code comments
- **Contributing**: See the [Developer Guide](developer/code-structure.md)

---

**Note**: This project is under active development. Some features are still being refined and tested.

_Built with assistance from GitHub Copilot and Claude Sonnet 4.5_

