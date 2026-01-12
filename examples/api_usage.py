#!/usr/bin/env python3
"""
Example script demonstrating how to use the PBI API

This script shows basic usage patterns for querying the PBI database through the REST API.
"""

import requests
import json
from typing import Optional

# API Configuration
API_BASE_URL = "http://localhost:8000"


def check_health():
    """Check if the API is healthy and responding"""
    print("🔍 Checking API health...")
    response = requests.get(f"{API_BASE_URL}/health")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ API is healthy: {data}")
        return True
    else:
        print(f"❌ API health check failed: {response.status_code}")
        return False


def get_stats():
    """Get database statistics"""
    print("\n📊 Fetching database statistics...")
    response = requests.get(f"{API_BASE_URL}/stats")
    
    if response.status_code == 200:
        stats = response.json()
        print("Database Statistics:")
        print(json.dumps(stats, indent=2))
        return stats
    else:
        print(f"❌ Failed to get stats: {response.status_code}")
        return None


def list_tables():
    """List all available tables"""
    print("\n📋 Listing all tables...")
    response = requests.get(f"{API_BASE_URL}/tables")
    
    if response.status_code == 200:
        tables = response.json()
        print("Available tables:")
        for table in tables.get("tables", []):
            print(f"  - {table}")
        return tables
    else:
        print(f"❌ Failed to list tables: {response.status_code}")
        return None


def get_table_schema(table_name: str):
    """Get schema for a specific table"""
    print(f"\n🔍 Getting schema for table '{table_name}'...")
    response = requests.get(f"{API_BASE_URL}/tables/{table_name}/schema")
    
    if response.status_code == 200:
        schema = response.json()
        print(f"Schema for {table_name}:")
        for col in schema.get("schema", []):
            print(f"  - {col.get('column_name')}: {col.get('column_type')}")
        return schema
    else:
        print(f"❌ Failed to get schema: {response.status_code}")
        return None


def query_phages(limit: int = 10, source_db: Optional[str] = None):
    """Query phages with optional filters"""
    print(f"\n🧬 Querying phages (limit={limit})...")
    
    params = {"limit": limit}
    if source_db:
        params["source_db"] = source_db
    
    response = requests.get(f"{API_BASE_URL}/phages", params=params)
    
    if response.status_code == 200:
        data = response.json()
        print(f"Found {data['count']} phages:")
        for i, phage in enumerate(data['phages'][:3], 1):  # Show first 3
            print(f"  {i}. {phage.get('Phage_ID')} - Length: {phage.get('Length')} bp")
        if data['count'] > 3:
            print(f"  ... and {data['count'] - 3} more")
        return data
    else:
        print(f"❌ Failed to query phages: {response.status_code}")
        return None


def get_data_sources():
    """Get list of data sources"""
    print("\n📚 Fetching data sources...")
    response = requests.get(f"{API_BASE_URL}/sources")
    
    if response.status_code == 200:
        sources = response.json()
        print("Data sources:")
        for source in sources.get("sources", []):
            print(f"  - {source.get('Source_DB')}: {source.get('phage_count')} phages")
        return sources
    else:
        print(f"❌ Failed to get sources: {response.status_code}")
        return None


def custom_query(sql: str, limit: int = 10):
    """Execute a custom SQL query"""
    print(f"\n💾 Executing custom query...")
    print(f"SQL: {sql[:100]}...")
    
    data = {
        "sql": sql,
        "limit": limit
    }
    
    response = requests.post(f"{API_BASE_URL}/query", json=data)
    
    if response.status_code == 200:
        result = response.json()
        print(f"Query returned {result['rows']} rows")
        print(f"Columns: {', '.join(result['columns'])}")
        
        # Show first few rows
        for i, row in enumerate(result['data'][:3], 1):
            print(f"  Row {i}: {row}")
        
        return result
    else:
        print(f"❌ Query failed: {response.status_code}")
        print(response.text)
        return None


def main():
    """Main example workflow"""
    print("=" * 80)
    print("PBI API Example Usage")
    print("=" * 80)
    
    # 1. Check health
    if not check_health():
        print("\n❌ API is not available. Make sure it's running:")
        print("   docker-compose up -d api")
        return
    
    # 2. Get statistics
    get_stats()
    
    # 3. List tables
    list_tables()
    
    # 4. Get schema for a table
    get_table_schema("fact_phages")
    
    # 5. Get data sources
    get_data_sources()
    
    # 6. Query phages
    query_phages(limit=10)
    
    # 7. Query phages from specific source
    query_phages(limit=5, source_db="RefSeq")
    
    # 8. Custom SQL query
    custom_query(
        "SELECT Source_DB, COUNT(*) as count FROM fact_phages GROUP BY Source_DB",
        limit=20
    )
    
    print("\n" + "=" * 80)
    print("✅ Example completed successfully!")
    print("=" * 80)
    print("\nFor more information, visit the API documentation:")
    print("  - Swagger UI: http://localhost:8000/docs")
    print("  - ReDoc: http://localhost:8000/redoc")


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print("\n❌ Could not connect to the API.")
        print("   Make sure the API is running:")
        print("   docker-compose up -d api")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
        import traceback
        traceback.print_exc()
