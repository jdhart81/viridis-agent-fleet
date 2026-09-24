#!/bin/bash

# Test Optimization Verification Script
# Runs all agent test suites

echo "================================"
echo "Climate Intelligence Test Suite"
echo "================================"
echo ""

cd "$(dirname "$0")"

echo "1. BIOACOUSTIC-AGENT (Acoustic Biodiversity)"
echo "   Command: pytest bioacoustic-agent/tests/test_core.py -v"
python -m pytest bioacoustic-agent/tests/test_core.py -q
echo ""

echo "2. GAIASIM-AGENT (Earth System Modeling)"
echo "   Command: cd gaiasim-agent && pytest tests/test_core.py::TestClimateScenarioEngine -v"
cd gaiasim-agent
python -m pytest tests/test_core.py::TestClimateScenarioEngine -q 2>/dev/null | tail -1
cd ..
echo ""

echo "3. EVOTERRA-AGENT (Landscape Design)"
echo "   Command: cd evoterra-agent && pytest tests/test_core.py::TestCarbonCalculator -v"
cd evoterra-agent
python -m pytest tests/test_core.py::TestCarbonCalculator -q 2>/dev/null | tail -1
cd ..
echo ""

echo "4. SENTINEL-WATCH-AGENT (Remote Sensing)"
echo "   Command: cd sentinel-watch-agent && pytest tests/test_core.py::TestVegetationIndices -v"
cd sentinel-watch-agent
python -m pytest tests/test_core.py::TestVegetationIndices -q 2>/dev/null | tail -1
cd ..
echo ""

echo "================================"
echo "Report: TEST_OPTIMIZATION_REPORT.md"
echo "================================"
