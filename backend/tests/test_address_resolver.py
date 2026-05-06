import unittest
from unittest.mock import patch

import test_support  # noqa: F401
from address_resolver import resolve_address


class AddressResolverTest(unittest.TestCase):
    @patch("address_resolver.geocode_with_amazon_location")
    def test_amazon_location_failure_is_pipeline_warning(self, mock_geocode):
        mock_geocode.side_effect = RuntimeError("Service unavailable")

        results = resolve_address(
            country_code="FR",
            raw_address="36 rue de la bergerie cessy",
            model_id="",
            pipelines=["aws_services"],
            rendered_prompt="",
            pricing={},
            region="eu-central-1",
            place_index="address-splitter-dev-place-index",
        )

        self.assertEqual(results["aws_services"]["source"], "amazon_location")
        self.assertEqual(results["aws_services"]["confidence"], 0.0)
        self.assertEqual(results["aws_services"]["warnings"][0], "amazon_location_failed")
        self.assertIn("Service unavailable", results["aws_services"]["warnings"][1])

    @patch("address_resolver.lookup_city_best")
    @patch("address_resolver.lookup_postcode")
    @patch("libpostal_real.parse_with_libpostal")
    def test_libpostal_result_is_normalized_with_geonames_postcode(self, mock_parse, mock_postcode, mock_city):
        mock_parse.return_value = {
            "country_code": "FR",
            "address_line1": "rue de la bergerie 36",
            "address_line2": "",
            "postcode": "01170",
            "city": "cessy",
            "state_region": "",
            "raw_address": "36 rue de la bergerie cessy 01170 france",
            "confidence": 0.85,
            "warnings": [],
            "libpostal_parts": [],
        }
        mock_postcode.return_value = {
            "country_code": "FR",
            "postcode": "01170",
            "place_name": "Cessy",
            "admin1_name": "Auvergne-Rhone-Alpes",
            "admin1_code": "84",
            "latitude": "46.3167",
            "longitude": "6.0667",
        }
        mock_city.return_value = {
            "country_code": "FR",
            "name": "Cessy",
            "ascii_name": "Cessy",
            "admin1_code": "84",
            "latitude": "46.3167",
            "longitude": "6.0667",
        }

        results = resolve_address(
            country_code="FR",
            raw_address="36 rue de la bergerie cessy 01170 france",
            model_id="",
            pipelines=["libpostal_geonames"],
            rendered_prompt="",
            pricing={},
            region="eu-central-1",
            geonames_table="postcodes",
            geonames_cities="cities",
        )

        out = results["libpostal_geonames"]
        self.assertEqual(out["country_code"], "FR")
        self.assertEqual(out["city"], "Cessy")
        self.assertEqual(out["state_region"], "Auvergne-Rhone-Alpes")
        self.assertEqual(out["geo_accuracy"], "postcode")
        self.assertEqual(out["geonames_match"], "Cessy 01170")
