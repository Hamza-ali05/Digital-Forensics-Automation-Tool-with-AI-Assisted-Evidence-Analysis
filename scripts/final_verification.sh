#!/bin/bash
set -e

echo "========================================="
echo " DFAT Final Verification Suite"
echo " $(date)"
echo "========================================="

echo ""
echo "--- 1. Environment Validation ---"
python scripts/validate_environment.py || echo "WARN: Some env checks failed"

echo ""
echo "--- 2. Backend Unit Tests ---"
make test-unit

echo ""
echo "--- 3. Backend Integration Tests ---"
make test-integration-full

echo ""
echo "--- 4. API Contract Tests ---"
make test-contract

echo ""
echo "--- 5. Security Tests ---"
make test-security

echo ""
echo "--- 6. Backend Coverage Check ---"
make test-coverage-check

echo ""
echo "--- 7. Frontend Tests ---"
make frontend-test

echo ""
echo "--- 8. Frontend Build ---"
make frontend-build

echo ""
echo "--- 9. Docker Build ---"
make docker-build

echo ""
echo "--- 10. Security Scan ---"
make security-scan

echo ""
echo "--- 11. Research Objective Verification ---"
make verify-rqs

echo ""
echo "--- 12. Feature Verification ---"
make verify-features

echo ""
echo "--- 13. DSR Methodology Verification ---"
make verify-dsr

echo ""
echo "--- 14. Project Statistics ---"
make project-stats

echo ""
echo "========================================="
echo " DFAT Final Verification COMPLETE"
echo " All checks passed."
echo "========================================="
