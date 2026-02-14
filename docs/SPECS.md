# Specs

## libpostal warm/sleep behavior

### Goals
- Support sporadic usage without paying constant idle cost.
- Keep Senzing overlay enabled for libpostal quality.

### Runtime contract
- API uses Lambda alias `live` as invocation target.
- libpostal usage requires provisioned concurrency to be enabled first.
- `wake`: set provisioned concurrency on alias `live` to `1`.
- `sleep`: remove provisioned concurrency on alias `live`.

### Operational commands
- `scripts/libpostal-wake.sh`
- `scripts/libpostal-sleep.sh`

### Cost posture
- Idle: no provisioned concurrency means no always-on capacity charge.
- Active: pay provisioned concurrency only while the service is intentionally awake.
