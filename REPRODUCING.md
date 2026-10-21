# Reproduction commands

Run from this checkout on x86_64 Linux. Nix flakes must be enabled. Builds patch
GNOME/GJS from source and can consume substantial time and disk space. VM tests
require usable KVM. These commands build/run isolated experiments; they do not
activate the host's NixOS configuration.

## Fast validation

```sh
python3 tools/verify-evidence.py
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m compileall -q tgnome.py shell tests tools
nix flake check --no-build
```

The integrity check verifies the exported bytes and manifest; it does not
rerun desktop experiments or authenticate the original experiment's claims.

## Small native controls

```sh
nix build --no-link .#interrupt-baseline .#interrupt-probe
nix build --no-link .#realm-probe .#native-type-probe
nix develop .#type-rebind -c python3 tests/type-rebind-supervisor.py \
  tgnome-type-rebind-probe artifacts/type-rebind-new.json
```

Derivations for the interruption, realm and native-type probes include their
own checks. They isolate specific architecture questions and are not evidence
of a complete graphical recovery cycle.

## Private compositor and VM

```sh
nix develop .#stable -c python3 tests/isolated.py --help
nix develop .#stable -c python3 tests/acceptance.py --help
nix build --no-link .#security-vm
nix build --no-link .#security-reload-vm
nix build --no-link .#security-preparation-vm
nix build --no-link .#security-construction-vm
nix build --no-link .#security-gap-vm
nix build --no-link .#security-quarantine-vm
```

Use the specific original report for that experiment's harness flags. The UI
fallback and complete-runtime experiment have different acceptance contracts.
Cached Nix VM results are not fresh executions; record the derivation and
whether a result was reused. See STATUS.md for known source/saved-run drift.

For the latest complete-context recovery and five-cycle shortcut checks, follow
the README in [the implementation repository](https://github.com/tomasmark79/gnome-shell-restart-nix).
Do not deploy this historical source snapshot as a desktop update.
