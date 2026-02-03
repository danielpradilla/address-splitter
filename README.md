# address-splitter

Experiment playground for **parsing / splitting / geocoding postal addresses** and comparing approaches side-by-side.

## What it does
- Simple web UI where you paste a free-text address (plus name + country)
- Runs **multiple pipelines** to split the address into structured fields
- Runs **geocoding** to produce latitude/longitude
- Stores results so you can review the **most recent submissions** and compare quality over time

## Pipelines (side-by-side)
1. **LLM splitting (AWS Bedrock) + offline GeoNames geocoding**
2. **libpostal splitting + offline GeoNames geocoding**
3. **AWS services** (Amazon Location Service for geocoding + structured components)

Each stored submission includes provenance so you always know which output came from which pipeline.

## Why
Addresses are messy. This repo is meant to help compare:
- accuracy
- cost
- failure modes
- operational complexity

## Deployment
See `deployment.md` (kept local; ignored by git).

## Repo layout
- `infra/` CloudFormation templates
- `backend/` Lambda source
- `frontend/` static site
- `docs/` additional docs (some files intentionally not tracked)
