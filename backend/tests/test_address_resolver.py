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
