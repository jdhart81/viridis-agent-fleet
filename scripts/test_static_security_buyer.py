import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
import x402_demo_client as client


class BuyerTests(unittest.TestCase):
    def test_scanner_aliases_build_bounded_inputs(self):
        for route,field in [('canon-scan','source'),('injection-screen','texts')]:
            step=client.select_steps(route)[0]
            self.assertIn(field,step.build_input({}))
            self.assertEqual(step.list_amount_atomic,1_000_000)

    def test_user_input_file_reaches_quote_without_payment(self):
        body={'agent_id':'buyer-real','source':'const x = 1;'}
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'input.json';p.write_text(json.dumps(body))
            with patch.object(client,'run_workflow') as run, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(client.main(['--route','canon-scan','--dry-run','--input-file',str(p)]),0)
                args=run.call_args
                self.assertTrue(args.args[2])
                self.assertEqual(args.kwargs['steps'][0].build_input({}),body)

    def test_single_route_purchase_requires_explicit_cap(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            client.main(['--route','injection-screen'])


if __name__=='__main__':
    unittest.main()
