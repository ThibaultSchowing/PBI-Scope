#!/bin/bash
# Test script to validate the fixed shell logic for FASTA file merging
# This script tests the three scenarios:
# 1. No FASTA files found (should create empty file)
# 2. One FASTA file found (should copy it)
# 3. Multiple FASTA files found (would call Python script in actual implementation)

set -e

# Create temporary test directories
TEST_DIR="/tmp/test_fasta_merge_$$"
mkdir -p "$TEST_DIR"

echo "🧪 Testing FASTA merge shell logic..."
echo "=================================="

# Test 1: No FASTA files
echo "Test 1: No FASTA files found"
SOURCE_DIR="$TEST_DIR/empty_source"
OUTPUT_FILE="$TEST_DIR/test1_output.fasta"
mkdir -p "$SOURCE_DIR"

# Run the shell logic
mapfile -t fasta_files < <(find "$SOURCE_DIR" -type f \( -name "*.fasta" -o -name "*.fa" \))

if [ "${#fasta_files[@]}" -eq 0 ]; then
    echo "⚠️ WARNING: No FASTA files found in $SOURCE_DIR - creating empty file" >&2
    touch "$OUTPUT_FILE"
elif [ "${#fasta_files[@]}" -eq 1 ]; then
    cp "${fasta_files[0]}" "$OUTPUT_FILE"
else
    echo "Multiple files found (would call Python script)"
fi

# Verify
if [ -f "$OUTPUT_FILE" ] && [ ! -s "$OUTPUT_FILE" ]; then
    echo "✅ Test 1 PASSED: Empty file created"
else
    echo "❌ Test 1 FAILED: Expected empty file"
    exit 1
fi

# Test 2: One FASTA file
echo ""
echo "Test 2: One FASTA file found"
SOURCE_DIR="$TEST_DIR/single_source"
OUTPUT_FILE="$TEST_DIR/test2_output.fasta"
mkdir -p "$SOURCE_DIR"
echo ">seq1" > "$SOURCE_DIR/test.fasta"
echo "ATGC" >> "$SOURCE_DIR/test.fasta"

# Run the shell logic
mapfile -t fasta_files < <(find "$SOURCE_DIR" -type f \( -name "*.fasta" -o -name "*.fa" \))

if [ "${#fasta_files[@]}" -eq 0 ]; then
    echo "⚠️ WARNING: No FASTA files found in $SOURCE_DIR - creating empty file" >&2
    touch "$OUTPUT_FILE"
elif [ "${#fasta_files[@]}" -eq 1 ]; then
    cp "${fasta_files[0]}" "$OUTPUT_FILE"
else
    echo "Multiple files found (would call Python script)"
fi

# Verify
if [ -f "$OUTPUT_FILE" ] && grep -q "ATGC" "$OUTPUT_FILE"; then
    echo "✅ Test 2 PASSED: File copied correctly"
else
    echo "❌ Test 2 FAILED: Expected copied file with content"
    exit 1
fi

# Test 3: Multiple FASTA files (with .fa extension too)
echo ""
echo "Test 3: Multiple FASTA files found"
SOURCE_DIR="$TEST_DIR/multi_source"
OUTPUT_FILE="$TEST_DIR/test3_output.fasta"
mkdir -p "$SOURCE_DIR"
echo ">seq1" > "$SOURCE_DIR/test1.fasta"
echo "ATGC" >> "$SOURCE_DIR/test1.fasta"
echo ">seq2" > "$SOURCE_DIR/test2.fa"
echo "GCTA" >> "$SOURCE_DIR/test2.fa"

# Run the shell logic
mapfile -t fasta_files < <(find "$SOURCE_DIR" -type f \( -name "*.fasta" -o -name "*.fa" \))

MERGE_SCRIPT_CALLED=false
if [ "${#fasta_files[@]}" -eq 0 ]; then
    echo "⚠️ WARNING: No FASTA files found in $SOURCE_DIR - creating empty file" >&2
    touch "$OUTPUT_FILE"
elif [ "${#fasta_files[@]}" -eq 1 ]; then
    cp "${fasta_files[0]}" "$OUTPUT_FILE"
else
    echo "Multiple files found - would call Python merge script"
    MERGE_SCRIPT_CALLED=true
fi

# Verify
if [ "$MERGE_SCRIPT_CALLED" = true ]; then
    echo "✅ Test 3 PASSED: Correctly detected multiple files (${#fasta_files[@]} files)"
else
    echo "❌ Test 3 FAILED: Should have detected multiple files"
    exit 1
fi

# Test 4: Test with files in subdirectories
echo ""
echo "Test 4: FASTA files in subdirectories"
SOURCE_DIR="$TEST_DIR/nested_source"
OUTPUT_FILE="$TEST_DIR/test4_output.fasta"
mkdir -p "$SOURCE_DIR/subdir1/subdir2"
echo ">seq1" > "$SOURCE_DIR/subdir1/test.fasta"
echo "ATGC" >> "$SOURCE_DIR/subdir1/test.fasta"
echo ">seq2" > "$SOURCE_DIR/subdir1/subdir2/test2.fa"
echo "GCTA" >> "$SOURCE_DIR/subdir1/subdir2/test2.fa"

# Run the shell logic
mapfile -t fasta_files < <(find "$SOURCE_DIR" -type f \( -name "*.fasta" -o -name "*.fa" \))

MERGE_SCRIPT_CALLED=false
if [ "${#fasta_files[@]}" -eq 0 ]; then
    echo "⚠️ WARNING: No FASTA files found in $SOURCE_DIR - creating empty file" >&2
    touch "$OUTPUT_FILE"
elif [ "${#fasta_files[@]}" -eq 1 ]; then
    cp "${fasta_files[0]}" "$OUTPUT_FILE"
else
    echo "Multiple files found in subdirectories - would call Python merge script"
    MERGE_SCRIPT_CALLED=true
fi

# Verify
if [ "$MERGE_SCRIPT_CALLED" = true ] && [ "${#fasta_files[@]}" -eq 2 ]; then
    echo "✅ Test 4 PASSED: Correctly found files in subdirectories (${#fasta_files[@]} files)"
else
    echo "❌ Test 4 FAILED: Should have found 2 files in subdirectories, found ${#fasta_files[@]}"
    exit 1
fi

# Cleanup
rm -rf "$TEST_DIR"

echo ""
echo "=================================="
echo "✅ All tests PASSED!"
echo "=================================="
