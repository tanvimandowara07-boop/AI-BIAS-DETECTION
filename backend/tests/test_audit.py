import io, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_lite import read_table, run_audit, sample_csv, guess_outcome, guess_favourable


class AuditTests(unittest.TestCase):
    def test_disparity_ratio_and_score(self):
        rows = [["F", "Yes"]] * 3 + [["F", "No"]] * 7 + [["M", "Yes"]] * 6 + [["M", "No"]] * 4
        r = run_audit(["gender", "approved"], rows)
        a = r["attrs"][0]
        self.assertAlmostEqual(a["ratio"], 0.5)      # 0.3 / 0.6
        self.assertEqual(a["score"], 50)
        self.assertEqual(r["score"], 50)

    def test_detection(self):
        head, rows = read_table(sample_csv().encode())
        self.assertEqual(guess_outcome(head), "approved")
        self.assertEqual(guess_favourable(r[-1] for r in rows), "Approved")

    def test_sample_shows_gender_bias(self):
        head, rows = read_table(sample_csv().encode())
        r = run_audit(head, rows)
        gender = next(a for a in r["attrs"] if a["name"] == "Gender")
        self.assertGreaterEqual(gender["score"], 20)

    def test_bad_file(self):
        with self.assertRaises(ValueError):
            read_table(b"a,b\n1,2\n")


if __name__ == "__main__":
    unittest.main()
