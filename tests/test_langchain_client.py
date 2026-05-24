from pydantic import BaseModel, Field

from pwps_agent.config import LLMSettings
from pwps_agent.llm.langchain_client import LangChainStructuredClient


class DemoOutput(BaseModel):
    value: str = Field(description="Extracted demo value.")


class FakeStructuredRunnable:
    def __init__(self) -> None:
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return DemoOutput(value="ok")


class FakeChatModel:
    def __init__(self) -> None:
        self.schema = None
        self.method = None
        self.runnable = FakeStructuredRunnable()

    def with_structured_output(self, schema, method):
        self.schema = schema
        self.method = method
        return self.runnable


def test_langchain_structured_client_uses_pydantic_schema_and_method() -> None:
    chat_model = FakeChatModel()
    client = LangChainStructuredClient(
        LLMSettings(
            api_key="key",
            base_url="https://llm.example",
            model="compat-model",
            structured_output_method="function_calling",
        ),
        chat_model=chat_model,
    )

    result = client.complete_structured(
        system_prompt="System prompt",
        user_prompt="User prompt",
        schema=DemoOutput,
    )

    assert result == DemoOutput(value="ok")
    assert chat_model.schema is DemoOutput
    assert chat_model.method == "function_calling"
    assert chat_model.runnable.messages == [
        ("system", "System prompt"),
        ("user", "User prompt"),
    ]
