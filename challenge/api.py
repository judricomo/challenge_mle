from typing import Dict, Any, List
import os
import tempfile

import fastapi
import pandas as pd
from google.cloud import aiplatform
from google.cloud import storage

from challenge.model import DelayModel

app = fastapi.FastAPI(
    title="Flight Delay Prediction API",
    description="""
    ## Predict flight delays using Machine Learning
    
    This API uses a Logistic Regression model trained on historical flight data to predict delays.
    
    ### Features
    * **Real-time predictions** based on flight operator, type, and month
    * **Model versioning** with Vertex AI Model Registry
    * **Production-ready** with health checks and monitoring
    
    ### Model Details
    - **Algorithm**: Logistic Regression with class balancing
    - **Top Features**: Airline operator, flight type, month
    - **Threshold**: 15 minutes delay classification
    
    ### How to use
    1. Send a POST request to `/predict` with flight information
    2. Receive predictions: 0 (no delay) or 1 (delay expected)
    """,
    version="1.0.0",
    contact={
        "name": "ML Engineering Team",
        "email": "ml-team@example.com",
    },
    license_info={
        "name": "MIT",
    },
)
_model = DelayModel()


@app.on_event("startup")
async def load_model_on_startup() -> None:
    """Load model from Vertex AI Model Registry on startup."""
    project_id = os.getenv("GCP_PROJECT_ID")
    location = os.getenv("GCP_LOCATION")
    model_name = os.getenv("VERTEX_MODEL_NAME")
    
    if not all([project_id, location, model_name]):
        print("Warning: GCP environment variables not set, using untrained model")
        return
    
    try:
        # Initialize Vertex AI
        aiplatform.init(project=project_id, location=location)
        
        # Get the latest version of the model
        models = aiplatform.Model.list(
            filter=f'display_name="{model_name}"',
            order_by="create_time desc"
        )
        
        if not models:
            print(f"No model found with name '{model_name}', using untrained model")
            return
        
        latest_model = models[0]
        print(f"Found model: {latest_model.resource_name}")
        
        # Extract GCS path from model artifact URI
        artifact_uri = latest_model.gca_resource.artifact_uri
        print(f"Artifact URI: {artifact_uri}")
        
        # Download model.pkl from GCS
        # artifact_uri format: gs://bucket/path/to/model/
        bucket_name = artifact_uri.split("/")[2]
        blob_path = "/".join(artifact_uri.split("/")[3:]) + "model.pkl"
        
        storage_client = storage.Client(project=project_id)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        
        # Download to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pkl") as tmp_file:
            blob.download_to_filename(tmp_file.name)
            print(f"Downloaded model to {tmp_file.name}")
            
            # Load into DelayModel
            _model.load_model(tmp_file.name)
            print("✓ Model loaded successfully from Vertex AI Model Registry")
            
    except Exception as e:
        print(f"Warning: Could not load model from Vertex AI: {e}")
        print("Continuing with untrained model (will return default predictions)")


@app.get(
    "/health",
    status_code=200,
    summary="Health check",
    response_description="API health status",
    tags=["Monitoring"]
)
async def get_health() -> dict:
    """
    Check if the API is running and healthy.
    
    Returns OK status if the service is operational.
    """
    return {"status": "OK"}


def _validate(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if "flights" not in payload or not isinstance(payload["flights"], list):
        raise fastapi.HTTPException(status_code=400)
    valid_ops = {
        "Aerolineas Argentinas",
        "Grupo LATAM",
        "Sky Airline",
        "Copa Air",
        "Latin American Wings",
    }
    rows: List[Dict[str, Any]] = []
    for f in payload["flights"]:
        if not all(k in f for k in ("OPERA", "TIPOVUELO", "MES")):
            raise fastapi.HTTPException(status_code=400)
        opera = f["OPERA"]
        tipo = f["TIPOVUELO"]
        mes = f["MES"]
        if opera not in valid_ops or tipo not in {"I", "N"} or not (1 <= int(mes) <= 12):
            raise fastapi.HTTPException(status_code=400)
        rows.append({"OPERA": opera, "TIPOVUELO": tipo, "MES": int(mes)})
    return rows


@app.post(
    "/predict",
    status_code=200,
    summary="Predict flight delays",
    response_description="List of delay predictions (0=no delay, 1=delay)",
    tags=["Predictions"]
)
async def post_predict(
    payload: Dict[str, Any] = fastapi.Body(
        ...,
        example={
            "flights": [
                {
                    "OPERA": "Aerolineas Argentinas",
                    "TIPOVUELO": "N",
                    "MES": 3
                }
            ]
        }
    )
) -> dict:
    """
    Predict flight delays based on flight information.
    
    - **OPERA**: Airline operator name
    - **TIPOVUELO**: Flight type (I=International, N=National)
    - **MES**: Month (1-12)
    
    Returns a list of predictions where 0=no delay, 1=delay expected.
    """
    rows = _validate(payload)
    df = pd.DataFrame(rows)
    features = _model.preprocess(df)
    predictions = _model.predict(features)
    return {"predict": predictions}