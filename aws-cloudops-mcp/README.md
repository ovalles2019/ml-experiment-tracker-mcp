# AWS CloudOps MCP Server

Model Context Protocol (**MCP**) server aimed at **Cloud Engineers**: expose common **read-only** operational queries across AWS APIs via **boto3**, so assistants can assist with triage, inventory, and alarm inspection inside MCP-aware clients (Cursor, Claude Code, and similar).

## What it exposes

| Area | Tools |
|------|--------|
| Identity | `aws_whoami` — STS caller identity + resolved Region |
| Compute | `list_ec2_instances`, `describe_ec2_instance` |
| Networking | `list_security_groups`, `describe_load_balancers_v2` |
| Observability | `list_cloudwatch_alarms`, `describe_cloudwatch_alarm` |
| Storage | `list_s3_buckets` |
| Serverless | `list_lambda_functions` |

**Resource:** `cloudops://whoami` — JSON STS snapshot.

**Prompt:** `incident_triage_prompt` — starter workflow text.

All tools return JSON strings (pretty-printed). API failures surface **normalized** `ClientError`/`BotoCoreError` payloads instead of crashing the server.

## Install & run

```bash
cd aws-cloudops-mcp
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

Authenticate like the AWS CLI (profiles in `~/.aws/config`), then:

```bash
export AWS_REGION=us-east-1              # or AWS_DEFAULT_REGION
export AWS_PROFILE=your-profile          # optional
python -m aws_cloudops_mcp.server
# or: aws-cloudops-mcp
```

**Development:** `pip install -e ".[dev]"` and optional `mcp dev aws_cloudops_mcp/server.py` after installing `mcp[cli]`.

## Cursor MCP snippet

```json
{
  "mcpServers": {
    "aws-cloudops": {
      "command": "/absolute/path/to/aws-cloudops-mcp/.venv/bin/python",
      "args": ["-m", "aws_cloudops_mcp.server"],
      "cwd": "/absolute/path/to/aws-cloudops-mcp",
      "env": {
        "AWS_PROFILE": "your-profile",
        "AWS_REGION": "us-east-1"
      }
    }
  }
}
```

Prefer **`AWS_*` env vars** in MCP configs rather than baking profiles into code.

## Suggested IAM (read-only baseline)

Attach something close to **AWS-managed `ReadOnlyAccess`** or stitch explicit Allow statements for the actions above (`sts:GetCallerIdentity`, `ec2:Describe*`, `cloudwatch:DescribeAlarms`, `s3:ListBuckets`, `lambda:ListFunctions`, `elasticloadbalancing:DescribeLoadBalancers`). Tighten with resource-level constraints where your org requires it.

Example narrow starter policy (adjust ARNs / tags as needed):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudOpsMCPRead",
      "Effect": "Allow",
      "Action": [
        "sts:GetCallerIdentity",
        "ec2:DescribeInstances",
        "ec2:DescribeSecurityGroups",
        "cloudwatch:DescribeAlarms",
        "s3:ListBuckets",
        "lambda:ListFunctions",
        "elasticloadbalancing:DescribeLoadBalancers"
      ],
      "Resource": "*"
    }
  ]
}
```

Do **not** grant destructive APIs (`TerminateInstances`, `DeleteSecurityGroup`, etc.) unless you intentionally extend this server for remediation workflows.

## Resume framing

Example bullet:

> Built an **AWS CloudOps MCP server** (FastMCP + boto3) exposing guardrail-focused inventory and observability tools (EC2, CloudWatch, ELBv2, Lambda, S3) with documented IAM patterns for assistant-driven operational workflows.

## License

MIT
