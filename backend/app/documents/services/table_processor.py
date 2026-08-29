import csv
import io
import re
from decimal import Decimal
from uuid import UUID

from app.documents.domain.models import (
    StructuredTable,
    TableCell,
    TableDimension,
    sanitize_cell_value,
)


class TableProcessor:
    @classmethod
    def parse_markdown_table(
        cls, element_id: UUID, markdown_text: str, title: str | None = None
    ) -> StructuredTable:
        lines = [
            line.strip() for line in markdown_text.strip().split("\n") if line.strip()
        ]
        if not lines:
            return StructuredTable(
                element_id=element_id,
                title=title,
                headers=[],
                dimensions=TableDimension(row_count=0, col_count=0),
                cells=[],
                summary=None,
            )

        # Filter out markdown divider line (e.g. |---|---|)
        divider_pattern = re.compile(r"^\|?(\s*:?-+:?\s*\|?)+$")
        parsed_rows: list[list[str]] = []
        for line in lines:
            if divider_pattern.match(line):
                continue
            # Split cells by pipe
            raw_cells = [c.strip() for c in line.strip("|").split("|")]
            parsed_rows.append(raw_cells)

        if not parsed_rows:
            return StructuredTable(
                element_id=element_id,
                title=title,
                headers=[],
                dimensions=TableDimension(row_count=0, col_count=0),
                cells=[],
                summary=None,
            )

        headers = parsed_rows[0]
        data_rows = parsed_rows[1:]
        col_count = len(headers)
        row_count = len(data_rows)

        cells: list[TableCell] = []
        for r_idx, row in enumerate(data_rows):
            for c_idx in range(col_count):
                raw_val = row[c_idx] if c_idx < len(row) else ""
                numeric_val, sanitized_val = sanitize_cell_value(raw_val)
                cells.append(
                    TableCell(
                        row_index=r_idx,
                        col_index=c_idx,
                        raw_value=raw_val,
                        sanitized_value=sanitized_val,
                        numeric_value=numeric_val,
                        row_span=1,
                        col_span=1,
                    )
                )

        summary = cls._generate_summary(title, headers, row_count, col_count)
        return StructuredTable(
            element_id=element_id,
            title=title,
            headers=headers,
            dimensions=TableDimension(row_count=row_count, col_count=col_count),
            cells=cells,
            summary=summary,
        )

    @classmethod
    def parse_csv_table(
        cls, element_id: UUID, csv_text: str, title: str | None = None
    ) -> StructuredTable:
        reader = csv.reader(io.StringIO(csv_text.strip()))
        rows = list(reader)
        if not rows:
            return StructuredTable(
                element_id=element_id,
                title=title,
                headers=[],
                dimensions=TableDimension(row_count=0, col_count=0),
                cells=[],
                summary=None,
            )

        headers = [h.strip() for h in rows[0]]
        data_rows = rows[1:]
        col_count = len(headers)
        row_count = len(data_rows)

        cells: list[TableCell] = []
        for r_idx, row in enumerate(data_rows):
            for c_idx in range(col_count):
                raw_val = row[c_idx].strip() if c_idx < len(row) else ""
                numeric_val, sanitized_val = sanitize_cell_value(raw_val)
                cells.append(
                    TableCell(
                        row_index=r_idx,
                        col_index=c_idx,
                        raw_value=raw_val,
                        sanitized_value=sanitized_val,
                        numeric_value=numeric_val,
                        row_span=1,
                        col_span=1,
                    )
                )

        summary = cls._generate_summary(title, headers, row_count, col_count)
        return StructuredTable(
            element_id=element_id,
            title=title,
            headers=headers,
            dimensions=TableDimension(row_count=row_count, col_count=col_count),
            cells=cells,
            summary=summary,
        )

    @classmethod
    def execute_aggregation(
        cls,
        table: StructuredTable,
        column_name: str,
        operation: str = "SUM",
    ) -> Decimal | None:
        """
        Executes a deterministic Decimal arithmetic aggregation on a named column.
        Supported operations: SUM, AVG, MIN, MAX, COUNT.
        """
        try:
            col_idx = table.headers.index(column_name)
        except ValueError:
            return None

        values: list[Decimal] = []
        for cell in table.cells:
            if cell.col_index == col_idx and cell.numeric_value is not None:
                values.append(cell.numeric_value)

        if not values:
            return None

        op_upper = operation.upper()
        if op_upper == "SUM":
            return sum(values, Decimal(0))
        elif op_upper == "AVG":
            return sum(values, Decimal(0)) / Decimal(len(values))
        elif op_upper == "MIN":
            return min(values)
        elif op_upper == "MAX":
            return max(values)
        elif op_upper == "COUNT":
            return Decimal(len(values))
        return None

    @classmethod
    def to_markdown(cls, table: StructuredTable) -> str:
        if not table.headers:
            return ""
        header_row = "| " + " | ".join(table.headers) + " |"
        divider_row = "| " + " | ".join(["---"] * len(table.headers)) + " |"
        data_rows_dict: dict[int, list[str]] = {
            r: [""] * len(table.headers) for r in range(table.dimensions.row_count)
        }

        for cell in table.cells:
            if cell.row_index in data_rows_dict and cell.col_index < len(table.headers):
                data_rows_dict[cell.row_index][cell.col_index] = cell.sanitized_value

        rows = [header_row, divider_row]
        for r_idx in sorted(data_rows_dict.keys()):
            rows.append("| " + " | ".join(data_rows_dict[r_idx]) + " |")

        return "\n".join(rows)

    @classmethod
    def _generate_summary(
        cls, title: str | None, headers: list[str], row_count: int, col_count: int
    ) -> str:
        parts = []
        if title:
            parts.append(f"Table '{title}'")
        else:
            parts.append("Structured table")
        parts.append(f"with {row_count} rows and {col_count} columns.")
        if headers:
            parts.append(f"Columns: {', '.join(headers)}.")
        return " ".join(parts)
