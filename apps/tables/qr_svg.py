"""
Print-quality table QR codes as SVG: rounded dots, square corner "eyes"
(rounded eyes fail on stricter scanners) and a clear centre for the logo.
Error correction H keeps it scannable with the centre covered.
"""

import qrcode


def qr_svg(data, color="#2A2A2C", logo_hole=True, quiet=3):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, border=0)
    qr.add_data(data)
    qr.make(fit=True)
    m = qr.get_matrix()
    n = len(m)

    eyes = [(0, 0), (n - 7, 0), (0, n - 7)]

    def in_eye(r, c):
        return any(er <= r < er + 7 and ec <= c < ec + 7 for er, ec in eyes)

    hole = 0
    if logo_hole:
        hole = int(n * 0.22) | 1  # odd, so it centres on a module
    h0 = (n - hole) // 2

    def in_hole(r, c):
        return hole and h0 - 1 <= r <= h0 + hole and h0 - 1 <= c <= h0 + hole

    parts = []
    for r in range(n):
        for c in range(n):
            if m[r][c] and not in_eye(r, c) and not in_hole(r, c):
                parts.append(f'<rect x="{c + 0.06:.2f}" y="{r + 0.06:.2f}" width="0.88" height="0.88" rx="0.32"/>')
    for er, ec in eyes:
        parts.append(
            f'<rect x="{ec + 0.5}" y="{er + 0.5}" width="6" height="6" fill="none" stroke="{color}" stroke-width="1"/>'
            f'<rect x="{ec + 2}" y="{er + 2}" width="3" height="3"/>'
        )
    size = n + quiet * 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-quiet} {-quiet} {size} {size}" '
        f'shape-rendering="geometricPrecision" role="img" aria-label="QR code">'
        f'<rect x="{-quiet}" y="{-quiet}" width="{size}" height="{size}" fill="#fff"/>'
        f'<g fill="{color}">{"".join(parts)}</g></svg>'
    )
