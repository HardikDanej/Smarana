"""
Phase 21 (Adaptive Configuration Profiles): TenantProfile, PolicyDefaults,
RetentionPolicy, TenantProfileStore, and apply_profile_defaults()'s
resolution logic (explicit value beats profile default beats hardcoded
fallback).
"""

from memory_os import PrivacyCategory, PrivacyLevel
from memory_os.profiles import (
    ApplicationType,
    BusinessType,
    Industry,
    PolicyDefaults,
    RetentionPolicy,
    TenantProfile,
    TenantProfileStore,
    apply_profile_defaults,
)


# --- per-industry starter defaults ---


def test_general_industry_has_no_automatic_retention_and_internal_sensitivity():
    profile = TenantProfile.for_industry("t1", Industry.GENERAL, ApplicationType.B2B_SAAS, BusinessType.B2B)
    assert profile.policy_defaults.sensitivity == PrivacyLevel.INTERNAL
    assert profile.policy_defaults.privacy_categories == ()
    assert profile.retention.default_retention_days is None


def test_healthcare_defaults_to_confidential_personal_with_long_retention():
    profile = TenantProfile.for_industry("t1", Industry.HEALTHCARE, ApplicationType.B2B_SAAS, BusinessType.B2B)
    assert profile.policy_defaults.sensitivity == PrivacyLevel.CONFIDENTIAL
    assert PrivacyCategory.PERSONAL in profile.policy_defaults.privacy_categories
    assert profile.retention.default_retention_days == 2555


def test_financial_defaults_to_confidential_financial_with_long_retention():
    profile = TenantProfile.for_industry("t1", Industry.FINANCIAL, ApplicationType.CONSUMER_APP, BusinessType.B2C)
    assert profile.policy_defaults.sensitivity == PrivacyLevel.CONFIDENTIAL
    assert PrivacyCategory.FINANCIAL in profile.policy_defaults.privacy_categories
    assert profile.retention.default_retention_days == 2555


def test_ecommerce_defaults_to_internal_personal_with_shorter_retention():
    profile = TenantProfile.for_industry("t1", Industry.ECOMMERCE, ApplicationType.CONSUMER_APP, BusinessType.B2C)
    assert profile.policy_defaults.sensitivity == PrivacyLevel.INTERNAL
    assert PrivacyCategory.PERSONAL in profile.policy_defaults.privacy_categories
    assert profile.retention.default_retention_days == 730


def test_explicit_policy_defaults_override_the_industry_starter():
    custom = PolicyDefaults(sensitivity=PrivacyLevel.SECRET)
    profile = TenantProfile.for_industry(
        "t1", Industry.GENERAL, ApplicationType.B2B_SAAS, BusinessType.B2B, policy_defaults=custom
    )
    assert profile.policy_defaults.sensitivity == PrivacyLevel.SECRET


def test_explicit_retention_overrides_the_industry_starter():
    custom = RetentionPolicy(default_retention_days=30)
    profile = TenantProfile.for_industry(
        "t1", Industry.HEALTHCARE, ApplicationType.B2B_SAAS, BusinessType.B2B, retention=custom
    )
    assert profile.retention.default_retention_days == 30


# --- TenantProfileStore ---


def test_store_registers_and_retrieves_a_profile():
    store = TenantProfileStore()
    profile = TenantProfile.for_industry("t1", Industry.HEALTHCARE, ApplicationType.B2B_SAAS, BusinessType.B2B)
    store.register(profile)
    assert store.get("t1") is profile


def test_store_returns_none_for_an_unregistered_tenant():
    store = TenantProfileStore()
    assert store.get("does-not-exist") is None


def test_store_returns_none_for_a_none_tenant_id():
    store = TenantProfileStore()
    assert store.get(None) is None


# --- apply_profile_defaults resolution ---


def test_explicit_values_always_win_over_the_profile():
    profile = TenantProfile.for_industry("t1", Industry.HEALTHCARE, ApplicationType.B2B_SAAS, BusinessType.B2B)
    sensitivity, categories, tags = apply_profile_defaults(
        profile, sensitivity=PrivacyLevel.PUBLIC, privacy_categories=[], tags=["custom"]
    )
    assert sensitivity == PrivacyLevel.PUBLIC
    assert categories == []
    assert tags == ["custom"]


def test_unset_values_fall_back_to_the_profile_default():
    profile = TenantProfile.for_industry("t1", Industry.FINANCIAL, ApplicationType.B2B_SAAS, BusinessType.B2B)
    sensitivity, categories, tags = apply_profile_defaults(
        profile, sensitivity=None, privacy_categories=None, tags=None
    )
    assert sensitivity == PrivacyLevel.CONFIDENTIAL
    assert categories == [PrivacyCategory.FINANCIAL]
    assert tags == []


def test_no_profile_falls_back_to_memory_objects_own_hardcoded_default():
    sensitivity, categories, tags = apply_profile_defaults(
        None, sensitivity=None, privacy_categories=None, tags=None
    )
    assert sensitivity == PrivacyLevel.INTERNAL
    assert categories == []
    assert tags == []
