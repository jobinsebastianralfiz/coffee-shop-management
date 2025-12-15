"""
ESC/POS Commands for thermal printers.
Standard commands compatible with most Epson-compatible thermal printers.
"""


# ESC/POS Command Constants
class Commands:
    """ESC/POS command codes."""

    # Initialization
    INIT = b'\x1b\x40'  # Initialize printer

    # Line Feed
    LF = b'\x0a'  # Line feed
    CR = b'\x0d'  # Carriage return

    # Text Formatting
    BOLD_ON = b'\x1b\x45\x01'
    BOLD_OFF = b'\x1b\x45\x00'

    UNDERLINE_ON = b'\x1b\x2d\x01'
    UNDERLINE_OFF = b'\x1b\x2d\x00'

    DOUBLE_HEIGHT_ON = b'\x1b\x21\x10'
    DOUBLE_WIDTH_ON = b'\x1b\x21\x20'
    DOUBLE_SIZE_ON = b'\x1b\x21\x30'
    NORMAL_SIZE = b'\x1b\x21\x00'

    # Alignment
    ALIGN_LEFT = b'\x1b\x61\x00'
    ALIGN_CENTER = b'\x1b\x61\x01'
    ALIGN_RIGHT = b'\x1b\x61\x02'

    # Paper Cut
    CUT_FULL = b'\x1d\x56\x00'  # Full cut
    CUT_PARTIAL = b'\x1d\x56\x01'  # Partial cut
    CUT_FEED = b'\x1d\x56\x42\x00'  # Feed and cut

    # Cash Drawer
    OPEN_DRAWER_PIN2 = b'\x1b\x70\x00\x19\x78'  # Open drawer (pin 2)
    OPEN_DRAWER_PIN5 = b'\x1b\x70\x01\x19\x78'  # Open drawer (pin 5)

    # Horizontal Line (using underscore characters)
    HORIZONTAL_LINE = b'-' * 32 + b'\x0a'

    # Barcode Commands
    BARCODE_HEIGHT = b'\x1d\x68\x50'  # Set barcode height
    BARCODE_WIDTH = b'\x1d\x77\x02'  # Set barcode width
    BARCODE_TEXT_BELOW = b'\x1d\x48\x02'  # Print barcode text below


class TextFormatter:
    """Helper class for formatting text for thermal printers."""

    def __init__(self, width=32):
        """Initialize with paper width (characters)."""
        self.width = width

    def center(self, text):
        """Center text within paper width."""
        return text.center(self.width)

    def left(self, text):
        """Left-align text."""
        return text.ljust(self.width)

    def right(self, text):
        """Right-align text."""
        return text.rjust(self.width)

    def line(self, char='-'):
        """Create a horizontal line."""
        return char * self.width

    def double_line(self):
        """Create a double horizontal line."""
        return '=' * self.width

    def format_row(self, left_text, right_text, fill_char=' '):
        """Format a row with left and right aligned text."""
        available_space = self.width - len(left_text) - len(right_text)
        if available_space < 1:
            # Truncate left text if needed
            left_text = left_text[:self.width - len(right_text) - 1]
            available_space = 1
        return f"{left_text}{fill_char * available_space}{right_text}"

    def format_item_row(self, qty, name, price):
        """Format an item row with quantity, name, and price."""
        qty_str = f"{qty}x "
        price_str = f" {price}"
        name_width = self.width - len(qty_str) - len(price_str)

        if len(name) > name_width:
            name = name[:name_width - 2] + ".."

        return f"{qty_str}{name.ljust(name_width)}{price_str}"

    def wrap_text(self, text, indent=0):
        """Wrap text to fit within paper width."""
        lines = []
        words = text.split()
        current_line = ' ' * indent

        for word in words:
            if len(current_line) + len(word) + 1 <= self.width:
                if current_line.strip():
                    current_line += ' ' + word
                else:
                    current_line = ' ' * indent + word
            else:
                if current_line.strip():
                    lines.append(current_line)
                current_line = ' ' * indent + word

        if current_line.strip():
            lines.append(current_line)

        return '\n'.join(lines)


class ReceiptBuilder:
    """Builder class for constructing receipt data."""

    def __init__(self, width=32):
        """Initialize receipt builder."""
        self.width = width
        self.formatter = TextFormatter(width)
        self.data = bytearray()

    def init(self):
        """Initialize printer."""
        self.data.extend(Commands.INIT)
        return self

    def newline(self, count=1):
        """Add line feeds."""
        self.data.extend(Commands.LF * count)
        return self

    def align_center(self):
        """Set center alignment."""
        self.data.extend(Commands.ALIGN_CENTER)
        return self

    def align_left(self):
        """Set left alignment."""
        self.data.extend(Commands.ALIGN_LEFT)
        return self

    def align_right(self):
        """Set right alignment."""
        self.data.extend(Commands.ALIGN_RIGHT)
        return self

    def bold_on(self):
        """Enable bold text."""
        self.data.extend(Commands.BOLD_ON)
        return self

    def bold_off(self):
        """Disable bold text."""
        self.data.extend(Commands.BOLD_OFF)
        return self

    def double_size(self):
        """Enable double size text."""
        self.data.extend(Commands.DOUBLE_SIZE_ON)
        return self

    def double_height(self):
        """Enable double height text."""
        self.data.extend(Commands.DOUBLE_HEIGHT_ON)
        return self

    def double_width(self):
        """Enable double width text."""
        self.data.extend(Commands.DOUBLE_WIDTH_ON)
        return self

    def normal_size(self):
        """Reset to normal size text."""
        self.data.extend(Commands.NORMAL_SIZE)
        return self

    def text(self, text):
        """Add text."""
        self.data.extend(text.encode('utf-8', errors='replace'))
        return self

    def line(self, text):
        """Add text with newline."""
        self.text(text)
        self.newline()
        return self

    def horizontal_line(self, char='-'):
        """Add a horizontal line."""
        self.line(self.formatter.line(char))
        return self

    def double_horizontal_line(self):
        """Add a double horizontal line."""
        self.line(self.formatter.double_line())
        return self

    def row(self, left, right):
        """Add a formatted row with left and right aligned text."""
        self.line(self.formatter.format_row(left, right))
        return self

    def item_row(self, qty, name, price):
        """Add an item row."""
        self.line(self.formatter.format_item_row(qty, name, price))
        return self

    def cut(self, partial=False):
        """Cut paper."""
        self.newline(3)
        self.data.extend(Commands.CUT_PARTIAL if partial else Commands.CUT_FULL)
        return self

    def open_drawer(self):
        """Open cash drawer."""
        self.data.extend(Commands.OPEN_DRAWER_PIN2)
        return self

    def get_data(self):
        """Get the built receipt data."""
        return bytes(self.data)


class KOTBuilder(ReceiptBuilder):
    """Builder class for Kitchen Order Tickets."""

    def __init__(self, width=32):
        """Initialize KOT builder with larger default text."""
        super().__init__(width)

    def header(self, ticket_number, table_info, priority="NORMAL"):
        """Add KOT header."""
        self.init()
        self.align_center()
        self.double_size()
        self.bold_on()
        self.line("*** KITCHEN ORDER ***")
        self.normal_size()
        self.bold_off()
        self.newline()

        self.align_left()
        self.bold_on()
        self.line(f"KOT #: {ticket_number}")
        self.line(f"Table: {table_info}")
        if priority and priority.upper() != "NORMAL":
            self.double_size()
            self.line(f"!!! {priority.upper()} !!!")
            self.normal_size()
        self.bold_off()
        self.horizontal_line()

        return self

    def items(self, items_list):
        """Add items to KOT."""
        self.double_height()
        for item in items_list:
            qty = item.get('quantity', 1)
            name = item.get('name', '')
            self.line(f"{qty}x {name}")

            # Special instructions
            instructions = item.get('special_instructions', '')
            if instructions:
                self.normal_size()
                self.line(f"   >> {instructions}")
                self.double_height()

        self.normal_size()
        return self

    def notes(self, note_text):
        """Add kitchen notes."""
        if note_text:
            self.horizontal_line()
            self.bold_on()
            self.line("NOTES:")
            self.bold_off()
            self.line(note_text)
        return self

    def footer(self, timestamp):
        """Add KOT footer."""
        self.horizontal_line()
        self.align_center()
        self.line(timestamp)
        self.cut()
        return self
