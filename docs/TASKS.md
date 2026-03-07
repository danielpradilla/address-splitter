# Tasks

## libpostal sporadic usage mode
- [x] Keep Senzing model overlay in Lambda image.
- [x] Diagnose timeout source with CloudWatch timings.
- [x] Route API Gateway integration to Lambda alias `live`.
- [x] Add manual wake/sleep operational scripts.
- [x] Document wake/sleep runbook in README.
- [ ] Optional next: add a UI admin toggle for wake/sleep.
- [x] Generate `data/fake_addresses.tsv`: 1,000 tab-separated rows (address/city/street/postcode/country) with 200 correct entries and 800 plausible errors across EN/CN/TH/JP/FR/DE/ES for testing address resolution.
