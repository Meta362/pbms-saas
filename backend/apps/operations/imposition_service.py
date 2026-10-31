import math
from decimal import Decimal
from typing import Any, Dict, List, Tuple


def calculate_sheet_imposition(
    parent_width_mm: float,
    parent_height_mm: float,
    cut_width_mm: float,
    cut_height_mm: float,
    margin_mm: float = 5.0,
    gripper_mm: float = 10.0,
    bleed_mm: float = 2.0,
    target_quantity: int = 1000,
    spoilage_percent: float = 3.0,
) -> Dict[str, Any]:
    """
    PROD-001: Commercial Sheet Imposition & Paper Cut Estimator.
    Calculates optimal 2D cuts per sheet, waste percentage, parent sheets required,
    and generates visual SVG cutting layout diagram.
    """
    parent_w = float(parent_width_mm)
    parent_h = float(parent_height_mm)
    cut_w = float(cut_width_mm)
    cut_h = float(cut_height_mm)
    m = float(margin_mm)
    g = float(gripper_mm)
    b = float(bleed_mm)
    qty = max(1, int(target_quantity))
    spoilage = max(0.0, float(spoilage_percent))

    # Usable area deducting safety margin and offset gripper edge
    usable_w = max(0.0, parent_w - (m * 2.0) - g)
    usable_h = max(0.0, parent_h - (m * 2.0))

    # Finished item dimension including printing bleed
    item_w = cut_w + (b * 2.0)
    item_h = cut_h + (b * 2.0)

    if usable_w < item_w or usable_h < item_h:
        if usable_w < item_h or usable_h < item_w:
            return {
                "error": "Finished item with bleed is larger than the usable sheet area.",
                "cuts_per_sheet": 0,
                "parent_sheets_required": 0,
            }

    # Strategy 1: Standard orientation (unrotated items)
    cols1 = int(usable_w // item_w)
    rows1 = int(usable_h // item_h)
    grid1_count = cols1 * rows1
    placed1: List[Tuple[float, float, float, float, bool]] = []
    for r in range(rows1):
        for c in range(cols1):
            x = m + g + (c * item_w)
            y = m + (r * item_h)
            placed1.append((x, y, item_w, item_h, False))

    # Strategy 1 extra: check remainder on right
    rem_w1 = usable_w - (cols1 * item_w)
    if rem_w1 >= item_h:
        extra_cols = int(rem_w1 // item_h)
        extra_rows = int(usable_h // item_w)
        for er in range(extra_rows):
            for ec in range(extra_cols):
                x = m + g + (cols1 * item_w) + (ec * item_h)
                y = m + (er * item_w)
                placed1.append((x, y, item_h, item_w, True))

    # Strategy 2: Rotated 90 degrees
    cols2 = int(usable_w // item_h)
    rows2 = int(usable_h // item_w)
    placed2: List[Tuple[float, float, float, float, bool]] = []
    for r in range(rows2):
        for c in range(cols2):
            x = m + g + (c * item_h)
            y = m + (r * item_w)
            placed2.append((x, y, item_h, item_w, True))

    # Strategy 2 extra: check remainder on right
    rem_w2 = usable_w - (cols2 * item_h)
    if rem_w2 >= item_w:
        extra_cols = int(rem_w2 // item_w)
        extra_rows = int(usable_h // item_h)
        for er in range(extra_rows):
            for ec in range(extra_cols):
                x = m + g + (cols2 * item_h) + (ec * item_w)
                y = m + (er * item_h)
                placed2.append((x, y, item_w, item_h, False))

    # Choose the layout with maximum yield
    if len(placed2) > len(placed1):
        best_placed = placed2
        orientation = "ROTATED_90"
    else:
        best_placed = placed1
        orientation = "STANDARD"

    cuts_per_sheet = len(best_placed)
    if cuts_per_sheet <= 0:
        return {
            "error": "No items could be placed on the sheet.",
            "cuts_per_sheet": 0,
            "parent_sheets_required": 0,
        }

    # Gross units with spoilage allowance
    gross_units = math.ceil(qty * (1.0 + (spoilage / 100.0)))
    parent_sheets_required = math.ceil(gross_units / cuts_per_sheet)
    net_sheets = math.ceil(qty / cuts_per_sheet)
    spoilage_sheets = parent_sheets_required - net_sheets

    # Efficiency & Waste
    sheet_area = parent_w * parent_h
    finished_cut_area = cuts_per_sheet * (cut_w * cut_h)
    efficiency_pct = round((finished_cut_area / sheet_area) * 100.0, 2)
    waste_pct = round(100.0 - efficiency_pct, 2)

    # Generate Layout Diagram SVG
    svg_markup = _generate_imposition_svg(
        parent_w=parent_w,
        parent_h=parent_h,
        margin=m,
        gripper=g,
        placed=best_placed,
        cuts_per_sheet=cuts_per_sheet,
    )

    return {
        "parent_sheet_width_mm": parent_w,
        "parent_sheet_height_mm": parent_h,
        "cut_width_mm": cut_w,
        "cut_height_mm": cut_h,
        "margin_mm": m,
        "gripper_mm": g,
        "bleed_mm": b,
        "target_quantity": qty,
        "spoilage_percent": spoilage,
        "cuts_per_sheet": cuts_per_sheet,
        "orientation": orientation,
        "parent_sheets_required": parent_sheets_required,
        "net_sheets": net_sheets,
        "spoilage_sheets": spoilage_sheets,
        "efficiency_percent": efficiency_pct,
        "waste_percent": waste_pct,
        "layout_svg": svg_markup,
    }


def _generate_imposition_svg(
    parent_w: float,
    parent_h: float,
    margin: float,
    gripper: float,
    placed: List[Tuple[float, float, float, float, bool]],
    cuts_per_sheet: int,
) -> str:
    """
    Renders clean, proportional vector SVG visualization of sheet cutting layout.
    """
    # Viewbox matches sheet dimensions
    vb_w = parent_w
    vb_h = parent_h

    cuts_svg: List[str] = []
    for idx, (x, y, w, h, is_rot) in enumerate(placed, start=1):
        # Color unrotated vs rotated distinctly for quick visual identification
        fill_color = "#38BDF8" if not is_rot else "#818CF8"  # Sky blue vs Indigo
        stroke_color = "#0284C7" if not is_rot else "#4F46E5"
        rx = round(x, 1)
        ry = round(y, 1)
        rw = round(w, 1)
        rh = round(h, 1)

        font_size = max(10, min(rw, rh) * 0.28)
        cx = rx + (rw / 2.0)
        cy = ry + (rh / 2.0)

        cut_rect = (
            f'  <rect x="{rx}" y="{ry}" width="{rw}" height="{rh}" '
            f'fill="{fill_color}" fill-opacity="0.85" stroke="{stroke_color}" stroke-width="1" rx="2"/>\n'
            f'  <text x="{cx}" y="{cy + (font_size*0.35)}" font-family="system-ui, sans-serif" font-size="{font_size:.1f}" '
            f'font-weight="bold" fill="#FFFFFF" text-anchor="middle">#{idx}</text>'
        )
        cuts_svg.append(cut_rect)

    cuts_str = "\n".join(cuts_svg)

    # Gripper zone indicator (left side edge)
    gripper_zone = (
        f'  <rect x="{margin}" y="{margin}" width="{gripper}" height="{parent_h - (margin*2)}" '
        f'fill="#F43F5E" fill-opacity="0.15" stroke="#E11D48" stroke-dasharray="3,3" stroke-width="1"/>\n'
        f'  <text x="{margin + (gripper/2)}" y="{parent_h / 2}" font-family="system-ui, sans-serif" font-size="10" '
        f'fill="#E11D48" font-weight="bold" transform="rotate(-90 {margin + (gripper/2)} {parent_h / 2})" text-anchor="middle">GRIPPER {gripper}mm</text>'
    )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vb_w} {vb_h}" '
        f'width="100%" height="auto" style="max-height: 480px; display: block; margin: auto; background: #F8FAFC; border-radius: 12px;">\n'
        f'  <!-- Parent Sheet Boundary -->\n'
        f'  <rect x="0" y="0" width="{vb_w}" height="{vb_h}" fill="#FFFFFF" stroke="#94A3B8" stroke-width="2" rx="4"/>\n'
        f'  <!-- Gripper Edge -->\n'
        f'{gripper_zone}\n'
        f'  <!-- Placed Finished Cuts ({cuts_per_sheet}-Up) -->\n'
        f'{cuts_str}\n'
        f'</svg>'
    )
    return svg
