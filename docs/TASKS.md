# Tasks

## Refactoring and improvement opportunities
- [x] Split the API router in `backend/src/index.py` into route-specific modules or handlers so prompt settings, submissions, and split execution stop living in one file.
- [x] Extract prompt/pricing settings loading into a shared service instead of reading `USER_SETTINGS_TABLE` ad hoc in multiple places.
- [ ] Add structured logging instead of `print` timing lines, with consistent fields for route, pipeline, submission/job id, and duration.
- [ ] Introduce typed request/response models for interactive and batch flows so result shapes are validated in one place.
- [x] Add test coverage for prompt rendering, resolver behavior, batch CSV processing, and API smoke paths.
- [ ] Make batch configuration explicit and validated at startup or invocation time (`BATCH_DEFAULT_MODEL_ID`, pipelines, prefixes, prompt template).
- [ ] Add collision-safe output naming and idempotency rules for batch output files and manifests.
- [x] Add batch job records in DynamoDB instead of relying only on S3 manifests, so UI status and retries have a first-class source of truth.
- [x] Split `frontend/app.js` into smaller modules once batch UI work starts, so auth, prompt editing, split execution, and recent/history rendering are isolated.
- [ ] Revisit persistence shape for submissions/results so previews, batch jobs, and future analytics do not all depend on one DynamoDB item structure.
- [x] Add CloudFormation support for the batch handler and the minimum IAM/S3 event wiring needed to deploy it safely.

## Batch processing
- [x] Extract the shared per-address resolution logic from the HTTP handler into a reusable backend service module.
- [x] Define the batch file contract for S3 input/output.
- [x] Support batch input upload to S3 with a tracked job record.
- [x] Process uploaded files row-by-row and write enriched output files back to S3.
- [ ] Add job status tracking and result download links.
- [ ] Add a basic UI section for batch processing: upload, status, and download.
- [ ] Decide the v1 output mode: best-result columns only, or best-result columns plus per-pipeline JSON details.
- [x] Add smoke tests for the shared resolver and the batch job flow.
- [x] Wire the batch handler into CloudFormation and deployment config.

## libpostal sporadic usage mode
- [x] Keep Senzing model overlay in Lambda image.
- [x] Diagnose timeout source with CloudWatch timings.
- [x] Route API Gateway integration to Lambda alias `live`.
- [x] Add manual wake/sleep operational scripts.
- [x] Document wake/sleep runbook in README.
- [ ] Optional next: add a UI admin toggle for wake/sleep.
- [x] Generate `data/fake_addresses.tsv`: 1,000 tab-separated rows (address/city/street/postcode/country) with 200 clean entries and 800 plausibly corrupted entries across EN/CN/TH/JP/FR/DE/ES. Corrupted rows must stay internally consistent so the full address contains the same typoed city/street/postcode values shown in the split columns, making it a resolution benchmark rather than a split benchmark.
