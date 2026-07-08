# Machine Learning with PBI-Scope

Comprehensive guide for using the PBI-Scope database to build machine learning models for phage-host interaction prediction and other bioinformatics tasks.

## Quick Start

### 1. Set Up Your Environment

```python
import sys
from pathlib import Path

# Add PBI package to path
sys.path.insert(0, str(Path.cwd().parent / 'src'))

from pbi import quick_connect, NegativeExampleGenerator
import pandas as pd
import numpy as np
```

### 2. Connect to Database

```python
# Quick connection with all data
retriever = quick_connect()

# Get statistics
stats = retriever.get_stats()
print(f"Phages: {stats['database']['phages']:,}")
print(f"Hosts: {stats['database']['hosts']:,}")
print(f"Phage-Host Associations: {stats['database']['phage_host_associations']:,}")
```

### 3. Query Phage-Host Pairs

```python
# Get positive interaction examples
positive_pairs = retriever.get_phage_host_pairs(limit=1000)

# Inspect data
print(positive_pairs.head())
print(positive_pairs.columns)
```

### 4. Generate Training Data

```python
# Initialize negative example generator
neg_gen = NegativeExampleGenerator(retriever)

# Create balanced dataset
dataset = neg_gen.generate_balanced_dataset(
    positive_pairs=positive_pairs,
    strategy='mixed',
    positive_ratio=0.5
)

print(f"Dataset size: {len(dataset):,}")
print(f"Positives: {(dataset['Label'] == 1).sum():,}")
print(f"Negatives: {(dataset['Label'] == 0).sum():,}")
```

## Understanding the Data

### Database Schema

The PBI database uses a star schema:

**Fact Tables:**
- `fact_phages` - Core phage metadata (Phage_ID, Length, GC_content, Host, Lifestyle)

**Dimension Tables:**
- `dim_proteins` - Protein annotations
- `dim_hosts` - Host bacterial genomes
- `dim_terminators` - Transcription terminators
- `dim_anti_crispr` - Anti-CRISPR proteins
- `dim_virulent_factors` - Virulence factors
- `dim_transmembrane_proteins` - Transmembrane proteins
- `dim_trna_tmrna` - tRNA/tmRNA annotations
- `dim_antimicrobial_resistance_genes` - AMR genes
- `dim_crispr_arrays` - CRISPR arrays

**Association Tables/Views:**
- `phage_host_associations` - View linking phages to their hosts (joins `dim_phage_host_links` and `dim_hosts` via Assembly_Accession)

### Key Fields for ML

#### Phage Features
- `Phage_ID` - Unique identifier
- `Length` - Genome length (bp)
- `GC_content` - GC percentage
- `Taxonomy` - Taxonomic classification
- `Lifestyle` - Lytic, lysogenic, or temperate
- `Cluster` - Phage cluster
- `Phage_Sequence` - DNA sequence

#### Host Features
- `Host_ID` - Unique identifier
- `Species_Name` - Host species
- `Genome_Length` - Host genome size
- `GC_Content` - Host GC percentage
- `Assembly_Level` - Genome completeness
- `RefSeq_Category` - Reference status
- `Host_Sequence` - DNA sequence

### Data Access Patterns

#### Query Specific Phages

```python
# Get phages by query
query = """
SELECT Phage_ID 
FROM fact_phages 
WHERE Lifestyle = 'Lytic' 
    AND Length > 50000
LIMIT 100
"""
phages = retriever.get_phage_sequences(query)
```

#### Get Host by Phage

```python
# Find host for a specific phage
host = retriever.get_host_by_phage("NC_000866")
print(host[['Host_ID', 'Species_Name', 'Genome_Length']])
```

#### Get Phage-Host Pairs with Filters

```python
# Get pairs with specific criteria
pairs = retriever.get_phage_host_pairs(
    where_clause="p.Lifestyle = 'Lytic' AND h.Species_Name LIKE '%Escherichia%'",
    limit=500
)
```

## Feature Engineering Guide

### Basic Features

```python
def engineer_basic_features(df):
    """Create basic features from phage-host pairs"""
    features = df.copy()
    
    # GC content features
    features['GC_Difference'] = abs(features['Phage_GC'] - features['Host_GC'])
    features['GC_Ratio'] = features['Phage_GC'] / (features['Host_GC'] + 1e-6)
    features['GC_Sum'] = features['Phage_GC'] + features['Host_GC']
    features['GC_Product'] = features['Phage_GC'] * features['Host_GC']
    
    # Length features
    features['Length_Ratio'] = features['Phage_Length'] / (features['Host_Length'] + 1)
    features['Log_Phage_Length'] = np.log10(features['Phage_Length'] + 1)
    features['Log_Host_Length'] = np.log10(features['Host_Length'] + 1)
    features['Length_Difference'] = features['Host_Length'] - features['Phage_Length']
    
    # Interaction features
    features['GC_x_Length_Ratio'] = features['GC_Ratio'] * features['Length_Ratio']
    
    return features
```

### K-mer Features

```python
from collections import Counter

def calculate_kmer_frequencies(sequence, k=4):
    """Calculate k-mer frequencies for a sequence"""
    kmers = [sequence[i:i+k] for i in range(len(sequence) - k + 1)]
    kmer_counts = Counter(kmers)
    total = sum(kmer_counts.values())
    return {kmer: count/total for kmer, count in kmer_counts.items()}

def kmer_similarity(seq1, seq2, k=4):
    """Calculate k-mer similarity between two sequences"""
    kmers1 = calculate_kmer_frequencies(seq1, k)
    kmers2 = calculate_kmer_frequencies(seq2, k)
    
    all_kmers = set(kmers1.keys()) | set(kmers2.keys())
    
    # Calculate cosine similarity
    dot_product = sum(kmers1.get(kmer, 0) * kmers2.get(kmer, 0) for kmer in all_kmers)
    norm1 = np.sqrt(sum(v**2 for v in kmers1.values()))
    norm2 = np.sqrt(sum(v**2 for v in kmers2.values()))
    
    return dot_product / (norm1 * norm2) if norm1 > 0 and norm2 > 0 else 0.0

# Apply to dataset
dataset['Kmer_Similarity_4'] = dataset.apply(
    lambda row: kmer_similarity(row['Phage_Sequence'], row['Host_Sequence'], k=4),
    axis=1
)
```

### Sequence Composition Features

```python
from Bio.SeqUtils import molecular_weight, gc_fraction
from Bio.Seq import Seq

def calculate_composition_features(sequence):
    """Calculate sequence composition features"""
    seq_obj = Seq(sequence)
    
    features = {
        'Length': len(seq_obj),
        'GC_Content': gc_fraction(seq_obj) * 100,
        'AT_Content': 100 - gc_fraction(seq_obj) * 100,
        'A_Count': seq_obj.count('A'),
        'T_Count': seq_obj.count('T'),
        'G_Count': seq_obj.count('G'),
        'C_Count': seq_obj.count('C'),
        'Purine_Content': (seq_obj.count('A') + seq_obj.count('G')) / len(seq_obj),
        'Pyrimidine_Content': (seq_obj.count('T') + seq_obj.count('C')) / len(seq_obj),
    }
    
    return features
```

### Protein-Based Features

```python
# Get protein features for phages
query = """
SELECT 
    p.Phage_ID,
    COUNT(DISTINCT pr.Protein_ID) as Protein_Count,
    AVG(pr.Molecular_weight) as Avg_Protein_MW,
    AVG(pr.Aromaticity) as Avg_Aromaticity,
    AVG(pr.Isoelectric_point) as Avg_pI,
    SUM(CASE WHEN pr.Protein_classification LIKE '%structural%' THEN 1 ELSE 0 END) as Structural_Proteins
FROM fact_phages p
LEFT JOIN dim_proteins pr ON p.Phage_ID = pr.Phage_ID
GROUP BY p.Phage_ID
"""

protein_features = retriever.conn.execute(query).fetchdf()
```

## Generating Training Data

### Negative Example Strategies

#### 1. Random Negatives

Best for: General-purpose models

```python
negatives = neg_gen.generate_random_negatives(
    positive_pairs,
    ratio=1.0  # 1:1 ratio
)
```

**Pros:**
- Simple and fast
- Unbiased sampling
- Good for large datasets

**Cons:**
- May include biologically plausible pairs
- Doesn't target hard negatives

#### 2. GC-Based Negatives

Best for: Emphasizing GC content mismatch

```python
negatives = neg_gen.generate_gc_based_negatives(
    positive_pairs,
    ratio=1.0,
    min_gc_difference=20.0  # >20% GC difference
)
```

**Pros:**
- Biologically informed
- Captures GC compatibility importance
- Creates clear decision boundaries

**Cons:**
- May oversimplify host-phage compatibility
- Doesn't capture other interaction factors

#### 3. Taxonomy-Based Negatives

Best for: Leveraging phylogenetic distance

```python
negatives = neg_gen.generate_taxonomy_based_negatives(
    positive_pairs,
    ratio=1.0,
    exclude_species=['Escherichia coli', 'Salmonella enterica']
)
```

**Pros:**
- Leverages evolutionary relationships
- Avoids closely related hosts
- Biologically meaningful

**Cons:**
- Limited by taxonomy completeness
- May miss cross-genus infections

#### 4. Mixed Strategy (Recommended)

Best for: Robust, generalizable models

```python
dataset = neg_gen.generate_balanced_dataset(
    positive_pairs=positive_pairs,
    strategy='mixed',  # Combines all strategies
    positive_ratio=0.5
)
```

**Pros:**
- Diverse negative examples
- Balanced representation
- Robust to overfitting

**Cons:**
- Slightly slower to generate
- More complex to interpret

## Model Selection

### Traditional ML Models

#### Random Forest

Best for: Feature importance analysis, baseline models

```python
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

# Prepare features
feature_cols = ['Phage_Length', 'Phage_GC', 'Host_Length', 'Host_GC', 
                'GC_Difference', 'Length_Ratio']
X = dataset[feature_cols]
y = dataset['Label']

# Standardize
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# Train
rf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
rf.fit(X_scaled, y)

# Feature importance
importance = pd.DataFrame({
    'Feature': feature_cols,
    'Importance': rf.feature_importances_
}).sort_values('Importance', ascending=False)
```

**Pros:**
- Handles non-linear relationships
- Feature importance analysis
- Robust to overfitting
- No extensive hyperparameter tuning needed

**Cons:**
- Can be slow with large datasets
- Less interpretable than linear models
- May not capture sequential patterns

#### Gradient Boosting (XGBoost)

Best for: Maximum performance, competitions

```python
import xgboost as xgb

# Prepare data
dtrain = xgb.DMatrix(X_train, label=y_train)
dtest = xgb.DMatrix(X_test, label=y_test)

# Parameters
params = {
    'objective': 'binary:logistic',
    'max_depth': 6,
    'learning_rate': 0.1,
    'eval_metric': 'auc'
}

# Train
model = xgb.train(params, dtrain, num_boost_round=100,
                 evals=[(dtest, 'test')],
                 early_stopping_rounds=10)
```

**Pros:**
- State-of-the-art performance
- Handles missing data
- Built-in regularization
- Feature importance

**Cons:**
- Requires careful tuning
- Can overfit easily
- Slower training

### Deep Learning Models

#### Sequence CNN

Best for: Direct sequence learning

```python
import tensorflow as tf
from tensorflow.keras import layers, models

def create_sequence_cnn(seq_length, vocab_size=5):
    """
    CNN for DNA sequence classification
    
    Args:
        seq_length: Length of input sequences
        vocab_size: Number of unique characters (A, T, G, C, N)
    """
    model = models.Sequential([
        layers.Embedding(vocab_size, 64, input_length=seq_length),
        layers.Conv1D(128, 7, activation='relu'),
        layers.MaxPooling1D(3),
        layers.Conv1D(256, 5, activation='relu'),
        layers.MaxPooling1D(3),
        layers.Conv1D(256, 3, activation='relu'),
        layers.GlobalMaxPooling1D(),
        layers.Dense(128, activation='relu'),
        layers.Dropout(0.5),
        layers.Dense(1, activation='sigmoid')
    ])
    
    model.compile(optimizer='adam',
                 loss='binary_crossentropy',
                 metrics=['accuracy', tf.keras.metrics.AUC()])
    
    return model

# Encode sequences
def encode_sequence(seq, max_length=50000):
    """Encode DNA sequence to integers"""
    mapping = {'A': 1, 'T': 2, 'G': 3, 'C': 4, 'N': 0}
    encoded = [mapping.get(base, 0) for base in seq[:max_length]]
    # Pad to max_length
    encoded += [0] * (max_length - len(encoded))
    return np.array(encoded)

# Train
model = create_sequence_cnn(seq_length=50000)
model.fit(X_train_encoded, y_train, 
         validation_split=0.2,
         epochs=10,
         batch_size=32)
```

#### LSTM for Sequential Patterns

```python
def create_lstm_model(seq_length, vocab_size=5):
    """LSTM for sequence classification"""
    model = models.Sequential([
        layers.Embedding(vocab_size, 64, input_length=seq_length),
        layers.Bidirectional(layers.LSTM(128, return_sequences=True)),
        layers.Bidirectional(layers.LSTM(64)),
        layers.Dense(64, activation='relu'),
        layers.Dropout(0.5),
        layers.Dense(1, activation='sigmoid')
    ])
    
    model.compile(optimizer='adam',
                 loss='binary_crossentropy',
                 metrics=['accuracy', tf.keras.metrics.AUC()])
    
    return model
```

## Example Projects

### 1. Host Range Prediction

Predict which bacterial hosts a phage can infect.

```python
# Get all phages with known hosts
known_infections = retriever.get_phage_host_pairs()

# For each phage, predict infectivity against all hosts
phage_id = "NC_000866"
all_hosts = retriever.conn.execute("SELECT Host_ID FROM dim_hosts").fetchdf()

# Create candidate pairs
candidates = []
for host_id in all_hosts['Host_ID']:
    # Extract features for phage-host pair
    # Make prediction
    # candidates.append((host_id, prediction_score))

# Rank hosts by infectivity probability
```

### 2. Therapeutic Candidate Identification

Find phages suitable for treating specific bacterial infections.

```python
# Target: E. coli infections
target_species = "Escherichia coli"

# Get all E. coli phages
query = f"""
SELECT p.Phage_ID, p.Lifestyle, p.Length
FROM fact_phages p
JOIN phage_host_associations pha ON p.Phage_ID = pha.Phage_ID
JOIN dim_hosts h ON pha.Host_ID = h.Host_ID
WHERE h.Species_Name = '{target_species}'
    AND p.Lifestyle = 'Lytic'
ORDER BY p.Length DESC
"""

candidates = retriever.conn.execute(query).fetchdf()

# Further filter by:
# - Lack of toxin genes
# - Lack of AMR genes
# - Temperate lifestyle markers
```

### 3. Lifestyle Classification

Predict phage lifestyle (lytic vs lysogenic) from genomic features.

```python
# Get phages with known lifestyle
query = """
SELECT Phage_ID, Lifestyle
FROM fact_phages
WHERE Lifestyle IN ('Lytic', 'Lysogenic')
"""

labeled_phages = retriever.conn.execute(query).fetchdf()
sequences = retriever.get_phage_sequences(
    f"SELECT Phage_ID FROM fact_phages WHERE Lifestyle IN ('Lytic', 'Lysogenic')"
)

# Combine and train classifier
# ...
```

## Best Practices

### Data Splitting

```python
from sklearn.model_selection import train_test_split

# Stratified split to maintain class balance
X_train, X_test, y_train, y_test = train_test_split(
    X, y,
    test_size=0.2,
    random_state=42,
    stratify=y  # Maintain class distribution
)

# Further split for validation
X_train, X_val, y_train, y_val = train_test_split(
    X_train, y_train,
    test_size=0.2,
    random_state=42,
    stratify=y_train
)
```

### Cross-Validation

```python
from sklearn.model_selection import StratifiedKFold, cross_val_score

# 5-fold cross-validation
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

scores = cross_val_score(
    model, X_scaled, y,
    cv=cv,
    scoring='roc_auc',
    n_jobs=-1
)

print(f"Cross-validation AUC: {scores.mean():.3f} (+/- {scores.std():.3f})")
```

### Handling Imbalanced Data

```python
from imblearn.over_sampling import SMOTE
from imblearn.under_sampling import RandomUnderSampler
from imblearn.pipeline import Pipeline

# SMOTE + RandomUnderSampler
oversample = SMOTE(sampling_strategy=0.5)
undersample = RandomUnderSampler(sampling_strategy=1.0)

# Pipeline
pipeline = Pipeline([
    ('oversample', oversample),
    ('undersample', undersample)
])

X_resampled, y_resampled = pipeline.fit_resample(X_train, y_train)
```

### Model Evaluation

```python
from sklearn.metrics import classification_report, roc_auc_score, precision_recall_curve

# Predictions
y_pred = model.predict(X_test)
y_pred_proba = model.predict_proba(X_test)[:, 1]

# Classification report
print(classification_report(y_test, y_pred))

# ROC-AUC
print(f"ROC-AUC: {roc_auc_score(y_test, y_pred_proba):.3f}")

# Precision-Recall curve
precision, recall, thresholds = precision_recall_curve(y_test, y_pred_proba)

# Find optimal threshold
f1_scores = 2 * (precision * recall) / (precision + recall + 1e-10)
optimal_idx = np.argmax(f1_scores)
optimal_threshold = thresholds[optimal_idx]

print(f"Optimal threshold: {optimal_threshold:.3f}")
```

## Common Pitfalls

### 1. Data Leakage

**Problem:** Including future information in training data

**Solution:**
```python
# ❌ Bad: Using all data for feature scaling
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)
X_train, X_test = train_test_split(X_scaled, ...)

# ✅ Good: Fit scaler only on training data
X_train, X_test = train_test_split(X, ...)
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)
```

### 2. Overfitting

**Problem:** Model performs well on training but poorly on test data

**Solutions:**
- Use cross-validation
- Regularization (L1, L2)
- Early stopping
- Dropout (neural networks)
- Reduce model complexity

### 3. Imbalanced Negatives

**Problem:** Negative examples don't represent real-world distribution

**Solution:**
```python
# Use diverse negative generation strategies
dataset = neg_gen.generate_balanced_dataset(
    strategy='mixed',  # Not just random
    positive_ratio=0.5
)

# Validate negative quality
# - Check GC distribution
# - Check taxonomic diversity
# - Verify no overlap with positives
```

### 4. Ignoring Sequence Context

**Problem:** Treating sequences as simple feature vectors

**Solution:**
- Use k-mer features to capture local context
- Consider using CNNs or transformers for sequences
- Include positional information

## Advanced Topics

### Transfer Learning

Use pre-trained models on DNA sequences:

```python
# Example with DNA-BERT (conceptual)
from transformers import AutoTokenizer, AutoModel

tokenizer = AutoTokenizer.from_pretrained("zhihan1996/DNA_bert_6")
model = AutoModel.from_pretrained("zhihan1996/DNA_bert_6")

# Encode sequences
inputs = tokenizer(sequence, return_tensors="pt", max_length=512, truncation=True)
outputs = model(**inputs)
embeddings = outputs.last_hidden_state.mean(dim=1)  # Sequence embedding
```

### Interpretability

SHAP values for model interpretation:

```python
import shap

# Create explainer
explainer = shap.TreeExplainer(rf_model)

# Calculate SHAP values
shap_values = explainer.shap_values(X_test)

# Visualize
shap.summary_plot(shap_values, X_test, feature_names=feature_cols)
```

### Ensemble Methods

Combine multiple models:

```python
from sklearn.ensemble import VotingClassifier

# Create ensemble
ensemble = VotingClassifier(
    estimators=[
        ('rf', RandomForestClassifier(n_estimators=100)),
        ('xgb', xgb.XGBClassifier(n_estimators=100)),
        ('svm', SVC(probability=True))
    ],
    voting='soft'  # Use predicted probabilities
)

ensemble.fit(X_train, y_train)
```

## Resources

### Documentation
- [PBI API Reference](../api/overview.md)
- [Database Schema](../database/overview.md)
- [Example Notebooks](../../notebooks/)

### Related Papers
- Phage-host interaction prediction methods
- Sequence-based ML for genomics
- Transfer learning in bioinformatics

### Tools
- [Scikit-learn](https://scikit-learn.org/)
- [XGBoost](https://xgboost.readthedocs.io/)
- [TensorFlow](https://www.tensorflow.org/)
- [BioPython](https://biopython.org/)
- [SHAP](https://shap.readthedocs.io/)

## Getting Help

- Check the [ML/streaming notebook](https://github.com/ThibaultSchowing/PBI/blob/main/notebooks/03_ml_streaming.ipynb)
- Review [database documentation](../database/overview.md)
- Open an issue on [GitHub](https://github.com/ThibaultSchowing/PBI/issues)
