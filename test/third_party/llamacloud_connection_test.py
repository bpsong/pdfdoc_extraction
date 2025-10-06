import logging
import pytest
import yaml
from pathlib import Path
from llama_cloud_services import LlamaExtract

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
def agent_id(test_config):
    """Fixture to provide LlamaCloud agent ID from test config"""
    return test_config['llamacloud']['agent_id']

def test_llamacloud_connection(api_key: str, agent_id: str):
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("LlamaCloudConnectionTest")

    try:
        logger.info("Initializing LlamaExtract client...")
        client = LlamaExtract(api_key=api_key)
        logger.info(f"Getting agent with ID: {agent_id}")
        agent = client.get_agent(id=agent_id)
        logger.info(f"Agent retrieved: {agent}")

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
    AGENT_ID = config['llamacloud']['agent_id']
    test_llamacloud_connection(API_KEY, AGENT_ID)