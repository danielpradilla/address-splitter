# Tasks

## Batch processing
- [x] Extract the shared per-address resolution logic from the HTTP handler into a reusable backend service module.
- [x] Define the batch file contract for S3 input/output.
- [ ] Support batch input upload to S3 with a tracked job record.
- [x] Process uploaded files row-by-row and write enriched output files back to S3.
- [ ] Add job status tracking and result download links.
- [ ] Add a basic UI section for batch processing: upload, status, and download.
- [ ] Decide the v1 output mode: best-result columns only, or best-result columns plus per-pipeline JSON details.
- [ ] Add smoke tests for the shared resolver and the batch job flow.
- [ ] Wire the batch handler into CloudFormation and deployment config.

## libpostal sporadic usage mode
- [x] Keep Senzing model overlay in Lambda image.
- [x] Diagnose timeout source with CloudWatch timings.
- [x] Route API Gateway integration to Lambda alias `live`.
- [x] Add manual wake/sleep operational scripts.
- [x] Document wake/sleep runbook in README.
- [ ] Optional next: add a UI admin toggle for wake/sleep.
- [x] Generate `data/fake_addresses.tsv`: 1,000 tab-separated rows (address/city/street/postcode/country) with 200 clean entries and 800 plausibly corrupted entries across EN/CN/TH/JP/FR/DE/ES. Corrupted rows must stay internally consistent so the full address contains the same typoed city/street/postcode values shown in the split columns, making it a resolution benchmark rather than a split benchmark.
