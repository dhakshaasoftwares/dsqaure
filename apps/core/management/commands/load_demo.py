"""
Fill an EMPTY installation with realistic sample data, for demos to new clients.

    python manage.py load_demo                # refuses if projects already exist
    python manage.py load_demo --password X   # password for the demo 'owner' login
"""

from datetime import timedelta
from decimal import Decimal as D

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.attendance.models import Attendance
from apps.core.models import CompanySettings, NumberSequence, Project, Unit
from apps.core.setup import ensure_defaults
from apps.documents.models import (Agreement, Client, DocumentTemplate, PaymentMilestone, Quotation, QuotationLine,
                                   WorkItem)
from apps.employees.models import Employee
from apps.inventory import models as inv
from apps.inventory import services as stock
from apps.progress.services import apply_standard_stages


class Command(BaseCommand):
    help = "Load sample projects, staff, stock, quotations and agreements into an empty install"

    def add_arguments(self, parser):
        parser.add_argument("--password", default="demo12345", help="Password for the 'owner' demo login")

    @transaction.atomic
    def handle(self, *args, password, **options):
        if Project.objects.exists():
            raise CommandError("This installation already has projects. Demo data is only for empty installs.")
        ensure_defaults("india")
        today = timezone.localdate()

        c = CompanySettings.load()
        c.name = "Demo Constructions"
        c.address = "12, Gandhi Road\nTambaram, Chennai 600045"
        c.phone = "+91 98400 12345"
        c.tax_enabled = True
        c.tax_registration_number = "33ABCDE1234F1Z5"
        c.signatory_name = "K. Velmurugan"
        c.signatory_designation = "Managing Partner"
        c.bank_details = "Indian Bank, Tambaram branch\nA/c 6012345678  IFSC IDIB000T012"
        c.save()

        owner = User.objects.filter(is_superuser=True).first()
        created_owner = owner is None
        if created_owner:
            owner = User.objects.create_superuser("owner", password=password, first_name="Demo", last_name="Owner")

        client = Client.objects.create(name="Mr. R. Selvam", address="45, Lake View Road, Velachery, Chennai",
                                       phone="98410 55555")
        villa = Project.objects.create(name="Selvam Residence G+1", code="SR01", client=client,
                                       address="Plot 7, Anna Nagar West, Chennai", contract_value=D("4250000"),
                                       start_date=today - timedelta(days=90), latitude=D("13.085000"),
                                       longitude=D("80.210000"))
        flats = Project.objects.create(name="Tambaram Apartments", code="TMB", client_name="Sri Homes",
                                       contract_value=D("12000000"), start_date=today - timedelta(days=30))
        apply_standard_stages(villa)
        apply_standard_stages(flats)
        for stage, pct in zip(villa.stages.all(), [100, 100, 100, 80, 40, 10]):
            stage.percent = D(pct)
            stage.save()
        for stage, pct in zip(flats.stages.all(), [100, 60, 10]):
            stage.percent = D(pct)
            stage.save()

        units = {u.symbol: u for u in Unit.objects.all()}
        civil = inv.MaterialCategory.objects.create(name="Civil")
        cement = inv.Material.objects.create(code="CEM53", name="Cement OPC 53", category=civil, unit=units["Bag"],
                                             tax_code="2523", tax_rate=28, reorder_level=100)
        steel = inv.Material.objects.create(code="TMT12", name="TMT Steel 12mm", category=civil, unit=units["Kg"],
                                            tax_code="7214", tax_rate=18, reorder_level=500)
        sand = inv.Material.objects.create(code="MSAND", name="M-Sand", category=civil, unit=units["Cft"], tax_rate=5)
        bricks = inv.Material.objects.create(code="BRICK", name="Red bricks", category=civil, unit=units["Nos"],
                                             tax_rate=5, reorder_level=2000)
        supplier = inv.Supplier.objects.create(name="Sri Balaji Traders", phone="044 2222 3333",
                                               address="GST Road, Chromepet", payment_terms="30 days credit")
        godown = inv.Location.objects.create(name="Central godown")

        po = inv.PurchaseOrder(date=today - timedelta(days=9), supplier=supplier, location=villa.stock_location,
                               expected_date=today - timedelta(days=4), terms=c.po_terms)
        stock.save_purchase_order(po, [
            inv.PurchaseOrderLine(material=cement, quantity=200, rate=D("395"), tax_rate=28),
            inv.PurchaseOrderLine(material=steel, quantity=1500, rate=D("62.50"), tax_rate=18),
            inv.PurchaseOrderLine(material=sand, quantity=400, rate=D("55"), tax_rate=5),
        ], owner)
        stock.approve_purchase_order(po, owner)
        stock.post_goods_receipt(
            inv.GoodsReceipt(date=today - timedelta(days=5), supplier=supplier, location=po.location,
                             purchase_order=po, supplier_invoice_no="SBT/1023"),
            [inv.GoodsReceiptLine(material=l.material, order_line=l, rate=l.rate,
                                  quantity=D("1000") if l.material == steel else l.quantity) for l in po.lines.all()],
            owner)
        stock.post_issue(inv.MaterialIssue(date=today - timedelta(days=2), location=villa.stock_location,
                                           purpose="First floor columns"),
                         [inv.MaterialIssueLine(material=cement, quantity=120),
                          inv.MaterialIssueLine(material=steel, quantity=850)], owner)
        stock.post_adjustment(inv.StockAdjustment(date=today - timedelta(days=30), location=godown),
                              [inv.StockAdjustmentLine(material=bricks, quantity=1500, rate=D("8.50"))], owner)
        stock.save_purchase_order(inv.PurchaseOrder(date=today, supplier=supplier, location=godown),
                                  [inv.PurchaseOrderLine(material=bricks, quantity=5000, rate=D("8.20"), tax_rate=5)],
                                  owner)

        items = [
            WorkItem.objects.create(category="Civil", name="Earthwork excavation", unit=units["Cum"], rate=450,
                                    tax_rate=18),
            WorkItem.objects.create(category="Civil", name="RCC M20 for slab & beams", unit=units["Cum"], rate=8500,
                                    description="Including shuttering and curing", tax_rate=18),
            WorkItem.objects.create(category="Civil", name="Brickwork in CM 1:6", unit=units["Cft"], rate=95,
                                    tax_rate=18),
            WorkItem.objects.create(category="Finishing", name="Vitrified tile flooring", unit=units["Sqft"],
                                    rate=110, tax_rate=18),
        ]
        quote = Quotation.objects.create(
            number=NumberSequence.next_number("quotation", today), date=today - timedelta(days=20),
            valid_until=today + timedelta(days=10), client=client, project=villa,
            subject="Construction of G+1 residential building", discount_percent=2, terms=c.quotation_terms,
            introduction="We are pleased to submit our quotation for the above work as per the drawings shared.",
            status=Quotation.Status.ACCEPTED, created_by=owner)
        for order, (item, qty) in enumerate(zip(items, [120, 85, 9500, 2400])):
            QuotationLine.objects.create(quotation=quote, order=order, item=item, unit=item.unit.symbol,
                                         description=item.name + (f"\n{item.description}" if item.description else ""),
                                         quantity=qty, rate=item.rate, tax_rate=item.tax_rate)
        template = DocumentTemplate.objects.filter(is_default=True).first()
        agreement = Agreement.objects.create(
            number=NumberSequence.next_number("agreement", today), date=today - timedelta(days=15), client=client,
            project=villa, quotation=quote, template=template, contract_value=D("4250000"),
            start_date=today - timedelta(days=10), completion_date=today + timedelta(days=240),
            body=template.body if template else "", created_by=owner)
        for order, (desc, pct) in enumerate([("Advance on signing", 10), ("Foundation & plinth complete", 20),
                                             ("Roof slab complete", 25), ("Brickwork & plastering complete", 25),
                                             ("Flooring & painting complete", 15), ("Handover", 5)]):
            PaymentMilestone.objects.create(agreement=agreement, order=order, description=desc, percent=pct)

        for i, (name, trade, wage_type, rate) in enumerate([
            ("Murugan", "Mason", "daily", 900), ("Lakshmi", "Helper", "daily", 600),
            ("Ravi", "Carpenter", "daily", 1000), ("Priya", "Site Engineer", "monthly", 32000),
        ]):
            emp = Employee.objects.create(code=f"E{i + 1:03}", name=name, designation=trade, wage_type=wage_type,
                                          wage_rate=rate, default_project=villa if i % 2 == 0 else flats)
            for back in range(1, 11):
                day = today - timedelta(days=back)
                status = "week_off" if day.weekday() == c.weekly_off_day else ("absent" if (back + i) % 7 == 0
                                                                               else "present")
                Attendance.objects.create(employee=emp, date=day, project=emp.default_project, status=status)

        if created_owner:
            self.stdout.write(self.style.SUCCESS(
                f"Demo data loaded. Log in as 'owner' with password '{password}' (change it before real use)."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Demo data loaded. Log in as '{owner.username}'."))
