"""
Unit tests for the Calculator module.
"""

import pytest
from calculator import Calculator


class TestCalculator:
    """Test cases for Calculator class."""

    def test_add(self):
        """Test addition operation."""
        calc = Calculator()
        assert calc.add(5, 3) == 8
        assert calc.add(0, 0) == 0

    def test_subtract(self):
        """Test subtraction operation."""
        calc = Calculator()
        assert calc.subtract(10, 4) == 6

    def test_multiply(self):
        """Test multiplication operation."""
        calc = Calculator()
        assert calc.multiply(6, 7) == 42
        assert calc.multiply(0, 100) == 0

    def test_divide(self):
        """Test division operation."""
        calc = Calculator()
        assert calc.divide(20, 4) == 5.0
        assert calc.divide(9, 3) == 3.0

    def test_divide_by_zero(self):
        """Test division by zero raises error."""
        calc = Calculator()
        with pytest.raises(ValueError, match="Division by zero"):
            calc.divide(10, 0)
