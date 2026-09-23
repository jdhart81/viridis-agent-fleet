#!/usr/bin/env python3
"""Build the one-page Regulatory Change Evidence Pack pilot scope PDF."""

from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


NAVY = colors.HexColor("#0A2342")
TEAL = colors.HexColor("#0F766E")
TEAL_LIGHT = colors.HexColor("#CCFBF1")
INK = colors.HexColor("#243447")
MUTED = colors.HexColor("#5B6777")
PAPER = colors.HexColor("#F8FAFC")
BORDER = colors.HexColor("#CBD5E1")
WHITE = colors.white


def make_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "kicker": ParagraphStyle(
            "Kicker", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=7.2, leading=9, textColor=TEAL, spaceAfter=5,
        ),
        "title": ParagraphStyle(
            "Title", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=20, leading=22, textColor=NAVY, spaceAfter=5,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle", parent=base["Normal"], fontName="Helvetica",
            fontSize=8.5, leading=11.2, textColor=MUTED, spaceAfter=8,
        ),
        "section": ParagraphStyle(
            "Section", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=10.2, leading=12.5, textColor=NAVY, spaceBefore=2,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["BodyText"], fontName="Helvetica",
            fontSize=7.25, leading=9.35, textColor=INK,
        ),
        "small": ParagraphStyle(
            "Small", parent=base["BodyText"], fontName="Helvetica",
            fontSize=6.35, leading=8.2, textColor=MUTED,
        ),
        "metric": ParagraphStyle(
            "Metric", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=13, leading=14, textColor=NAVY, alignment=TA_CENTER,
        ),
        "metric_label": ParagraphStyle(
            "MetricLabel", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=5.9, leading=7.2, textColor=MUTED, alignment=TA_CENTER,
        ),
        "white": ParagraphStyle(
            "White", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=7.2, leading=9.2, textColor=WHITE,
        ),
    }


def metric(value: str, label: str, styles: dict[str, ParagraphStyle]) -> Table:
    card = Table(
        [[Paragraph(value, styles["metric"])], [Paragraph(label, styles["metric_label"])]],
        colWidths=[1.68 * inch],
    )
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PAPER),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
        ("TOPPADDING", (0, 1), (-1, 1), 1),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 5),
    ]))
    return card


def bullet(text: str, styles: dict[str, ParagraphStyle]) -> Paragraph:
    return Paragraph(f"<font color='#0F766E'>+</font>&nbsp; {text}", styles["body"])


def on_page(canvas, document) -> None:
    canvas.saveState()
    canvas.setTitle("Regulatory Change Evidence Pack - 30-day pilot scope")
    canvas.setAuthor("Viridis Agent Fleet")
    canvas.setSubject("Buyer-ready design-partner pilot scope")
    canvas.setStrokeColor(BORDER)
    canvas.line(44, 31, LETTER[0] - 44, 31)
    canvas.setFont("Helvetica", 6.3)
    canvas.setFillColor(MUTED)
    canvas.drawString(44, 19, "VIRIDIS AGENT FLEET / SCREENING ONLY - NOT LEGAL ADVICE")
    canvas.drawRightString(LETTER[0] - 44, 19, "PILOT SCOPE / 14 AUG 2026")
    canvas.restoreState()


def build(output_pdf: Path) -> None:
    styles = make_styles()
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(output_pdf), pagesize=LETTER,
        leftMargin=44, rightMargin=44, topMargin=35, bottomMargin=39,
        title="Regulatory Change Evidence Pack - 30-day pilot scope",
        author="Viridis Agent Fleet",
    )

    story = [
        Paragraph("VIRIDIS AGENT FLEET / DESIGN-PARTNER OFFER", styles["kicker"]),
        Paragraph("Regulatory Change Evidence Pack", styles["title"]),
        Paragraph(
            "A bounded 30-day pilot for sustainability and ESG advisory teams that need traceable, "
            "official-source monitoring without replacing legal or professional judgment.",
            styles["subtitle"],
        ),
    ]

    metric_row = Table([[
        metric("$500", "30-DAY PILOT", styles),
        metric("1", "JURISDICTION", styles),
        metric("UP TO 5", "OFFICIAL SOURCES", styles),
        metric("WEEKLY", "OBSERVATIONS", styles),
    ]], colWidths=[1.72 * inch] * 4)
    metric_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.extend([metric_row, Spacer(1, 7)])

    outcome = Table([
        [Paragraph("INTENDED OUTCOME", styles["white"])],
        [Paragraph(
            "Reduce the manual evidence work required to notice, document, and route material "
            "changes on named official regulator pages.", styles["body"]
        )],
    ], colWidths=[7.0 * inch])
    outcome.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("BACKGROUND", (0, 1), (-1, 1), TEAL_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.7, TEAL),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 1), (-1, 1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
    ]))
    story.extend([outcome, Spacer(1, 7)])

    included = [
        "Initial source baseline with retrieval timestamps and SHA-256 hashes",
        "Weekly unchanged, changed, or failed-retrieval observations",
        "Bounded before-and-after text diff when monitored text changes",
        "Source-linked deadline and effective-date layer",
        "Screening questions and action-owner prompts",
        "Machine-readable JSON and buyer-readable PDF",
        "Buyer delivery, usefulness, and would-buy-again receipt fields",
    ]
    buyer = [
        "Jurisdiction or regulatory topic",
        "Up to five official pages, or approval for Viridis to propose them",
        "Nonconfidential reporting or advisory context",
        "Named reviewer or review role",
        "Preferred delivery day, time zone, and route",
    ]
    two_col = Table([[
        [Paragraph("WHAT IS INCLUDED", styles["section"])] + [bullet(item, styles) for item in included],
        [Paragraph("WHAT THE BUYER PROVIDES", styles["section"])] + [bullet(item, styles) for item in buyer],
    ]], colWidths=[3.56 * inch, 3.28 * inch])
    two_col.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (0, 0), 0.55, BORDER),
        ("BOX", (1, 0), (1, 0), 0.55, BORDER),
        ("BACKGROUND", (0, 0), (-1, -1), PAPER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([two_col, Spacer(1, 7)])

    story.append(Paragraph("PILOT WORKFLOW", styles["section"]))
    steps = [
        ("1", "Agree source list and screening context"),
        ("2", "Confirm exact payment path"),
        ("3", "Create source-hashed baseline"),
        ("4", "Deliver weekly observations and diffs"),
        ("5", "Record receipt and separate feedback"),
        ("6", "Stop or agree to another paid period"),
    ]
    workflow = Table(
        [[Paragraph(f"<b>{n}</b><br/>{label}", styles["small"]) for n, label in steps]],
        colWidths=[1.16 * inch] * 6,
    )
    workflow.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PAPER),
        ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([workflow, Spacer(1, 7)])

    boundaries = (
        "<b>BOUNDARIES</b> - Technology-assisted screening, not legal advice. No legal conclusion, "
        "applicability determination, assurance opinion, filing, submission, or regulator communication. "
        "A new baseline is not a detected change, and a hash change is not automatically a legal change. "
        "A qualified reviewer remains responsible for interpretation and action."
    )
    boundary_box = Table([[Paragraph(boundaries, styles["body"])]], colWidths=[7.0 * inch])
    boundary_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF7ED")),
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#C2410C")),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([boundary_box, Spacer(1, 7)])

    acceptance = (
        "<b>ACCEPTANCE AND PAYMENT GATE</b><br/>Reply with the jurisdiction/topic, official sources, "
        "reviewer role, and delivery cadence. Written scope acceptance must come before Justin authorizes "
        "an invoice, payment link, checkout, or subscription. Work begins only after the agreed payment "
        "state is verified. Payment, delivery, usefulness, renewal, and recurring revenue remain separate evidence."
    )
    acceptance_box = Table([[Paragraph(acceptance, styles["body"])]], colWidths=[7.0 * inch])
    acceptance_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TEAL_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.7, TEAL),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([
        acceptance_box,
        Spacer(1, 6),
        Paragraph(
            "<b>Contact:</b> Justin Hart / Viridis Agent Fleet / viridissecurity1@gmail.com",
            styles["body"],
        ),
    ])

    document.build(story, onFirstPage=on_page, onLaterPages=on_page)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/pdf/regulatory-change-evidence-pack-pilot-scope.pdf"),
    )
    args = parser.parse_args()
    build(args.output)


if __name__ == "__main__":
    main()
