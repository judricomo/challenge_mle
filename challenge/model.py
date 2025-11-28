import pandas as pd
import numpy as np
import pickle
from datetime import datetime
from pathlib import Path
from typing import Tuple, Union, List
from sklearn.linear_model import LogisticRegression


class DelayModel:
    """
    A model to predict flight delays using Logistic Regression.
    
    This model uses the top 10 most important features identified through
    feature importance analysis and applies class balancing to handle
    the imbalanced dataset.
    """
    
    # Top 10 features identified from feature importance analysis
    TOP_10_FEATURES = [
        "OPERA_Latin American Wings",
        "MES_7",
        "MES_10",
        "OPERA_Grupo LATAM",
        "MES_12",
        "TIPOVUELO_I",
        "MES_4",
        "MES_11",
        "OPERA_Sky Airline",
        "OPERA_Copa Air"
    ]
    
    def __init__(self):
        """Initialize the DelayModel with a Logistic Regression model."""
        self._model = None  # Model should be saved in this attribute.

    def preprocess(
        self,
        data: pd.DataFrame,
        target_column: str = None
    ) -> Union[Tuple[pd.DataFrame, pd.DataFrame], pd.DataFrame]:
        """
        Prepare raw data for training or predict.

        Args:
            data (pd.DataFrame): raw data.
            target_column (str, optional): if set, the target is returned.

        Returns:
            Tuple[pd.DataFrame, pd.DataFrame]: features and target.
            or
            pd.DataFrame: features.
        """
        # Create a copy to avoid modifying the original data
        data = data.copy()
        
        # Generate the delay target if needed for training
        if target_column:
            data['delay'] = self._generate_delay_target(data)
        
        # Create one-hot encoded features
        features = pd.concat([
            pd.get_dummies(data['OPERA'], prefix='OPERA'),
            pd.get_dummies(data['TIPOVUELO'], prefix='TIPOVUELO'),
            pd.get_dummies(data['MES'], prefix='MES')
        ], axis=1)
        
        # Ensure all top 10 features exist (add missing columns with zeros)
        for feature in self.TOP_10_FEATURES:
            if feature not in features.columns:
                features[feature] = 0
        
        # Select only the top 10 features
        features = features[self.TOP_10_FEATURES]
        
        # Return features and target if target_column is specified
        if target_column:
            if target_column in data.columns:
                target = data[[target_column]]
                return features, target
            else:
                raise ValueError(f"Target column '{target_column}' not found in data")
        
        return features
    
    def _generate_delay_target(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate the delay target variable.
        
        A flight is considered delayed if the difference between
        actual and scheduled departure time is greater than 15 minutes.
        
        Args:
            data (pd.DataFrame): raw data with 'Fecha-O' and 'Fecha-I' columns.
            
        Returns:
            pd.Series: binary delay indicator (1 = delayed, 0 = not delayed)
        """
        def calculate_min_diff(row):
            """Calculate the difference in minutes between scheduled and actual departure."""
            try:
                fecha_o = datetime.strptime(row['Fecha-O'], '%Y-%m-%d %H:%M:%S')
                fecha_i = datetime.strptime(row['Fecha-I'], '%Y-%m-%d %H:%M:%S')
                min_diff = ((fecha_o - fecha_i).total_seconds()) / 60
                return min_diff
            except:
                return 0
        
        # Calculate minute differences
        data['min_diff'] = data.apply(calculate_min_diff, axis=1)
        
        # Define threshold and create binary delay indicator
        threshold_in_minutes = 15
        delay = np.where(data['min_diff'] > threshold_in_minutes, 1, 0)
        
        return pd.Series(delay, index=data.index)

    def fit(
        self,
        features: pd.DataFrame,
        target: pd.DataFrame
    ) -> None:
        """
        Fit model with preprocessed data.
        
        Uses Logistic Regression with class balancing to handle
        the imbalanced dataset (more non-delayed flights than delayed).

        Args:
            features (pd.DataFrame): preprocessed data.
            target (pd.DataFrame): target.
        """
        # Convert target DataFrame to Series if needed
        if isinstance(target, pd.DataFrame):
            target = target.iloc[:, 0]
        
        # Calculate class weights for balancing
        n_y0 = (target == 0).sum()
        n_y1 = (target == 1).sum()
        class_weight = {1: n_y0 / len(target), 0: n_y1 / len(target)}
        
        # Initialize and train the Logistic Regression model with class balancing
        self._model = LogisticRegression(
            class_weight=class_weight,
            random_state=42,
            max_iter=1000  # Ensure convergence
        )
        
        self._model.fit(features, target)

    def predict(
        self,
        features: pd.DataFrame
    ) -> List[int]:
        """
        Predict delays for new flights.

        Args:
            features (pd.DataFrame): preprocessed data.
        
        Returns:
            (List[int]): predicted targets.
        """
        if self._model is None:
            # Return default predictions (no delay) if model not trained
            return [0] * len(features)
        
        # Make predictions
        predictions = self._model.predict(features)
        
        # Convert to list of integers
        return predictions.tolist()
    
    def save_model(self, filepath: str = "model.pkl") -> None:
        """
        Save the trained model to disk.
        
        Args:
            filepath (str): path where the model will be saved.
            
        Raises:
            ValueError: if no model has been trained yet.
        """
        if self._model is None:
            raise ValueError("No model to save. Train the model first using fit().")
        
        filepath_obj = Path(filepath)
        filepath_obj.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'wb') as f:
            pickle.dump(self._model, f)
    
    def load_model(self, filepath: str = "model.pkl") -> None:
        """
        Load a trained model from disk.
        
        Args:
            filepath (str): path to the saved model file.
            
        Raises:
            FileNotFoundError: if the model file doesn't exist.
        """
        if not Path(filepath).exists():
            raise FileNotFoundError(f"Model file not found: {filepath}")
        
        with open(filepath, 'rb') as f:
            self._model = pickle.load(f)