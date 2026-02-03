from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

setup(
    name="pbi",
    version="0.1.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="Phage Bioinformatics Interface - Tools for phage genomics database interaction",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/PBI",
    
    # Package discovery
    package_dir={"": "src"},  # Packages are under src/
    packages=find_packages(where="src"),  # Find all packages in src/
    
    # Python version requirement
    python_requires=">=3.8",
    
    # Dependencies
    install_requires=[
        "duckdb>=0.9.0",
        "pyfaidx>=0.7.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "biopython>=1.80",
        # Added for workflow scripts compatibility
        "pyyaml>=6.0",
        "aiohttp>=3.8.0",
        "aiofiles>=23.0.0",
    ],
    
    # Optional dependencies for development
    extras_require={
        "dev": [
            "pytest>=7.0",
            "jupyter>=1.0",
            "ipython>=8.0",
        ],
        "analysis": [
            "matplotlib>=3.5",
            "seaborn>=0.12",
            "biopython>=1.80",
            "numpy>=1.24.0",
        ],
    },
    
    # Command-line scripts (optional)
    entry_points={
        "console_scripts": [
            "pbi-retrieve=pbi.sequence_retrieval:main",  # If you add a main() function
        ],
    },
    
    # Classifiers for PyPI
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    
    # Include non-Python files
    include_package_data=True,
)