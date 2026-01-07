# Phase 0: Validation Plan

**Duration:** Week 1-2
**Goal:** Confirm willingness-to-pay before writing code
**Status:** NOT STARTED

---

## Objective

Validate that enough people will pay for a Dependency Health API before investing 6-8 weeks building it.

**Success = GO:** 100+ email signups AND 3+ "would pay" from interviews
**Failure = NO-GO:** <30 signups OR zero "would pay"

---

## Week 1: Build Validation Assets

### Day 1-2: Name & Domain

| Task | Status | Notes |
|------|--------|-------|
| Brainstorm product names | NOT STARTED | See name ideas below |
| Check domain availability | NOT STARTED | .dev, .io, .com |
| Purchase domain | NOT STARTED | ~$10-15 |
| Set up DNS (Cloudflare) | NOT STARTED | Free |

**Name Ideas:**
- dephealth.dev / dephealth.io
- pkghealth.dev / pkghealth.io
- packagepulse.dev
- depscore.dev
- healthydeps.dev
- depwatch.dev
- pkgsafe.dev

**Criteria:**
- Short and memorable
- Clearly relates to dependencies/packages
- .dev or .io available
- No trademark conflicts

### Day 2-3: Landing Page

| Task | Status | Notes |
|------|--------|-------|
| Choose platform | NOT STARTED | Carrd ($19/yr) or HTML on Vercel (free) |
| Write headline & copy | NOT STARTED | See copy below |
| Create CLI output mockup | NOT STARTED | Terminal screenshot |
| Add email signup form | NOT STARTED | ConvertKit or simple form |
| Deploy and test | NOT STARTED | |

**Landing Page Copy:**

```
HEADLINE:
Know which dependencies will fail before they break your build

SUBHEAD:
Predictive health scores for npm packages. Get warned about
abandonment risk months before it becomes a problem.

VALUE PROPS:
- Health scores for 10,000+ npm packages
- Abandonment risk prediction (6-12 month horizon)
- CLI tool and API for CI/CD integration
- Alerts when your dependencies show warning signs

EXAMPLE OUTPUT:
[CLI screenshot showing package health check]

PRICING TEASER:
Starting at $29/month. Free tier available.

CTA:
[Get Early Access] - Join 0 developers on the waitlist
```

### Day 3-4: Email Setup

| Task | Status | Notes |
|------|--------|-------|
| Create ConvertKit account | NOT STARTED | Free up to 1,000 subscribers |
| Create signup form | NOT STARTED | Embed on landing page |
| Set up welcome email | NOT STARTED | |
| Test full flow | NOT STARTED | |

**Welcome Email:**

```
Subject: You're on the [ProductName] early access list

Hey!

Thanks for signing up for early access to [ProductName].

You're now on the list to be notified when we launch. We're building
an API that predicts which npm packages are at risk of being
abandoned - so you can address problems before they break your build.

Quick question: What's the biggest dependency headache you've
dealt with? Reply to this email - I read every response.

[Your name]

P.S. Know someone who's been burned by an abandoned package?
Forward this to them.
```

### Day 4-5: Community Post Drafts

| Task | Status | Notes |
|------|--------|-------|
| Write HackerNews post | NOT STARTED | "Show HN" style |
| Write Reddit post | NOT STARTED | r/programming, r/node |
| Write Dev.to article | NOT STARTED | Problem-focused |
| Prepare for responses | NOT STARTED | FAQ answers |

**HackerNews Post Draft:**

```
Title: Show HN: I'm building an API to predict npm package abandonment

I've been working on a tool that predicts which npm packages are
at risk of being abandoned before it becomes a problem.

The idea came from getting burned by packages like colors/faker,
and realizing that the warning signs were there months before -
declining commit activity, maintainer burnout signals, etc.

Current tools (Snyk, Dependabot) tell you about known CVEs. But
they can't tell you that a package's sole maintainer hasn't
committed in 6 months and has 50 unanswered issues.

I'm building an API that:
- Tracks 10,000+ npm packages
- Scores them on health signals (commit recency, bus factor,
  issue response time, etc.)
- Predicts abandonment risk on a 6-12 month horizon
- Provides CLI tool and API for CI/CD

Academic research shows this is achievable with 0.846 C-index
accuracy (arXiv:2507.21678).

Would love feedback:
1. Is this something you'd use?
2. What signals would you want to see?
3. Would you pay $29-99/month for this?

Landing page: [URL]
```

---

## Week 2: Validate Demand

### Day 6-7: Post to Communities

| Task | Status | Notes |
|------|--------|-------|
| Post to HackerNews | NOT STARTED | Best: Tue-Thu, 8-10am EST |
| Post to r/programming | NOT STARTED | |
| Post to r/node | NOT STARTED | |
| Post to Dev.to | NOT STARTED | |
| Monitor and respond | NOT STARTED | |

**Engagement Tracking:**

| Platform | Post Date | Upvotes/Comments | Signups | Notes |
|----------|-----------|------------------|---------|-------|
| HackerNews | | | | |
| r/programming | | | | |
| r/node | | | | |
| Dev.to | | | | |

### Day 7-10: Customer Interviews

| Task | Status | Notes |
|------|--------|-------|
| Identify 20 potential interviewees | NOT STARTED | LinkedIn, HN commenters |
| Send outreach messages | NOT STARTED | |
| Schedule 5-10 calls | NOT STARTED | 15-20 min each |
| Conduct interviews | NOT STARTED | |
| Document findings | NOT STARTED | |

**Where to Find Interviewees:**

1. **LinkedIn:**
   - Search: "VP Engineering" + "dependency" in posts
   - Search: "Engineering Manager" + "open source"
   - People who commented on dependency-related content

2. **HackerNews:**
   - Commenters on colors/faker incident threads
   - Commenters on dependency management threads
   - People who posted about tech debt

3. **Twitter/X:**
   - Search: "left-pad" OR "colors faker" OR "dependency hell"
   - Developers who complain about npm

4. **Your Network:**
   - Friends of friends in engineering roles
   - Former colleagues

**Outreach Template:**

```
Subject: Quick question about dependency management

Hi [Name],

I saw your [post/comment] about [dependency topic] and it resonated.

I'm researching the dependency management problem and would love
to hear about your experience. Would you have 15 minutes for a
quick call this week?

I'm not selling anything - just trying to understand the problem
better before building a solution.

Thanks,
[Your name]
```

**Interview Script:**

```
INTRO (2 min):
- Thanks for your time
- I'm researching dependency management problems
- No sales pitch, just learning

PAIN DISCOVERY (5 min):
1. "Tell me about a time a dependency caused you problems"
   - Listen for: specific incidents, time spent, business impact

2. "How do you currently evaluate new dependencies before adding them?"
   - Listen for: process, tools used, gaps

3. "How much time does your team spend on dependency maintenance?"
   - Listen for: quantified time, frequency

SOLUTION VALIDATION (5 min):
4. "What if you could know 6 months early that a package would
    become unmaintained? How would that change things?"
   - Listen for: enthusiasm level, concrete use cases

5. "Would you want this as a one-time check or ongoing monitoring?"
   - Listen for: integration preferences

WILLINGNESS TO PAY (3 min):
6. "If this existed and cost $99/month for your team, would you use it?"
   - Listen for: objections, budget authority, alternatives mentioned

7. "What would make this a must-have vs nice-to-have?"
   - Listen for: specific features, integrations

WRAP UP (2 min):
8. "Anything else about dependency management I should know?"
9. "Can I follow up when we have something to show?"
```

**Interview Log:**

| # | Name | Role | Company Size | Key Pain | Would Pay? | Notes |
|---|------|------|--------------|----------|------------|-------|
| 1 | | | | | | |
| 2 | | | | | | |
| 3 | | | | | | |
| 4 | | | | | | |
| 5 | | | | | | |

### Day 11-14: Analyze & Decide

| Task | Status | Notes |
|------|--------|-------|
| Tally email signups | NOT STARTED | Target: 100+ |
| Count "would pay" responses | NOT STARTED | Target: 3+ |
| Analyze interview themes | NOT STARTED | |
| Document learnings | NOT STARTED | |
| Make GO/NO-GO decision | NOT STARTED | |

---

## GO/NO-GO Decision Framework

### Signals to Evaluate

| Signal | Weight | GO Threshold | Your Result |
|--------|--------|--------------|-------------|
| Email signups | 30% | 100+ | |
| "Would pay" (interviews) | 40% | 3+ of 10 | |
| Community engagement | 20% | High interest | |
| Feature requests | 10% | Specific asks | |

### Decision Matrix

```
                    HIGH SIGNUPS (100+)    LOW SIGNUPS (<30)
                    ┌─────────────────────┬─────────────────────┐
HIGH "WOULD PAY"    │                     │                     │
(3+ of 10)          │    STRONG GO        │   INVESTIGATE       │
                    │                     │   (marketing issue?)│
                    ├─────────────────────┼─────────────────────┤
LOW "WOULD PAY"     │                     │                     │
(0-1 of 10)         │   INVESTIGATE       │    NO-GO            │
                    │   (pricing issue?)  │                     │
                    └─────────────────────┴─────────────────────┘
```

### If GO:

1. Update IMPLEMENTATION_PLAN.md status
2. Begin Phase 1: MVP Build
3. Announce timeline to email list

### If NO-GO:

1. Document learnings in research folder
2. Decide: Pivot product OR return to discovery
3. Update DECISION_LOG.md

---

## Files & Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| Landing page | [URL TBD] | NOT STARTED |
| Email list | ConvertKit | NOT STARTED |
| Interview notes | `work/phase-0-validation/interviews/` | NOT STARTED |
| Community post drafts | `work/phase-0-validation/posts/` | NOT STARTED |
| GO/NO-GO decision | `work/phase-0-validation/DECISION.md` | NOT STARTED |

---

## Session Notes

Track progress here:

### Session: [DATE]
- Completed:
- Blockers:
- Next:

---

*Created: January 7, 2026*
