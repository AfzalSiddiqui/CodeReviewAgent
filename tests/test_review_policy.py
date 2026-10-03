import textwrap

import pytest

from app.agent.review_policy import ReviewPolicy


@pytest.fixture
def policy(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text(textwrap.dedent("""
        review:
          defaults:
            model: default-model
          categories:
            security:
              enabled: true
              checks: [hardcoded_secrets, authentication]
            performance:
              enabled: true
              checks: [memory_usage]
            style:
              enabled: false
              checks: [naming]
          agents:
            security_agent:
              enabled: true
              model: big-model
              categories: [security]
            performance_agent:
              enabled: true
              categories: [performance]
            style_agent:
              enabled: false
              categories: [style]
    """))
    return ReviewPolicy(str(path))


def test_only_enabled_categories_are_returned(policy):
    assert policy.get_categories() == ["security", "performance"]


def test_checks_exclude_disabled_categories(policy):
    checks = policy.get_checks()
    assert "style" not in checks
    assert checks["security"] == ["hardcoded_secrets", "authentication"]


def test_agent_config_uses_its_own_model(policy):
    assert policy.get_agent_config("security_agent")["model"] == "big-model"


def test_agent_config_falls_back_to_default_model(policy):
    assert policy.get_agent_config("performance_agent")["model"] == "default-model"


def test_unknown_agent_is_disabled(policy):
    cfg = policy.get_agent_config("missing_agent")
    assert cfg["enabled"] is False
    assert cfg["categories"] == []


def test_enabled_agents(policy):
    assert policy.get_enabled_agents() == ["security_agent", "performance_agent"]


def test_checks_filtered_by_category(policy):
    assert policy.get_checks_for_categories(["performance"]) == {"performance": ["memory_usage"]}


def test_default_policy_file_loads():
    policy = ReviewPolicy("policies/default.yaml")
    assert policy.get_enabled_agents()
