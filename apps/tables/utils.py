"""
Utility functions for the tables app.
"""

import io
import os

import qrcode
from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image


def generate_table_qr_code(table, base_url=None):
    """
    Generate a QR code for a table that links to the customer ordering page.

    Args:
        table: Table model instance
        base_url: Base URL for the ordering system (optional)

    Returns:
        ContentFile containing the QR code image
    """
    if base_url is None:
        # Use the site URL from settings or default
        base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')

    # The URL that customers will scan to order
    order_url = f"{base_url}/order/t/{table.uuid}/"

    # Create QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(order_url)
    qr.make(fit=True)

    # Create image with custom colors
    img = qr.make_image(fill_color="#1e293b", back_color="white")

    # Convert to PIL Image if not already
    if not isinstance(img, Image.Image):
        img = img.get_image()

    # Save to buffer
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    # Create filename
    filename = f"qr_table_{table.number}_{table.uuid}.png"

    return ContentFile(buffer.read(), name=filename)


def regenerate_table_qr_code(table, base_url=None):
    """
    Regenerate QR code for a table (after UUID change, etc.)

    Args:
        table: Table model instance
        base_url: Base URL for the ordering system (optional)
    """
    import uuid as uuid_module

    # Generate new UUID
    table.uuid = uuid_module.uuid4()

    # Delete old QR code if exists
    if table.qr_code:
        try:
            if os.path.isfile(table.qr_code.path):
                os.remove(table.qr_code.path)
        except Exception:
            pass

    # Generate new QR code
    qr_file = generate_table_qr_code(table, base_url)
    table.qr_code.save(qr_file.name, qr_file, save=False)
    table.save()

    return table
