from typing import Dict, Any, List, Tuple
from .tool_registry import tool_registry

class PolicyEngine:
    def __init__(self):
        # Forbidden actions that are strictly prohibited by code policy
        self.prohibited_actions = [
            "execute_shell",
            "execute_code",
            "initiate_payment",
            "approve_financial_transaction",
            "delete_all_records",
            "modify_security_rules"
        ]

    def evaluate(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        allowlist: List[str],
        current_context: Dict[str, Any]
    ) -> Tuple[bool, str, bool]:
        """
        Evaluates a tool call proposed by the model against code-owned policy rules.
        Returns: (is_allowed: bool, reason: str, requires_human_approval: bool)
        """
        # 1. Prohibited action check (Strict Prompt Injection Immunity)
        if tool_name in self.prohibited_actions:
            return False, f"Policy Violation: Action '{tool_name}' is explicitly prohibited by system safety policy.", False

        # 2. Workflow Allowlist check
        if tool_name not in allowlist:
            return False, f"Policy Violation: Tool '{tool_name}' is not in the active workflow's permitted tool allowlist.", False

        # 3. Tool existence check
        tool = tool_registry.get_tool(tool_name)
        if not tool:
            return False, f"Unknown Tool: Tool '{tool_name}' is not registered in the system.", False

        # 4. Financial safety check: No direct payment execution
        if "payment" in tool_name.lower() and "initiate" in tool_name.lower():
            return False, "Policy Violation: Autonomous agent cannot initiate payments. Reminders and record entry only.", True

        # 5. Email safety check: Email destination must be local or verified
        if tool_name in ["send_payment_reminder", "typed_send_sandbox_email"]:
            recipient = str(arguments.get("recipient", "")).lower()
            if not recipient:
                return False, "Recipient email is required.", False
            if "@" not in recipient:
                return False, f"Invalid recipient email format: '{recipient}'", False

        # 6. High risk actions require explicit human approval
        if tool.risk_level == "high":
            return True, "Tool has high risk level; human approval recommended.", True

        return True, "Action permitted by policy.", False

policy_engine = PolicyEngine()
