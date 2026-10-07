# Publish G5 only after the other developer finishes and integrates G2.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)

$issueJson = gh api repos/Wcno/hackiaton-whoamisfc/issues/20
if ($LASTEXITCODE -ne 0) { throw 'Unable to verify G2 issue #20.' }
$issue = $issueJson | ConvertFrom-Json
$pullJson = gh api repos/Wcno/hackiaton-whoamisfc/pulls/32
if ($LASTEXITCODE -ne 0) { throw 'Unable to verify G2 PR #32.' }
$pullRequest = $pullJson | ConvertFrom-Json
if ($issue.state -ne 'closed' -or $issue.state_reason -ne 'completed') {
    throw 'G2 issue #20 is not completed. No push was sent.'
}
if (-not $pullRequest.merged -or $pullRequest.user.login -ne 'NoSkill007') {
    throw 'The other developer has not integrated G2 PR #32. No push was sent.'
}

$branchName = git branch --show-current
if ($LASTEXITCODE -ne 0 -or $branchName -ne 'feat/g5-backend') { throw 'Run this from feat/g5-backend.' }
$workingChanges = git status --porcelain
if ($workingChanges) { throw 'Commit the reviewed changes before publishing.' }
git fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Unable to update origin refs.' }
git merge-base --is-ancestor origin/prod HEAD
if ($LASTEXITCODE -ne 0) { throw 'Integrate origin/prod and review the final diff before publishing.' }
git merge-base --is-ancestor $pullRequest.merge_commit_sha HEAD
if ($LASTEXITCODE -ne 0) { throw 'The final G2 merge is missing from this branch.' }
uv run --locked pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed. No push was sent.' }
git push -u origin feat/g5-backend
if ($LASTEXITCODE -ne 0) { throw 'Push failed.' }
