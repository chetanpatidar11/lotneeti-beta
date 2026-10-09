from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from platform_admin.models import AdminTOTPDevice
from platform_admin.totp import enroll_admin


class Command(BaseCommand):
    help = "Enroll an existing Founder Admin in authenticator-app MFA"

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, **options):
        user = User.objects.filter(email=options["email"].strip().lower()).first()
        if user is None or not user.is_staff or not user.is_founder_admin:
            raise CommandError("Founder Admin account not found")
        if AdminTOTPDevice.objects.filter(user=user).exists():
            raise CommandError("Authenticator is already enrolled")
        uri = enroll_admin(user)
        self.stdout.write(
            "Add this one-time URI to your authenticator app, then clear this terminal:"
        )
        self.stdout.write(uri)
