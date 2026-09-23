#!/usr/bin/env python3
"""Render a buyer-readable Regulatory Change Evidence Pack PDF."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


NAVY = colors.HexColor("#0A2342")
TEAL = colors.HexColor("#0F766E")
TEAL_LIGHT = colors.HexColor("#CCFBF1")
GREEN_LIGHT = colors.HexColor("#DCFCE7")
ORANGE = colors.HexColor("#C2410C")
ORANGE_LIGHT = colors.HexColor("#FFEDD5")
INK = colors.HexColor("#243447")
MUTED = colors.HexColor("#5B6777")
PAPER = colors.HexColor("#F8FAFC")
BORDER = colors.HexColor("#CBD5E1")
WHITE = colors.white


def ascii_text(value: object) -> str:
    return (
        str(value)
        .replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2011", "-")
        .replace("\u2026", "...")
    )


def safe(value: object) -> str:
    return html.escape(ascii_text(value))


def para(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "kicker": ParagraphStyle(
            "Kicker", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=7.8, leading=10, textColor=TEAL, spaceAfter=7,
        ),
        "title": ParagraphStyle(
            "Title", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=24, leading=27, textColor=NAVY, alignment=TA_LEFT,
            spaceAfter=7,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle", parent=base["Normal"], fontName="Helvetica",
            fontSize=10.5, leading=14, textColor=MUTED, spaceAfter=13,
        ),
        "section": ParagraphStyle(
            "Section", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=13, leading=16, textColor=NAVY, spaceBefore=4,
            spaceAfter=7,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["BodyText"], fontName="Helvetica",
            fontSize=8.3, leading=11.2, textColor=INK,
        ),
        "body_bold": ParagraphStyle(
            "BodyBold", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=8.3, leading=11.2, textColor=INK,
        ),
        "small": ParagraphStyle(
            "Small", parent=base["BodyText"], fontName="Helvetica",
            fontSize=7.1, leading=9.3, textColor=MUTED,
        ),
        "small_white": ParagraphStyle(
            "SmallWhite", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=7.5, leading=9.5, textColor=WHITE,
        ),
        "metric": ParagraphStyle(
            "Metric", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=17, leading=18, textColor=NAVY, alignment=TA_CENTER,
        ),
        "metric_label": ParagraphStyle(
            "MetricLabel", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=6.6, leading=8, textColor=MUTED, alignment=TA_CENTER,
        ),
        "pilot_metric": ParagraphStyle(
            "PilotMetric", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=13.2, leading=14.5, textColor=NAVY, alignment=TA_CENTER,
        ),
        "card_title": ParagraphStyle(
            "CardTitle", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8.5, leading=11, textColor=NAVY,
        ),
        "step": ParagraphStyle(
            "Step", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=7.2, leading=9, textColor=NAVY, alignment=TA_CENTER,
        ),
        "source": ParagraphStyle(
            "Source", parent=base["BodyText"], fontName="Helvetica",
            fontSize=6.1, leading=7.7, textColor=MUTED,
        ),
    }


def metric_card(number: str, label: str, style_map: dict) -> Table:
    table = Table(
        [[para(safe(number), style_map["metric"])],
         [para(safe(label), style_map["metric_label"])]],
        colWidths=[1.58 * inch],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PAPER),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
        ("TOPPADDING", (0, 1), (-1, 1), 1),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
    ]))
    return table


def info_box(title: str, body: str, style_map: dict, *, accent=TEAL,
             background=TEAL_LIGHT) -> Table:
    table = Table([
        [para(safe(title), style_map["card_title"])],
        [para(body, style_map["body"])],
    ], colWidths=[7.0 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), background),
        ("BOX", (0, 0), (-1, -1), 0.7, accent),
        ("LINEBEFORE", (0, 0), (0, -1), 4, accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 11),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
        ("TOPPADDING", (0, 1), (-1, 1), 1),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 9),
    ]))
    return table


def source_label(source_id: str) -> str:
    labels = {
        "carb-climate-disclosure-resources": "Resources",
        "carb-climate-disclosure-rulemaking": "Rulemaking",
        "carb-corporate-climate-program": "Program",
    }
    return labels.get(source_id, source_id)


def on_page(canvas, document) -> None:
    canvas.saveState()
    canvas.setTitle("California SB 253 and SB 261 Regulatory Change Evidence Pack")
    canvas.setAuthor("Viridis Agent Fleet")
    canvas.setSubject("Buyer sample - official-source regulatory monitoring")
    canvas.setStrokeColor(BORDER)
    canvas.line(44, 32, LETTER[0] - 44, 32)
    canvas.setFont("Helvetica", 6.8)
    canvas.setFillColor(MUTED)
    canvas.drawString(44, 20, "VIRIDIS AGENT FLEET  /  SCREENING ONLY - NOT LEGAL ADVICE")
    canvas.drawRightString(
        LETTER[0] - 44, 20, f"CALIFORNIA SAMPLE  /  {document.page}"
    )
    canvas.restoreState()


def build(input_json: Path, output_pdf: Path) -> None:
    data = json.loads(input_json.read_text(encoding="utf-8"))
    style_map = styles()
    live = data["live_source_monitoring"]
    sources = live["sources"]
    calendar = data["curated_deadline_calendar"]
    delivery = data["delivery_receipt"]

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(output_pdf), pagesize=LETTER,
        leftMargin=44, rightMargin=44, topMargin=38, bottomMargin=42,
        title="California SB 253 and SB 261 Regulatory Change Evidence Pack",
        author="Viridis Agent Fleet",
    )
    story = []

    story.extend([
        para("VIRIDIS AGENT FLEET / BUYER SAMPLE / 14 AUG 2026", style_map["kicker"]),
        para("California SB 253 / SB 261<br/>Regulatory Change Evidence Pack", style_map["title"]),
        para(
            "Live, source-hashed screening evidence for an illustrative California reporting company. "
            "Every monitored page is owned by the California Air Resources Board (CARB).",
            style_map["subtitle"],
        ),
    ])

    metrics = Table([[
        metric_card(str(live["retrieved_source_count"]), "OFFICIAL SOURCES", style_map),
        metric_card(str(live["unchanged_count"]), "UNCHANGED ON REPEAT", style_map),
        metric_card(str(live["failed_count"]), "FAILED RETRIEVALS", style_map),
        metric_card("1", "RECENT KEY DATE", style_map),
    ]], colWidths=[1.75 * inch] * 4)
    metrics.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([metrics, Spacer(1, 10)])

    evidence_body = (
        f"CARB retrieval completed for <b>{live['retrieved_source_count']} of "
        f"{live['selected_source_count']}</b> registry-owned sources. The repeat observation "
        f"matched all stored baselines. Pack SHA-256: <font name='Courier'>"
        f"{safe(delivery['pack_sha256'])}</font><br/><br/>"
        "A stable content hash means the normalized page text matched the stored baseline. "
        "It does <b>not</b> prove that legal status, applicability, or external context is unchanged."
    )
    story.extend([
        info_box("Evidence state: verified repeat observation", evidence_body, style_map),
        Spacer(1, 12),
        para("Official-source evidence", style_map["section"]),
    ])

    source_rows = [[
        para("SOURCE", style_map["small_white"]),
        para("OBSERVATION", style_map["small_white"]),
        para("RETRIEVED UTC", style_map["small_white"]),
        para("SHA-256", style_map["small_white"]),
        para("AUTHORITY", style_map["small_white"]),
    ]]
    for source in sources:
        retrieved = ascii_text(source["retrieved_at"]).replace("T", " ").replace("Z", "")[:19]
        source_rows.append([
            para(safe(source_label(source["source_id"])), style_map["body_bold"]),
            para(safe(source["change_status"].replace("_", " ")), style_map["body"]),
            para(safe(retrieved), style_map["small"]),
            para(f"<font name='Courier'>{safe(source['sha256'][:12])}...</font>", style_map["small"]),
            para(f"<a href='{safe(source['source_url'])}' color='#0F766E'>CARB page</a>", style_map["body"]),
        ])
    evidence_table = Table(
        source_rows, repeatRows=1,
        colWidths=[1.12 * inch, 1.05 * inch, 1.27 * inch, 1.15 * inch, 0.95 * inch],
    )
    evidence_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, PAPER]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([evidence_table, Spacer(1, 12)])

    authority_cards = [para("Current authority signals", style_map["section"])]
    for index, source in enumerate(sources, 1):
        card = Table([
            [para(f"{index}. {safe(source['title'])}", style_map["card_title"])],
            [para(
                f"<b>Signal:</b> {safe(source['screening_summary'])}<br/>"
                f"<b>Review focus:</b> {safe(source['review_focus'])}",
                style_map["body"],
            )],
        ], colWidths=[7.0 * inch])
        card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), PAPER),
            ("BOX", (0, 0), (-1, -1), 0.45, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
            ("TOPPADDING", (0, 1), (-1, 1), 1),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
        ]))
        authority_cards.extend([card, Spacer(1, 5)])
    story.append(KeepTogether(authority_cards))

    story.append(PageBreak())
    story.extend([
        para("Deadline and action layer", style_map["kicker"]),
        para("What the evidence asks a reviewer to check", style_map["title"]),
    ])

    change = calendar["changes"][0] if calendar.get("changes") else None
    if change:
        deadline_body = (
            f"The curated calendar flags <b>{safe(change['regulation_name'])}</b> as "
            f"<b>{safe(str(change['overdue_days']))} days past</b> its stored key date "
            f"({safe(change['deadline'][:10])}). Screening alert: <b>critical</b>.<br/><br/>"
            f"{safe(change['scope_note'])} Confirm current applicability, legal effect, "
            "and any relief or enforcement posture with CARB or qualified counsel."
        )
        story.extend([
            info_box(
                "Recently passed key date - human review required",
                deadline_body, style_map, accent=ORANGE, background=ORANGE_LIGHT,
            ),
            Spacer(1, 11),
        ])

    story.extend([
        para("Evidence lifecycle", style_map["section"]),
    ])
    steps = [
        ("1", "Retrieve", "Registry-owned URL"),
        ("2", "Normalize", "Visible main text"),
        ("3", "Hash", "SHA-256 receipt"),
        ("4", "Compare", "Baseline or diff"),
        ("5", "Route", "Reviewer action"),
    ]
    step_cells = []
    for number, label, detail in steps:
        step_cells.append(para(
            f"<font size='13'>{number}</font><br/>{safe(label)}<br/>"
            f"<font name='Helvetica' size='6.3' color='#5B6777'>{safe(detail)}</font>",
            style_map["step"],
        ))
    step_table = Table([step_cells], colWidths=[1.38 * inch] * 5)
    step_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PAPER),
        ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([step_table, Spacer(1, 12)])

    story.append(para("30-day design-partner pilot", style_map["section"]))
    pilot = Table([
        [para("$500", style_map["pilot_metric"]), para("30 DAYS", style_map["pilot_metric"]),
         para("1 JURISDICTION", style_map["pilot_metric"]), para("UP TO 5 SOURCES", style_map["pilot_metric"])],
        [para("TEST PRICE", style_map["metric_label"]), para("PILOT TERM", style_map["metric_label"]),
         para("BOUNDED SCOPE", style_map["metric_label"]), para("OFFICIAL PAGES", style_map["metric_label"])],
    ], colWidths=[1.75 * inch] * 4)
    pilot.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GREEN_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.7, TEAL),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#A7F3D0")),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
    ]))
    story.extend([pilot, Spacer(1, 9)])

    included = (
        "<b>Included</b><br/>"
        "- Initial source-hashed baseline<br/>"
        "- Weekly observations<br/>"
        "- Bounded exact text diff after a change<br/>"
        "- Deadline and action-owner prompts<br/>"
        "- JSON, buyer PDF, and delivery receipt"
    )
    human = (
        "<b>Human review remains required</b><br/>"
        "- Legal conclusions and assurance<br/>"
        "- Entity-specific applicability<br/>"
        "- Filing or regulator communication<br/>"
        "- Interpretation of a hash change<br/>"
        "- Payment and renewal decisions"
    )
    scope_table = Table([
        [para(included, style_map["body"]), para(human, style_map["body"])],
    ], colWidths=[3.45 * inch, 3.45 * inch])
    scope_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), PAPER),
        ("BACKGROUND", (1, 0), (1, 0), ORANGE_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.extend([scope_table, Spacer(1, 10)])

    boundary_body = (
        "This sample proves current source retrieval, hashing, baseline comparison, and "
        "packaging only. Buyer delivery, usefulness, pilot acceptance, payment, renewal, "
        "and recurring revenue remain unset."
    )
    story.extend([
        info_box("Commercial evidence boundary", boundary_body, style_map,
                 accent=NAVY, background=PAPER),
        Spacer(1, 8),
        para(
            "<b>Design-partner contact:</b> Justin Hart / Viridis Agent Fleet / "
            "viridissecurity1@gmail.com",
            style_map["body"],
        ),
        Spacer(1, 6),
        para("Official CARB sources", style_map["card_title"]),
    ])
    for source in sources:
        story.append(para(
            f"{safe(source_label(source['source_id']))}: "
            f"<a href='{safe(source['source_url'])}' color='#0F766E'>"
            f"{safe(source['source_url'])}</a>",
            style_map["source"],
        ))
    if change:
        story.append(para(
            f"Deadline authority: <a href='{safe(change['source_url'])}' color='#0F766E'>"
            f"{safe(change['source_url'])}</a>",
            style_map["source"],
        ))

    document.build(story, onFirstPage=on_page, onLaterPages=on_page)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-json", type=Path, required=True)
    parser.add_argument("--output-pdf", type=Path, required=True)
    args = parser.parse_args()
    build(args.input_json, args.output_pdf)
    print(args.output_pdf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
