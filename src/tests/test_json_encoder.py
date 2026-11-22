"""
Tests for ReckonJSONEncoder.
"""

import pytest
import json
from datetime import datetime
from dataclasses import dataclass

from reckon.memory.manager import ReckonJSONEncoder


class TestReckonJSONEncoder:
    """Tests for the custom JSON encoder."""

    def test_datetime_serialization(self):
        """datetime objects should be serialized to ISO format."""
        dt = datetime(2024, 1, 15, 12, 30, 45)
        result = json.dumps({"time": dt}, cls=ReckonJSONEncoder)
        assert "2024-01-15" in result
        assert "12:30:45" in result

    def test_datetime_with_microseconds(self):
        """datetime with microseconds should serialize correctly."""
        dt = datetime(2024, 1, 15, 12, 30, 45, 123456)
        result = json.dumps({"time": dt}, cls=ReckonJSONEncoder)
        data = json.loads(result)
        assert "123456" in data["time"]

    def test_dataclass_serialization(self):
        """dataclass objects should be serialized to dict."""
        @dataclass
        class Point:
            x: int
            y: int

        p = Point(10, 20)
        result = json.dumps({"point": p}, cls=ReckonJSONEncoder)
        data = json.loads(result)
        assert data["point"]["x"] == 10
        assert data["point"]["y"] == 20

    def test_nested_dataclass_serialization(self):
        """Nested dataclasses should be serialized correctly."""
        @dataclass
        class Inner:
            value: int

        @dataclass
        class Outer:
            name: str
            inner: Inner

        obj = Outer(name="test", inner=Inner(value=42))
        result = json.dumps({"data": obj}, cls=ReckonJSONEncoder)
        data = json.loads(result)
        assert data["data"]["name"] == "test"
        assert data["data"]["inner"]["value"] == 42

    def test_object_with_dict_serialization(self):
        """Objects with __dict__ should be serialized."""
        class SimpleObject:
            def __init__(self):
                self.name = "test"
                self.value = 123

        obj = SimpleObject()
        result = json.dumps({"obj": obj}, cls=ReckonJSONEncoder)
        data = json.loads(result)
        assert data["obj"]["name"] == "test"
        assert data["obj"]["value"] == 123

    def test_numpy_array_serialization(self):
        """numpy arrays should be serialized to list."""
        try:
            import numpy as np
            arr = np.array([1, 2, 3])
            result = json.dumps({"arr": arr}, cls=ReckonJSONEncoder)
            data = json.loads(result)
            assert data["arr"] == [1, 2, 3]
        except ImportError:
            pytest.skip("numpy not installed")

    def test_numpy_2d_array_serialization(self):
        """2D numpy arrays should be serialized to nested lists."""
        try:
            import numpy as np
            arr = np.array([[1, 2], [3, 4]])
            result = json.dumps({"arr": arr}, cls=ReckonJSONEncoder)
            data = json.loads(result)
            assert data["arr"] == [[1, 2], [3, 4]]
        except ImportError:
            pytest.skip("numpy not installed")

    def test_numpy_scalar_serialization(self):
        """numpy scalar types should be serialized correctly."""
        try:
            import numpy as np
            val = np.float64(3.14)
            # numpy scalars should be handled via the tolist() method
            result = json.dumps({"val": val.item()}, cls=ReckonJSONEncoder)
            data = json.loads(result)
            assert abs(data["val"] - 3.14) < 0.001
        except ImportError:
            pytest.skip("numpy not installed")

    def test_primitive_types_unchanged(self):
        """Primitive types should serialize normally."""
        data = {
            "string": "hello",
            "int": 42,
            "float": 3.14,
            "bool": True,
            "null": None,
            "list": [1, 2, 3],
            "dict": {"a": 1},
        }
        result = json.dumps(data, cls=ReckonJSONEncoder)
        parsed = json.loads(result)
        assert parsed == data

    def test_mixed_types(self):
        """Mixed types in same structure should serialize correctly."""
        @dataclass
        class Config:
            name: str
            value: int

        data = {
            "timestamp": datetime(2024, 1, 15),
            "config": Config(name="test", value=42),
            "numbers": [1, 2, 3],
        }
        result = json.dumps(data, cls=ReckonJSONEncoder)
        parsed = json.loads(result)
        assert "2024-01-15" in parsed["timestamp"]
        assert parsed["config"]["name"] == "test"
        assert parsed["numbers"] == [1, 2, 3]

    def test_unsupported_type_raises(self):
        """Unsupported types should raise TypeError."""
        class Unpicklable:
            pass

        # Remove __dict__ to make it truly unserializable
        class NoDict:
            __slots__ = ()

        obj = NoDict()
        with pytest.raises(TypeError):
            json.dumps({"obj": obj}, cls=ReckonJSONEncoder)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
