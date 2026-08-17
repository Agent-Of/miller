#!/usr/bin/env python3
"""
MILLER Phase 1 Verification Script

Automated testing for MILLER tape-slurper privacy enforcement.
Runs redaction checks, data integrity validation, and generates test report.

Usage:
    python miller-phase1-verify.py --tape-path <path> --output-path <path>

Example:
    python miller-phase1-verify.py \
      --tape-path "C:\Users\victorb\.claude\projects\...\memory\tape.jsonl" \
      --output-path "test-output-phase1.jsonl"
"""

import json
import re
import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple


class Phase1Verifier:
    """MILLER Phase 1 Verification Suite"""

    def __init__(self, tape_path: str, output_path: str):
        self.tape_path = Path(tape_path)
        self.output_path = Path(output_path)
        self.report = {
            "date": datetime.now().isoformat(),
            "tape": str(self.tape_path),
            "output": str(self.output_path),
            "results": {}
        }

    def run_verification(self) -> bool:
        """Execute full Phase 1 verification"""
        print("=" * 60)
        print("MILLER Phase 1 Verification")
        print("=" * 60)

        # Step 1: Pre-flight checks
        print("\n[1/6] Pre-flight checks...")
        if not self._precheck():
            return False

        # Step 2: Run slurper
        print("[2/6] Running slurper...")
        if not self._run_slurper():
            return False

        # Step 3: Verify redaction
        print("[3/6] Verifying PII redaction...")
        if not self._verify_redaction():
            return False

        # Step 4: Verify structure
        print("[4/6] Verifying data structure...")
        if not self._verify_structure():
            return False

        # Step 5: Compare metrics
        print("[5/6] Comparing metrics...")
        self._compare_metrics()

        # Step 6: Generate report
        print("[6/6] Generating report...")
        self._generate_report()

        return True

    def _precheck(self) -> bool:
        """Verify prerequisites"""
        if not self.tape_path.exists():
            print(f"❌ Tape file not found: {self.tape_path}")
            return False

        if self.tape_path.stat().st_size == 0:
            print(f"❌ Tape file is empty: {self.tape_path}")
            return False

        print(f"✓ Tape file found: {self.tape_path.stat().st_size} bytes")
        self.report["results"]["precheck"] = {
            "status": "PASS",
            "tape_size": self.tape_path.stat().st_size
        }
        return True

    def _run_slurper(self) -> bool:
        """Execute MILLER slurper"""
        try:
            # Run: python slurper.py --tape-path <tape> --output-path <output>
            result = subprocess.run(
                ["python", "slurper.py",
                 "--tape-path", str(self.tape_path),
                 "--output-path", str(self.output_path)],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                print(f"❌ Slurper failed: {result.stderr}")
                self.report["results"]["slurper"] = {
                    "status": "FAIL",
                    "error": result.stderr
                }
                return False

            if not self.output_path.exists():
                print(f"❌ Output file not created: {self.output_path}")
                return False

            output_size = self.output_path.stat().st_size
            print(f"✓ Slurper executed successfully: {output_size} bytes output")
            self.report["results"]["slurper"] = {
                "status": "PASS",
                "output_size": output_size
            }
            return True

        except subprocess.TimeoutExpired:
            print("❌ Slurper timeout (60s)")
            return False
        except Exception as e:
            print(f"❌ Slurper error: {e}")
            return False

    def _verify_redaction(self) -> bool:
        """Check for PII in output"""
        print("\n  Checking for PII...")

        pii_patterns = {
            "file_paths_windows": r"C:\\Users\\",
            "file_paths_unix_users": r"/Users/",
            "file_paths_unix_home": r"/home/",
            "session_ids": r"\b[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\b",
            "emails": r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b",
            "aws_keys": r"\bAKIA[0-9A-Z]{16}\b",
            "secrets": r"(Bearer|token|key|secret|password)\s*=\s*['\"]?[A-Za-z0-9_-]{20,}"
        }

        pii_found = {}
        failed = False

        with open(self.output_path) as f:
            content = f.read()

        for pii_type, pattern in pii_patterns.items():
            matches = re.findall(pattern, content, re.IGNORECASE)
            count = len(matches)
            pii_found[pii_type] = count

            if count > 0:
                print(f"  ❌ {pii_type}: {count} found (MUST BE 0)")
                failed = True
            else:
                print(f"  ✓ {pii_type}: 0")

        if failed:
            print("\n❌ REDACTION CHECK FAILED: PII detected in output")
            self.report["results"]["redaction"] = {
                "status": "FAIL",
                "pii_found": pii_found
            }
            return False

        print("\n✓ REDACTION CHECK PASSED: No PII detected")
        self.report["results"]["redaction"] = {
            "status": "PASS",
            "pii_found": pii_found
        }
        return True

    def _verify_structure(self) -> bool:
        """Verify JSON structure and required fields"""
        print("\n  Checking structure...")

        required_fields = ["agent_id", "timestamp", "event_type", "content"]
        line_count = 0
        parse_errors = 0
        missing_fields = {}

        try:
            with open(self.output_path) as f:
                for i, line in enumerate(f, 1):
                    line_count = i
                    try:
                        obj = json.loads(line)

                        # Check for raw session_id (should not exist)
                        if "session_id" in obj:
                            print(f"  ⚠ Line {i}: Contains raw session_id field (should use metadata instead)")

                        # Check for required fields
                        for field in required_fields:
                            if field not in obj:
                                missing_fields[field] = missing_fields.get(field, 0) + 1

                    except json.JSONDecodeError as e:
                        parse_errors += 1
                        if parse_errors <= 3:  # Show first 3 errors
                            print(f"  ❌ Line {i}: JSON parse error: {e}")

            if parse_errors > 0:
                print(f"\n❌ STRUCTURE CHECK FAILED: {parse_errors} JSON parse errors")
                self.report["results"]["structure"] = {
                    "status": "FAIL",
                    "parse_errors": parse_errors,
                    "lines": line_count
                }
                return False

            if missing_fields:
                print(f"\n❌ STRUCTURE CHECK FAILED: Missing required fields")
                print(f"  {missing_fields}")
                self.report["results"]["structure"] = {
                    "status": "FAIL",
                    "missing_fields": missing_fields,
                    "lines": line_count
                }
                return False

            print(f"\n✓ STRUCTURE CHECK PASSED: {line_count} lines, all valid JSON, required fields present")
            self.report["results"]["structure"] = {
                "status": "PASS",
                "lines": line_count,
                "parse_errors": 0,
                "missing_fields": {}
            }
            return True

        except Exception as e:
            print(f"\n❌ STRUCTURE CHECK ERROR: {e}")
            return False

    def _compare_metrics(self):
        """Compare input and output metrics"""
        print("\n  Calculating metrics...")

        input_size = self.tape_path.stat().st_size
        output_size = self.output_path.stat().st_size

        if input_size > 0:
            compression = (output_size / input_size) * 100
        else:
            compression = 0

        # Count lines
        input_lines = sum(1 for _ in open(self.tape_path))
        output_lines = sum(1 for _ in open(self.output_path))

        print(f"  Input:  {input_size:,} bytes ({input_lines} lines)")
        print(f"  Output: {output_size:,} bytes ({output_lines} lines)")
        print(f"  Ratio:  {compression:.1f}%")

        self.report["results"]["metrics"] = {
            "input_size": input_size,
            "output_size": output_size,
            "input_lines": input_lines,
            "output_lines": output_lines,
            "compression_ratio": compression
        }

    def _generate_report(self):
        """Generate and save test report"""
        report_path = self.output_path.with_suffix(".report.json")

        with open(report_path, "w") as f:
            json.dump(self.report, f, indent=2)

        # Determine verdict
        all_passed = all(
            result.get("status") == "PASS"
            for result in self.report["results"].values()
            if isinstance(result, dict) and "status" in result
        )

        verdict = "✅ PHASE 1 PASSED" if all_passed else "❌ PHASE 1 FAILED"
        print(f"\n{verdict}")
        print(f"Report saved: {report_path}")

        self.report["verdict"] = "PASS" if all_passed else "FAIL"

    def print_summary(self):
        """Print verification summary"""
        print("\n" + "=" * 60)
        print("VERIFICATION SUMMARY")
        print("=" * 60)
        for check, result in self.report["results"].items():
            if isinstance(result, dict):
                status = result.get("status", "UNKNOWN")
                symbol = "✅" if status == "PASS" else "❌"
                print(f"{symbol} {check.upper()}: {status}")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="MILLER Phase 1 Verification")
    parser.add_argument("--tape-path", required=True, help="Path to sample JSONL tape")
    parser.add_argument("--output-path", required=True, help="Path for output JSONL")

    args = parser.parse_args()

    verifier = Phase1Verifier(args.tape_path, args.output_path)
    success = verifier.run_verification()
    verifier.print_summary()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
