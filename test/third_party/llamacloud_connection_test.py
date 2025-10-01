import logging
import pytest
from llama_cloud_services import LlamaExtract

@pytest.fixture
def api_key():
    """Fixture to provide LlamaCloud API key"""
    return "llx-CsOui2BBuQIAsd9tGmxWo3EdViSjz59L5nxitWDByvn100tT"

@pytest.fixture
def agent_id():
    """Fixture to provide LlamaCloud agent ID"""
    return "f311fd08-282f-4fef-8a41-f728242159e9"

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
    # Replace with your actual API key and agent ID
    API_KEY = "llx-CsOui2BBuQIAsd9tGmxWo3EdViSjz59L5nxitWDByvn100tT"
    AGENT_ID = "f311fd08-282f-4fef-8a41-f728242159e9" 
    test_llamacloud_connection(API_KEY, AGENT_ID)