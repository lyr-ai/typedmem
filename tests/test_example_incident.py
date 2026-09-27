"""examples/incident_investigation.py is a published, end-to-end example. Its real
output is pinned here, so the example can't drift from what TypedMem does."""

import subprocess
import sys
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "incident_investigation.py"

EXPECTED = """\
CLAIMS AND EVIDENCE
  one record, 2 sources: ['runtime_telemetry', 'support_cases'], confidence 0.72
  conflict, both kept: [['The certificate is causing client failures', 'The certificate is valid']]
  still unresolved: True

INVESTIGATION DECISION
  current: ['Investigate logging-service connectivity']
  kept as history: Investigate certificate failure -> superseded by the new decision: True

HOW THE INVESTIGATION MEMORY CHANGED
  1. added       evidence   logging.cert_errors
  2. reinforced  evidence   logging.cert_errors
  3. added       assessment logging.certificate
  4. flagged     assessment logging.certificate
  5. flagged     assessment logging.certificate
  6. added       decision   logging.investigation_path
  7. added       evidence   logging.connectivity
  8. superseded  decision   logging.investigation_path
  9. supersedes  decision   logging.investigation_path

REPLAY
  full log rebuilds the current state: True
  before the revision, the decision was: ['Investigate certificate failure']
"""


def test_incident_example_output_is_pinned():
    out = subprocess.run([sys.executable, str(EXAMPLE)], capture_output=True, text=True, check=True)
    assert out.stdout == EXPECTED
