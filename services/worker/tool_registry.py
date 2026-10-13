from typing import Callable, Dict, Any, List, Optional
from pydantic import BaseModel

class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]
    risk_level: str = "low" # low, medium, high
    preconditions: List[str] = []
    handler: Optional[Callable] = None

    class Config:
        arbitrary_types_allowed = True

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition):
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def get_all_tools(self) -> Dict[str, ToolDefinition]:
        return self._tools

    def get_openai_tools(self, allowlist: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Returns tools formatted for Gemini/OpenAI function calling schemas,
        filtered by workflow allowlist if specified.
        """
        schemas = []
        for name, tool in self._tools.items():
            if allowlist is not None and name not in allowlist:
                continue
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters
                }
            })
        return schemas

    def execute(self, name: str, arguments: Dict[str, Any]) -> Any:
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool '{name}' is not registered.")
        if not tool.handler:
            raise ValueError(f"Tool '{name}' does not have an executable handler.")
        return tool.handler(**arguments)

tool_registry = ToolRegistry()
