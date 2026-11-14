# UFHOB CORE — AGENT OPERATING INSTRUCTIONS

## 1. PROJECT IDENTITY

This repository is:

UFHOB Core

Project path:

C:\Users\HP\PycharmProjects\ufhob-core

UFHOB is a university management platform derived from the former ESFÉ Core architecture.

IMPORTANT:

UFHOB is NOT ESFÉ.

The project was cloned from ESFÉ because the existing platform already contains mature business engines for:

- admissions;
- registrations;
- payments;
- students;
- academic management;
- courses;
- evaluations;
- grades;
- dashboards;
- staff management;
- finance;
- communication;
- administration.

The objective is NOT to rewrite these engines.

The objective is to progressively extend them so they can operate correctly in a university composed of multiple Schools and multiple physical Campuses/Branches.

---

# 2. ABSOLUTE REPOSITORY ISOLATION

Work ONLY inside:

C:\Users\HP\PycharmProjects\ufhob-core

Never modify:

C:\Users\HP\PycharmProjects\esfe-core

The original ESFÉ project must remain untouched.

UFHOB database:

ufhob_db

Original ESFÉ database:

esfe_db

NEVER write UFHOB migrations, data, bootstrap data, test data, or operational data into:

esfe_db

Never run UFHOB migration commands against esfe_db.

Never intentionally modify esfe_db.

If database targeting is uncertain, verify it BEFORE performing any mutating operation.

---

# 3. PYTHON ENVIRONMENT

UFHOB has its own virtual environment.

Expected interpreter:

C:\Users\HP\PycharmProjects\ufhob-core\.venv\Scripts\python.exe

The project currently targets Python 3.14.

Do not use the ESFÉ virtual environment.

Do not install project dependencies globally.

Use:

python -m pip ...

from the UFHOB virtual environment.

Before environment-sensitive work, verify:

- current working directory;
- sys.executable;
- Python version;
- active virtual environment;
- Django settings;
- database target.

---

# 4. DATABASE PRINCIPLE

UFHOB uses one main PostgreSQL database.

Current application database:

ufhob_db

Do NOT create one database per School.

Do NOT create one schema per School.

Do NOT introduce multi-tenant database architecture.

The university is one institution.

Schools are organizational and academic components inside the same university platform.

---

# 5. CORE ARCHITECTURAL PRINCIPLE

The fundamental architecture is:

    UNIVERSITY
        ↓
    SCHOOL
        ↓
    SCHOOLBRANCH
        ↓
    BRANCH / CAMPUS
        ↓
    PROGRAMME
        ↓
    ACADEMIC STRUCTURES
        ↓
    BUSINESS WORKFLOWS

More precisely:

UFHOB
→ Schools
→ Campus/Branches
→ Programmes
→ Levels
→ Classes
→ UE
→ EC
→ Courses
→ Evaluations
→ Grades
→ Academic history

Existing business engines must remain shared.

Do NOT build separate applications for each School.

---

# 6. SCHOOL MODEL

A School represents an academic component of UFHOB.

Known School codes currently include:

- ESMED
- ESGA
- FATEC

IMPORTANT:

Do not invent long official School names unless they already exist in the repository or are explicitly provided by the user.

School names and presentation data should remain configurable.

A Programme belongs to a School.

Example:

Medicine
→ ESMED

Pharmacy
→ ESMED

Dental Surgery
→ ESMED

Other programmes may belong to ESGA or FATEC.

---

# 7. BRANCH MODEL

Branch represents a physical Campus or Annex.

Branch is NOT the same thing as School.

School answers:

"Which academic component?"

Branch answers:

"Which physical location?"

These dimensions must remain separate.

A single Campus may host multiple Schools.

A single School may operate on multiple Campuses.

Therefore:

DO NOT model:

Branch → one School only.

---

# 8. SCHOOLBRANCH

SchoolBranch is the association between:

School
+
Branch

This relationship is intentionally many-to-many.

Example:

Campus Bamako may host:

- ESMED
- ESGA
- FATEC

Another Campus may host:

- ESMED only

Another Campus may host:

- ESGA + FATEC

This architecture must be preserved.

Do not replace SchoolBranch with a single school_id on Branch.

---

# 9. PROGRAMME AVAILABILITY RULE

A Programme belongs to a School.

A Programme may only be offered on a Branch where its School exists through SchoolBranch.

Conceptually:

Programme.school = ESMED

Branch = Campus X

For that Programme to be available on Campus X:

SchoolBranch(
    school=ESMED,
    branch=Campus X
)

must exist.

This is a business rule, not merely a frontend filter.

Whenever implementation work touches programme availability, registration, admission, academic offering, or Campus assignment, preserve this rule.

---

# 10. SOURCE OF TRUTH PRINCIPLE

Avoid redundant foreign keys.

Before adding a field, ask:

"Can this information already be derived reliably from an existing relationship?"

Example:

Class
→ Programme
→ School

If School is already unambiguously derivable through Programme, do not automatically add:

Class.school

Likewise:

Admission
→ Programme
→ School

may be preferable to duplicating:

Admission.school

Avoid parallel sources of truth.

Prefer normalized relationships.

---

# 11. ACCESS CONTEXT

UFHOB must support contextual access.

The main dimensions are:

- University-wide;
- School;
- Branch;
- School + Branch.

Roles and scope are different concepts.

ROLE answers:

"What is the user allowed to do?"

ACCESS CONTEXT answers:

"Where and for which academic structure may the user do it?"

Example:

ROLE:
Director of Studies

CONTEXT:
School = ESMED
Branch = Campus Bamako

That user should work as Director of Studies for:

ESMED + Campus Bamako

and must not automatically see ESGA data from the same Campus.

---

# 12. GLOBAL UNIVERSITY USERS

Some users may have university-wide access.

Examples may include:

- Director General;
- Deputy Director General;
- super administrators;
- selected central administrators.

These users may legitimately see multiple Schools and multiple Branches.

Do not artificially force every user to one School.

Do not implement global access through repeated ad-hoc:

if user.is_superuser

checks across the application.

Prefer the existing role/permission/context architecture.

---

# 13. SCHOOL-LEVEL USERS

A user may be scoped to one School while covering multiple Campuses.

Example:

School-level academic administrator for ESMED.

Such a user may see ESMED information across authorized Branches but should not automatically see ESGA or FATEC information.

---

# 14. BRANCH-LEVEL USERS

A user may operate primarily on one physical Branch.

However, Branch-only scoping may not always be sufficient in UFHOB.

If a Campus hosts several Schools, users may need:

School + Branch

context.

Never assume:

same Branch = same academic access.

---

# 15. USERS, STAFF AND PROFILES

Do not create a second user system.

Reuse existing:

- User;
- profile models;
- staff models;
- positions;
- roles;
- assignments;
- AccessContext;
- permission helpers.

Extend the current architecture when needed.

Do not create UFHOB-specific duplicate authentication systems.

Do not duplicate dashboards by School.

---

# 16. DASHBOARD PRINCIPLE

UFHOB uses the existing unified dashboard architecture.

Do NOT create:

- ESMED Director Dashboard;
- ESGA Director Dashboard;
- FATEC Director Dashboard;

as separate dashboard systems.

Use the existing role dashboards and inject the appropriate contextual data.

The application should behave as:

same dashboard shell
+
same business engine
+
different access context.

---

# 17. DASHBOARD SHELL

The project already contains a shared DashboardShell/UI architecture.

Preserve it.

Do not redesign it unless explicitly requested.

Do not introduce role-specific shell duplication.

Do not rebuild navigation architecture during backend/domain work.

---

# 18. UI CORE

The existing UI Core architecture contains shared behavior such as:

- HTMX lifecycle handling;
- notifications;
- toasts;
- loading indicators;
- drawers;
- modals;
- refresh/invalidation mechanisms;
- shared navigation behavior.

Do not replace this architecture during backend missions.

Fix shared behavior globally when needed.

Avoid isolated role-specific UI hacks.

---

# 19. BUSINESS ENGINES TO PRESERVE

The following existing engines are valuable and should be extended rather than rewritten:

Admissions

Registration / Enrollment

Payments

Students

Academic structure

Academic years

Semesters

Classes

UE / EC

Course management

Course Studio

Student Course Workspace

Assessments

Grades

Remedial sessions

Academic results

Timetables

Communications

Notifications

Secretary workflows

Manager workflows

Director workflows

Finance

Human Resources

Reporting

---

# 20. ADMISSIONS

Admissions remain one shared UFHOB engine.

Do not create separate admission engines per School.

A future application may select:

Academic Year
→ School
→ Programme
→ Branch

but the underlying admission workflow remains unified.

Whenever School is already derivable from Programme, avoid unnecessary duplicated school fields unless a genuine historical/business need exists.

---

# 21. REGISTRATION / ENROLLMENT

Registration remains one shared engine.

Registrations must remain historically traceable.

A student's academic history may include changes in:

- Academic Year;
- Programme;
- Level;
- Branch;
- potentially School through Programme changes.

Do not place all historical truth only in a user profile.

Use the existing academic registration/enrollment history.

---

# 22. STUDENTS

Students belong to the university.

Their academic context is defined through their academic records.

A student may change:

- Programme;
- Level;
- Branch;
- Academic Year.

Therefore, avoid overly static modelling such as placing every academic truth directly on the User model.

Use historical registration/enrollment structures.

---

# 23. TEACHERS

Teachers may potentially teach:

- multiple Programmes;
- multiple Schools;
- multiple Branches.

Do not automatically force Teacher → one School if pedagogical assignments already represent the actual teaching scope.

A profile may have a primary context, but course assignments should remain capable of representing cross-School teaching where allowed.

---

# 24. MONITORS

Monitor / Monitrice is a permanent salaried staff category in the existing business model.

They may teach or replace teachers.

Teaching/replacement activity must not automatically become hourly honoraria.

Existing salary and teaching rules must remain intact unless explicitly changed.

---

# 25. ACADEMIC YEAR

AcademicYear remains primarily university-wide.

Example:

2026-2027

Do not create one separate AcademicYear row per School unless an explicit future business requirement demands it.

The same university academic year may contain activities from multiple Schools.

---

# 26. ACADEMIC STRUCTURE

Preserve the existing academic engine.

Concepts include:

- Programme;
- Level;
- Semester;
- Class;
- Maquette;
- UE;
- EC;
- Course;
- Evaluation;
- Grade.

School should normally propagate through Programme when structurally appropriate.

Do not add School independently to every academic model without a concrete need.

---

# 27. ACADEMIC GOVERNANCE

Existing governance principles must remain respected.

Examples:

IT/Admin IT:
grade entry/import/calculation/control.

Director of Studies:
validation/publication/deliberation/locking.

Teachers:
do not replace the established grade-entry governance unless explicitly instructed.

Remedial and annual decision logic should remain consistent with existing implementation.

---

# 28. PAYMENTS

Payments remain one shared engine.

Do not create:

payments_esmed
payments_esga
payments_fatec

Do not redesign OTP/payment receipt logic during unrelated missions.

School and Branch context should be derived from the concerned business object whenever possible.

---

# 29. FINANCE

Finance remains institutionally coherent.

Do not duplicate finance engines per School unless explicitly required.

Existing distinctions between:

- revenue;
- expense;
- cash movement;
- internal transfer;
- bank deposit;

must remain preserved.

A cash transfer does not create income.

A bank deposit does not create new revenue.

---

# 30. PUBLIC WEBSITE

The current public website is inherited from ESFÉ.

It is NOT considered the final UFHOB public website.

Do NOT invest in large-scale redesign of the inherited public templates unless explicitly requested.

A future phase will rebuild the UFHOB public website.

The future public website is expected to include:

- University homepage;
- University presentation;
- Schools directory;
- dedicated School landing pages;
- Programmes;
- Admissions;
- Campus information;
- student life;
- news;
- research/events;
- contact;
- application journey.

Each School may later have its own visual identity.

However, the Schools remain part of the same UFHOB platform.

---

# 31. DJANGO COTTON

Django Cotton is planned for the future UFHOB public frontend.

Do not install or introduce Django Cotton unless the current mission explicitly requests it.

When frontend rebuilding begins, verify compatible versions with:

- current Python version;
- current Django version;
- Tailwind;
- existing HTMX/Alpine architecture.

Do not blindly port old ESFÉ public templates.

---

# 32. HTMX / ALPINE

The project already uses HTMX and Alpine-style frontend behavior.

Preserve existing working lifecycle conventions.

Avoid:

- full-page reloads where existing architecture uses HTMX;
- multiple competing global spinners;
- duplicated JS state systems;
- random role-specific loading logic.

Frontend changes must integrate into the shared UI Core.

---

# 33. DJANGO COTTON FRONTEND PHILOSOPHY

When the future public frontend is built, Cotton should be used for reusable presentation components such as:

- navigation;
- hero blocks;
- buttons;
- cards;
- School cards;
- Programme cards;
- sections;
- breadcrumbs;
- statistics;
- testimonials;
- calls-to-action;
- content blocks;
- forms;
- footer elements.

Do not use Cotton to duplicate business logic.

Business logic remains in Django models/services/views/forms/selectors.

Cotton is a presentation/component layer.

---

# 34. NO SCHOOL-SPECIFIC APP SILOS

Never create architecture such as:

esmed/
esga/
fatec/

containing duplicated business logic.

Never create:

AdmissionsESMED
AdmissionsESGA

Never create:

PaymentESMED
PaymentESGA

Never create:

StudentESMED
StudentESGA

Schools are scoped components of one university system.

---

# 35. NO DATABASE MULTI-TENANCY

Do not introduce:

- django-tenants;
- schema-per-School;
- database-per-School;
- host/domain-per-School business isolation;

unless explicitly requested in a future architectural decision.

UFHOB currently requires logical scoping, not infrastructure multi-tenancy.

---

# 36. NO MASS REBRANDING

Do NOT run global search-and-replace:

ESFÉ → UFHOB

The clone contains:

- historical strings;
- documentation;
- technical references;
- old frontend templates;
- business terminology;
- data migration references;
- test fixtures.

Branding transformation must be progressive.

Change only what the current mission requires.

---

# 37. PROJECT NAME

Always use:

UFHOB

Do NOT silently rename it to:

UFHB

The repository identity is UFHOB.

Respect this exact project name unless explicitly instructed otherwise.

---

# 38. GIT SAFETY

Multiple agents may work on this repository.

Before editing:

git status

and when useful:

git diff

Preserve concurrent work.

Never use destructive Git commands to "clean" a repository without explicit authorization.

PROHIBITED unless explicitly authorized:

git reset --hard
git clean -fd
git checkout .
git restore .
git stash
git revert of unrelated work

Do not discard modifications created by another agent.

---

# 39. EXISTING MIGRATIONS

Respect already-applied migrations.

Do not rewrite historical migrations simply to make the repository look cleaner.

Create new migrations when legitimate schema changes are needed.

Avoid unrelated migration noise.

There may be pre-existing migration differences in unrelated apps.

Do not fix unrelated migration changes unless the mission explicitly includes them.

---

# 40. DATA SAFETY

Never run broad destructive data operations without explicit instruction.

Do not automatically execute:

reset_business_data

bootstrap_institution

database flush

manual mass deletes

DROP DATABASE

DROP SCHEMA

TRUNCATE

or similar destructive operations.

Do not rebuild UFHOB data merely to test a code change.

---

# 41. BOOTSTRAP

UFHOB may contain institutional bootstrap mechanisms.

Bootstrap operations must be:

- deliberate;
- scoped;
- idempotent;
- explicitly required by the current mission.

Do not rerun bootstrap casually.

---

# 42. DEVELOPMENT METHOD

Before implementing a significant change:

1. inspect existing models;
2. inspect existing services/selectors;
3. inspect existing forms;
4. inspect existing views;
5. inspect permissions;
6. inspect existing tests;
7. understand current data flow;
8. identify the smallest compatible extension.

Do not begin by rewriting architecture.

---

# 43. EXTENSION OVER REPLACEMENT

Default strategy:

EXTEND EXISTING ARCHITECTURE.

Avoid:

REPLACE EXISTING ARCHITECTURE.

When a new university requirement appears, first ask:

"Can the current business engine support this by adding School/Branch context?"

Only introduce a new subsystem when the existing architecture genuinely cannot represent the requirement.

---

# 44. BACKWARD COMPATIBILITY

Existing functionality should continue working after university extensions.

Avoid breaking:

- current role dashboards;
- forms;
- existing API/view contracts;
- templates;
- academic engines;
- payment workflows;
- historical data.

Where new School information becomes optional during migration, handle older objects gracefully until the transition is complete.

---

# 45. SCOPING SECURITY

School and Branch scoping is not cosmetic.

It protects organizational data.

Never rely only on frontend filtering.

Security-sensitive scoping must be enforced in server-side querysets/services/permissions.

Example:

If a user is scoped to:

ESMED + Campus A

they must not access ESGA data from Campus A simply by changing a URL or request parameter.

---

# 46. QUERYSET DISCIPLINE

When introducing School scoping, avoid excessive database queries.

Use:

select_related

prefetch_related

when appropriate.

Avoid N+1 query regressions.

However, do not perform unrelated optimization refactors during small feature missions.

---

# 47. PERMISSIONS

Reuse existing permission infrastructure.

Do not scatter hardcoded permission conditions across many views.

When possible:

centralize scope interpretation;
reuse helpers/services/selectors/policies;
keep role permissions separate from access scope.

---

# 48. ADMIN

Django Admin is a technical/administrative interface.

Keep it usable and coherent.

When adding School-related fields, appropriate admin features may include:

- list_display;
- search_fields;
- list_filter;
- autocomplete/select_related.

Do not turn every backend mission into a Django Admin redesign.

---

# 49. TEST STRATEGY

Prefer targeted tests.

After relevant changes, normally run:

python manage.py check

python manage.py makemigrations --check --dry-run

plus targeted tests for modified modules.

Run broader suites when justified.

Do not repeatedly run expensive suites after every minor edit.

---

# 50. REQUIRED UNIVERSITY SCOPING TESTS

When working on university scoping, consider scenarios such as:

Campus A hosts ESMED and ESGA.

User context:

ESMED + Campus A

Expected:

can access ESMED data from Campus A.

Must not automatically access ESGA data from Campus A.

Another expected case:

University-global user

can access multiple Schools and Branches according to permissions.

---

# 51. SCHOOLBRANCH TESTS

Important rules to preserve:

One School may exist on multiple Branches.

One Branch may host multiple Schools.

Duplicate SchoolBranch relationships should normally be prevented.

Programme availability on a Branch must respect SchoolBranch.

---

# 52. HISTORICAL DATA

Do not destroy history for convenience.

Academic, financial and registration records often require historical traceability.

Do not overwrite historical relationships just because a student or employee changes current context.

Use historical business records where already available.

---

# 53. FILE STORAGE

Do not redesign storage architecture during unrelated tasks.

Large media may eventually use external S3-compatible storage.

Django should not become dependent on storing all large media directly in PostgreSQL or the application database.

---

# 54. SECURITY

Do not expose:

- secrets;
- passwords;
- OTP codes;
- environment credentials;
- database passwords;
- storage secrets.

Do not print `.env` values in final reports.

Do not commit secrets.

---

# 55. ENVIRONMENT FILES

Treat `.env` as sensitive.

Do not overwrite it casually.

If a mission needs an environment change:

modify only the necessary keys;
do not expose secret values;
document which key names changed.

---

# 56. PRODUCTION MINDSET

Changes should remain compatible with future deployment.

Avoid hard-coded machine-specific absolute paths inside application code.

Local development paths may be used only for operational instructions, not application runtime logic.

---

# 57. CODE QUALITY

Prefer:

clear code;
small abstractions;
existing patterns;
testable services;
predictable querysets;
single sources of truth.

Avoid:

overengineering;
framework-within-framework architecture;
large generic abstractions with no immediate value;
duplicated business engines.

---

# 58. COMMENTS AND DOCUMENTATION

Document non-obvious business rules.

Do not add excessive comments explaining obvious Python/Django syntax.

Useful comments should explain:

WHY a rule exists,

not merely WHAT the code does.

---

# 59. CURRENT DEVELOPMENT PRIORITY

Current priority is the university backend/domain architecture.

Primary concerns include:

- School;
- SchoolBranch;
- Branch;
- Programme;
- AccessContext;
- role/context scoping;
- university-level aggregation;
- School-level isolation;
- Campus-level isolation;
- School + Branch combined scope;
- compatibility with existing business engines.

The new public frontend comes later.

---

# 60. FUTURE FRONTEND ARCHITECTURE

The future UFHOB public site will likely have:

UFHOB global identity

plus

School-specific landing experiences.

Example:

UFHOB homepage
→ Schools
→ ESMED landing page
→ ESMED Programmes
→ Programme details
→ Application workflow

and:

UFHOB homepage
→ Schools
→ FATEC landing page
→ FATEC Programmes

These are presentation variations on top of the same backend domain model.

Do not implement separate Django projects for those School landing pages.

---

# 61. FUTURE SCHOOL BRANDING

Each School may later have configurable presentation data such as:

- logo;
- accent colors;
- hero;
- imagery;
- description;
- statistics;
- programme highlights;
- contacts.

Do not hardcode these values into backend business logic.

When that phase arrives, prefer configurable presentation metadata.

---

# 62. UNIVERSITY-WIDE REPORTING

Central leadership should eventually be able to aggregate information across:

Schools;
Branches;
Programmes;
Academic Years.

Do not introduce School scoping in a way that makes university-level aggregation impossible.

Context filters should restrict users according to authorization, not fragment the data model.

---

# 63. ROLE PRINCIPLE

A Role is not a School.

A School is not a Role.

A Branch is not a Role.

Keep separate:

AUTHORIZATION
vs
ORGANIZATIONAL SCOPE.

This distinction is fundamental to UFHOB.

---

# 64. SHARED ENGINE PRINCIPLE

The UFHOB architecture must remain understandable as:

ONE UNIVERSITY
ONE APPLICATION
ONE DATABASE
ONE AUTHENTICATION SYSTEM
ONE BUSINESS ENGINE

with:

MULTIPLE SCHOOLS
MULTIPLE CAMPUSES
MULTIPLE PROGRAMMES
CONTEXTUAL ACCESS.

---

# 65. WHEN REQUIREMENTS ARE AMBIGUOUS

When facing an ambiguous business decision:

1. inspect the existing implementation;
2. preserve existing behavior;
3. choose the least destructive extension;
4. avoid irreversible schema choices;
5. report the ambiguity if it materially affects architecture.

Do not invent university policy without evidence.

---

# 66. DO NOT INVENT INSTITUTIONAL DATA

Never invent:

official School names;
official programme names;
official Campus names;
official tuition amounts;
official academic regulations;
official contact information.

Use configurable placeholders or existing repository data when information has not been provided.

---

# 67. AGENT REPORTING

At the end of substantial missions, report:

- what was inspected;
- architecture decisions made;
- files changed;
- migrations created;
- tests executed;
- tests skipped;
- warnings;
- remaining risks;
- whether esfe-core was touched;
- whether esfe_db was touched.

Be precise.

Do not claim success merely because code was written.

Validation results matter.

---

# 68. DEFINITION OF SUCCESS

A change is successful when it:

- satisfies the requested UFHOB business requirement;
- preserves existing working engines;
- respects School/Branch architecture;
- preserves data integrity;
- maintains role/access isolation;
- avoids duplicated business logic;
- passes relevant validation/tests;
- does not contaminate ESFÉ.

---

# 69. MAIN ARCHITECTURAL MOTTO

For UFHOB, always prefer:

SHARED ENGINE
+
UNIVERSITY CONTEXT
+
SCHOOL SCOPE
+
BRANCH SCOPE
+
ACCESS CONTROL

over:

DUPLICATED APPLICATIONS.

---

# 70. FINAL RULE

UFHOB must evolve from the ESFÉ foundation without remaining structurally trapped as a single-school application.

At the same time, the transformation must not destroy the mature business logic already present.

Therefore:

PRESERVE THE ENGINE.
EXTEND THE DOMAIN.
ADD UNIVERSITY CONTEXT.
ENFORCE SCHOOL/BRANCH SCOPING.
KEEP ONE COHERENT PLATFORM.