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
