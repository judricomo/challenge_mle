#!/usr/bin/env python3
"""
Training script to create model.pkl for production use.

This script:
1. Loads the full dataset from data/data.csv
2. Preprocesses features and generates delay target
3. Trains a LogisticRegression model with class balancing
4. Saves the trained model to model.pkl
"""

import sys
from pathlib import Path

# Add parent directory to path so we can import challenge module
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from challenge.model import DelayModel


def main():
    """Train and save the delay prediction model."""
    print("Loading data from data/data.csv...")
    data_path = Path(__file__).parent.parent / "data" / "data.csv"
    
    if not data_path.exists():
        print(f"Error: Data file not found at {data_path}")
        sys.exit(1)
    
    data = pd.read_csv(data_path)
    print(f"Loaded {len(data)} records")
    
    print("\nPreprocessing features and generating target...")
    model = DelayModel()
    features, target = model.preprocess(data=data, target_column="delay")
    
    print(f"Features shape: {features.shape}")
    print(f"Target distribution: {target.value_counts().to_dict()}")
    
    print("\nTraining Logistic Regression with class balancing...")
    model.fit(features=features, target=target)
    
    print("\nSaving model to model.pkl...")
    output_path = Path(__file__).parent.parent / "model.pkl"
    model.save_model(str(output_path))
    
    print(f"✓ Model successfully saved to {output_path}")
    print("\nYou can now start the API and it will load this trained model.")


if __name__ == "__main__":
    main()
