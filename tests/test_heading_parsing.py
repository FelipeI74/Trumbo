import unittest

from app.main import _parse_heading_fields


class HeadingParsingTests(unittest.TestCase):
    def test_hyphen_in_location_does_not_split(self):
        result = _parse_heading_fields("INT. CASA DE ANA-MARÍA - DÍA")
        self.assertEqual(result["int_ext"], "INT.")
        self.assertEqual(result["location"], "CASA DE ANA-MARÍA")
        self.assertEqual(result["sublocation"], "")
        self.assertEqual(result["time_of_day"], "DÍA")

    def test_normal_split_still_works(self):
        result = _parse_heading_fields("INT. CASA - DÍA")
        self.assertEqual(result["int_ext"], "INT.")
        self.assertEqual(result["location"], "CASA")
        self.assertEqual(result["sublocation"], "")
        self.assertEqual(result["time_of_day"], "DÍA")

    def test_multiple_segments_still_work(self):
        result = _parse_heading_fields("EXT. PLAZA - SANTIAGO CENTRO - NOCHE")
        self.assertEqual(result["int_ext"], "EXT.")
        self.assertEqual(result["location"], "PLAZA")
        self.assertEqual(result["sublocation"], "SANTIAGO CENTRO")
        self.assertEqual(result["time_of_day"], "NOCHE")

    def test_em_dash_separator(self):
        result = _parse_heading_fields("INT. CASA — DÍA")
        self.assertEqual(result["int_ext"], "INT.")
        self.assertEqual(result["location"], "CASA")
        self.assertEqual(result["time_of_day"], "DÍA")

    def test_compound_location_with_two_hyphens(self):
        result = _parse_heading_fields("INT. CASA-MUSEO DE ANA-MARÍA - NOCHE")
        self.assertEqual(result["int_ext"], "INT.")
        self.assertEqual(result["location"], "CASA-MUSEO DE ANA-MARÍA")
        self.assertEqual(result["time_of_day"], "NOCHE")

    def test_no_spaces_hyphen_is_not_separator(self):
        # Antes del fix esto se comportaba mal:
        # "CASA-ANA" se partia en "CASA" + "ANA"
        result = _parse_heading_fields("INT. CASA-ANA - DÍA")
        self.assertEqual(result["location"], "CASA-ANA")
        self.assertEqual(result["sublocation"], "")


if __name__ == "__main__":
    unittest.main()
