from datetime import timedelta
from types import SimpleNamespace

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.market_access import (
    MARKETS,
    can_access_gold_features,
    can_access_market,
    market_access_v2_enabled,
    resolve_market_access,
    with_market_access_relations,
)
from apps.accounts.models import (
    TrialCampaign,
    TrialGrant,
    User,
    UserAccessProfile,
    UserMarketGrant,
    UserMarketPreference,
)
from common.permissions import CanAccessMarketV2, CanManageMarketAccess, CanManageUsers, CanStartMarketTrialCampaign


class MarketAccessV2FoundationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="market-v2-user")
        self.admin = User.objects.create_user(username="market-v2-admin", role=User.Role.SUPER_ADMIN)
        self.support = User.objects.create_user(username="market-v2-support", role=User.Role.SUPPORT)

    def grant(self, market):
        return UserMarketGrant.objects.create(
            user=self.user,
            market=market,
            source=UserMarketGrant.Source.ADMIN,
            granted_by=self.admin,
        )

    def test_feature_gate_defaults_off_without_changing_legacy_access(self):
        self.assertFalse(market_access_v2_enabled())
        self.assertEqual(self.user.effective_access_level, User.AccessLevel.LEVEL_1)
        request = SimpleNamespace(user=self.user)
        view = SimpleNamespace(required_market=User.MarketType.CRYPTO)
        self.grant(User.MarketType.CRYPTO)
        self.assertFalse(CanAccessMarketV2().has_permission(request, view))
        with override_settings(MARKET_ACCESS_V2_ENABLED=True):
            self.assertTrue(market_access_v2_enabled())
            self.assertTrue(CanAccessMarketV2().has_permission(request, view))
        self.assertEqual(self.user.effective_access_level, User.AccessLevel.LEVEL_1)

    def test_selected_checkbox_never_grants_market_access(self):
        UserMarketPreference.objects.create(user=self.user, market=User.MarketType.CRYPTO)
        state = resolve_market_access(self.user)
        self.assertEqual(state.membership_tier, "LEVEL_1")
        self.assertEqual(state.selected_markets, {User.MarketType.CRYPTO})
        self.assertFalse(state.granted_markets)
        self.assertFalse(can_access_market(self.user, User.MarketType.CRYPTO))
        self.assertFalse(state.market_selection_confirmed)
        UserAccessProfile.objects.create(user=self.user, market_selection_confirmed_at=timezone.now())
        self.assertTrue(resolve_market_access(self.user).market_selection_confirmed)

    def test_one_two_three_grants_derive_basic_pro_gold(self):
        for market, tier in (
            (User.MarketType.INTERNAL, "BASIC"),
            (User.MarketType.FOREX, "PRO"),
            (User.MarketType.CRYPTO, "GOLD"),
        ):
            self.grant(market)
            state = resolve_market_access(self.user)
            self.assertEqual(state.membership_tier, tier)
        self.assertEqual(state.effective_markets, MARKETS)
        self.assertTrue(can_access_gold_features(self.user))
        self.assertTrue(can_access_market(self.user, "CRYPTO"))
        self.assertFalse(can_access_market(self.user, "unknown"))

    def test_active_grant_is_unique_and_revocation_preserves_history(self):
        first = self.grant(User.MarketType.CRYPTO)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.grant(User.MarketType.CRYPTO)
        first.revoked_at = timezone.now()
        first.revoked_by = self.admin
        first.save(update_fields=("revoked_at", "revoked_by"))
        self.assertFalse(can_access_market(self.user, User.MarketType.CRYPTO))
        self.grant(User.MarketType.CRYPTO)
        self.assertEqual(UserMarketGrant.objects.filter(user=self.user).count(), 2)
        self.assertTrue(can_access_market(self.user, User.MarketType.CRYPTO))

    def test_invalid_market_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserMarketPreference.objects.create(user=self.user, market="invalid")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.grant("invalid")

    def test_new_trial_is_independent_of_legacy_dates_and_is_once_per_user(self):
        now = timezone.now()
        self.user.access_level = User.AccessLevel.LEVEL_5
        self.user.gold_trial_started_at = now - timedelta(days=2)
        self.user.gold_trial_expires_at = now + timedelta(days=5)
        self.user.save(update_fields=("access_level", "gold_trial_started_at", "gold_trial_expires_at"))
        self.assertFalse(resolve_market_access(self.user, at=now).trial_active)
        campaign = TrialCampaign.objects.create(created_by=self.admin)
        TrialGrant.objects.create(user=self.user, campaign=campaign, started_at=now, ends_at=now + timedelta(days=7))
        active = resolve_market_access(self.user, at=now + timedelta(days=1))
        self.assertTrue(active.trial_active)
        self.assertEqual(active.membership_tier, "LEVEL_1")
        self.assertEqual(active.effective_markets, MARKETS)
        self.assertTrue(active.has_gold_features)
        self.assertFalse(resolve_market_access(self.user, at=now + timedelta(days=7)).trial_active)
        with self.assertRaises(IntegrityError), transaction.atomic():
            TrialGrant.objects.create(user=self.user, campaign=campaign, started_at=now, ends_at=now + timedelta(days=7))

    def test_elite_does_not_grant_unselected_markets(self):
        UserAccessProfile.objects.create(user=self.user, is_elite=True, elite_updated_by=self.admin)
        state = resolve_market_access(self.user)
        self.assertTrue(state.is_elite)
        self.assertEqual(state.membership_tier, "LEVEL_1")
        self.assertFalse(state.effective_markets)

    def test_special_roles_are_excluded_without_changing_old_role_permissions(self):
        super_state = resolve_market_access(self.admin)
        support_state = resolve_market_access(self.support)
        self.assertIsNone(super_state.membership_tier)
        self.assertEqual(super_state.effective_markets, MARKETS)
        self.assertIsNone(support_state.membership_tier)
        self.assertFalse(support_state.effective_markets)
        self.assertTrue(CanManageMarketAccess().has_permission(SimpleNamespace(user=self.support), None))
        self.assertFalse(CanManageUsers().has_permission(SimpleNamespace(user=self.support), None))
        self.assertFalse(CanStartMarketTrialCampaign().has_permission(SimpleNamespace(user=self.support), None))
        self.assertTrue(CanStartMarketTrialCampaign().has_permission(SimpleNamespace(user=self.admin), None))

    def test_paginated_users_can_resolve_from_prefetched_relations(self):
        UserMarketPreference.objects.create(user=self.user, market=User.MarketType.INTERNAL)
        self.grant(User.MarketType.CRYPTO)
        users = list(with_market_access_relations(User.objects.filter(pk=self.user.pk)))
        with self.assertNumQueries(0):
            state = resolve_market_access(users[0])
        self.assertEqual(state.membership_tier, "BASIC")
