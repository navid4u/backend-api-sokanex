from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.exceptions import (
    ValidationError,
)

from .exceptions import (
    custom_exception_handler,
)


class CustomExceptionHandlerTests(
    SimpleTestCase
):
    @patch(
        "common.exceptions.logger.error"
    )
    def test_unhandled_exception_is_logged(
        self,
        mocked_logger,
    ):
        exception = ValueError(
            "Sensitive internal error"
        )

        response = custom_exception_handler(
            exception,
            {
                "request": None,
                "view": None,
            },
        )

        self.assertEqual(
            response.status_code,
            (
                status
                .HTTP_500_INTERNAL_SERVER_ERROR
            ),
        )
        self.assertEqual(
            response.data,
            {
                "success": False,
                "message": (
                    "Internal Server Error"
                ),
                "errors": {},
            },
        )

        mocked_logger.assert_called_once()

        self.assertNotIn(
            "Sensitive internal error",
            str(response.data),
        )

    @patch(
        "common.exceptions.logger.error"
    )
    def test_validation_error_is_not_logged_as_server_error(
        self,
        mocked_logger,
    ):
        exception = ValidationError(
            {
                "email": [
                    "Invalid email.",
                ]
            }
        )

        response = custom_exception_handler(
            exception,
            {
                "request": None,
                "view": None,
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(
            response.data["success"]
        )
        self.assertIn(
            "email",
            response.data["errors"],
        )

        mocked_logger.assert_not_called()