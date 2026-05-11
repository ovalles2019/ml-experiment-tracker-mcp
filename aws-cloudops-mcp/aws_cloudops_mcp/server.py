"""FastMCP server: read-focused AWS Cloud Operations tools."""

from __future__ import annotations

import json
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from mcp.server.fastmcp import FastMCP

from aws_cloudops_mcp.session import resolve_boto_session

mcp = FastMCP(
    "AWS CloudOps",
    instructions=(
        "Read-focused AWS operations helpers for CloudOps workflows: identity, EC2, "
        "security groups, CloudWatch alarms, S3 buckets, Lambda functions, and load balancers. "
        "Uses boto3 with AWS_PROFILE / AWS_REGION (or default credential chain). "
        "Prefer least-privilege IAM; see project README for suggested read-only actions."
    ),
)


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def _tags_to_map(tags: list[dict[str, str]] | None) -> dict[str, str]:
    if not tags:
        return {}
    out: dict[str, str] = {}
    for t in tags:
        out[t.get("Key", "")] = t.get("Value", "")
    return out


def _aws_call(fn: Any, label: str) -> str:
    try:
        return _json(fn())
    except ClientError as e:
        err = e.response.get("Error", {})
        return _json(
            {
                "ok": False,
                "error": label,
                "code": err.get("Code"),
                "message": err.get("Message"),
            }
        )
    except BotoCoreError as e:
        return _json({"ok": False, "error": label, "message": str(e)})


@mcp.tool()
def aws_whoami() -> str:
    """Return STS caller identity (account, ARN, user/role id) and resolved region."""

    def run() -> dict[str, Any]:
        session, region = resolve_boto_session()
        sts = session.client("sts", region_name=region)
        ident = sts.get_caller_identity()
        return {
            "ok": True,
            "region": region,
            "account": ident.get("Account"),
            "arn": ident.get("Arn"),
            "user_id": ident.get("UserId"),
        }

    return _aws_call(run, "sts:GetCallerIdentity")


@mcp.tool()
def list_ec2_instances(
    max_results: int = 50,
    instance_states: list[str] | None = None,
    tag_key: str | None = None,
    tag_value: str | None = None,
) -> str:
    """Describe EC2 instances (summarized). Optional filters: states, single tag key/value."""

    def run() -> dict[str, Any]:
        session, region = resolve_boto_session()
        ec2 = session.client("ec2", region_name=region)
        caps = max(1, min(max_results, 100))
        filters: list[dict[str, Any]] = []
        if instance_states:
            filters.append({"Name": "instance-state-name", "Values": instance_states})
        if tag_key and tag_value:
            filters.append({"Name": f"tag:{tag_key}", "Values": [tag_value]})
        kwargs: dict[str, Any] = {"MaxResults": caps}
        if filters:
            kwargs["Filters"] = filters
        resp = ec2.describe_instances(**kwargs)
        instances: list[dict[str, Any]] = []
        for r in resp.get("Reservations", []):
            for inst in r.get("Instances", []):
                instances.append(
                    {
                        "InstanceId": inst.get("InstanceId"),
                        "InstanceType": inst.get("InstanceType"),
                        "State": (inst.get("State") or {}).get("Name"),
                        "AvailabilityZone": (inst.get("Placement") or {}).get(
                            "AvailabilityZone"
                        ),
                        "PrivateIpAddress": inst.get("PrivateIpAddress"),
                        "PublicIpAddress": inst.get("PublicIpAddress"),
                        "LaunchTime": inst.get("LaunchTime").isoformat()
                        if inst.get("LaunchTime")
                        else None,
                        "Tags": _tags_to_map(inst.get("Tags")),
                    }
                )
        return {"ok": True, "count": len(instances), "instances": instances}

    return _aws_call(run, "ec2:DescribeInstances")


@mcp.tool()
def describe_ec2_instance(instance_id: str) -> str:
    """Single EC2 instance detail (security groups, subnets, root volume ids summarized)."""

    def run() -> dict[str, Any]:
        session, region = resolve_boto_session()
        ec2 = session.client("ec2", region_name=region)
        resp = ec2.describe_instances(InstanceIds=[instance_id])
        reservations = resp.get("Reservations", [])
        if not reservations or not reservations[0].get("Instances"):
            return {"ok": False, "error": f"Instance not found: {instance_id}"}
        inst = reservations[0]["Instances"][0]
        block = inst.get("BlockDeviceMappings") or []
        return {
            "ok": True,
            "InstanceId": inst.get("InstanceId"),
            "InstanceType": inst.get("InstanceType"),
            "State": (inst.get("State") or {}).get("Name"),
            "VpcId": inst.get("VpcId"),
            "SubnetId": inst.get("SubnetId"),
            "PrivateIpAddress": inst.get("PrivateIpAddress"),
            "PublicIpAddress": inst.get("PublicIpAddress"),
            "SecurityGroups": inst.get("SecurityGroups"),
            "IamInstanceProfile": inst.get("IamInstanceProfile"),
            "Tags": _tags_to_map(inst.get("Tags")),
            "LaunchTime": inst.get("LaunchTime").isoformat()
            if inst.get("LaunchTime")
            else None,
            "BlockDeviceMappings": [
                {"DeviceName": b.get("DeviceName"), "VolumeId": (b.get("Ebs") or {}).get("VolumeId")}
                for b in block
            ],
        }

    return _aws_call(run, "ec2:DescribeInstances")


@mcp.tool()
def list_security_groups(vpc_id: str | None = None, limit: int = 30) -> str:
    """List EC2 security groups (optional vpc-id filter)."""

    def run() -> dict[str, Any]:
        session, region = resolve_boto_session()
        ec2 = session.client("ec2", region_name=region)
        lim = max(1, min(limit, 100))
        kwargs: dict[str, Any] = {}
        if vpc_id:
            kwargs["Filters"] = [{"Name": "vpc-id", "Values": [vpc_id]}]
        paginator = ec2.get_paginator("describe_security_groups")
        groups: list[dict[str, Any]] = []
        for page in paginator.paginate(**kwargs):
            groups.extend(page.get("SecurityGroups") or [])
            if len(groups) >= lim:
                break
        groups = groups[:lim]
        slim = [
            {
                "GroupId": g.get("GroupId"),
                "GroupName": g.get("GroupName"),
                "VpcId": g.get("VpcId"),
                "Description": g.get("Description"),
                "IngressRules": len(g.get("IpPermissions") or []),
                "EgressRules": len(g.get("IpPermissionsEgress") or []),
            }
            for g in groups
        ]
        return {"ok": True, "count": len(slim), "security_groups": slim}

    return _aws_call(run, "ec2:DescribeSecurityGroups")


@mcp.tool()
def list_cloudwatch_alarms(max_records: int = 50, alarm_name_prefix: str | None = None) -> str:
    """Describe CloudWatch alarms (names, states, metrics summary)."""

    def run() -> dict[str, Any]:
        session, region = resolve_boto_session()
        cw = session.client("cloudwatch", region_name=region)
        lim = max(1, min(max_records, 100))
        kwargs: dict[str, Any] = {"MaxRecords": lim}
        if alarm_name_prefix:
            kwargs["AlarmNamePrefix"] = alarm_name_prefix
        resp = cw.describe_alarms(**kwargs)
        alarms = []
        for a in resp.get("MetricAlarms", []):
            alarms.append(
                {
                    "AlarmName": a.get("AlarmName"),
                    "StateValue": a.get("StateValue"),
                    "MetricName": a.get("MetricName"),
                    "Namespace": a.get("Namespace"),
                    "Statistic": a.get("Statistic"),
                    "Threshold": a.get("Threshold"),
                    "ComparisonOperator": a.get("ComparisonOperator"),
                }
            )
        return {"ok": True, "count": len(alarms), "alarms": alarms}

    return _aws_call(run, "cloudwatch:DescribeAlarms")


@mcp.tool()
def describe_cloudwatch_alarm(alarm_name: str) -> str:
    """Full detail for one CloudWatch metric alarm."""

    def run() -> dict[str, Any]:
        session, region = resolve_boto_session()
        cw = session.client("cloudwatch", region_name=region)
        resp = cw.describe_alarms(AlarmNames=[alarm_name])
        alarms = resp.get("MetricAlarms") or []
        if not alarms:
            return {"ok": False, "error": f"Alarm not found: {alarm_name}"}
        return {"ok": True, "alarm": alarms[0]}

    return _aws_call(run, "cloudwatch:DescribeAlarms")


@mcp.tool()
def list_s3_buckets() -> str:
    """List S3 buckets (Name, CreationDate)."""

    def run() -> dict[str, Any]:
        session, region = resolve_boto_session()
        # ListBuckets is global; client region mainly affects signing defaults.
        s3 = session.client("s3", region_name=region)
        resp = s3.list_buckets()
        buckets = resp.get("Buckets") or []
        slim = [
            {
                "Name": b.get("Name"),
                "CreationDate": b.get("CreationDate").isoformat()
                if b.get("CreationDate")
                else None,
            }
            for b in buckets
        ]
        return {"ok": True, "count": len(slim), "buckets": slim}

    return _aws_call(run, "s3:ListBuckets")


@mcp.tool()
def list_lambda_functions(max_items: int = 50) -> str:
    """List Lambda functions (runtime, memory, last modified)."""

    def run() -> dict[str, Any]:
        session, region = resolve_boto_session()
        lam = session.client("lambda", region_name=region)
        lim = max(1, min(max_items, 50))
        resp = lam.list_functions(MaxItems=lim)
        fns = []
        for f in resp.get("Functions", []):
            fns.append(
                {
                    "FunctionName": f.get("FunctionName"),
                    "Runtime": f.get("Runtime"),
                    "MemorySize": f.get("MemorySize"),
                    "LastModified": f.get("LastModified"),
                    "Timeout": f.get("Timeout"),
                    "VpcConfig": f.get("VpcConfig"),
                }
            )
        return {"ok": True, "count": len(fns), "functions": fns}

    return _aws_call(run, "lambda:ListFunctions")


@mcp.tool()
def describe_load_balancers_v2(max_items: int = 25) -> str:
    """Describe ELBv2 load balancers (ALB/NLB/GWLB), DNS name, scheme, state."""

    def run() -> dict[str, Any]:
        session, region = resolve_boto_session()
        elbv2 = session.client("elbv2", region_name=region)
        lim = max(1, min(max_items, 50))
        resp = elbv2.describe_load_balancers(PageSize=lim)
        lbs = []
        for lb in resp.get("LoadBalancers", []):
            state = (lb.get("State") or {}).get("Code")
            lbs.append(
                {
                    "LoadBalancerArn": lb.get("LoadBalancerArn"),
                    "DNSName": lb.get("DNSName"),
                    "Type": lb.get("Type"),
                    "Scheme": lb.get("Scheme"),
                    "VpcId": lb.get("VpcId"),
                    "State": state,
                }
            )
        return {"ok": True, "count": len(lbs), "load_balancers": lbs}

    return _aws_call(run, "elasticloadbalancing:DescribeLoadBalancers")


@mcp.resource("cloudops://whoami")
def resource_whoami() -> str:
    """STS identity + region as MCP resource."""
    session, region = resolve_boto_session()
    sts = session.client("sts", region_name=region)
    try:
        ident = sts.get_caller_identity()
        return _json(
            {
                "region": region,
                "account": ident.get("Account"),
                "arn": ident.get("Arn"),
                "user_id": ident.get("UserId"),
            }
        )
    except (ClientError, BotoCoreError) as e:
        return _json({"error": str(e)})


@mcp.prompt()
def incident_triage_prompt(service_hint: str = "EC2") -> str:
    """Starter prompt for ops triage using CloudOps tools."""
    return (
        f"You are assisting with AWS CloudOps. The impacted area may involve {service_hint}. "
        "Use aws_whoami first, then pull the smallest read-only dataset needed "
        "(instances, alarms, load balancers, Lambda). Summarize blast radius and next checks."
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
