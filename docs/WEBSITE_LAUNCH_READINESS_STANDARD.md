# Website Launch Readiness Standard

**Version:** 1.0  
**Applies to:** Public websites and web applications, including AI/vibe-coded projects.  
**Release rule:** No launch without evidence-backed verification or an explicitly accepted exception.

## Operating principles
1. Audit before changing code. Report findings before implementing fixes.
2. Verify behavior, not merely the presence of code.
3. Use statuses consistently: **PASS**, **FAIL**, **PARTIAL**, **BLOCKED**, **N/A**.
4. BLOCKED never counts as PASS. N/A requires a reason.
5. Never invent business facts, structured-data values, analytics results, delivery confirmations, or Search Console status.
6. Never expose secrets or personal data in audit output.
7. Test in a branch/staging environment first. Do not alter production, DNS, external accounts, or live data without approval.
8. Re-run affected checks and regression tests after changes.

## Mandatory checks
| ID | Check | Acceptance criteria |
|---|---|---|
| WLS-01 | SSR/prerendering | Important public content is crawlable in initial HTML or verified through an appropriate rendering strategy. SSR is not mandatory when static prerendering is suitable. |
| WLS-02 | robots.txt | Accessible, syntactically reasonable, and does not unintentionally block public pages or required assets. |
| WLS-03 | sitemap.xml | Valid, accessible, contains canonical/indexable URLs, and excludes unsuitable URLs. |
| WLS-04 | Unique title tags | Every indexable page has a descriptive title unique within the site. |
| WLS-05 | Meta descriptions | Appropriate descriptions exist and are not unintentionally duplicated. |
| WLS-06 | H1 | Each applicable page has a clear primary H1; missing or multiple H1s are reviewed. |
| WLS-07 | Canonical tags | Absolute canonical URLs are correct and consistent with redirects and indexability. |
| WLS-08 | Open Graph | Appropriate og:title, og:description, og:image, and og:url are present; share image is reachable. |
| WLS-09 | 404 handling | Unknown URLs return HTTP 404 and a useful error page, not a misleading 200. |
| WLS-10 | 301 redirects | Required permanent redirects work; no loops, unnecessary chains, or unrelated destinations. |
| WLS-11 | Image alt text | Meaningful images have useful alt text; decorative images use empty alt text. |
| WLS-12 | Image optimization | Use WebP/AVIF or another appropriate optimized format where beneficial; check dimensions, responsive variants, and quality. |
| WLS-13 | Lazy loading | Below-the-fold images/embeds are lazy-loaded where appropriate; do not lazy-load the LCP/hero image unnecessarily. |
| WLS-14 | Organization schema | Valid JSON-LD uses verified business facts and appropriate schema properties. |
| WLS-15 | Breadcrumbs | Nested pages have useful visible breadcrumbs and appropriate BreadcrumbList structured data where applicable. |
| WLS-16 | Internal links | Important pages are reachable; broken links, incorrect destinations, and orphan pages are reviewed. |
| WLS-17 | Google Analytics | GA4 is configured and event delivery is verified; check duplicate tags and relevant conversions. |
| WLS-18 | Search Console | Verification and sitemap submission are confirmed when authorized access is available; otherwise provide a manual action. |
| WLS-19 | Privacy policy | Policy accurately reflects real collection, cookies, analytics, processors, retention, and applicable obligations. |
| WLS-20 | Contact form | Validation, backend processing, success/error states, spam controls, and actual delivery are tested. A UI success message alone is insufficient. |

## Additional release checks
- HTTPS, certificate validity, and mixed content.
- Mobile layout, accessibility basics, keyboard operation, labels, focus, and contrast.
- Core Web Vitals using field data when available; Lighthouse is diagnostic, not field data.
- Broken images, console errors, failed API calls, and missing assets.
- Authentication/authorization boundaries, secret exposure, debug endpoints, and sensitive data.
- Deployment health, backups, and rollback readiness.
- Functional tests for critical user journeys.

## Priority definitions
- **P0:** Critical security/privacy issue, data loss, or production outage.
- **P1:** Launch blocker, indexing blocker, broken lead capture, or core journey failure.
- **P2:** Important SEO, performance, accessibility, or usability defect.
- **P3:** Optional refinement.

## Required audit report
For every check, report: ID, status, evidence, affected URL/component, risk, recommended fix, and any access needed. Distinguish static code inspection from live verification. Include totals by status, unresolved failures, blocked checks, accepted exceptions, and manual actions.

The release recommendation must be exactly one of:
- **READY TO LAUNCH**
- **READY WITH ACCEPTED EXCEPTIONS**
- **NOT READY TO LAUNCH**

A check passes only when sufficient evidence supports the result. The audit tool is a triage aid; human review and authorized third-party verification remain necessary for analytics, Search Console, privacy/legal review, and real message delivery.
