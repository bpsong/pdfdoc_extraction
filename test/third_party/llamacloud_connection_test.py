import logging
import pytest
import yaml
from pathlib import Path
from llama_cloud import LlamaCloud

@pytest.fixture
def test_config():
    """Fixture to load test configuration from test_config.yaml"""
    config_path = Path(__file__).parent / "test_config.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

@pytest.fixture
def api_key(test_config):
    """Fixture to provide LlamaCloud API key from test config"""
    return test_config['llamacloud']['api_key']

@pytest.fixture
def configuration_id(test_config):
    """Fixture to provide optional LlamaCloud Extract v2 configuration ID."""
    return test_config.get('llamacloud', {}).get('configuration_id')

def test_llamacloud_connection(api_key: str, configuration_id: str | None):
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("LlamaCloudConnectionTest")

    try:
        logger.info("Initializing LlamaCloud client...")
        client = LlamaCloud(api_key=api_key)

        if configuration_id:
            logger.info("Retrieving Extract v2 configuration...")
            configuration = client.configurations.retrieve(configuration_id)
            logger.info(f"Configuration retrieved: {configuration.id}")
        else:
            logger.info("Listing Extract v2 configurations...")
            configurations = client.configurations.list(product_type=["extract_v2"], page_size=1)
            first_configuration = next(iter(configurations), None)
            logger.info(f"First Extract v2 configuration: {first_configuration}")

        # Optionally, test a simple extraction call with a dummy or real PDF path if available
        # pdf_path = "path/to/sample.pdf"
        # result = agent.extract(pdf_path)
        # logger.info(f"Extraction result: {result}")

        logger.info("LlamaCloud connection test succeeded.")
    except Exception as e:
        logger.error(f"LlamaCloud connection test failed: {e}")
        raise

if __name__ == "__main__":
    # Load credentials from test config file
    config_path = Path(__file__).parent / "test_config.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    API_KEY = config['llamacloud']['api_key']
    CONFIGURATION_ID = config.get('llamacloud', {}).get('configuration_id')
    test_llamacloud_connection(API_KEY, CONFIGURATION_ID)
