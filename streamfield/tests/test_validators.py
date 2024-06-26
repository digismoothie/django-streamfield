from django.core.exceptions import ValidationError
from django.test import TestCase

from .. import validators


# ./manage.py test streamfield.tests.test_validators
class TestValidators(TestCase):
    def setUp(self):
        self.v = validators.RelURLValidator()

    def test_url(self):
        self.v("http://localhost:8000/django-admin/tester/page/1/change/")

    def test_uri_1(self):
        self.v("/page/1/change/")

    def test_uri_2(self):
        self.v("page/1/change/")

    def test_uri_3(self):
        self.v("#page")

    def test_bad_uri_1(self):
        with self.assertRaises(ValidationError):
            self.v(r"/page\/1/change/")

    def test_bad_uri_2(self):
        with self.assertRaises(ValidationError):
            self.v("/page~dop/1/change/")
