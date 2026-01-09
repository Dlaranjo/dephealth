# PR Merge Coordination Plan (v2 - Agent Reviewed)

## Executive Summary

15 PRs created by specialized agents have been analyzed by 6 opus-explorer review agents. This document provides the **definitive merge strategy** based on their findings.

**Total Conflicts Identified:** 12 semantic + 8 textual
**Estimated Resolution Effort:** Medium-High
**Recommended Approach:** 6-wave sequential merge with manual conflict resolution

---

## Critical Conflict Summary

### MUST-DECIDE ISSUES

| Issue | Conflicting PRs | Decision Required |
|-------|-----------------|-------------------|
| `magic-token-index` GSI projection | #2, #5, #9 | **Use INCLUDE (PR #5)** - richer data for auth |
| `error_response()` retry_after | #4, #6 | **Use PR #4** - PR #6 superseded |
| `metrics.py` implementation | #13, #14 | **Use PR #13** - has `emit_batch_metrics()` |
| `classify_error()` patterns | #13, #14 | **Merge both pattern lists** |
| HTTP client pattern | #7, #15 | **Use PR #15** - connection pooling |

---

## Definitive Merge Order (6 Waves)

### WAVE 1: Zero-Conflict PRs
**Status:** VERIFIED SAFE by opus agent

| PR | Agent | Focus | Risk |
|----|-------|-------|------|
| **#11** | 8 | Testing (DLQ) | NONE |
| **#12** | 11 | Landing Page | NONE |
| **#3** | 6 | CLI/Action UX | NONE |

**Note:** All 3 PRs add identical `PRODUCT_REVIEW.md` and `agent-prompts/*` files. Git handles this cleanly.

```bash
gh pr merge 11 --squash
gh pr merge 12 --squash
gh pr merge 3 --squash
```

---

### WAVE 2: Infrastructure Foundation

| Order | PR | Agent | Focus | Dependencies |
|-------|-----|-------|-------|--------------|
| 1 | **#1** | 4 | AWS Infrastructure | None |
| 2 | **#2** | 5 | DynamoDB Schema | #1 |

**PR #1 Changes:**
- `pointInTimeRecoverySpecification` syntax (cosmetic)
- S3 lifecycle 30→7 days (cost optimization)

**PR #2 Changes:**
- TTL attribute on API Keys table
- `magic-token-index` GSI (KEYS_ONLY)
- Packages table GSIs

**Conflict Resolution for PR #2:**
After merging #1, rebase #2. Accept the `pointInTimeRecoverySpecification` syntax from #1.

---

### WAVE 3: Security Critical

| Order | PR | Agent | Focus | Conflicts |
|-------|-----|-------|-------|-----------|
| 3 | **#9** | 15 | Critical Fixes | storage-stack.ts, conftest.py |
| 4 | **#5** | 1 | Security | Same files + API endpoints |

**Critical Decision:** `magic-token-index` projection

Both PRs add the same GSI with different projections:
- PR #9: `KEYS_ONLY` (minimal)
- PR #5: `INCLUDE` with `["email", "magic_expires", "tier"]`

**USE PR #5's version** - authentication needs email/expiry without secondary query.

**Conflict Resolution:**
```typescript
// Final magic-token-index definition (from PR #5):
this.apiKeysTable.addGlobalSecondaryIndex({
  indexName: "magic-token-index",
  partitionKey: { name: "magic_token", type: dynamodb.AttributeType.STRING },
  projectionType: dynamodb.ProjectionType.INCLUDE,
  nonKeyAttributes: ["email", "magic_expires", "tier"],
});
```

---

### WAVE 4: Code Quality & API Design

| Order | PR | Agent | Focus | Notes |
|-------|-----|-------|-------|-------|
| 5 | **#4** | 12 | Code Quality | Shared utilities base |
| 6 | **#6** | 2 | API Design | **PARTIAL MERGE** |

**PR #4 establishes:**
- `dynamo.py` logging
- `response_utils.py` refactor + `retry_after` parameter
- Shared constants

**PR #6 superseded for:**
- `response_utils.py` (PR #4 has same changes + more)

**PR #6 unique changes to keep:**
- `docs/openapi.yaml`
- `docs/api-versioning.md`
- API endpoint consistency improvements

**Action:**
1. Merge PR #4 first
2. Rebase PR #6, remove `response_utils.py` changes
3. Merge PR #6 remaining changes

---

### WAVE 5: Backend Logic (Complex Conflicts)

| Order | PR | Agent | Focus | Conflict Level |
|-------|-----|-------|-------|----------------|
| 7 | **#15** | 7 | Performance | HIGH (foundational patterns) |
| 8 | **#7** | 3 | Scoring | LOW |
| 9 | **#13** | 13 | Data Pipeline | MEDIUM |
| 10 | **#14** | 9 | Error Handling | MEDIUM |
| 11 | **#10** | 10 | Rate Limiting | MEDIUM |

**PR #15 MUST MERGE FIRST** - establishes:
- Lazy boto3 initialization pattern
- HTTP connection pooling
- Relative imports

All subsequent PRs (#7, #13, #14, #10) need rebasing to use new patterns.

**metrics.py Conflict (PR #13 vs #14):**
- PR #13 has `emit_batch_metrics()` - REQUIRED by its own code
- PR #14 has helper functions (unused)
- **Merge PR #13 first**, then add PR #14's helpers

**classify_error() Conflict (PR #13 vs #14):**
Both add similar error classification. Merge pattern lists:
```python
TRANSIENT_ERRORS = [
    "timeout", "timed out", "connection reset", "connection refused",
    "503", "502", "504", "rate limit", "too many requests",
    "temporarily unavailable", "service unavailable", "connection", "unavailable"
]
PERMANENT_ERRORS = [
    "404", "not found", "does not exist", "invalid package",
    "malformed", "forbidden", "unauthorized", "validation_error",
    "Invalid package name"
]
```

**github_collector.py Conflict (PR #7 vs #15):**
- PR #15: HTTP pooling pattern
- PR #7: New metrics (bot filtering, issue response time)
- **Merge #15 first**, then rebase #7 to use shared HTTP client

**Field name warning in PR #15:**
PR #15 renames `days_since_last_commit` → `days_since_commit`
**REVERT** this change during merge (breaking downstream).

---

### WAVE 6: Documentation (Last)

| Order | PR | Agent | Focus |
|-------|-----|-------|-------|
| 12 | **#8** | 14 | Documentation |

**Contains:**
- `docs/openapi.yaml` (conflict with PR #6)
- `CHANGELOG.md`
- `CONTRIBUTING.md`
- Component READMEs

**Merge last** - can update docs to reflect final merged state.

---

## File-by-File Conflict Resolution

### infrastructure/lib/storage-stack.ts

**Touched by:** PRs #1, #2, #5, #9

**Final state after all merges:**
```typescript
this.apiKeysTable = new dynamodb.Table(this, "ApiKeysTable", {
  tableName: "dephealth-api-keys",
  partitionKey: { name: "pk", type: dynamodb.AttributeType.STRING },
  sortKey: { name: "sk", type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
  pointInTimeRecoverySpecification: {     // From PR #1
    pointInTimeRecoveryEnabled: true,
  },
  timeToLiveAttribute: "ttl",             // From PRs #2/#5/#9
  removalPolicy: cdk.RemovalPolicy.RETAIN,
});

// Use PR #5's INCLUDE projection
this.apiKeysTable.addGlobalSecondaryIndex({
  indexName: "magic-token-index",
  partitionKey: { name: "magic_token", type: dynamodb.AttributeType.STRING },
  projectionType: dynamodb.ProjectionType.INCLUDE,
  nonKeyAttributes: ["email", "magic_expires", "tier"],
});
```

### functions/api/create_api_key.py

**Touched by:** PRs #5, #6, #9, #10

**Merge order:** #9 → #5 → #6 → #10

**Key changes to preserve:**
- Atomic key count limiting (from #9 or #10)
- Response formatting (from #6)
- Security validation (from #5)

### functions/collectors/package_collector.py

**Touched by:** PRs #10, #13, #15

**Merge order:** #15 → #13 → #10

**After PR #15, all functions must use:**
```python
table = get_packages_table()  # Not dynamodb.Table(PACKAGES_TABLE)
```

### tests/conftest.py

**Touched by:** PRs #2, #5, #9

**Merge order:** #5 → #9 → #2

**Key resolution:** Use PR #5's INCLUDE projection for magic-token-index

---

## Execution Commands

### Phase 1: Wave 1 (Immediate)
```bash
cd /home/iebt/projects/startup-experiment/work/dephealth
gh pr merge 11 --squash -t "Add comprehensive DLQ processor tests"
gh pr merge 12 --squash -t "Implement landing page improvements"
gh pr merge 3 --squash -t "Implement CLI and GitHub Action UX improvements"
git pull origin main
```

### Phase 2-6: Pattern for Each PR
```bash
# For each PR in order:
gh pr checkout <PR_NUMBER>
git fetch origin main
git rebase origin/main
# Resolve conflicts per this document
git push --force-with-lease
gh pr merge <PR_NUMBER> --squash
git checkout main && git pull
```

---

## Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Semantic conflict in error classification | High | Medium | Use merged pattern lists |
| Breaking change in field rename | Medium | High | Revert `days_since_commit` rename |
| Test fixture shadowing | Medium | Medium | Remove local fixture in PR #13 |
| API signature incompatibility | Low | High | Verify callers use positional args |

---

## Post-Merge Verification

```bash
# After all merges:
cd /home/iebt/projects/startup-experiment/work/dephealth

# 1. Run tests
cd functions && pytest -v

# 2. Lint
ruff check functions/

# 3. Build all clients
cd ../cli && npm run build
cd ../action && npm run build

# 4. Verify infrastructure
cd ../infrastructure && cdk synth

# 5. Build landing page
cd ../landing-page && npm run build
```

---

## Status Tracker

| Wave | PR | Status | Notes |
|------|-----|--------|-------|
| 1 | #11 | PENDING | |
| 1 | #12 | PENDING | |
| 1 | #3 | PENDING | |
| 2 | #1 | PENDING | |
| 2 | #2 | PENDING | Rebase after #1 |
| 3 | #9 | PENDING | |
| 3 | #5 | PENDING | Keep INCLUDE projection |
| 4 | #4 | PENDING | |
| 4 | #6 | PENDING | Remove response_utils.py |
| 5 | #15 | PENDING | FIRST in wave |
| 5 | #7 | PENDING | Rebase after #15 |
| 5 | #13 | PENDING | |
| 5 | #14 | PENDING | |
| 5 | #10 | PENDING | |
| 6 | #8 | PENDING | Last |
