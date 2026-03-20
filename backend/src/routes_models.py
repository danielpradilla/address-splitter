import os

from http_utils import response
from models import list_bedrock_models, list_inference_profiles


def handle_get_models():
    try:
        region = os.getenv("AWS_REGION_NAME")
        profiles = []
        profiles_error = ""
        try:
            profiles = list_inference_profiles(region=region)
        except Exception as e:
            profiles_error = str(e)
            profiles = []

        models = list_bedrock_models(region=region)
        payload = {"inference_profiles": profiles, "models": models}
        if profiles_error:
            payload["inference_profiles_error"] = profiles_error
        return response(200, payload)
    except Exception as e:
        return response(500, {"error": "bedrock_list_failed", "message": str(e)})
