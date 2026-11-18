"""Load demo data for local development: a Super Admin, four turfs, owners, a manager,
pricing, customers, bookings, payments, expenses and applications.

    python manage.py seed_demo

Safe to re-run (skips when the demo admin already exists unless --reset is given).
Refuses to run with DEBUG=False. Demo logins are listed in README.md.
"""

import random
from datetime import time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.applications.models import TurfApplication
from apps.applications.services import create_turf_with_owner
from apps.bookings.models import Booking, Payment
from apps.bookings.services import (
    SlotUnavailable,
    change_status,
    get_or_create_customer,
    record_payment,
    reserve_slot,
)
from apps.expenses.models import Expense
from apps.locations.models import Area, District
from apps.turfs.models import Amenity, PricingRule, TenantMembership, Turf, TurfField
from apps.turfs.pricing import local_dt, recompute_min_price

ADMIN_EMAIL = "admin@turfos.local"
ADMIN_PASSWORD = "TurfosAdmin#2026"
OWNER_PASSWORD = "TurfosOwner#2026"
MANAGER_EMAIL = "manager@turfos.local"
MANAGER_PASSWORD = "TurfosManager#2026"

TURFS = [
    {
        "name": "Green Arena Gulshan",
        "district": "dhaka",
        "area": "gulshan-dhaka",
        "address": "Road 90, Gulshan 2, Dhaka 1212",
        "turf_type": "rooftop",
        "owner": ("owner@turfos.local", "Rahim Uddin", "01711000001"),
        "fields": 2,
        "rate": "2000.00",
        "peak": "2800.00",
        "featured": True,
        "short": "Rooftop 5-a-side and 7-a-side pitches with a skyline view.",
        "amenities": ["floodlights", "parking", "washroom", "changing-room", "drinking-water", "cctv"],
    },
    {
        "name": "Mirpur Kickoff Zone",
        "district": "dhaka",
        "area": "mirpur-dhaka",
        "address": "Section 10, Mirpur, Dhaka 1216",
        "turf_type": "outdoor",
        "owner": ("mirpur.owner@turfos.local", "Karim Hasan", "01811000002"),
        "fields": 3,
        "rate": "1400.00",
        "peak": "1900.00",
        "featured": True,
        "short": "Three full-size artificial pitches, open until midnight.",
        "amenities": ["floodlights", "washroom", "drinking-water", "cafeteria", "seating-area"],
    },
    {
        "name": "Uttara Indoor Sports Hub",
        "district": "dhaka",
        "area": "uttara-dhaka",
        "address": "Sector 7, Uttara, Dhaka 1230",
        "turf_type": "indoor",
        "owner": ("uttara.owner@turfos.local", "Nusrat Jahan", "01911000003"),
        "fields": 1,
        "rate": "1800.00",
        "peak": "2400.00",
        "featured": False,
        "short": "Air-conditioned indoor futsal court — play in any weather.",
        "amenities": ["parking", "washroom", "changing-room", "prayer-room", "wi-fi", "first-aid"],
    },
    {
        "name": "Port City Turf",
        "district": "chattogram",
        "area": "agrabad-chattogram",
        "address": "Agrabad C/A, Chattogram 4100",
        "turf_type": "outdoor",
        "owner": ("ctg.owner@turfos.local", "Tanvir Ahmed", "01611000004"),
        "fields": 2,
        "rate": "1200.00",
        "peak": "1600.00",
        "featured": False,
        "short": "Chattogram's friendliest 6-a-side turf near Agrabad.",
        "amenities": ["floodlights", "parking", "washroom", "equipment-rental"],
    },
]

CUSTOMERS = [
    ("Arif Hossain", "01712345601", "Gulshan Strikers"),
    ("Sabbir Rahman", "01812345602", "Banani FC"),
    ("Imran Khan", "01912345603", "Office League"),
    ("Fahim Chowdhury", "01612345604", "Friday Legends"),
    ("Rakib Islam", "01512345605", "Uni Boys"),
    ("Mehedi Hasan", "01312345606", "Night Owls"),
    ("Shakil Ahmed", "01712345607", ""),
    ("Tariq Aziz", "01812345608", "Corporate XI"),
]


class Command(BaseCommand):
    help = "Load demo data (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing demo turfs first.")

    def handle(self, *args, reset=False, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DEBUG=True.")
        User = get_user_model()
        if User.objects.filter(email=ADMIN_EMAIL).exists() and not reset:
            self.stdout.write("Demo data already loaded (use --reset to rebuild).")
            return
        with transaction.atomic():
            if reset:
                self._reset()
            self._seed()
        self.stdout.write(self.style.SUCCESS("Demo data loaded. Logins are listed in README.md."))

    def _reset(self):
        User = get_user_model()
        emails = [t["owner"][0] for t in TURFS] + [ADMIN_EMAIL, MANAGER_EMAIL]
        turfs = Turf.objects.filter(memberships__user__email__in=emails).distinct()
        for turf in turfs:
            Payment.objects.filter(turf=turf).delete()
            Booking.objects.filter(turf=turf).delete()
            turf.delete()
        TurfApplication.objects.filter(email__endswith="@example.com").delete()
        User.objects.filter(email__in=emails).delete()

    def _seed(self):
        User = get_user_model()
        rng = random.Random(42)  # noqa: S311 - demo data, not security
        User.objects.create_superuser(ADMIN_EMAIL, ADMIN_PASSWORD, full_name="TURFOS Admin")

        created = []
        for spec in TURFS:
            email, name, phone = spec["owner"]
            turf, owner, _ = create_turf_with_owner(
                name=spec["name"],
                district=District.objects.get(slug=spec["district"]),
                area=Area.objects.get(slug=spec["area"]),
                address=spec["address"],
                turf_type=spec["turf_type"],
                owner_email=email,
                owner_name=name,
                owner_phone="+88" + phone,
                number_of_fields=spec["fields"],
                hourly_rate=Decimal(spec["rate"]),
            )
            owner.set_password(OWNER_PASSWORD)
            owner.save(update_fields=["password"])
            turf.is_listed = True
            turf.is_featured = spec["featured"]
            turf.short_description = spec["short"]
            turf.description = (
                f"{spec['name']} offers well-maintained {turf.get_surface_display().lower()} pitches with "
                "bright LED floodlights for evening games. Book a slot online and the team confirms by phone."
            )
            turf.public_email = email
            turf.booking_instructions = "Send a request online. We call to confirm within 30 minutes."
            turf.cancellation_policy = (
                "Free cancellation up to 6 hours before the slot. Advance is non-refundable after that."
            )
            turf.payment_methods_text = "Cash, bKash, Nagad"
            turf.save()
            turf.amenities.set(Amenity.objects.filter(slug__in=spec["amenities"]))
            for i, field in enumerate(turf.fields.all()):
                field.size = "7-a-side" if i == 0 and spec["fields"] > 1 else "5-a-side"
                field.is_indoor = spec["turf_type"] == "indoor"
                field.save()
            PricingRule.objects.create(
                turf=turf,
                label="Peak hours",
                start_time=time(17, 0),
                end_time=time(23, 0),
                hourly_rate=Decimal(spec["peak"]),
                priority=10,
            )
            PricingRule.objects.create(
                turf=turf,
                label="Weekend",
                weekdays=[4, 5],
                start_time=time(8, 0),
                end_time=time(0, 0),
                hourly_rate=Decimal(spec["peak"]),
                priority=20,
            )
            recompute_min_price(turf)
            created.append((turf, owner))

        # Manager at the first turf
        first_turf, first_owner = created[0]
        manager = User.objects.create_user(
            MANAGER_EMAIL, MANAGER_PASSWORD, full_name="Jamal Manager", phone="+8801700000099"
        )
        TenantMembership.objects.create(user=manager, turf=first_turf, role=TenantMembership.Role.MANAGER)

        today = timezone.localdate()
        for turf, owner in created:
            fields = list(TurfField.objects.filter(turf=turf))
            customers = [get_or_create_customer(turf, name=n, phone=p, email="") for n, p, _ in CUSTOMERS]
            teams = {c.id: t for c, (_, _, t) in zip(customers, CUSTOMERS, strict=True)}
            for offset in range(-14, 4):
                day = today + timedelta(days=offset)
                for hour in rng.sample([7, 9, 16, 17, 18, 19, 20, 21, 22], k=rng.randint(2, 5)):
                    field = rng.choice(fields)
                    customer = rng.choice(customers)
                    start = local_dt(day, time(hour, 0))
                    is_future = start > timezone.now()
                    try:
                        booking = reserve_slot(
                            turf=turf,
                            field_id=field.id,
                            start=start,
                            end=start + timedelta(hours=1),
                            customer=customer,
                            status=Booking.Status.PENDING
                            if is_future and rng.random() < 0.25
                            else Booking.Status.CONFIRMED,
                            source=rng.choice(["phone", "walk_in", "online"]),
                            team_name=teams[customer.id],
                            created_by=owner,
                        )
                    except SlotUnavailable:
                        continue
                    if booking.status == Booking.Status.PENDING:
                        continue
                    method = rng.choice(["cash", "bkash", "nagad", "cash"])
                    if is_future:
                        if rng.random() < 0.6:
                            record_payment(
                                booking, amount=Decimal("500.00"), method=method, kind="payment", user=owner
                            )
                        continue
                    roll = rng.random()
                    if roll < 0.08:
                        change_status(booking, Booking.Status.CANCELLED)
                        continue
                    record_payment(booking, amount=booking.total, method=method, kind="payment", user=owner)
                    Payment.objects.filter(booking=booking).update(paid_at=booking.start)
                    change_status(booking, Booking.Status.COMPLETED)

            for days_ago, category, amount, note in [
                (12, "electricity", "8500.00", "DESCO bill"),
                (10, "salary", "15000.00", "Ground staff"),
                (6, "maintenance", "4200.00", "Net and line paint"),
                (3, "equipment", "3600.00", "New footballs"),
                (1, "marketing", "2000.00", "Facebook boost"),
            ]:
                Expense.objects.create(
                    turf=turf,
                    category=category,
                    amount=Decimal(amount),
                    spent_on=today - timedelta(days=days_ago),
                    note=note,
                    created_by=owner,
                )

        for name, owner, phone, district, area in [
            ("Dhanmondi Goal Club", "Sadia Islam", "+8801755000010", "dhaka", "dhanmondi-dhaka"),
            ("Sylhet Tea Garden Turf", "Abdul Malik", "+8801855000011", "sylhet", "zindabazar-sylhet"),
        ]:
            TurfApplication.objects.create(
                turf_name=name,
                owner_name=owner,
                phone=phone,
                email=f"{owner.split()[0].lower()}@example.com",
                district=District.objects.get(slug=district),
                area=Area.objects.get(slug=area),
                address=f"Main road, {area.split('-')[0].title()}",
                turf_type="outdoor",
                number_of_fields=2,
                message="We'd like to list our turf and manage bookings online.",
            )
