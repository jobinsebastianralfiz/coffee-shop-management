"""
Management command to set up demo data for the Coffee Shop Management System.
Run this after deployment to create initial admin user and demo outlet.
"""

from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.core.models import Outlet
from apps.tables.models import Floor, Table


class Command(BaseCommand):
    help = "Set up demo data with admin user, outlet, floor, and tables"

    def add_arguments(self, parser):
        parser.add_argument(
            "--admin-password",
            type=str,
            default="admin123",
            help="Password for admin user (default: admin123)",
        )
        parser.add_argument(
            "--admin-pin",
            type=str,
            default="123456",
            help="PIN for admin user (default: 123456)",
        )

    def handle(self, *args, **options):
        admin_password = options["admin_password"]
        admin_pin = options["admin_pin"]

        self.stdout.write("Setting up demo data...")

        # Create superuser if not exists
        if not User.objects.filter(username="admin").exists():
            admin = User.objects.create_user(
                username="admin",
                email="admin@coffeeshop.com",
                password=admin_password,
                first_name="Admin",
                last_name="User",
                role=User.Role.SUPER_ADMIN,
                pin=admin_pin,
                phone="9876543210",
            )
            admin.is_staff = True
            admin.is_superuser = True
            admin.save()
            self.stdout.write(
                self.style.SUCCESS(f"Created admin user (password: {admin_password}, PIN: {admin_pin})")
            )
        else:
            self.stdout.write(self.style.WARNING("Admin user already exists"))

        # Create demo outlet if not exists
        if not Outlet.objects.exists():
            outlet = Outlet.objects.create(
                name="Demo Coffee Shop",
                code="DEMO01",
                address="123 Demo Street",
                city="Mumbai",
                state="Maharashtra",
                country="India",
                postal_code="400001",
                phone="9876543210",
                email="demo@coffeeshop.com",
                currency_code="INR",
                currency_symbol="₹",
                is_active=True,
            )
            self.stdout.write(self.style.SUCCESS(f"Created outlet: {outlet.name}"))

            # Create a floor
            floor = Floor.objects.create(
                outlet=outlet,
                name="Main Floor",
                description="Main seating area",
                is_active=True,
            )
            self.stdout.write(self.style.SUCCESS(f"Created floor: {floor.name}"))

            # Create 3 demo tables
            for i in range(1, 4):
                table = Table(
                    floor=floor,
                    number=f"T{i}",
                    name=f"Table {i}",
                    capacity=4,
                    table_type=Table.TableType.FOUR_SEATER,
                )
                table.save()
                self.stdout.write(self.style.SUCCESS(f"Created table: {table.number}"))
        else:
            self.stdout.write(self.style.WARNING("Outlet already exists"))

        # Create outlet manager if not exists
        if not User.objects.filter(username="manager").exists():
            if Outlet.objects.exists():
                outlet = Outlet.objects.first()
                manager = User.objects.create_user(
                    username="manager",
                    email="manager@coffeeshop.com",
                    password="manager123",
                    first_name="Outlet",
                    last_name="Manager",
                    role=User.Role.OUTLET_MANAGER,
                    pin="111111",
                    phone="9876543211",
                    outlet=outlet,
                )
                self.stdout.write(
                    self.style.SUCCESS(f"Created outlet manager (password: manager123, PIN: 111111)")
                )
        else:
            self.stdout.write(self.style.WARNING("Outlet manager already exists"))

        self.stdout.write(self.style.SUCCESS("\nDemo setup complete!"))
        self.stdout.write(f"\nLogin credentials:")
        self.stdout.write(f"  Super Admin:")
        self.stdout.write(f"    Username: admin")
        self.stdout.write(f"    Password: {admin_password}")
        self.stdout.write(f"    PIN: {admin_pin}")
        self.stdout.write(f"  Outlet Manager:")
        self.stdout.write(f"    Username: manager")
        self.stdout.write(f"    Password: manager123")
        self.stdout.write(f"    PIN: 111111")
