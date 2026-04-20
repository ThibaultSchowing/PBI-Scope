from pathlib import Path

import yaml


def _load_compose_config():
    compose_path = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    with compose_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_analysis_service_has_private_data_mount():
    compose = _load_compose_config()
    analysis_volumes = compose["services"]["analysis"]["volumes"]
    assert "./private_data:/private-data:ro" in analysis_volumes


def test_analysis_service_exposes_private_data_env_var():
    compose = _load_compose_config()
    analysis_env = compose["services"]["analysis"]["environment"]
    assert "PBI_PRIVATE_DATA_DIR=/private-data" in analysis_env


def test_analysis_service_has_results_mount():
    compose = _load_compose_config()
    analysis_volumes = compose["services"]["analysis"]["volumes"]
    assert "./analysis_results:/results" in analysis_volumes


def test_analysis_service_exposes_results_env_var():
    compose = _load_compose_config()
    analysis_env = compose["services"]["analysis"]["environment"]
    assert "PBI_RESULTS_DIR=/results" in analysis_env
