from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings

from academics.storage import build_recording_download_url, get_recording_s3_client


class RecordingStorageTests(SimpleTestCase):
    @override_settings(B2_RECORDINGS_CONFIGURED=False)
    def test_storage_is_optional_until_a_recording_operation_requires_it(self):
        with self.assertRaises(ValidationError):
            get_recording_s3_client()

    @override_settings(
        B2_RECORDINGS_CONFIGURED=True,
        B2_RECORDINGS_BUCKET="private-recordings",
        B2_RECORDINGS_SIGNED_URL_SECONDS=300,
    )
    @patch("academics.storage.get_recording_s3_client")
    def test_signed_download_is_short_lived_and_private(self, client_factory):
        client = Mock()
        client.generate_presigned_url.return_value = "https://example.test/temporary"
        client_factory.return_value = client
        self.assertEqual(
            build_recording_download_url(object_key="recordings/year/recording.mp4"),
            "https://example.test/temporary",
        )
        client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "private-recordings", "Key": "recordings/year/recording.mp4"},
            ExpiresIn=300,
        )

    @override_settings(B2_RECORDINGS_CONFIGURED=True, B2_RECORDINGS_BUCKET="private-recordings")
    @patch("academics.storage.get_recording_s3_client")
    def test_download_url_requests_attachment_only_when_requested(self, client_factory):
        build_recording_download_url(
            object_key="recordings/year/recording.mp4",
            force_download=True,
        )
        client_factory.return_value.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={
                "Bucket": "private-recordings",
                "Key": "recordings/year/recording.mp4",
                "ResponseContentDisposition": "attachment",
            },
            ExpiresIn=300,
        )

    @override_settings(B2_RECORDINGS_CONFIGURED=True, B2_RECORDINGS_BUCKET="private-recordings")
    @patch("academics.storage.get_recording_s3_client")
    def test_storage_errors_are_translated_without_exposing_provider_details(self, client_factory):
        client_factory.return_value.generate_presigned_url.side_effect = RuntimeError("provider diagnostic")
        with self.assertRaises(ValidationError) as raised:
            build_recording_download_url(object_key="recordings/year/recording.mp4")
        self.assertNotIn("provider diagnostic", str(raised.exception))
