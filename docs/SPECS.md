# Specs

## Batch processing

### Goal
- Accept a file of addresses via S3 and produce a corresponding output file with the original rows plus resolved and corrected address columns.
- Reuse the same resolution pipelines already used by the interactive UI.

### V1 scope
- Input is a CSV file uploaded to S3.
- Required input column: `raw_address`.
- Optional input columns: `record_id`, `country_code`.
- Batch output is a CSV written back to S3.
- Output preserves all original columns and appends normalized fields such as:
  - `resolved_address_line1`
  - `resolved_address_line2`
  - `resolved_postcode`
  - `resolved_city`
  - `resolved_state_region`
  - `resolved_country_code`
  - `resolved_latitude`
  - `resolved_longitude`
  - `resolved_confidence`
  - `resolved_pipeline`
  - `resolved_warnings`
  - `corrected_address_full`
- Output should also include one JSON column with full per-pipeline details if we want auditability without exploding the CSV width.

### CSV contract
- Input encoding: UTF-8 or UTF-8 with BOM.
- Header row is required.
- Required column:
  - `raw_address`
- Optional passthrough columns:
  - `record_id`
  - `country_code`
  - any additional caller-provided columns
- Output preserves all input columns and appends:
  - `resolved_pipeline`
  - `resolved_confidence`
  - `resolved_warnings`
  - `resolved_address_line1`
  - `resolved_address_line2`
  - `resolved_postcode`
  - `resolved_city`
  - `resolved_state_region`
  - `resolved_country_code`
  - `resolved_latitude`
  - `resolved_longitude`
  - `corrected_address_full`
  - `pipeline_results_json`

### Architecture
- Keep one shared per-address resolver used by both the UI/API flow and batch processing.
- Add a batch job entrypoint triggered after an input object is uploaded to S3.
- Batch worker reads the file, processes rows one by one, and writes the result file to an output S3 prefix.
- Store one job record per uploaded file so the UI can show status and result links.

### UI role
- UI is not the processing engine.
- UI should provide a thin batch-processing surface:
  - upload file
  - choose pipelines
  - submit job
  - see status
  - download output

### Refactor plan
- Extract the current pipeline execution logic from `backend/src/index.py` into a reusable module such as `backend/src/address_resolver.py`.
- Keep the existing HTTP route as the interactive path over the shared resolver.
- Add a second entrypoint for batch processing over the same resolver.

### Implementation status
- Implemented: shared per-address resolver extracted to `backend/src/address_resolver.py`.
- Current interactive API path in `backend/src/index.py` now delegates pipeline execution to the shared resolver.
- Implemented: CSV batch processor in `backend/src/batch_processor.py`.
- Implemented: direct batch Lambda-style entrypoint in `backend/src/batch_handler.py` for S3 object processing.
- Remaining: wire the batch handler into CloudFormation, add job tracking, and expose it in the UI.

### Open decisions
- Which output format comes first: CSV only, CSV plus JSONL, or both.
- Whether v1 writes only the best resolved result or includes all pipeline outputs in the tabular output.
- How “corrected address” is assembled: canonical formatted string from the preferred pipeline vs raw provider-normalized text.
- Whether large files should move directly to SQS or Step Functions instead of a single S3-triggered worker.

### Delivery order
1. Shared resolver extraction.
2. Input/output contract.
3. S3 batch worker and job records.
4. Output file writing.
5. Minimal UI for upload, status, and download.
6. Tests and operational runbook.

## libpostal warm/sleep behavior

### Goals
- Support sporadic usage without paying constant idle cost.
- Keep Senzing overlay enabled for libpostal quality.

### Runtime contract
- API uses Lambda alias `live` as invocation target.
- libpostal usage requires provisioned concurrency to be enabled first.
- `wake`: set provisioned concurrency on alias `live` to `1`.
- `wake`: execute one explicit prewarm invoke for `libpostal_geonames`.
- `sleep`: remove provisioned concurrency on alias `live`.
- Offline geonames lookups rely on the `cities500` dump (Supplemented by `allCountries.txt` for postcodes) loaded into `address-splitter-dev-geonames-cities`/`-geonames`.

### Operational commands
- `scripts/libpostal-wake.sh`
- `scripts/libpostal-sleep.sh`

### Cost posture
- Idle: no provisioned concurrency means no always-on capacity charge.
- Active: pay provisioned concurrency only while the service is intentionally awake.
