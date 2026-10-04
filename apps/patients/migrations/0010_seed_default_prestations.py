from django.db import migrations


def seed_default_prestations(apps, schema_editor):
    Prestation = apps.get_model("patients", "Prestation")
    defaults = [
        {
            "name": "Consultation Générale",
            "code": "CONS_GEN",
            "category": "CONSULTATION",
            "standard_price": 10000.00,
            "is_active": True,
        },
        {
            "name": "Consultation Spécialisée",
            "code": "CONS_SPEC",
            "category": "CONSULTATION",
            "standard_price": 15000.00,
            "is_active": True,
        },
        {
            "name": "Échographie Abdominale",
            "code": "ECHO_ABD",
            "category": "IMAGERIE",
            "standard_price": 25000.00,
            "is_active": True,
        },
        {
            "name": "Électrocardiogramme (ECG)",
            "code": "ECG_STD",
            "category": "CARDIO",
            "standard_price": 15000.00,
            "is_active": True,
        },
        {
            "name": "Prise de sang / Bilan biologique",
            "code": "LAB_BLOOD",
            "category": "LABORATOIRE",
            "standard_price": 8000.00,
            "is_active": True,
        },
        {
            "name": "Soins infirmiers / Pansement",
            "code": "SOIN_INF",
            "category": "SOINS",
            "standard_price": 5000.00,
            "is_active": True,
        },
    ]

    for item in defaults:
        Prestation.objects.get_or_create(code=item["code"], defaults=item)


def unseed_default_prestations(apps, schema_editor):
    Prestation = apps.get_model("patients", "Prestation")
    Prestation.objects.filter(code__in=["CONS_GEN", "CONS_SPEC", "ECHO_ABD", "ECG_STD", "LAB_BLOOD", "SOIN_INF"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("patients", "0009_alter_patient_allergies_consultation_facture_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_default_prestations, reverse_code=unseed_default_prestations),
    ]
