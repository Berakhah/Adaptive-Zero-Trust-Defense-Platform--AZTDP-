"""Run every attack scenario in sequence."""
import importlib
import sys


SCENARIOS = [
    "brute_force",
    "credential_stuffing",
    "token_replay",
    "privilege_escalation",
    "geo_drift_attack",
    "anomaly_flood",
]


def main() -> int:
    failures = []
    for name in SCENARIOS:
        print(f"\n=== running {name} ===")
        try:
            module = importlib.import_module(name)
            module.main()
        except Exception as exc:
            failures.append((name, str(exc)))
            print(f"!! {name} raised {exc}")

    if failures:
        print("\nFAILURES:")
        for name, err in failures:
            print(f"  - {name}: {err}")
        return 1
    print("\nall scenarios completed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
