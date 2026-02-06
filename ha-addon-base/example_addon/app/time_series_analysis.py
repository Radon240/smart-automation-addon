"""
Advanced time series analysis for Home Assistant automation suggestions.

This module implements time series models (ARIMA, SARIMA) for analyzing
historical state change events and predicting future patterns. It extends the basic
correlation analysis with more powerful statistical techniques.

Key features:
- ARIMA/SARIMA models for time series forecasting
- Seasonality and trend analysis
- Integration with existing correlation analysis
- Lightweight implementation compatible with Home Assistant Python 3.12
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import json
import warnings
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_squared_error
import matplotlib.pyplot as plt
import io
import base64

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')

# Import statsmodels for ARIMA
try:
    from statsmodels.tsa.arima.model import ARIMA
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    from statsmodels.tsa.seasonal import seasonal_decompose
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False
    SARIMAX = None  # Placeholder to avoid NameError

@dataclass
class TimeSeriesPrediction:
    """Prediction result from time series models."""
    entity_id: str
    timestamp: datetime
    predicted_value: float
    confidence: float
    model_type: str  # 'arima', 'sarima'
    actual_value: Optional[float] = None
    error: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert prediction to dictionary for JSON serialization."""
        result = {
            'entity_id': self.entity_id,
            'timestamp': self.timestamp.isoformat(),
            'predicted_value': round(self.predicted_value, 4),
            'confidence': round(self.confidence, 4),
            'model_type': self.model_type
        }
        if self.actual_value is not None:
            result['actual_value'] = round(self.actual_value, 4)
        if self.error is not None:
            result['error'] = round(self.error, 4)
        return result

@dataclass
class TimeSeriesAnalysisResult:
    """Complete analysis result for a time series."""
    entity_id: str
    predictions: List[TimeSeriesPrediction]
    model_type: str
    training_metrics: Dict[str, float]
    visualization: Optional[str] = None  # Base64 encoded plot

    def to_dict(self) -> Dict[str, Any]:
        """Convert analysis result to dictionary."""
        return {
            'entity_id': self.entity_id,
            'predictions': [p.to_dict() for p in self.predictions],
            'model_type': self.model_type,
            'training_metrics': self.training_metrics,
            'visualization': self.visualization
        }

class TimeSeriesAnalyzer:
    """
    Advanced time series analyzer using ARIMA models.

    This class provides methods for:
    - Preprocessing time series data from Home Assistant events
    - Training ARIMA/SARIMA models
    - Making predictions
    - Visualizing results
    - Generating automation suggestions based on predictions
    """

    def __init__(self,
                 forecast_horizon: int = 6,
                 test_size: float = 0.2,
                 random_state: int = 42):
        """
        Initialize the time series analyzer.

        Args:
            forecast_horizon: How many steps ahead to predict
            test_size: Proportion of data to use for testing
            random_state: Random seed for reproducibility
        """
        self.forecast_horizon = forecast_horizon
        self.test_size = test_size
        self.random_state = random_state
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self.models = {}  # Store trained models by entity_id

        # Set random seeds for reproducibility
        np.random.seed(random_state)

    def preprocess_events_to_timeseries(self,
                                      events: List[Dict[str, Any]],
                                      target_entity: str,
                                      frequency: str = '1H') -> Optional[pd.DataFrame]:
        """
        Convert Home Assistant events to time series DataFrame.

        Args:
            events: List of Home Assistant state change events
            target_entity: Entity ID to analyze
            frequency: Resampling frequency (e.g., '1H', '30min', '1D')

        Returns:
            DataFrame with datetime index and numeric values, or None if conversion fails
        """
        try:
            # Filter events for target entity
            entity_events = [e for e in events if e.get('entity_id') == target_entity]
            if not entity_events:
                return None

            # Extract numeric values from events
            data = []
            for event in entity_events:
                event_data = event.get('event', {}) if 'event' in event else event
                state = event_data.get('state') or event_data.get('new_state', {}).get('state')

                # Try to extract timestamp
                timestamp_str = event_data.get('last_changed') or event_data.get('timestamp')
                if isinstance(timestamp_str, str):
                    try:
                        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    except:
                        continue
                elif isinstance(timestamp_str, datetime):
                    timestamp = timestamp_str
                else:
                    continue

                # Try to get numeric value
                try:
                    value = float(state)
                except (ValueError, TypeError):
                    # Check if it's a binary state we can convert
                    if state in ['on', 'open', 'true']:
                        value = 1.0
                    elif state in ['off', 'close', 'false']:
                        value = 0.0
                    else:
                        continue

                data.append({'timestamp': timestamp, 'value': value})

            if not data:
                return None

            # Create DataFrame and resample
            df = pd.DataFrame(data)
            df.set_index('timestamp', inplace=True)
            df.index = pd.to_datetime(df.index)
            df.sort_index(inplace=True)

            # Resample to regular frequency and forward fill missing values
            df_resampled = df.resample(frequency).mean().ffill()

            return df_resampled

        except Exception as e:
            print(f"Error preprocessing events for {target_entity}: {e}")
            return None

    def train_arima_model(self,
                         series: pd.Series,
                         entity_id: str,
                         order: Tuple[int, int, int] = (2, 1, 2),
                         seasonal_order: Tuple[int, int, int, int] = (1, 1, 1, 24)) -> Any:
        """
        Train ARIMA/SARIMA model for time series prediction.

        Args:
            series: Time series data
            entity_id: Entity ID for model identification
            order: ARIMA order (p, d, q)
            seasonal_order: Seasonal order (P, D, Q, s)

        Returns:
            Trained SARIMAX model or None if training fails
        """
        if not STATSMODELS_AVAILABLE:
            print("Statsmodels not available. Cannot train ARIMA model.")
            return None

        try:
            # Train SARIMA model (extends ARIMA with seasonality)
            model = SARIMAX(
                series,
                order=order,
                seasonal_order=seasonal_order,
                enforce_stationarity=False,
                enforce_invertibility=False
            )

            model_fit = model.fit(disp=False)

            # Store the model
            self.models[f'arima_{entity_id}'] = model_fit

            return model_fit

        except Exception as e:
            print(f"Error training ARIMA model for {entity_id}: {e}")
            return None

    def analyze_entity_timeseries(self,
                                events: List[Dict[str, Any]],
                                entity_id: str,
                                frequency: str = '1H') -> Optional[TimeSeriesAnalysisResult]:
        """
        Complete analysis pipeline for a single entity.

        Args:
            events: List of Home Assistant events
            entity_id: Entity ID to analyze
            frequency: Resampling frequency

        Returns:
            TimeSeriesAnalysisResult or None if analysis fails
        """
        try:
            # Step 1: Preprocess data
            ts_data = self.preprocess_events_to_timeseries(events, entity_id, frequency)
            if ts_data is None or len(ts_data) < 10:
                print(f"Not enough data for {entity_id}. Need at least 10 data points.")
                return None

            # Normalize data
            scaled_data = self.scaler.fit_transform(ts_data.values)

            # Split into train/test
            train_size = int(len(scaled_data) * (1 - self.test_size))
            train, test = scaled_data[0:train_size], scaled_data[train_size:len(scaled_data)]

            results = []

            # Step 2: Train and evaluate ARIMA model
            print(f"Training ARIMA model for {entity_id}...")

            # Train on original (non-scaled) data since ARIMA works better with original scale
            arima_model = self.train_arima_model(ts_data['value'], entity_id)

            if arima_model:
                # Make predictions
                forecast_steps = min(self.forecast_horizon, len(test))
                predictions = arima_model.get_forecast(steps=forecast_steps)
                pred_mean = predictions.predicted_mean
                conf_int = predictions.conf_int()

                # Create prediction objects
                test_dates = ts_data.index[-forecast_steps:]

                for i, (date, pred_val) in enumerate(zip(test_dates, pred_mean)):
                    # Confidence from prediction intervals
                    lower_bound = conf_int.iloc[i, 0]
                    upper_bound = conf_int.iloc[i, 1]
                    confidence = 1.0 - (abs(pred_val - lower_bound) / (upper_bound - lower_bound))

                    result = TimeSeriesPrediction(
                        entity_id=entity_id,
                        timestamp=date,
                        predicted_value=float(pred_val),
                        confidence=float(confidence),
                        model_type='arima',
                        actual_value=float(ts_data.loc[date, 'value']) if date in ts_data.index else None
                    )
                    results.append(result)

                # Calculate metrics
                actual_values = [ts_data.loc[date, 'value'] for date in test_dates if date in ts_data.index]
                pred_values = [float(p) for p in pred_mean]
                mse = mean_squared_error(actual_values, pred_values)
                rmse = np.sqrt(mse)

                # Generate visualization
                visualization = self._generate_visualization(
                    ts_data, train_size, pred_mean.reshape(-1, 1), actual_values, 'ARIMA'
                )

                metrics = {
                    'mse': float(mse),
                    'rmse': float(rmse),
                    'r2_score': float(1 - (mse / np.var(actual_values))) if len(actual_values) > 1 else 1.0,
                    'samples_used': len(ts_data) - forecast_steps
                }

                arima_result = TimeSeriesAnalysisResult(
                    entity_id=entity_id,
                    predictions=results,
                    model_type='arima',
                    training_metrics=metrics,
                    visualization=visualization
                )

                return arima_result

            return None

        except Exception as e:
            print(f"Error analyzing time series for {entity_id}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _generate_visualization(self,
                              ts_data: pd.DataFrame,
                              train_size: int,
                              predictions: np.array,
                              actual_values: np.array,
                              model_name: str) -> Optional[str]:
        """
        Generate visualization of predictions vs actual values.

        Args:
            ts_data: Original time series data
            train_size: Size of training set
            predictions: Model predictions
            actual_values: Actual test values
            model_name: Name of the model for title

        Returns:
            Base64 encoded image or None if visualization fails
        """
        try:
            plt.figure(figsize=(12, 6))
            plt.plot(ts_data.index, ts_data['value'], label='Original Data', alpha=0.5)

            # Plot training data
            train_dates = ts_data.index[:train_size]
            plt.plot(train_dates, ts_data.loc[train_dates, 'value'], 'g-', label='Training Data')

            # Plot test data and predictions
            test_dates = ts_data.index[train_size:train_size + len(predictions)]
            plt.plot(test_dates, actual_values, 'b-', label='Actual Test Data')
            plt.plot(test_dates, predictions, 'r--', label='Predictions')

            plt.title(f'{model_name} Predictions for {entity_id}')
            plt.xlabel('Time')
            plt.ylabel('Value')
            plt.legend()
            plt.grid(True)

            # Save plot to base64 string
            buf = io.BytesIO()
            plt.savefig(buf, format='png', bbox_inches='tight', dpi=100)
            buf.seek(0)
            image_base64 = base64.b64encode(buf.read()).decode('utf-8')
            plt.close()

            return f"data:image/png;base64,{image_base64}"

        except Exception as e:
            print(f"Error generating visualization: {e}")
            return None

    def get_automation_suggestions_from_predictions(self,
                                                  predictions: List[TimeSeriesPrediction],
                                                  confidence_threshold: float = 0.7) -> List[Dict[str, Any]]:
        """
        Generate automation suggestions based on time series predictions.

        Args:
            predictions: List of time series predictions
            confidence_threshold: Minimum confidence for suggestions

        Returns:
            List of automation suggestion dictionaries
        """
        suggestions = []

        # Group predictions by entity and time patterns
        by_entity = {}
        for pred in predictions:
            if pred.confidence < confidence_threshold:
                continue

            if pred.entity_id not in by_entity:
                by_entity[pred.entity_id] = []

            by_entity[pred.entity_id].append(pred)

        # Generate suggestions for each entity
        for entity_id, entity_predictions in by_entity.items():
            # Sort by timestamp to find patterns
            entity_predictions.sort(key=lambda x: x.timestamp)

            # Find recurring patterns (e.g., same time each day)
            time_patterns = self._find_time_patterns(entity_predictions)

            for pattern in time_patterns:
                # Generate automation suggestion
                suggestion = self._create_automation_suggestion(entity_id, pattern)
                suggestions.append(suggestion)

        return suggestions

    def _find_time_patterns(self, predictions: List[TimeSeriesPrediction]) -> List[Dict[str, Any]]:
        """
        Find recurring time patterns in predictions.

        Args:
            predictions: List of predictions for a single entity

        Returns:
            List of detected time patterns
        """
        patterns = []

        # Simple pattern detection: look for predictions at similar times
        time_clusters = {}

        for pred in predictions:
            # Round to nearest 15 minutes for clustering
            hour = pred.timestamp.hour
            minute = (pred.timestamp.minute // 15) * 15
            time_key = f"{hour:02d}:{minute:02d}"

            if time_key not in time_clusters:
                time_clusters[time_key] = []

            time_clusters[time_key].append(pred)

        # Filter significant patterns
        for time_key, cluster in time_clusters.items():
            if len(cluster) >= 2:  # At least 2 occurrences
                # Calculate average predicted value
                avg_value = np.mean([p.predicted_value for p in cluster])
                avg_confidence = np.mean([p.confidence for p in cluster])

                patterns.append({
                    'time': time_key,
                    'average_value': float(avg_value),
                    'confidence': float(avg_confidence),
                    'occurrences': len(cluster),
                    'predictions': cluster
                })

        return patterns

    def _create_automation_suggestion(self,
                                    entity_id: str,
                                    pattern: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create automation suggestion from time pattern.

        Args:
            entity_id: Entity ID
            pattern: Detected time pattern

        Returns:
            Automation suggestion dictionary
        """
        hour, minute = pattern['time'].split(':')
        time_str = f"{hour}:{minute}"

        # Determine action based on predicted value
        if pattern['average_value'] > 0.7:  # High value
            action = "turn_on"
            state = "on"
        elif pattern['average_value'] < 0.3:  # Low value
            action = "turn_off"
            state = "off"
        else:
            action = "set_value"
            state = str(round(pattern['average_value'], 2))

        # Generate YAML for Home Assistant automation
        automation_yaml = f"""alias: "Auto {entity_id} at {time_str}"
trigger:
  - platform: time
    at: "{time_str}"
action:
  - service: homeassistant.{action}
    target:
      entity_id: {entity_id}
    data:
      {f'value: {state}' if action == 'set_value' else ''}
"""

        return {
            'title': f"Automate {entity_id} at {time_str}",
            'description': f"Entity {entity_id} should be {state} at {time_str} (confidence: {pattern['confidence']:.2f})",
            'trigger_type': 'time',
            'trigger_details': {
                'at': time_str,
                'weekdays': list(range(7))  # All days
            },
            'actions': [{
                'service': f"homeassistant.{action}",
                'entity_id': entity_id,
                'data': {'value': state} if action == 'set_value' else {}
            }],
            'confidence': pattern['confidence'],
            'automation_yaml': automation_yaml.strip(),
            'model_type': 'time_series'
        }

    def get_available_models_info(self) -> Dict[str, Any]:
        """
        Get information about available models and their status.

        Returns:
            Dictionary with model availability information
        """
        return {
            'arima_available': STATSMODELS_AVAILABLE,
            'statsmodels_version': None,  # Would need to import to get version
            'trained_models': list(self.models.keys())
        }