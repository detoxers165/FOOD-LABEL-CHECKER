# ============================================================
# PRODUCT LABEL OCR READER
# Clean-start reader + layout reconstruction
#
# PaddleOCR 3.x
# General-purpose packaged-product labels
# ============================================================

import os

# ------------------------------------------------------------
# IMPORTANT:
# These must be set BEFORE importing Paddle/PaddleOCR.
# ------------------------------------------------------------
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_enable_pir_api"] = "0"

import json
import sys
import statistics

from paddleocr import PaddleOCR


class ProductOCR:

    def __init__(self):

        print("=" * 70)
        print("INITIALIZING PRODUCT LABEL READER")
        print("=" * 70)

        try:

            self.ocr = PaddleOCR(
                lang="en",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False
            )

            print("OCR model loaded successfully.")
            print()

        except Exception as e:

            print()
            print("ERROR: Could not initialize PaddleOCR.")
            print()
            print(str(e))
            sys.exit(1)

    # ========================================================
    # BOX UTILITIES
    # ========================================================

    @staticmethod
    def normalize_box(box):

        if box is None:
            return None

        try:

            if hasattr(box, "tolist"):
                box = box.tolist()

            # Expected format:
            # [x1, y1, x2, y2]

            if len(box) >= 4:

                x1 = float(box[0])
                y1 = float(box[1])
                x2 = float(box[2])
                y2 = float(box[3])

                if x2 < x1:
                    x1, x2 = x2, x1

                if y2 < y1:
                    y1, y2 = y2, y1

                return [
                    int(round(x1)),
                    int(round(y1)),
                    int(round(x2)),
                    int(round(y2))
                ]

        except Exception:
            pass

        return None

    @staticmethod
    def box_info(box):

        if not box:
            return None

        x1, y1, x2, y2 = box

        width = max(1, x2 - x1)
        height = max(1, y2 - y1)

        return {
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "width": width,
            "height": height,
            "center_x": (x1 + x2) / 2,
            "center_y": (y1 + y2) / 2
        }

    # ========================================================
    # EXTRACT RAW OCR REGIONS
    # ========================================================

    def extract_regions(self, results):

        regions = []

        for result in results:

            try:
                data = result["res"]
            except Exception:
                data = result

            texts = data.get("rec_texts", [])
            scores = data.get("rec_scores", [])
            boxes = data.get("rec_boxes", [])

            for i, text in enumerate(texts):

                if text is None:
                    continue

                text = str(text).strip()

                if not text:
                    continue

                # ----------------------------
                # Confidence
                # ----------------------------

                confidence = None

                if i < len(scores):

                    try:
                        confidence = float(scores[i])
                    except Exception:
                        confidence = None

                # ----------------------------
                # Bounding box
                # ----------------------------

                box = None

                if i < len(boxes):

                    box = self.normalize_box(boxes[i])

                if box is None:
                    continue

                info = self.box_info(box)

                regions.append({
                    "id": len(regions) + 1,
                    "text": text,
                    "confidence": confidence,
                    "box": box,

                    # Geometry
                    "x": info["x1"],
                    "y": info["y1"],
                    "width": info["width"],
                    "height": info["height"],
                    "center_x": info["center_x"],
                    "center_y": info["center_y"]
                })

        return regions

    # ========================================================
    # GROUP OCR BOXES INTO LINES
    # ========================================================

    def group_into_lines(self, regions):

        if not regions:
            return []

        # Sort approximately from top to bottom.
        sorted_regions = sorted(
            regions,
            key=lambda r: (
                r["center_y"],
                r["x"]
            )
        )

        heights = [
            r["height"]
            for r in sorted_regions
            if r["height"] > 0
        ]

        if heights:
            median_height = statistics.median(heights)
        else:
            median_height = 20

        # Tolerance for determining whether two OCR boxes
        # belong to the same visual line.
        line_tolerance = max(
            8,
            median_height * 0.55
        )

        lines = []

        for region in sorted_regions:

            placed = False

            for line in lines:

                # Compare with average center of existing line.
                average_y = statistics.mean(
                    r["center_y"]
                    for r in line["regions"]
                )

                vertical_difference = abs(
                    region["center_y"] - average_y
                )

                # Also check vertical overlap.
                region_y1 = region["y"]
                region_y2 = region["y"] + region["height"]

                line_y1 = min(
                    r["y"]
                    for r in line["regions"]
                )

                line_y2 = max(
                    r["y"] + r["height"]
                    for r in line["regions"]
                )

                overlap = max(
                    0,
                    min(region_y2, line_y2)
                    - max(region_y1, line_y1)
                )

                smaller_height = max(
                    1,
                    min(
                        region["height"],
                        line_y2 - line_y1
                    )
                )

                overlap_ratio = (
                    overlap / smaller_height
                )

                if (
                    vertical_difference <= line_tolerance
                    or overlap_ratio >= 0.45
                ):

                    line["regions"].append(region)
                    placed = True
                    break

            if not placed:

                lines.append({
                    "regions": [region]
                })

        # ----------------------------------------------------
        # Sort regions inside each line left -> right
        # ----------------------------------------------------

        final_lines = []

        for line in lines:

            line_regions = sorted(
                line["regions"],
                key=lambda r: r["x"]
            )

            # Calculate complete line bounding box.
            x1 = min(
                r["x"]
                for r in line_regions
            )

            y1 = min(
                r["y"]
                for r in line_regions
            )

            x2 = max(
                r["x"] + r["width"]
                for r in line_regions
            )

            y2 = max(
                r["y"] + r["height"]
                for r in line_regions
            )

            text = self.join_line_text(line_regions)

            confidence_values = [
                r["confidence"]
                for r in line_regions
                if r["confidence"] is not None
            ]

            average_confidence = None

            if confidence_values:
                average_confidence = sum(
                    confidence_values
                ) / len(confidence_values)

            final_lines.append({
                "text": text,
                "confidence": average_confidence,
                "box": [
                    int(x1),
                    int(y1),
                    int(x2),
                    int(y2)
                ],
                "regions": line_regions
            })

        # ----------------------------------------------------
        # Top -> bottom
        # ----------------------------------------------------

        final_lines.sort(
            key=lambda line: (
                line["box"][1],
                line["box"][0]
            )
        )

        # Give lines IDs.
        for index, line in enumerate(
            final_lines,
            start=1
        ):
            line["line_id"] = index

        return final_lines

    # ========================================================
    # JOIN TEXT INSIDE A LINE
    # ========================================================

    @staticmethod
    def join_line_text(regions):

        if not regions:
            return ""

        pieces = []

        for region in regions:

            text = region["text"].strip()

            if not text:
                continue

            if not pieces:

                pieces.append(text)
                continue

            previous = pieces[-1]

            # ------------------------------------------------
            # Avoid unnecessary spaces around punctuation.
            # ------------------------------------------------

            if text.startswith(
                (".", ",", ":", ";", ")", "]", "%")
            ):

                pieces[-1] = previous + text

            elif previous.endswith(
                ("(", "[", "/", "-")
            ):

                pieces[-1] = previous + text

            else:

                pieces.append(text)

        return " ".join(pieces)

    # ========================================================
    # DETECT COLUMNS
    # ========================================================

    def detect_columns(
        self,
        lines,
        image_width
    ):

        if not lines:
            return []

        if image_width <= 0:
            return [{
                "column_id": 1,
                "lines": lines
            }]

        # ----------------------------------------------------
        # We look for a large horizontal whitespace gap
        # separating groups of text.
        #
        # This is intentionally geometry-based and does NOT
        # assume "nutrition is always on the left" etc.
        # ----------------------------------------------------

        line_data = []

        for line in lines:

            x1 = line["box"][0]
            x2 = line["box"][2]

            line_data.append({
                "line": line,
                "x1": x1,
                "x2": x2
            })

        # ----------------------------------------------------
        # Determine whether the page appears to contain
        # separate vertical text regions.
        # ----------------------------------------------------

        # Maximum allowed whitespace relative to image width.
        significant_gap = max(
            60,
            image_width * 0.08
        )

        # Start with one group.
        groups = [
            list(line_data)
        ]

        changed = True

        while changed:

            changed = False
            new_groups = []

            for group in groups:

                if len(group) <= 1:
                    new_groups.append(group)
                    continue

                ordered = sorted(
                    group,
                    key=lambda item: item["x1"]
                )

                best_gap = 0
                best_position = None

                for i in range(
                    len(ordered) - 1
                ):

                    left_item = ordered[i]
                    right_item = ordered[i + 1]

                    gap = (
                        right_item["x1"]
                        - left_item["x2"]
                    )

                    if gap > best_gap:

                        best_gap = gap
                        best_position = i

                if (
                    best_position is not None
                    and best_gap >= significant_gap
                ):

                    left_group = ordered[
                        :best_position + 1
                    ]

                    right_group = ordered[
                        best_position + 1:
                    ]

                    new_groups.append(
                        left_group
                    )

                    new_groups.append(
                        right_group
                    )

                    changed = True

                else:

                    new_groups.append(group)

            groups = new_groups

        # ----------------------------------------------------
        # Avoid treating tiny groups as independent columns.
        # ----------------------------------------------------

        meaningful_groups = []

        for group in groups:

            if len(group) >= 2:
                meaningful_groups.append(group)

        if not meaningful_groups:

            return [{
                "column_id": 1,
                "lines": lines
            }]

        # ----------------------------------------------------
        # Sort columns left -> right.
        # ----------------------------------------------------

        meaningful_groups.sort(
            key=lambda group: min(
                item["x1"]
                for item in group
            )
        )

        columns = []

        for column_number, group in enumerate(
            meaningful_groups,
            start=1
        ):

            column_lines = [
                item["line"]
                for item in group
            ]

            column_lines.sort(
                key=lambda line: (
                    line["box"][1],
                    line["box"][0]
                )
            )

            columns.append({
                "column_id": column_number,
                "lines": column_lines
            })

        return columns

    # ========================================================
    # BUILD LAYOUT READING ORDER
    # ========================================================

    def build_reading_order(
        self,
        lines,
        columns
    ):

        if not lines:
            return []

        # ----------------------------------------------------
        # If only one column exists:
        # top -> bottom
        # ----------------------------------------------------

        if len(columns) <= 1:

            ordered = sorted(
                lines,
                key=lambda line: (
                    line["box"][1],
                    line["box"][0]
                )
            )

            return ordered

        # ----------------------------------------------------
        # Multiple columns:
        #
        # Read top -> bottom within the left column,
        # then top -> bottom within the next column.
        #
        # This is a much better starting point for product
        # labels than globally sorting every OCR box by Y.
        # ----------------------------------------------------

        ordered = []

        for column in columns:

            column_lines = sorted(
                column["lines"],
                key=lambda line: (
                    line["box"][1],
                    line["box"][0]
                )
            )

            ordered.extend(column_lines)

        return ordered

    # ========================================================
    # BUILD SECTION / BLOCK GROUPS
    # ========================================================

    def build_sections(
        self,
        ordered_lines
    ):

        if not ordered_lines:
            return []

        sections = []

        current = []

        for index, line in enumerate(
            ordered_lines
        ):

            current.append(line)

            if index == len(ordered_lines) - 1:

                sections.append(current)
                break

            current_box = line["box"]

            next_line = ordered_lines[
                index + 1
            ]

            next_box = next_line["box"]

            current_bottom = current_box[3]
            next_top = next_box[1]

            vertical_gap = (
                next_top - current_bottom
            )

            current_height = max(
                1,
                current_box[3] - current_box[1]
            )

            # Large gap can indicate a new visual block.
            if vertical_gap > current_height * 2.5:

                sections.append(current)
                current = []

        output_sections = []

        for section_id, section_lines in enumerate(
            sections,
            start=1
        ):

            if not section_lines:
                continue

            text = "\n".join(
                line["text"]
                for line in section_lines
                if line["text"]
            )

            x1 = min(
                line["box"][0]
                for line in section_lines
            )

            y1 = min(
                line["box"][1]
                for line in section_lines
            )

            x2 = max(
                line["box"][2]
                for line in section_lines
            )

            y2 = max(
                line["box"][3]
                for line in section_lines
            )

            output_sections.append({
                "section_id": section_id,
                "text": text,
                "box": [
                    x1,
                    y1,
                    x2,
                    y2
                ],
                "line_count": len(section_lines),
                "lines": section_lines
            })

        return output_sections

    # ========================================================
    # MAIN READ FUNCTION
    # ========================================================

    def read(self, image_path):

        # ----------------------------------------------------
        # Check image path
        # ----------------------------------------------------

        if not os.path.isfile(image_path):

            raise FileNotFoundError(
                f"\nImage not found:\n{image_path}"
            )

        print("=" * 70)
        print("READING IMAGE")
        print("=" * 70)

        print(f"Image: {image_path}")
        print()

        try:

            results = self.ocr.predict(
                image_path
            )

        except Exception as e:

            print()
            print("=" * 70)
            print("OCR INFERENCE ERROR")
            print("=" * 70)
            print(str(e))
            print()

            raise

        # ----------------------------------------------------
        # Determine image size
        # ----------------------------------------------------

        image_width = None
        image_height = None

        try:

            from PIL import Image

            with Image.open(image_path) as img:

                image_width = img.width
                image_height = img.height

        except Exception:

            # Fallback to OCR metadata if available.
            image_width = None
            image_height = None

        # ----------------------------------------------------
        # Raw OCR regions
        # ----------------------------------------------------

        regions = self.extract_regions(
            results
        )

        # ----------------------------------------------------
        # Lines
        # ----------------------------------------------------

        lines = self.group_into_lines(
            regions
        )

        # ----------------------------------------------------
        # Columns
        # ----------------------------------------------------

        if image_width:

            columns = self.detect_columns(
                lines,
                image_width
            )

        else:

            columns = [{
                "column_id": 1,
                "lines": lines
            }]

        # ----------------------------------------------------
        # Reading order
        # ----------------------------------------------------

        ordered_lines = self.build_reading_order(
            lines,
            columns
        )

        # ----------------------------------------------------
        # Sections
        # ----------------------------------------------------

        sections = self.build_sections(
            ordered_lines
        )

        # ----------------------------------------------------
        # Reconstructed full text
        # ----------------------------------------------------

        full_text = "\n".join(
            line["text"]
            for line in ordered_lines
            if line["text"]
        )

        # ----------------------------------------------------
        # Final result
        # ----------------------------------------------------

        output = {

            "success": True,

            "image": os.path.abspath(
                image_path
            ),

            "image_size": {
                "width": image_width,
                "height": image_height
            },

            # Original OCR detections.
            "regions": regions,

            # OCR detections grouped into visual lines.
            "lines": ordered_lines,

            # Detected visual columns.
            "columns": [
                {
                    "column_id": column[
                        "column_id"
                    ],

                    "line_ids": [
                        line["line_id"]
                        for line in column["lines"]
                    ]
                }

                for column in columns
            ],

            # Larger visual sections.
            "sections": sections,

            # Reconstructed document text.
            "full_text": full_text
        }

        return output


# ============================================================
# PRINT RESULT
# ============================================================

def print_result(result):

    print()
    print("=" * 70)
    print("OCR COMPLETE")
    print("=" * 70)

    print()

    print(
        f"Detected OCR regions: "
        f"{len(result['regions'])}"
    )

    print(
        f"Detected lines: "
        f"{len(result['lines'])}"
    )

    print(
        f"Detected columns: "
        f"{len(result['columns'])}"
    )

    print(
        f"Detected sections: "
        f"{len(result['sections'])}"
    )

    # --------------------------------------------------------
    # Reconstructed reading order
    # --------------------------------------------------------

    print()
    print("-" * 70)
    print("RECONSTRUCTED READING ORDER")
    print("-" * 70)

    for number, line in enumerate(
        result["lines"],
        start=1
    ):

        print(
            f"{number:03d}. "
            f"{line['text']}"
        )

        print(
            f"     Confidence: "
            f"{line['confidence']}"
        )

        print(
            f"     Box: "
            f"{line['box']}"
        )

        print()

    # --------------------------------------------------------
    # Sections
    # --------------------------------------------------------

    print()
    print("-" * 70)
    print("DETECTED SECTIONS")
    print("-" * 70)

    for section in result["sections"]:

        print()
        print(
            f"SECTION "
            f"{section['section_id']}"
        )

        print(
            section["text"]
        )

        print()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 70)
    print("PRODUCT LABEL READER")
    print("=" * 70)
    print()

    image_path = input(
        "Enter product image path: "
    ).strip().strip('"')

    if not image_path:

        print()
        print("No image path was provided.")
        sys.exit(1)

    reader = ProductOCR()

    try:

        result = reader.read(
            image_path
        )

        print_result(result)

        # ----------------------------------------------------
        # Save result
        # ----------------------------------------------------

        output_directory = os.path.join(
            os.path.dirname(
                os.path.dirname(
                    os.path.abspath(__file__)
                )
            ),
            "output"
        )

        os.makedirs(
            output_directory,
            exist_ok=True
        )

        output_file = os.path.join(
            output_directory,
            "ocr_result.json"
        )

        with open(
            output_file,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                result,
                file,
                indent=2,
                ensure_ascii=False
            )

        print("=" * 70)
        print("RESULT SAVED")
        print("=" * 70)

        print(output_file)
        print()

    except Exception as e:

        print()
        print("=" * 70)
        print("READER FAILED")
        print("=" * 70)
        print()

        print(str(e))
        print()