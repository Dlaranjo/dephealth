# Dependency Health API - Implementation Plan

**Created:** January 7, 2026
**Last Updated:** January 7, 2026
**Status:** Phase 0 - Not Started
**Product:** Dependency Health Intelligence API

---

## Executive Summary

Build an API that predicts which open-source packages are at risk of abandonment or maintenance decline, enabling developers to address dependency issues before they cause problems.

**Timeline:** 12 weeks to launch, 12 months to $5K MRR
**Investment:** ~$200 AWS credits + time
**Kill criteria:** Clear go/no-go checkpoints at each phase

---

## Current Status

```
[■□□□□□□□□□] Phase 0: Validation (Week 1-2)     NOT STARTED
[□□□□□□□□□□] Phase 1: MVP Build (Week 3-8)      NOT STARTED
[□□□□□□□□□□] Phase 2: Launch (Week 9-12)        NOT STARTED
```

**Next Action:** Start Phase 0 - Create landing page

---

## Phase 0: Validate Before Building (Week 1-2)

### Goal
Confirm willingness-to-pay before writing code.

### Deliverables

| # | Task | Status | Notes |
|---|------|--------|-------|
| 0.1 | Choose product name and domain | NOT STARTED | |
| 0.2 | Create landing page | NOT STARTED | Carrd or simple HTML |
| 0.3 | Set up email capture | NOT STARTED | ConvertKit free tier |
| 0.4 | Write "Show HN" post draft | NOT STARTED | |
| 0.5 | Post to HN/Reddit/Dev.to | NOT STARTED | |
| 0.6 | Identify 10 potential customers | NOT STARTED | LinkedIn, HN commenters |
| 0.7 | Conduct 5-10 customer interviews | NOT STARTED | |
| 0.8 | GO/NO-GO decision | NOT STARTED | |

### Landing Page Requirements

```
URL: [TBD].dev or [TBD].io

Content:
- Headline: "Know which dependencies will fail before they break your build"
- Subhead: Predictive health scores for npm, PyPI, and Cargo packages
- Value props (3 bullets)
- Example output (CLI screenshot or mock)
- Pricing teaser ($29-299/month)
- Email signup form
- "Early access" framing
```

### Customer Interview Script

**Find people who:**
- Engineering managers / VPs
- Have posted about dependency issues
- Work at companies with 20-500 developers

**Questions:**
1. "Tell me about a time a dependency caused you problems"
2. "How do you currently evaluate new dependencies?"
3. "How much time does your team spend on dependency maintenance?"
4. "If you could know 6 months early that a package would be abandoned, what would that be worth?"
5. "At $99/month, would your team use this?"

### GO/NO-GO Criteria

| Signal | GO | NO-GO |
|--------|-----|-------|
| Email signups | 100+ | <30 |
| "Would pay" responses | 3+ of 10 interviewed | 0-1 |
| Community engagement | High interest, war stories | "Meh" or "just use X" |

**Decision date:** End of Week 2

---

## Phase 1: MVP Build (Week 3-8)

### Goal
Working API + CLI for npm packages.

### Week 3-4: Data Pipeline

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1.1 | Set up AWS account with credits | NOT STARTED | |
| 1.2 | Create GitHub tokens (5 accounts) | NOT STARTED | For rate limit rotation |
| 1.3 | Set up BigQuery project | NOT STARTED | GH Archive access |
| 1.4 | Build npm metadata collector | NOT STARTED | Top 10K packages |
| 1.5 | Build GitHub metrics collector | NOT STARTED | Commits, issues, PRs |
| 1.6 | Set up DynamoDB for storage | NOT STARTED | |
| 1.7 | Create daily refresh pipeline | NOT STARTED | EventBridge + Lambda |
| 1.8 | Backfill historical data | NOT STARTED | 12 months from GH Archive |

**Deliverable:** Database with health signals for 10K npm packages, updating daily.

### Week 5-6: Scoring Engine

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1.9 | Implement health score algorithm | NOT STARTED | See technical validation doc |
| 1.10 | Implement abandonment risk model | NOT STARTED | Based on academic research |
| 1.11 | Create backtest dataset | NOT STARTED | 30 packages with known outcomes |
| 1.12 | Run backtest, measure accuracy | NOT STARTED | Target: 75%+ |
| 1.13 | Tune weights based on results | NOT STARTED | |
| 1.14 | Add confidence scoring | NOT STARTED | |

**Deliverable:** Scoring model with validated accuracy (target: 75%+).

### Week 7-8: API + CLI

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1.15 | Design API schema | NOT STARTED | OpenAPI spec |
| 1.16 | Build REST API | NOT STARTED | API Gateway + Lambda |
| 1.17 | Implement API key management | NOT STARTED | |
| 1.18 | Add rate limiting | NOT STARTED | By tier |
| 1.19 | Build CLI tool | NOT STARTED | `npx dephealth` |
| 1.20 | Write API documentation | NOT STARTED | |
| 1.21 | Set up Stripe billing | NOT STARTED | |
| 1.22 | Create pricing tiers | NOT STARTED | Free/Starter/Pro/Business |

**Deliverable:** Working product that people can use and pay for.

### Technical Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      DATA COLLECTION                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ GitHub   │    │   npm    │    │ deps.dev │              │
│  │   API    │    │   API    │    │   API    │              │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘              │
│       │               │               │                     │
│       └───────────────┼───────────────┘                     │
│                       ▼                                     │
│              ┌──────────────┐                               │
│              │   Lambda     │                               │
│              │  Collectors  │                               │
│              └──────┬───────┘                               │
│                     │                                       │
│  ┌──────────────────┼──────────────────┐                   │
│  ▼                  ▼                  ▼                   │
│ ┌────┐         ┌─────────┐       ┌──────────┐             │
│ │ S3 │         │DynamoDB │       │ BigQuery │             │
│ │Raw │         │ Scores  │       │ Historical│             │
│ └────┘         └─────────┘       └──────────┘             │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                         API LAYER                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │   CLI    │    │   Web    │    │  CI/CD   │              │
│  │  Tool    │    │ Dashboard│    │ Actions  │              │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘              │
│       │               │               │                     │
│       └───────────────┼───────────────┘                     │
│                       ▼                                     │
│              ┌──────────────┐                               │
│              │ API Gateway  │                               │
│              │   (HTTP)     │                               │
│              └──────┬───────┘                               │
│                     │                                       │
│              ┌──────┴───────┐                               │
│              │   Lambda     │                               │
│              │   Handlers   │                               │
│              └──────┬───────┘                               │
│                     │                                       │
│              ┌──────┴───────┐                               │
│              │  DynamoDB    │                               │
│              │   (Cache)    │                               │
│              └──────────────┘                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Infrastructure Cost Estimate

| Service | MVP (Month 1-3) | Growth (Month 4-6) |
|---------|-----------------|---------------------|
| Lambda | $5-10 | $15-20 |
| API Gateway | $1-5 | $5-10 |
| DynamoDB | $10-20 | $30-50 |
| S3 | $2-5 | $5-10 |
| BigQuery | $0-50 | $50-100 |
| **Total** | **$20-90/mo** | **$105-190/mo** |

---

## Phase 2: Launch & Validate WTP (Week 9-12)

### Goal
Get paying customers and validate the business.

### Week 9: Soft Launch

| # | Task | Status | Notes |
|---|------|--------|-------|
| 2.1 | Announce to email list | NOT STARTED | |
| 2.2 | Post "Show HN" with working product | NOT STARTED | |
| 2.3 | Offer early-bird pricing | NOT STARTED | $19/mo instead of $29 |
| 2.4 | Set up feedback collection | NOT STARTED | |
| 2.5 | Monitor and respond to users | NOT STARTED | |

### Week 10-12: Iterate & Measure

| # | Task | Status | Notes |
|---|------|--------|-------|
| 2.6 | Track key metrics daily | NOT STARTED | |
| 2.7 | Collect user feedback | NOT STARTED | |
| 2.8 | Fix critical bugs | NOT STARTED | |
| 2.9 | Iterate on scoring based on feedback | NOT STARTED | |
| 2.10 | Expand package coverage if needed | NOT STARTED | |
| 2.11 | Build GitHub Action (if demand) | NOT STARTED | |
| 2.12 | Evaluate Month 3 metrics | NOT STARTED | |

### Success Metrics

| Metric | Week 9 | Week 12 | Month 6 | Month 12 |
|--------|--------|---------|---------|----------|
| Free users | 100 | 500 | 1,500 | 4,000 |
| Paid customers | 1 | 5-10 | 35 | 100 |
| MRR | $19 | $150-300 | $2,500 | $8,000 |
| Conversion rate | - | 1-2% | 2-3% | 2.5% |

### Kill Triggers

| Milestone | Target | Kill If |
|-----------|--------|---------|
| Free users (Week 12) | 500 | <100 |
| First paying customer | Week 10 | None by Week 12 |
| MRR (Month 6) | $2,500 | <$500 |
| MRR (Month 12) | $8,000 | <$2,000 |

---

## Post-Launch Roadmap (Month 4-12)

### Month 4-6: Growth Features

| Feature | Priority | Effort |
|---------|----------|--------|
| GitHub Action integration | HIGH | 1 week |
| PyPI ecosystem support | HIGH | 2 weeks |
| Web dashboard | MEDIUM | 2 weeks |
| Slack/Discord alerts | MEDIUM | 1 week |
| Project scanning (bulk) | MEDIUM | 1 week |

### Month 7-9: Expansion

| Feature | Priority | Effort |
|---------|----------|--------|
| Cargo (Rust) support | MEDIUM | 1 week |
| Maven (Java) support | MEDIUM | 2 weeks |
| Team features | MEDIUM | 2 weeks |
| Historical trending | LOW | 1 week |

### Month 10-12: Scale

| Feature | Priority | Effort |
|---------|----------|--------|
| Enterprise tier | IF DEMAND | 2 weeks |
| VS Code extension | LOW | Community |
| SBOM integration | LOW | 1 week |
| SOC2 prep | IF ENTERPRISE | Ongoing |

---

## Key Decisions Log

Track important decisions made during implementation.

| Date | Decision | Rationale | Revisit |
|------|----------|-----------|---------|
| 2026-01-07 | Selected Dependency Health API | Strongest moat (8/10), no direct competitor | - |
| | | | |

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| WTP doesn't materialize | 40% | HIGH | Phase 0 validation, kill triggers |
| GitHub API restrictions | 10% | HIGH | Multiple tokens, GH Archive fallback |
| Scoring accuracy <70% | 20% | HIGH | Iterate on model, publish methodology |
| Competitor fast-follow | 25% | MEDIUM | Move fast, build data moat |
| Solo founder burnout | 30% | MEDIUM | Ruthless prioritization, automation |

---

## Resources

### Key Documents

| Document | Location |
|----------|----------|
| Product Overview | `research/product/dependency-health-api/README.md` |
| Technical Validation | `research/product/dependency-health-api/technical/` |
| Market Validation | `research/product/dependency-health-api/market/` |
| Discovery Decision | `research/discovery-archive/DECISION.md` |

### External References

| Resource | URL |
|----------|-----|
| GitHub API Docs | https://docs.github.com/en/rest |
| GH Archive | https://www.gharchive.org/ |
| deps.dev API | https://docs.deps.dev/api/v3/ |
| OpenSSF Scorecard | https://scorecard.dev/ |
| Academic Research | arXiv:2507.21678 |

---

## Session Notes

Use this section to track progress across sessions.

### Session: [DATE]
- What was accomplished:
- Blockers encountered:
- Next session priorities:

---

*Plan created: January 7, 2026*
*Last updated: January 7, 2026*
