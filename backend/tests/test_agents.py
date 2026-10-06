import unittest

from app.agents import AgentOrchestrator
from app.services.query_understanding import understand_query


class AgentPlanTests(unittest.TestCase):
    def test_vulnerability_plan_is_bounded(self):
        plan = AgentOrchestrator().plan(understand_query("Investigate CVE-2024-12345 and map mitigation"))
        self.assertIn("VulnerabilityAgent", plan.agents)
        self.assertIn("KnowledgeGraphAgent", plan.agents)
        self.assertNotIn("ExploitAgent", plan.agents)

    def test_ood_plan_does_not_route_to_cyber_actions(self):
        plan = AgentOrchestrator().plan(understand_query("What is the weather?"))
        self.assertEqual(plan.agents, ["OODGuardAgent"])


if __name__ == "__main__":
    unittest.main()
