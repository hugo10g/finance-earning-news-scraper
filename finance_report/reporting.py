"""Research summaries and Excel workbook generation."""

from numbers import Real

import pandas as pd


REPORT_COLUMNS = [
    "Ticker",
    "Price ($)",
    "Earnings Date",
    "Forward P/E",
    "PEG Ratio",
    "Analyst Upside (%)",
    "Revenue Growth (%)",
    "Projected Holding-Period Upside (%)",
    "Final Combined Score",
    "Recommendation",
    "Research Considerations (Not Advice)",
    "Detailed Rationale",
    "Scraped Statistics",
    "Article Links & Outlets",
]


class ReportingMixin:
    """Build human-readable rationale and export research to Excel."""

    REPORT_COLUMNS = REPORT_COLUMNS

    @staticmethod
    def _coerce_score_column(series: pd.Series) -> pd.Series:
        # Force mixed numeric/text score columns to numeric values so sorting is stable.
        return pd.to_numeric(series, errors="coerce").fillna(0.0)

    def build_research_considerations(self, row: pd.Series) -> str:
        """Summarize rule-based evidence and risks; this is not personalized advice."""
        # Keep the narrative short but explicit so users understand the screening logic.
        notes = []
        growth = row.get("Revenue Growth (%)")
        upside = row.get("Projected Holding-Period Upside (%)")
        peg = row.get("PEG Ratio")
        if isinstance(growth, Real):
            notes.append(
                f"Revenue growth of {growth:+.1f}% is a "
                f"{'positive' if growth > 0 else 'weak/negative'} fundamental signal."
            )
        else:
            notes.append("Revenue-growth data is unavailable; verify recent filings before relying on the score.")
        if isinstance(upside, Real):
            notes.append(
                f"Analyst-target extrapolation for the selected horizon is {upside:+.1f}%; "
                "this is an estimate, not a forecast guarantee."
            )
        if isinstance(peg, Real):
            if peg >= 2.5:
                notes.append(f"PEG of {peg:.2f} is above this model's 2.5 valuation screen.")
            elif peg > 0:
                notes.append(f"PEG of {peg:.2f} is below this model's 2.5 valuation screen; confirm earnings assumptions.")
        if row.get("Article Pages Read", 0) == 0 and row.get("Article Summaries Used", 0) > 0:
            notes.append(
                "Online evidence came from search summaries rather than readable article pages; "
                "independently verify figures and dates."
            )
        elif row.get("Article Pages Read", 0) == 0:
            notes.append("No readable article pages were verified; treat news-based evidence as limited.")
        notes.append(
            "Review earnings timing, cash flow, debt, and the original filings before making an investment decision."
        )
        return " ".join(notes) + " Not personalized financial advice."

    def build_rationale(self, row: pd.Series) -> str:
        holding_period_months = getattr(self, "holding_period_months", 1)
        score = row.get("Final Score", 0.0)
        score_value = pd.to_numeric(score, errors="coerce")
        score_text = f"{float(score_value) if pd.notna(score_value) else 0.0:.3f}"
        lines = [
            f"RULE-BASED {row.get('Recommendation', 'HOLD / WATCH')}: "
            f"combined score {score_text}.",
            f"Revenue growth: {row.get('Revenue Growth (%)', 'N/A')}%; "
            f"{row.get('Holding Period (Months)', holding_period_months)}-month horizon.",
        ]
        upside = row.get("Projected Holding-Period Upside (%)", "N/A")
        if upside != "N/A":
            lines.append(f"Projected horizon upside: {upside}%.")
        lines.append(f"PEG Ratio: {row.get('PEG Ratio', 'N/A')}.")
        fundamentals = row.get("Yahoo Finance Fundamentals", "N/A")
        if fundamentals and fundamentals != "N/A":
            lines.append(f"Fundamentals: {fundamentals}")
        lines.append(f"News research: {row.get('Detailed Reasons & News Findings', 'N/A')}")
        return "\n".join(lines)

    def build_signal_justification_report(self, full_df: pd.DataFrame) -> pd.DataFrame:
        if full_df.empty:
            return pd.DataFrame(columns=self.REPORT_COLUMNS)
        rows = []
        for _, row in full_df.iterrows():
            rows.append(
                {
                    "Ticker": row.get("Ticker", ""),
                    "Price ($)": row.get("Price ($)", "N/A"),
                    "Earnings Date": row.get("Earnings Date", "N/A"),
                    "Forward P/E": row.get("Forward P/E", "N/A"),
                    "PEG Ratio": row.get("PEG Ratio", "N/A"),
                    "Analyst Upside (%)": row.get("Analyst Upside (%)", "N/A"),
                    "Revenue Growth (%)": row.get("Revenue Growth (%)", "N/A"),
                    "Projected Holding-Period Upside (%)": row.get("Projected Holding-Period Upside (%)", "N/A"),
                    "Final Combined Score": row.get("Final Score", "N/A"),
                    "Recommendation": row.get("Recommendation", "HOLD / WATCH"),
                    "Research Considerations (Not Advice)": self.build_research_considerations(row),
                    "Detailed Rationale": self.build_rationale(row),
                    "Scraped Statistics": row.get("Scraped Statistics", "N/A"),
                    "Article Links & Outlets": row.get("Article Links & Outlets", "N/A"),
                }
            )
        report_df = pd.DataFrame(rows, columns=self.REPORT_COLUMNS)
        if "Final Combined Score" in report_df.columns:
            report_df["Final Combined Score"] = self._coerce_score_column(report_df["Final Combined Score"])
        return report_df.sort_values(by="Final Combined Score", ascending=False, kind="stable")

    @staticmethod
    def format_signal_worksheet(worksheet) -> None:
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.worksheet.table import Table, TableStyleInfo

        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        worksheet.sheet_view.showGridLines = False
        widths = {
            "A": 12,
            "B": 13,
            "C": 16,
            "D": 14,
            "E": 12,
            "F": 21,
            "G": 18,
            "H": 22,
            "I": 23,
            "J": 19,
            "K": 65,
            "L": 75,
            "M": 75,
            "N": 45,
        }
        for column, width in widths.items():
            worksheet.column_dimensions[column].width = width
        header_fill = PatternFill("solid", fgColor="4472C4")
        alternate_fill = PatternFill("solid", fgColor="D9E5F3")
        for cell in worksheet[1]:
            cell.fill = header_fill
            cell.font = Font(color="FFFFFF", bold=True)
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        worksheet.row_dimensions[1].height = 32
        for row_number in range(2, worksheet.max_row + 1):
            if row_number % 2 == 0:
                for cell in worksheet[row_number]:
                    cell.fill = alternate_fill
            for cell in worksheet[row_number]:
                cell.alignment = Alignment(vertical="top", wrap_text=cell.column >= 9)
            worksheet.row_dimensions[row_number].height = 60
        if worksheet.max_row > 1 and worksheet.max_column >= 1:
            table = Table(displayName="SignalJustification", ref=worksheet.dimensions)
            table.tableStyleInfo = TableStyleInfo(
                name="TableStyleMedium2",
                showFirstColumn=False,
                showLastColumn=False,
                showRowStripes=True,
                showColumnStripes=False,
            )
            worksheet.add_table(table)

    def export_report(
        self,
        execution_df: pd.DataFrame,
        full_df: pd.DataFrame,
        filename: str = "explicit_selenium_report.xlsx",
    ) -> None:
        try:
            with pd.ExcelWriter(filename, engine="openpyxl") as writer:
                # Always export a shortlist sheet; if there are no buy candidates,
                # provide a clear notice instead of leaving a blank workbook.
                if not execution_df.empty:
                    execution_df.to_excel(writer, sheet_name="Priority Research List", index=False)
                else:
                    pd.DataFrame([{"Notice": "No BUY signals triggered."}]).to_excel(
                        writer, sheet_name="Priority Research List", index=False
                    )

                # Write the full signal justification and a detailed row-level export.
                self.build_signal_justification_report(full_df).to_excel(
                    writer, sheet_name="Full Signal Justification", index=False
                )
                if not full_df.empty:
                    research_df = full_df.copy()
                    if "Final Score" in research_df.columns:
                        research_df["Final Score"] = self._coerce_score_column(research_df["Final Score"])
                    research_df.sort_values(by="Final Score", ascending=False, kind="stable").to_excel(
                        writer, sheet_name="Research Details", index=False
                    )
                self.format_signal_worksheet(writer.sheets["Full Signal Justification"])
            print(f"\nSUCCESS: Exported report to '{filename}'.")
        except Exception as exc:
            print(f"Error exporting Excel file: {exc}")
