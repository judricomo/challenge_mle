#!/usr/bin/env python3
"""
Upload model.pkl to Vertex AI Model Registry for versioning and storage.

This script uploads the trained model to GCS and registers it in Vertex AI
Model Registry WITHOUT deploying it to an endpoint.
"""

import sys
import os
from pathlib import Path
from datetime import datetime

from google.cloud import storage
from google.cloud import aiplatform


def upload_to_gcs(local_path: Path, bucket_name: str, blob_name: str) -> str:
    """Upload model file to Google Cloud Storage."""
    print(f"Uploading {local_path} to gs://{bucket_name}/{blob_name}...")
    
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    
    blob.upload_from_filename(str(local_path))
    
    gcs_uri = f"gs://{bucket_name}/{blob_name}"
    print(f"✓ Uploaded to {gcs_uri}")
    return gcs_uri


def register_model_in_vertex(
    display_name: str,
    artifact_uri: str,
    project_id: str,
    location: str = "us-central1",
    description: str = None,
    labels: dict = None
) -> str:
    """Register model in Vertex AI Model Registry."""
    print(f"\nRegistering model in Vertex AI Model Registry...")
    
    aiplatform.init(project=project_id, location=location)
    
    # Upload model to registry (not deploying)
    model = aiplatform.Model.upload(
        display_name=display_name,
        artifact_uri=artifact_uri,
        serving_container_image_uri="us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.1-0:latest",
        description=description,
        labels=labels,
    )
    
    print(f"✓ Model registered: {model.resource_name}")
    print(f"  Model ID: {model.name}")
    print(f"  Version: {model.version_id}")
    return model.resource_name


def main():
    """Upload model.pkl to GCS and register in Vertex AI Model Registry."""
    
    # Configuration
    project_id = os.getenv("GCP_PROJECT_ID")
    bucket_name = os.getenv("GCS_BUCKET")
    location = os.getenv("GCP_LOCATION", "us-central1")
    
    if not project_id or not bucket_name:
        print("Error: Set GCP_PROJECT_ID and GCS_BUCKET environment variables")
        print("\nExample:")
        print("  export GCP_PROJECT_ID=my-project")
        print("  export GCS_BUCKET=my-models-bucket")
        print("  export GCP_LOCATION=us-central1  # optional, defaults to us-central1")
        sys.exit(1)
    
    # Model paths
    model_path = Path(__file__).parent.parent / "model.pkl"
    
    if not model_path.exists():
        print(f"Error: Model file not found at {model_path}")
        print("Run: ./venv/bin/python scripts/train_model.py")
        sys.exit(1)
    
    # Generate versioned directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    version_dir = f"models/flight-delay/v_{timestamp}"
    blob_name = f"{version_dir}/model.pkl"
    
    # Upload to GCS
    gcs_uri = upload_to_gcs(model_path, bucket_name, blob_name)
    
    # Get directory URI (without filename) for Vertex AI
    artifact_uri = f"gs://{bucket_name}/{version_dir}/"
    
    # Register in Vertex AI
    description = f"Logistic Regression model for flight delay prediction. Trained on {timestamp}."
    labels = {
        "framework": "scikit-learn",
        "model_type": "logistic_regression",
        "task": "classification",
        "domain": "aviation"
    }
    
    register_model_in_vertex(
        display_name="flight-delay-model",
        artifact_uri=artifact_uri,
        project_id=project_id,
        location=location,
        description=description,
        labels=labels
    )
    
    print("\n✓ Model successfully stored and versioned in Vertex AI Model Registry")
    print(f"\nView in console:")
    print(f"https://console.cloud.google.com/vertex-ai/models?project={project_id}")


if __name__ == "__main__":
    main()
