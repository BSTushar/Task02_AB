# Recreate task02-spoke-bootstrap with the current template (PrimaryRegionForIam fix).
# Run from repo root in PowerShell. Requires AWS CLI + credentials for management account.
#
# SERVICE_MANAGED StackSets: targeted deletes must use OU + Accounts + AccountFilterType=INTERSECTION
# (Accounts= alone causes ValidationError).
#
# Usage:
#   .\automation\recreate-stackset.ps1
# Optional:
#   .\automation\recreate-stackset.ps1 -BucketName "my-db-discovery-bucket"

param(
    [string] $StackSetName = "task02-spoke-bootstrap",
    [string] $ManagementAccountId = "587010590580",
    [string] $BucketName = "my-db-discovery-bucket",
    [string] $PrimaryRegionForIam = "ap-south-1",
    [string[]] $Regions = @("ap-south-1", "eu-west-1"),
    [string] $OrganizationalUnitId = "r-cmha",
    [string[]] $SuspendedAccountsRetainOnly = @("281136219844", "720546261655"),
    # DEMOR1 / DEMOR2 / DEMOR3 (replace when spokes change)
    [string[]] $ActiveSpokeAccounts = @("987213268214", "349865003021", "599657398371")
)

$ErrorActionPreference = "Stop"

function Wait-StackSetIdle {
    param([string]$Name)
    do {
        $ops = aws cloudformation list-stack-set-operations --stack-set-name $Name --max-items 1 --query "Summaries[0].{Id:OperationId,Status:Status,Action:Action}" --output json 2>$null | ConvertFrom-Json
        if ($null -ne $ops -and $ops.Status -eq "RUNNING") {
            Write-Host "Waiting for StackSet operation $($ops.Id) ($($ops.Action)) ..."
            Start-Sleep -Seconds 20
        } else {
            break
        }
    } while ($true)
}

Write-Host "==> Waiting for any in-flight StackSet operations on $StackSetName ..."
Wait-StackSetIdle -Name $StackSetName

$exists = $false
try {
    aws cloudformation describe-stack-set --stack-set-name $StackSetName --query "StackSet.StackSetName" --output text 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $exists = $true }
} catch { $exists = $false }

# Targets for SERVICE_MANAGED: OU + account list + INTERSECTION
function Remove-StackInstancesForAccounts {
    param(
        [string[]]$AccountIds,
        [bool] $RetainStacks
    )
    $acctList = $AccountIds -join ","
    $retainArg = if ($RetainStacks) { "--retain-stacks" } else { "--no-retain-stacks" }
    Write-Host "==> Delete stack instances (OU=$OrganizationalUnitId, accounts=$acctList, retain=$RetainStacks) ..."
    aws cloudformation delete-stack-instances `
        --stack-set-name $StackSetName `
        --deployment-targets "OrganizationalUnitIds=$OrganizationalUnitId,Accounts=$acctList,AccountFilterType=INTERSECTION" `
        --regions $Regions `
        $retainArg `
        --operation-preferences "FailureToleranceCount=1,MaxConcurrentCount=2"
    Wait-StackSetIdle -Name $StackSetName
}

if ($exists) {
    if ($SuspendedAccountsRetainOnly.Count -gt 0) {
        Write-Host "==> Removing suspended-account instances from StackSet (retain stacks in AWS) ..."
        Remove-StackInstancesForAccounts -AccountIds $SuspendedAccountsRetainOnly -RetainStacks $true
    }

    Write-Host "==> Deleting stack instances for active spokes (delete stacks in those accounts) ..."
    Remove-StackInstancesForAccounts -AccountIds $ActiveSpokeAccounts -RetainStacks $false

    # Root OU includes the management account; StackSet instances must all be removed before delete-stack-set.
    Write-Host "==> Deleting stack instances for management account $ManagementAccountId (if present) ..."
    Remove-StackInstancesForAccounts -AccountIds @($ManagementAccountId) -RetainStacks $false

    Write-Host "==> Purging any remaining stack instances reported by list-stack-instances ..."
    $raw = aws cloudformation list-stack-instances --stack-set-name $StackSetName --query "Summaries[].Account" --output text 2>$null
    if ($raw) {
        $stillThere = ($raw -split "\s+") | Where-Object { $_ } | Sort-Object -Unique
        if ($stillThere.Count -gt 0) {
            Write-Host "    Remaining account IDs: $($stillThere -join ', ')"
            Remove-StackInstancesForAccounts -AccountIds $stillThere -RetainStacks $false
        }
    }

    Write-Host "==> Deleting stack set $StackSetName ..."
    aws cloudformation delete-stack-set --stack-set-name $StackSetName
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARN: delete-stack-set failed. List instances with:"
        Write-Host "  aws cloudformation list-stack-instances --stack-set-name $StackSetName"
        exit 1
    }
    Start-Sleep -Seconds 5
} else {
    Write-Host "Stack set $StackSetName not found - will create fresh."
}

$templatePath = Join-Path $PSScriptRoot "spoke-bootstrap-stackset.yaml"
if (-not (Test-Path $templatePath)) {
    throw "Template not found: $templatePath"
}

Write-Host "==> Creating stack set $StackSetName ..."
aws cloudformation create-stack-set `
    --stack-set-name $StackSetName `
    --template-body "file://$templatePath" `
    --permission-model SERVICE_MANAGED `
    --auto-deployment "Enabled=true,RetainStacksOnAccountRemoval=true" `
    --capabilities CAPABILITY_NAMED_IAM `
    --parameters `
        "ParameterKey=ManagementAccountId,ParameterValue=$ManagementAccountId" `
        "ParameterKey=BucketName,ParameterValue=$BucketName" `
        "ParameterKey=PrimaryRegionForIam,ParameterValue=$PrimaryRegionForIam" `
        "ParameterKey=SpokeRoleName,ParameterValue=DBDiscoverySpokeRole" `
        "ParameterKey=Ec2RoleName,ParameterValue=EC2-SSM-Discovery-Role" `
        "ParameterKey=Ec2InstanceProfileName,ParameterValue=EC2-SSM-Discovery-InstanceProfile" `
        "ParameterKey=SsmDocumentName,ParameterValue=DBDiscovery" `
        "ParameterKey=ScriptS3Key,ParameterValue=ssm/discovery_python.py"

if ($LASTEXITCODE -ne 0) {
    Write-Host "==> create-stack-set failed (name may already exist). Trying update-stack-set with new template ..."
    aws cloudformation update-stack-set `
        --stack-set-name $StackSetName `
        --template-body "file://$templatePath" `
        --capabilities CAPABILITY_NAMED_IAM `
        --parameters `
            "ParameterKey=ManagementAccountId,ParameterValue=$ManagementAccountId" `
            "ParameterKey=BucketName,ParameterValue=$BucketName" `
            "ParameterKey=PrimaryRegionForIam,ParameterValue=$PrimaryRegionForIam" `
            "ParameterKey=SpokeRoleName,ParameterValue=DBDiscoverySpokeRole" `
            "ParameterKey=Ec2RoleName,ParameterValue=EC2-SSM-Discovery-Role" `
            "ParameterKey=Ec2InstanceProfileName,ParameterValue=EC2-SSM-Discovery-InstanceProfile" `
            "ParameterKey=SsmDocumentName,ParameterValue=DBDiscovery" `
            "ParameterKey=ScriptS3Key,ParameterValue=ssm/discovery_python.py"
    Wait-StackSetIdle -Name $StackSetName
}

$deployTargets = "OrganizationalUnitIds=$OrganizationalUnitId"
Write-Host "==> Deploying to $deployTargets in regions $($Regions -join ', ') ..."
aws cloudformation create-stack-instances `
    --stack-set-name $StackSetName `
    --deployment-targets $deployTargets `
    --regions $Regions `
    --operation-preferences "FailureToleranceCount=0,MaxConcurrentCount=1"

Write-Host 'Done. Watch Operations in the console until SUCCEEDED.'
