#!/usr/bin/env python3
"""
Test script for streaming dataset functionality.

Tests the PhageHostStreamingDataset and PhageHostIndexedDataset classes
to ensure they can be instantiated and used correctly.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

def test_streaming_dataset_imports():
    """Test that streaming dataset classes can be imported."""
    print("=" * 60)
    print("Test 1: Import Streaming Dataset Classes")
    print("=" * 60)
    
    try:
        from pbi import PhageHostStreamingDataset, PhageHostIndexedDataset
        print("✓ Successfully imported PhageHostStreamingDataset")
        print("✓ Successfully imported PhageHostIndexedDataset")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


def test_sequence_retriever_methods():
    """Test that SequenceRetriever has new methods."""
    print("\n" + "=" * 60)
    print("Test 2: SequenceRetriever Methods")
    print("=" * 60)
    
    try:
        from pbi import SequenceRetriever
        
        # Check for new methods
        required_methods = [
            'create_streaming_dataset',
            'create_indexed_dataset',
            'get_phage_host_pairs_iterator',
            '_get_sequence_safe'
        ]
        
        all_present = True
        for method in required_methods:
            if hasattr(SequenceRetriever, method):
                print(f"✓ Method '{method}' exists")
            else:
                print(f"✗ Method '{method}' NOT FOUND")
                all_present = False
        
        return all_present
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False


def test_dataset_class_structure():
    """Test that dataset classes have required methods."""
    print("\n" + "=" * 60)
    print("Test 3: Dataset Class Structure")
    print("=" * 60)
    
    try:
        from pbi.streaming_dataset import PhageHostStreamingDataset, PhageHostIndexedDataset
        
        # Check PhageHostStreamingDataset
        print("\nPhageHostStreamingDataset:")
        streaming_methods = ['__iter__', '_init_worker', '_get_phage_sequence_safe', '_get_host_sequence_safe']
        all_present = True
        for method in streaming_methods:
            if hasattr(PhageHostStreamingDataset, method):
                print(f"  ✓ Method '{method}' exists")
            else:
                print(f"  ✗ Method '{method}' NOT FOUND")
                all_present = False
        
        # Check PhageHostIndexedDataset
        print("\nPhageHostIndexedDataset:")
        indexed_methods = ['__len__', '__getitem__', '_load_metadata', '_ensure_fasta_loaded']
        for method in indexed_methods:
            if hasattr(PhageHostIndexedDataset, method):
                print(f"  ✓ Method '{method}' exists")
            else:
                print(f"  ✗ Method '{method}' NOT FOUND")
                all_present = False
        
        return all_present
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False


def test_error_handling():
    """Test that datasets properly handle missing files."""
    print("\n" + "=" * 60)
    print("Test 4: Error Handling")
    print("=" * 60)
    
    try:
        from pbi.streaming_dataset import PhageHostStreamingDataset
        
        # Test with non-existent database
        try:
            dataset = PhageHostStreamingDataset(
                db_path='/nonexistent/db.duckdb',
                phage_fasta_path='/nonexistent/phages.fasta',
                host_fasta_path='/nonexistent/hosts.fasta'
            )
            print("✗ Should have raised FileNotFoundError")
            return False
        except FileNotFoundError as e:
            print(f"✓ Properly raised FileNotFoundError: {str(e)[:60]}...")
            return True
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False


def test_torch_optional():
    """Test that datasets work without PyTorch."""
    print("\n" + "=" * 60)
    print("Test 5: PyTorch Optional Dependency")
    print("=" * 60)
    
    try:
        # Import without PyTorch should still work
        from pbi.streaming_dataset import PhageHostStreamingDataset, TORCH_AVAILABLE
        
        if TORCH_AVAILABLE:
            print("✓ PyTorch is available")
        else:
            print("✓ PyTorch not available - fallback classes used")
        
        # Classes should be importable either way
        print("✓ Dataset classes can be imported without PyTorch")
        return True
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False


def test_collate_function():
    """Test the custom collate function."""
    print("\n" + "=" * 60)
    print("Test 6: Custom Collate Function")
    print("=" * 60)
    
    try:
        from pbi.streaming_dataset import phage_host_collate_fn
        
        # Test with sample data
        batch = [
            {'Phage_ID': 'phage1', 'Host_ID': 'host1', 'Phage_Length': 100},
            {'Phage_ID': 'phage2', 'Host_ID': 'host2', 'Phage_Length': 200},
            {'Phage_ID': 'phage3', 'Host_ID': 'host3', 'Phage_Length': 150},
        ]
        
        collated = phage_host_collate_fn(batch)
        
        # Verify structure
        assert isinstance(collated, dict), "Result should be a dictionary"
        assert len(collated['Phage_ID']) == 3, "Should have 3 Phage_IDs"
        assert collated['Phage_ID'] == ['phage1', 'phage2', 'phage3'], "Phage IDs should match"
        assert collated['Phage_Length'] == [100, 200, 150], "Lengths should match"
        print("✓ Collate function handles mixed types correctly")
        
        # Test with empty batch
        empty_result = phage_host_collate_fn([])
        assert empty_result == {}, "Empty batch should return empty dict"
        print("✓ Collate function handles empty batch")
        
        # Test with None values
        batch_with_none = [
            {'Phage_ID': 'phage1', 'Cluster': 'A', 'Subcluster': None},
            {'Phage_ID': 'phage2', 'Cluster': None, 'Subcluster': 'B1'},
        ]
        collated_none = phage_host_collate_fn(batch_with_none)
        assert collated_none['Cluster'] == ['A', None], "Should preserve None values"
        print("✓ Collate function handles None values correctly")
        
        return True
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("PBI Streaming Dataset Tests")
    print("=" * 60 + "\n")
    
    tests = [
        test_streaming_dataset_imports,
        test_sequence_retriever_methods,
        test_dataset_class_structure,
        test_error_handling,
        test_torch_optional,
        test_collate_function
    ]
    
    results = []
    for test in tests:
        result = test()
        results.append(result)
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    print(f"\nPassed: {passed}/{total}")
    
    if passed == total:
        print("\n✅ All tests passed!")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
