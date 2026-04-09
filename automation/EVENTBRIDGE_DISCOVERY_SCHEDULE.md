# Automate discovery — EventBridge schedule (IaC)

This replaces the console-only steps in **FULL_SETUP_IN_ORDER.md → Step 12** with a repeatable CloudFormation deploy.

## What it creates (management account, one region)

- **EventBridge rule** — schedule you choose (default `rate(1 day)`)
- **Lambda invoke permission** — allows EventBridge to call **`db-discovery`**

It does **not** create the Lambda, bucket, or spoke roles — only the schedule + permission.

## Prerequisites

- `db-discovery` is already deployed in the **same region** as the stack (EventBridge invokes that regional function ARN).

## Get the Lambda ARN

```bash
aws lambda get-function --function-name db-discovery --query Configuration.FunctionArn --output text
```

Use your management profile / region if needed (`--profile`, `--region`).

## Deploy

From the repo root:

```bash
aws cloudformation deploy \
  --stack-name task02-discovery-schedule \
  --template-file automation/discovery-eventbridge-schedule.yaml \
  --parameter-overrides \
    DiscoveryLambdaArn=arn:aws:lambda:REGION:ACCOUNT_ID:function:db-discovery
```

Add `--profile` and `--region` to match where **`db-discovery`** lives.

### Optional parameters

| Parameter | Example | Purpose |
|-----------|---------|---------|
| `ScheduleExpression` | `cron(0 6 * * ? *)` | Daily 06:00 UTC |
| `ScheduleExpression` | `rate(6 hours)` | Every 6 hours |
| `RuleName` | `db-discovery-inventory-schedule` | Rule name (unique in account+region) |
| `RuleState` | `DISABLED` | Create rule but do not run until you enable it |

Example with cron and disabled until demo week:

```bash
aws cloudformation deploy \
  --stack-name task02-discovery-schedule \
  --template-file automation/discovery-eventbridge-schedule.yaml \
  --parameter-overrides \
    DiscoveryLambdaArn="$LAMBDA_ARN" \
    ScheduleExpression="cron(0 6 * * ? *)" \
    RuleState=DISABLED
```

## Pause or resume without deleting

- **Console:** EventBridge → Rules → your rule → **Disable** / **Enable**
- **CLI:** update stack with `RuleState=DISABLED` or `ENABLED`

## Update schedule only

Redeploy with a new `ScheduleExpression` (same stack name). CloudFormation updates the rule in place.

## Delete

```bash
aws cloudformation delete-stack --stack-name task02-discovery-schedule
```

This removes the rule and the Lambda permission. It does **not** delete **`db-discovery`**.

## Note on other EventBridge rules

Rules like **AutoScalingManagedRule** or **demo_sns** are unrelated to this project — they are AWS or your own event rules, not the discovery schedule. This stack creates a **dedicated** rule whose only target is **`db-discovery`**.
