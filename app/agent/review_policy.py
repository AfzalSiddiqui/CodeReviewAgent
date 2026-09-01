import yaml


class ReviewPolicy:

    def __init__(self, policy_file="policies/default.yaml"):
        with open(policy_file, "r") as file:
            self.policy = yaml.safe_load(file)

    def get_categories(self):

        categories = self.policy["review"]["categories"]

        return [
            name
            for name, config in categories.items()
            if config.get("enabled", False)
        ]

    def get_checks(self):

        categories = self.policy["review"]["categories"]

        checks = {}

        for category, config in categories.items():

            if config.get("enabled", False):
                checks[category] = config.get("checks", [])

        return checks

    def get_agent_config(self, agent_name: str) -> dict:
        """Return config for a specific agent with defaults fallback."""
        defaults = self.policy["review"].get("defaults", {})
        agents = self.policy["review"].get("agents", {})
        agent_cfg = agents.get(agent_name, {})

        return {
            "enabled": agent_cfg.get("enabled", False),
            "model": agent_cfg.get("model", defaults.get("model", "qwen2.5-coder:7b")),
            "categories": agent_cfg.get("categories", []),
        }

    def get_checks_for_categories(self, category_names: list[str]) -> dict:
        """Return checks filtered to only the given categories."""
        all_checks = self.get_checks()
        return {
            cat: checks
            for cat, checks in all_checks.items()
            if cat in category_names
        }

    def get_enabled_agents(self) -> list[str]:
        """Return list of enabled agent names."""
        agents = self.policy["review"].get("agents", {})
        return [
            name
            for name, config in agents.items()
            if config.get("enabled", False)
        ]
