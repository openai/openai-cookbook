import pytest
import pandas as pd
import numpy as np

@pytest.fixture
def sample_dataframe():
    """Create a sample DataFrame for testing."""
    return pd.DataFrame({
        'A': np.random.randn(100),
        'B': np.random.randn(100),
        'C': np.random.choice(['X', 'Y', 'Z'], 100),
        'D': pd.date_range('2023-01-01', periods=100)
    })

@pytest.fixture
def sample_series():
    """Create a sample Series for testing."""
    return pd.Series(np.random.randn(100), name='test_series')

@pytest.fixture
def sample_array():
    """Create a sample numpy array for testing."""
    return np.random.randn(100, 3) 