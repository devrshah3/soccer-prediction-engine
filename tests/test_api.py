from soccer_engine.api.app import app
from soccer_engine.schemas import FixturePrediction


def test_api_contract_is_versioned() -> None:
    schema = FixturePrediction.model_json_schema()
    assert "schema_version" in schema["properties"]
    paths = app.openapi()["paths"]
    assert "/predictions/{fixture_id}" in paths
    assert "/fixtures" in paths
