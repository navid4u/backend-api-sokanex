from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.accounts.models import FinancialPersonalityAssessment, User
from apps.accounts.personality_risk import (
    ASSESSMENT_VERSION,
    QUESTION_SCORES,
    dominant_type_for_scores,
)


class PersonalityRiskV2APITests(TestCase):
    url = "/api/accounts/personality-test/submit/"

    def setUp(self):
        self.user = User.objects.create_user(username="risk-v2-user", password="Pass123!")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @staticmethod
    def answers(overrides=None):
        overrides = overrides or {}
        result = []
        for question_id in range(1, 19):
            if question_id == 2:
                result.append({"question_id": 2, "option_ids": ["ASSET_1", "ASSET_3"]})
            else:
                result.append({
                    "question_id": question_id,
                    "option_id": overrides.get(question_id, next(iter(QUESTION_SCORES[question_id]))),
                })
        return result

    def payload(self, **extra):
        return {
            "assessment_version": ASSESSMENT_VERSION,
            "answers": self.answers(),
            **extra,
        }

    def test_both_endpoints_require_authentication(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get("/api/accounts/personality-test/").status_code, 401)
        self.assertEqual(self.client.post(self.url, self.payload(), format="json").status_code, 401)

    def test_valid_submission_and_get_return_same_canonical_result(self):
        response = self.client.post(self.url, self.payload(), format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["assessment_version"], ASSESSMENT_VERSION)
        self.assertEqual(response.data["asset_inventory"], ["ASSET_1", "ASSET_3"])
        self.assertEqual(sum(response.data["percentages"].values()), 100)

        current = self.client.get("/api/accounts/personality-test/")
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.data, response.data)

    def test_incomplete_duplicate_and_unknown_options_are_rejected(self):
        incomplete = self.payload()
        incomplete["answers"] = incomplete["answers"][:-1]
        duplicate = self.payload()
        duplicate["answers"][-1]["question_id"] = 17
        unknown = self.payload()
        unknown["answers"][0]["option_id"] = "UNKNOWN"
        bad_assets = self.payload()
        bad_assets["answers"][1]["option_ids"] = ["ASSET_1", "ASSET_1"]
        for payload in (incomplete, duplicate, unknown, bad_assets):
            self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 400)

    def test_client_result_is_never_trusted(self):
        response = self.client.post(
            self.url,
            self.payload(client_result={
                "personality_type": "OPPORTUNITY_SEEKER",
                "percentages": {"guardian": 0, "balanced": 0, "growth": 0, "opportunity": 100},
                "asset_inventory": ["ASSET_7"],
            }),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertNotEqual(response.data["percentages"]["opportunity"], 100)
        self.assertEqual(response.data["asset_inventory"], ["ASSET_1", "ASSET_3"])

    def test_legacy_history_is_preserved_when_v2_becomes_current(self):
        legacy = FinancialPersonalityAssessment.objects.create(
            user=self.user,
            personality_type=FinancialPersonalityAssessment.PersonalityType.WEALTH_ARCHITECT,
        )
        response = self.client.post(self.url, self.payload(), format="json")
        self.assertEqual(response.status_code, 201)
        legacy.refresh_from_db()
        self.assertFalse(legacy.is_current)
        self.assertEqual(legacy.assessment_version, "LEGACY_V1")
        self.assertEqual(FinancialPersonalityAssessment.objects.filter(user=self.user).count(), 2)

    def test_resubmission_preserves_history_and_updates_profile_and_dashboard(self):
        first = self.client.post(self.url, self.payload(), format="json")
        second_payload = self.payload()
        second_payload["answers"] = self.answers({question_id: list(QUESTION_SCORES[question_id])[-1] for question_id in QUESTION_SCORES})
        second = self.client.post(self.url, second_payload, format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(FinancialPersonalityAssessment.objects.filter(user=self.user).count(), 2)
        self.assertEqual(FinancialPersonalityAssessment.objects.filter(user=self.user, is_current=True).count(), 1)

        profile = self.client.get("/api/accounts/profile/details/")
        dashboard = self.client.get("/api/dashboard/")
        self.assertEqual(profile.data["personality_result"]["personality_type"], second.data["personality_type"])
        self.assertEqual(dashboard.data["data"]["personality_result"]["personality_type"], second.data["personality_type"])

    def test_tie_break_prefers_balanced_then_guardian(self):
        self.assertEqual(
            dominant_type_for_scores({"guardian": 10, "balanced": 10, "growth": 10, "opportunity": 10}),
            "BALANCED_SMART",
        )
        self.assertEqual(
            dominant_type_for_scores({"guardian": 11, "balanced": 10, "growth": 11, "opportunity": 11}),
            "CAPITAL_GUARDIAN",
        )

    def test_dashboard_does_not_issue_repeated_personality_queries(self):
        self.client.post(self.url, self.payload(), format="json")
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/api/dashboard/")
        self.assertEqual(response.status_code, 200)
        personality_queries = [
            query["sql"] for query in queries.captured_queries
            if "accounts_financialpersonalityassessment" in query["sql"].lower()
        ]
        self.assertLessEqual(len(personality_queries), 1)
