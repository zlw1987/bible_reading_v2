import argparse
import csv
from pathlib import Path


def clean_value(value):
    if value is None:
        return ""

    return str(value).strip()


def main():
    parser = argparse.ArgumentParser(
        description="Normalize a legacy reading plan CSV into Django import format."
    )

    parser.add_argument("--input", required=True, help="Legacy CSV input path.")
    parser.add_argument("--output", required=True, help="Clean CSV output path.")

    parser.add_argument("--day-column", required=True, help="Legacy day number column.")
    parser.add_argument("--reading-column", required=True, help="Legacy reading text column.")
    parser.add_argument("--memory-column", default="", help="Legacy memory verse column.")

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []

    with input_path.open("r", encoding="utf-8-sig", newline="") as input_file:
        reader = csv.DictReader(input_file)

        if not reader.fieldnames:
            raise ValueError("Input CSV has no headers.")

        required_columns = {args.day_column, args.reading_column}

        if args.memory_column:
            required_columns.add(args.memory_column)

        missing_columns = required_columns - set(reader.fieldnames)

        if missing_columns:
            raise ValueError(
                f"Missing column(s): {', '.join(sorted(missing_columns))}. "
                f"Available columns: {', '.join(reader.fieldnames)}"
            )

        for line_number, row in enumerate(reader, start=2):
            day_raw = clean_value(row.get(args.day_column))
            reading_text = clean_value(row.get(args.reading_column))
            memory_verse = clean_value(row.get(args.memory_column)) if args.memory_column else ""

            if not day_raw:
                raise ValueError(f"Line {line_number}: day number is blank.")

            try:
                day_number = int(day_raw)
            except ValueError:
                raise ValueError(f"Line {line_number}: invalid day number: {day_raw}")

            if day_number <= 0:
                raise ValueError(f"Line {line_number}: day number must be greater than 0.")

            if not reading_text:
                raise ValueError(f"Line {line_number}: reading text is blank.")

            rows.append({
                "day_number": day_number,
                "reading_text": reading_text,
                "memory_verse": memory_verse,
            })

    rows.sort(key=lambda item: item["day_number"])

    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=["day_number", "reading_text", "memory_verse"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Normalized {len(rows)} row(s).")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()