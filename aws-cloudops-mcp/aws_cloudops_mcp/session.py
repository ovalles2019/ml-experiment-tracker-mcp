"""Shared boto3 session construction (profile + region)."""

from __future__ import annotations

import os

import boto3


def resolve_boto_session() -> tuple[boto3.Session, str]:
    """Return (Session, region_name) using AWS_PROFILE and AWS_REGION / AWS_DEFAULT_REGION."""
    profile = os.environ.get("AWS_PROFILE")
    explicit_region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    region = explicit_region or session.region_name or "us-east-1"
    return session, region
