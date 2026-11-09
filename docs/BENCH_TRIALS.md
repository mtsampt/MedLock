# Collect and evaluate independent bench trials

Use these commands during the physical tests in HARDWARE_ACCEPTANCE.md. They record operator-supplied ground truth against an actual completed check. They do not infer fill labels from predictions or convert photo replay into physical accuracy evidence.

## Prepare a run

Run the collector on the Pi beside the loopback station. The tool identifies a physical run only when the local host reports Linux/Raspberry Pi and the station explicitly reports hardware mode. Laptop replay is retained as replay evidence and excluded from physical metrics. This is provenance metadata, not cryptographic proof of a test's conduct.

Enable original capture archiving and retain the station's session event log. In the installed service, add --capture-dir /var/lib/medlock/captures to MEDLOCK_ARGS. Keep the matching volume calibration and its setup ID. Do not reuse calibration fit or calibration holdout sessions/images for final tests; also keep the air-model training collections separate from the air evaluation study. The utility can check calibration reuse, while the operator must verify independence from air training data.

Agree the bench target/tolerance and the blinded reference-label protocol before combined tests. Use a new collection-session identifier only for an actual independent collection, not every photograph. Use the actual syringe brand/profile identifier, including the two alternative brands in the unsupported-syringe test. Use water and needleless syringes as specified in the project report.

## Record each completed check

Complete the station flow and record the result within its 60-second freshness window. Choose one or more --test flags for a check; the recorder will not append the same check twice. Run as the service user if capture/log permissions require it. From /opt/medlock, an example air-free fill trial is:

```sh
.venv/bin/python scripts/record_trial.py \
  --output /var/lib/medlock/trials/run-01.jsonl \
  --test volume --test air --test combined --test latency \
  --collection-session ACTUAL_COLLECTION_SESSION \
  --syringe-id ACTUAL_SUPPORTED_SYRINGE --supported true \
  --reference-volume-ml 1.0 --reference-air-ml 0.0 \
  --expected-valid true --blinded \
  --capture-root /var/lib/medlock/captures \
  --events /var/lib/medlock/session-events.jsonl
```

Replace the example quantities with independently measured references. --blinded declares how reference labels were obtained; the software cannot verify that the study was blinded. Do not mark an invalid preparation valid based on the station's answer. Use --expected-valid false for invalid combined cases. For controlled-air trials, pass the measured air amount; for unsupported cases use --test unsupported --supported false --expected-valid false and the actual alternative brand ID. Do not label an air-containing image as a volume-accuracy trial: the present estimator measures occupied barrel volume, so S1 uses explicitly air-free fills.

A raw capture is read only within the operator-specified --capture-root. Its original-byte checksum must match the measurement, and its rotation-corrected pixel hash is saved for reuse checks. The collector attaches the matching earliest display acknowledgement from the event log. No matching acknowledgement means missing latency evidence, not a zero-time result.

The append is locked and rejects duplicate check/trial identifiers. Preserve the original file if reference labels need correction; make a documented corrected dataset version rather than silently rewriting the experiment history.

## Evaluate the run

```sh
.venv/bin/python scripts/evaluate_trials.py \
  /var/lib/medlock/trials/run-01.jsonl \
  --calibration /path/to/matching-calibration.json --setup-id ACTUAL_SETUP_ID \
  --min-latency-trials AGREED_SAMPLE_COUNT \
  --output /var/lib/medlock/trials/run-01-report.json
```

The output must be a new path. The report hashes the exact trial file and calibration so it can be reproduced. Evaluation rejects duplicate checks, repeated physical image pixels, inconsistent pass records, mixed model versions and reused calibration sessions/images.

The per-target result is met_in_recorded_trials, not_met or insufficient_evidence. Replay and unverified-host records never enter physical metrics. The software does not issue an overall certification or enable pass based on these reports.

- S1 uses 0.5, 1.0, 1.5, 2.0 and 2.5 mL, with 20 usable independent observations at each. This collection gate is deliberately stricter than counting 20 attempts when some failed. Failed/out-of-design attempts remain visible as exclusions. A false air flag does not exclude an otherwise valid volume estimate from S1. At least 95% of usable errors must be within ±0.05 mL. Matching calibration and archived-image evidence are required.
- S2 requires at least 100 referenced physical trials across below/at/above 0.10 mL. Sensitivity is computed on the at/above group. Unable results in that group count as misses. Camera failures that produced no frame still count as misses; a capture cannot be required when none was produced. All denominators and air bands are shown.
- S3 reports valid-case pass yield and false passes separately. Unable results remain in valid-case yield. A recorded false pass fails the zero-false-pass target even if other coverage is incomplete. Blinded valid and invalid cases, a matching calibration and independent evidence are required to mark the target met in the recorded samples.
- S5 counts matched seat-to-display acknowledgements and the proportion at or below 10 seconds. Declare the minimum trial count explicitly; the report does not specify one. Missing acknowledgements prevent a met result.
- S7 requires two identified unsupported brands and an independent calibrated supported-syringe control that passes. An all-unable program cannot demonstrate discrimination.

S4 physical load/lift/fault testing, S6 comprehension, S8 actual cost, Pi installation/reboot recovery and optical setup still require their separate manual evidence. No real bench data or completed physical tests are supplied with these tools.
