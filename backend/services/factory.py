import os

def create_service():
    if os.getenv("MISSION_AUTOPSY_USE_MOCK_SERVICES", "true").lower() == "true":
        from backend.services.mock_service import MockInvestigationService
        return MockInvestigationService()
    from backend.services.autopsy_service import AutopsyInvestigationService
    from autopsy.llm.client import LLMClient
    from autopsy.llm.config import LLMConfig
    fake = os.getenv("MISSION_AUTOPSY_FAKE_LLM", "false").lower() == "true"
    return AutopsyInvestigationService(llm=LLMClient(LLMConfig(fake=fake)))
