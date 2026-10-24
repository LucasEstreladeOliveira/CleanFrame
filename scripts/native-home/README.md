# Native Home control

This one-shot development helper is scoped to Nathan's Frame and firmware 2130.0. It does not run inside CleanFrame or remain active on the TV. It uses the existing SDB developer connection and the published package-name command workaround to execute as SDK UID 901. It does not request root or change security policy.

`Control.cs` exposes read-only query, guarded apply, and exact-value restore through native Home and vconf APIs. It refuses other firmware, root, changed original values, or an ineligible/missing app. Apply failures attempt immediate restore. The baseline and compiled tools remain in ignored `.local/native-home/`.

From the project root:

```sh
python3 scripts/native-home/run.py query
python3 scripts/native-home/run.py restore
```

The existing private `original.json` is the tested rollback baseline. Do not overwrite it with the applied state. The runner re-stages the helper and baseline each time. The query/apply/restore/inspect shell source is retained beside the runner. It needs the compiled output in `.local/native-home/out/`; build with the private verified Microsoft SDK when the C# source changes. No local address, device identifier, compiled binary or signing secret belongs in this source folder.

Even query/inspect stages temporary helper files on the device. These are device operations, not offline repository checks. A clone without the private baseline, SDK and compiled output cannot perform the tested rollback. Preserve the local recovery folder separately; GitHub is a source backup only.

The implementation was reviewed against the [published S90D native Home work](https://github.com/splitcipher/couchroot/blob/83906b468836869933012da03a4018fb339462b3/docs/devices/s90d/README.md). This Frame's native query, apply/restore/reapply and physical Home-from-Netflix test were checked independently. Source review does not replace device testing after future firmware changes.

## Other TVs (staged approval)

The helper was reviewed on one TV. For a different model or firmware, approval is staged so nothing is written until the owner has seen what that TV reports:

1. `inspect` and `query` run on models listed in `READ_ONLY_MODELS` (`run.py`). They read values and report the firmware (`CLEANFRAME_FIRMWARE=` and `APPLY_APPROVED=` in the query output). Even these stage temporary files on the TV.
2. `apply` and `restore` are limited to `APPLY_MODELS` in `run.py` and `ApplyFirmware` in `Control.cs`. Both start with the reference TV only.
3. Add your model and firmware to those lists only after reviewing the inspect and query output: root not required, 32-bit SDK user, the native libraries and a .NET runtime present, a boot-eligible launcher, and a complete baseline saved outside the project.
4. Take the baseline (`original.json`) while the TV still has its original values, keep it private, and prove `restore` before keeping an `apply`.

Keep the TV's address in `.local/device.json`. It does not belong in source or in a commit.
