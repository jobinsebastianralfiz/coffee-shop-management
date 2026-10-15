"""
Barcode generation and management service for the Retail module.

Supports multiple barcode formats:
- EAN-13: Standard retail barcode (13 digits)
- EAN-8: Short retail barcode (8 digits)
- CODE-128: Variable length alphanumeric
- CODE-39: Alphanumeric industrial
- UPC-A: US retail standard (12 digits)
- QR Code: 2D matrix barcode
"""

import io
import os
from decimal import Decimal
from typing import Optional, Tuple

from django.conf import settings
from django.core.files.base import ContentFile

try:
    import barcode
    from barcode.writer import ImageWriter
    BARCODE_AVAILABLE = True
except ImportError:
    BARCODE_AVAILABLE = False

try:
    import qrcode
    from qrcode.image.pil import PilImage
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


class BarcodeService:
    """
    Service for generating barcodes, QR codes, and product labels.
    """

    # Standard label sizes in mm (width, height)
    LABEL_SIZES = {
        'small': (38, 25),      # 38mm x 25mm
        'medium': (50, 30),     # 50mm x 30mm
        'large': (60, 40),      # 60mm x 40mm
        'shelf': (80, 50),      # 80mm x 50mm - for shelf labels
    }

    # DPI for label printing
    LABEL_DPI = 203  # Standard thermal printer DPI

    def __init__(self):
        self.barcode_prefix = getattr(settings, 'BARCODE_PREFIX', '869')
        self.default_type = getattr(settings, 'DEFAULT_BARCODE_TYPE', 'EAN13')

    @staticmethod
    def check_dependencies():
        """Check if required dependencies are installed."""
        missing = []
        if not BARCODE_AVAILABLE:
            missing.append('python-barcode')
        if not QRCODE_AVAILABLE:
            missing.append('qrcode[pil]')
        if not PIL_AVAILABLE:
            missing.append('Pillow')
        if not REPORTLAB_AVAILABLE:
            missing.append('reportlab')
        return missing

    def calculate_ean13_checksum(self, digits: str) -> str:
        """
        Calculate EAN-13 check digit.

        Args:
            digits: First 12 digits of the barcode

        Returns:
            The check digit as a string
        """
        if len(digits) != 12:
            raise ValueError("EAN-13 requires exactly 12 digits before checksum")

        odd_sum = sum(int(digits[i]) for i in range(0, 12, 2))
        even_sum = sum(int(digits[i]) for i in range(1, 12, 2))
        total = odd_sum + (even_sum * 3)
        check_digit = (10 - (total % 10)) % 10

        return str(check_digit)

    def generate_ean13(self, product_id: int) -> str:
        """
        Generate a valid EAN-13 barcode value for a product.

        Format: PPP + MMMMMMMM + C
        - PPP: 3-digit country prefix (from settings)
        - MMMMMMMM: 8-digit product ID (zero-padded)
        - C: 1-digit check digit

        Args:
            product_id: The product's database ID

        Returns:
            A valid 13-digit EAN-13 barcode string
        """
        prefix = self.barcode_prefix[:3].zfill(3)
        product_code = str(product_id).zfill(8)[:8]

        base_code = prefix + product_code
        check_digit = self.calculate_ean13_checksum(base_code)

        return base_code + check_digit

    def generate_ean8(self, product_id: int) -> str:
        """
        Generate a valid EAN-8 barcode value.

        Format: PP + MMMMM + C
        - PP: 2-digit prefix
        - MMMMM: 5-digit product ID
        - C: 1-digit check digit
        """
        prefix = self.barcode_prefix[:2].zfill(2)
        product_code = str(product_id).zfill(5)[:5]

        base_code = prefix + product_code

        # EAN-8 checksum calculation
        odd_sum = sum(int(base_code[i]) for i in range(0, 7, 2))
        even_sum = sum(int(base_code[i]) for i in range(1, 7, 2))
        total = (odd_sum * 3) + even_sum
        check_digit = (10 - (total % 10)) % 10

        return base_code + str(check_digit)

    def generate_code128(self, value: str) -> str:
        """
        Generate a CODE-128 barcode value.
        CODE-128 accepts alphanumeric values.
        """
        # CODE-128 can handle the value directly
        return value.upper()[:48]  # Max reasonable length

    def generate_barcode_image(
        self,
        value: str,
        barcode_type: str = 'EAN13',
        include_text: bool = True
    ) -> Tuple[bytes, str]:
        """
        Generate a barcode image.

        Args:
            value: The barcode value/number
            barcode_type: Type of barcode (EAN13, EAN8, CODE128, CODE39, UPCA)
            include_text: Whether to include the number below the barcode

        Returns:
            Tuple of (image bytes, filename)
        """
        if not BARCODE_AVAILABLE:
            raise ImportError("python-barcode library is required for barcode generation")

        barcode_type_map = {
            'EAN13': 'ean13',
            'EAN8': 'ean8',
            'CODE128': 'code128',
            'CODE39': 'code39',
            'UPCA': 'upca',
        }

        bc_type = barcode_type_map.get(barcode_type.upper(), 'ean13')

        # python-barcode library calculates checksum itself, so we need to strip it
        # EAN-13 expects 12 digits, EAN-8 expects 7 digits, UPC-A expects 11 digits
        barcode_value = value
        if bc_type == 'ean13' and len(value) == 13 and value.isdigit():
            barcode_value = value[:12]  # Strip checksum digit
        elif bc_type == 'ean8' and len(value) == 8 and value.isdigit():
            barcode_value = value[:7]  # Strip checksum digit
        elif bc_type == 'upca' and len(value) == 12 and value.isdigit():
            barcode_value = value[:11]  # Strip checksum digit

        # Create barcode
        bc_class = barcode.get_barcode_class(bc_type)

        # Configure writer options
        writer = ImageWriter()
        writer_options = {
            'module_width': 0.4,
            'module_height': 15.0,
            'font_size': 10,
            'text_distance': 5.0,
            'quiet_zone': 6.5,
            'write_text': include_text,
        }

        bc = bc_class(barcode_value, writer=writer)

        # Generate image to buffer
        buffer = io.BytesIO()
        bc.write(buffer, options=writer_options)
        buffer.seek(0)

        filename = f"barcode_{value}.png"  # Use original value for filename
        return buffer.getvalue(), filename

    def generate_qr_code(
        self,
        data: str,
        size: int = 200,
        error_correction: str = 'M'
    ) -> Tuple[bytes, str]:
        """
        Generate a QR code image.

        Args:
            data: The data to encode in the QR code
            size: Target size in pixels
            error_correction: Error correction level (L, M, Q, H)

        Returns:
            Tuple of (image bytes, filename)
        """
        if not QRCODE_AVAILABLE:
            raise ImportError("qrcode library is required for QR code generation")

        error_levels = {
            'L': qrcode.constants.ERROR_CORRECT_L,
            'M': qrcode.constants.ERROR_CORRECT_M,
            'Q': qrcode.constants.ERROR_CORRECT_Q,
            'H': qrcode.constants.ERROR_CORRECT_H,
        }

        qr = qrcode.QRCode(
            version=1,
            error_correction=error_levels.get(error_correction.upper(), qrcode.constants.ERROR_CORRECT_M),
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Resize if needed
        if img.size[0] != size:
            img = img.resize((size, size), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        # Create a safe filename
        safe_data = ''.join(c for c in data[:20] if c.isalnum())
        filename = f"qr_{safe_data}.png"

        return buffer.getvalue(), filename

    def generate_product_label(
        self,
        product_name: str,
        barcode_value: str,
        price: Decimal,
        currency_symbol: str = '₹',
        mrp: Optional[Decimal] = None,
        label_size: str = 'medium',
        barcode_type: str = 'EAN13'
    ) -> Tuple[bytes, str]:
        """
        Generate a complete product label with barcode, name, and price.

        Args:
            product_name: Name of the product
            barcode_value: The barcode number
            price: Selling price
            currency_symbol: Currency symbol to display
            mrp: Maximum retail price (optional, shown if different from price)
            label_size: Size preset ('small', 'medium', 'large', 'shelf')
            barcode_type: Type of barcode to generate

        Returns:
            Tuple of (image bytes, filename)
        """
        if not PIL_AVAILABLE:
            raise ImportError("Pillow library is required for label generation")

        # Get label dimensions in pixels
        size_mm = self.LABEL_SIZES.get(label_size, self.LABEL_SIZES['medium'])
        width_px = int(size_mm[0] * self.LABEL_DPI / 25.4)
        height_px = int(size_mm[1] * self.LABEL_DPI / 25.4)

        # Create white background
        img = Image.new('RGB', (width_px, height_px), 'white')
        draw = ImageDraw.Draw(img)

        # Try to load a better font, fall back to default
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
            font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
        except (IOError, OSError):
            font_large = ImageFont.load_default()
            font_medium = font_large
            font_small = font_large

        # Layout calculations
        padding = 10
        current_y = padding

        # Product name (truncate if too long)
        max_name_len = 20 if label_size == 'small' else 30
        display_name = product_name[:max_name_len]
        if len(product_name) > max_name_len:
            display_name = display_name[:-3] + '...'

        draw.text((padding, current_y), display_name, fill='black', font=font_medium)
        current_y += 25

        # Generate and paste barcode
        try:
            barcode_bytes, _ = self.generate_barcode_image(
                barcode_value,
                barcode_type,
                include_text=True
            )
            barcode_img = Image.open(io.BytesIO(barcode_bytes))

            # Scale barcode to fit
            max_barcode_width = width_px - (2 * padding)
            max_barcode_height = height_px - current_y - 40  # Leave room for price

            scale = min(
                max_barcode_width / barcode_img.width,
                max_barcode_height / barcode_img.height,
                1.0  # Don't scale up
            )

            new_size = (int(barcode_img.width * scale), int(barcode_img.height * scale))
            barcode_img = barcode_img.resize(new_size, Image.Resampling.LANCZOS)

            # Center barcode horizontally
            barcode_x = (width_px - barcode_img.width) // 2
            img.paste(barcode_img, (barcode_x, current_y))

            current_y += barcode_img.height + 5
        except Exception:
            # If barcode generation fails, show the value as text
            draw.text((padding, current_y), barcode_value, fill='black', font=font_small)
            current_y += 20

        # Price section
        price_text = f"{currency_symbol}{price:.2f}"

        if mrp and mrp > price:
            # Show MRP crossed out and selling price
            mrp_text = f"MRP: {currency_symbol}{mrp:.2f}"
            draw.text((padding, current_y), mrp_text, fill='gray', font=font_small)
            # Draw strikethrough
            bbox = draw.textbbox((padding, current_y), mrp_text, font=font_small)
            draw.line([(bbox[0], bbox[1] + 7), (bbox[2], bbox[1] + 7)], fill='gray', width=1)
            current_y += 18

        # Bold price
        draw.text((padding, current_y), price_text, fill='black', font=font_large)

        # Save to buffer
        buffer = io.BytesIO()
        img.save(buffer, format='PNG', dpi=(self.LABEL_DPI, self.LABEL_DPI))
        buffer.seek(0)

        filename = f"label_{barcode_value}.png"
        return buffer.getvalue(), filename

    def generate_batch_labels_pdf(
        self,
        products: list,
        label_size: str = 'medium',
        labels_per_row: int = 3,
        page_size: str = 'A4'
    ) -> Tuple[bytes, str]:
        """
        Generate a PDF with multiple product labels for batch printing.

        Args:
            products: List of dicts with 'name', 'barcode', 'price', 'quantity', 'mrp'
            label_size: Size preset for each label
            labels_per_row: Number of labels per row
            page_size: Paper size ('A4' or 'letter')

        Returns:
            Tuple of (PDF bytes, filename)
        """
        if not REPORTLAB_AVAILABLE:
            raise ImportError("reportlab library is required for PDF generation")

        page = A4 if page_size == 'A4' else letter

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=page)

        page_width, page_height = page
        margin = 10 * mm

        # Get label size in points
        size_mm = self.LABEL_SIZES.get(label_size, self.LABEL_SIZES['medium'])
        label_width = size_mm[0] * mm
        label_height = size_mm[1] * mm

        # Calculate spacing
        usable_width = page_width - (2 * margin)
        col_spacing = (usable_width - (labels_per_row * label_width)) / (labels_per_row - 1) if labels_per_row > 1 else 0

        row_spacing = 5 * mm

        # Current position
        current_x = margin
        current_y = page_height - margin - label_height
        col = 0

        for product in products:
            quantity = product.get('quantity', 1)

            for _ in range(quantity):
                # Generate label image
                try:
                    label_bytes, _ = self.generate_product_label(
                        product_name=product['name'],
                        barcode_value=product['barcode'],
                        price=product['price'],
                        mrp=product.get('mrp'),
                        label_size=label_size,
                        barcode_type=product.get('barcode_type', 'EAN13')
                    )

                    label_img = Image.open(io.BytesIO(label_bytes))

                    # Draw label on PDF
                    c.drawImage(
                        ImageReader(label_img),
                        current_x,
                        current_y,
                        width=label_width,
                        height=label_height
                    )
                except Exception as e:
                    # Draw placeholder rectangle with error
                    c.rect(current_x, current_y, label_width, label_height)
                    c.drawString(current_x + 5, current_y + label_height/2, f"Error: {str(e)[:30]}")

                # Move to next position
                col += 1
                if col >= labels_per_row:
                    col = 0
                    current_x = margin
                    current_y -= (label_height + row_spacing)

                    # Check if need new page
                    if current_y < margin:
                        c.showPage()
                        current_y = page_height - margin - label_height
                else:
                    current_x += label_width + col_spacing

        c.save()
        buffer.seek(0)

        return buffer.getvalue(), "batch_labels.pdf"

    def validate_barcode(self, value: str, barcode_type: str = 'EAN13') -> Tuple[bool, str]:
        """
        Validate a barcode value.

        Args:
            value: The barcode value to validate
            barcode_type: Type of barcode

        Returns:
            Tuple of (is_valid, error_message)
        """
        if barcode_type == 'EAN13':
            if len(value) != 13:
                return False, "EAN-13 must be exactly 13 digits"
            if not value.isdigit():
                return False, "EAN-13 must contain only digits"

            # Validate checksum
            expected_check = self.calculate_ean13_checksum(value[:12])
            if value[12] != expected_check:
                return False, f"Invalid checksum. Expected {expected_check}"

            return True, ""

        elif barcode_type == 'EAN8':
            if len(value) != 8:
                return False, "EAN-8 must be exactly 8 digits"
            if not value.isdigit():
                return False, "EAN-8 must contain only digits"
            return True, ""

        elif barcode_type in ('CODE128', 'CODE39'):
            if not value:
                return False, "Barcode value cannot be empty"
            if len(value) > 48:
                return False, "Barcode value too long (max 48 characters)"
            return True, ""

        elif barcode_type == 'UPCA':
            if len(value) != 12:
                return False, "UPC-A must be exactly 12 digits"
            if not value.isdigit():
                return False, "UPC-A must contain only digits"
            return True, ""

        elif barcode_type == 'QR':
            if not value:
                return False, "QR code data cannot be empty"
            return True, ""

        return False, f"Unknown barcode type: {barcode_type}"


# Singleton instance
barcode_service = BarcodeService()
