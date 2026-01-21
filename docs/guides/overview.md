# Guides Overview

Welcome to the PBI guides! Choose the guide that matches your needs.

## Getting Started

New to PBI? Start here:

### 🐳 [Docker Guide](docker-guide.md) (Recommended)
The fastest way to get PBI up and running. Ideal for:
- Quick evaluation and testing
- Consistent environments
- Production deployments
- Users who prefer containers

**Time to first query**: ~2-4 hours (mostly downloading data)

### 💻 [Local Installation](installation.md)
For development and customization. Best for:
- Active development
- Custom modifications
- Learning the pipeline internals
- Maximum flexibility

**Time to setup**: ~30 minutes + 2-4 hours for pipeline

## Usage Guides

Once installed, learn how to use PBI:

### 📊 [Database Overview](../database/overview.md)
Understand the database schema, tables, and data sources.

### 🔌 [API Reference](../api/overview.md)
Learn to query data via the REST API (work in progress).

### 📝 [Command Reference](../reference/commands.md)
Quick reference for common operations and commands.

## Choosing Your Path

```
Are you...
│
├─ Just trying it out?
│  └─> Use Docker Guide
│
├─ Planning to modify the code?
│  └─> Use Local Installation
│
├─ Setting up for production?
│  └─> Use Docker Guide + custom configuration
│
└─ Analyzing existing data?
   └─> Either works, Docker is faster
```

## What You'll Get

Regardless of installation method, you'll have:

- **~873,000 phage genomes** with metadata
- **~43 million protein annotations**
- **Optimized DuckDB database** (~15 GB)
- **Indexed FASTA files** (~100 GB)
- **HTML validation reports**
- **REST API** for programmatic access (optional)

## Prerequisites Comparison

| Requirement | Docker | Local |
|-------------|--------|-------|
| Docker | ✅ Required | ❌ Not needed |
| Python | ❌ Not needed | ✅ Required (3.8+) |
| Conda | ❌ Not needed | ✅ Required |
| Disk Space | 60+ GB | 60+ GB |
| RAM | 16+ GB | 32+ GB recommended |
| Time to First Run | 2-4 hours | 2-4 hours + setup |

## Next Steps

1. Choose your installation method
2. Follow the corresponding guide
3. Explore the [Database Documentation](../database/overview.md)
4. Try some [example commands](../reference/commands.md)
5. Query data via the [API](../api/overview.md) or Python

## Need Help?

- Check the [Command Reference](../reference/commands.md) for quick answers
- Review [troubleshooting sections](installation.md#troubleshooting) in each guide
- Open an issue on [GitHub](https://github.com/ThibaultSchowing/PBI/issues)

---

Ready? Pick a guide above and get started! 🚀
