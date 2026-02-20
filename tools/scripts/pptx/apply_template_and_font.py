#!/usr/bin/env python3
"""
Apply Colppy template and set Nunito font for PowerPoint presentations.
======================================================================
Replaces theme, slide master, and layouts from a template file into a target
presentation, then sets all text to Nunito Sans (Nunito Normal).
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run(cmd: list[str], cwd: Path | None = None) -> None:
    """Run command, raise on failure."""
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")


def apply_template_and_font(
    template_path: Path,
    target_path: Path,
    output_path: Path,
    font_name: str = "Nunito Sans",
) -> None:
    """
    Apply template theme/master/layouts to target and set font to Nunito Sans.

    - Replaces target's theme, slideMasters, slideLayouts with template's
    - Copies template's fonts and media
    - Updates slide layout references (slide 1 -> cover layout, others -> content)
    - Replaces all typeface attributes with Nunito Sans
    """
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        target_dir = work / "target"
        template_dir = work / "template"

        # Extract both
        run(["unzip", "-q", "-o", str(target_path), "-d", str(target_dir)])
        run(["unzip", "-q", "-o", str(template_path), "-d", str(template_dir)])

        ppt_target = target_dir / "ppt"
        ppt_tpl = template_dir / "ppt"

        # Remove target's theme, masters, layouts
        for d in ("theme", "slideMasters", "slideLayouts"):
            shutil.rmtree(ppt_target / d, ignore_errors=True)

        # Copy template's theme, masters, layouts
        shutil.copytree(ppt_tpl / "theme", ppt_target / "theme")
        shutil.copytree(ppt_tpl / "slideMasters", ppt_target / "slideMasters")
        shutil.copytree(ppt_tpl / "slideLayouts", ppt_target / "slideLayouts")

        # Copy template's fonts (needed for Nunito)
        if (ppt_tpl / "fonts").exists():
            if (ppt_target / "fonts").exists():
                shutil.rmtree(ppt_target / "fonts")
            shutil.copytree(ppt_tpl / "fonts", ppt_target / "fonts")

        # Merge template's media (layouts reference Colppy assets)
        if (ppt_tpl / "media").exists():
            media_target = ppt_target / "media"
            media_target.mkdir(exist_ok=True)
            for f in (ppt_tpl / "media").iterdir():
                if f.is_file():
                    shutil.copy2(f, media_target / f.name)

        # Update presentation.xml.rels: use template's theme (theme2)
        pres_rels = ppt_target / "_rels" / "presentation.xml.rels"
        rels_content = pres_rels.read_text(encoding="utf-8")
        rels_content = rels_content.replace(
            'Target="theme/theme1.xml"',
            'Target="theme/theme2.xml"',
        )
        # Add template's font relationships (keep target's slide/slideMaster refs)
        # Build new rels: keep target's structure for slides, merge template fonts
        pres_rels.write_text(rels_content, encoding="utf-8")

        # Update slide layout references
        # Template: slideLayout10 = Título Cover, slideLayout11 = Subtítulo + Título 1
        layout_map = {
            "slideLayout12": "slideLayout10",  # cover
            "slideLayout11": "slideLayout11",
            "slideLayout10": "slideLayout11",
            "slideLayout13": "slideLayout11",
            "slideLayout14": "slideLayout11",
            "slideLayout15": "slideLayout11",
            "slideLayout16": "slideLayout11",
            "slideLayout17": "slideLayout11",
            "slideLayout18": "slideLayout11",
            "slideLayout19": "slideLayout11",
            "slideLayout1": "slideLayout10",
            "slideLayout2": "slideLayout11",
            "slideLayout3": "slideLayout11",
            "slideLayout4": "slideLayout11",
            "slideLayout5": "slideLayout11",
            "slideLayout6": "slideLayout11",
            "slideLayout7": "slideLayout11",
            "slideLayout8": "slideLayout11",
            "slideLayout9": "slideLayout11",
        }

        slides_rels = ppt_target / "slides" / "_rels"
        for rel_file in sorted(slides_rels.glob("slide*.xml.rels")):
            content = rel_file.read_text(encoding="utf-8")
            for old, new in layout_map.items():
                content = content.replace(
                    f"slideLayouts/{old}.xml",
                    f"slideLayouts/{new}.xml",
                )
            rel_file.write_text(content, encoding="utf-8")

        # Update master's rels to use template's theme
        master_rels = ppt_target / "slideMasters" / "_rels" / "slideMaster1.xml.rels"
        if master_rels.exists():
            # Template master may reference theme2
            tpl_master_rels = ppt_tpl / "slideMasters" / "_rels" / "slideMaster1.xml.rels"
            if tpl_master_rels.exists():
                shutil.copy(tpl_master_rels, master_rels)

        # Replace all fonts in slides with Nunito Sans
        font_pattern = re.compile(
            r'typeface="[^"]*"',
            re.IGNORECASE,
        )
        bu_font_pattern = re.compile(
            r'buFont typeface="[^"]*"',
            re.IGNORECASE,
        )

        for slide_file in ppt_target.glob("slides/slide*.xml"):
            content = slide_file.read_text(encoding="utf-8")
            content = font_pattern.sub(f'typeface="{font_name}"', content)
            content = bu_font_pattern.sub(f'buFont typeface="{font_name}"', content)
            slide_file.write_text(content, encoding="utf-8")

        # Replace fonts in charts if any
        charts_dir = ppt_target / "charts"
        if charts_dir.exists():
            for chart_file in charts_dir.glob("*.xml"):
                content = chart_file.read_text(encoding="utf-8")
                content = font_pattern.sub(f'typeface="{font_name}"', content)
                chart_file.write_text(content, encoding="utf-8")

        # Rezip (preserve directory structure)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        run(
            [
                "zip",
                "-q",
                "-r",
                str(output_path),
                ".",
            ],
            cwd=target_dir,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply Colppy template and Nunito font to a PowerPoint presentation",
    )
    parser.add_argument(
        "template",
        type=Path,
        help="Path to template .pptx (e.g. All Template Base Colppy 2025.pptx)",
    )
    parser.add_argument(
        "target",
        type=Path,
        help="Path to target .pptx (e.g. Subiendo la Vara: Definición de Objetivos 2026.pptx)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output path (default: target with _styled suffix)",
    )
    parser.add_argument(
        "--font",
        default="Nunito Sans",
        help="Font to apply (default: Nunito Sans)",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite target file instead of creating new file",
    )
    args = parser.parse_args()

    if not args.template.exists():
        print(f"Error: Template not found: {args.template}", file=sys.stderr)
        sys.exit(1)
    if not args.target.exists():
        print(f"Error: Target not found: {args.target}", file=sys.stderr)
        sys.exit(1)

    if args.in_place:
        output = args.target
    elif args.output:
        output = args.output
    else:
        stem = args.target.stem
        output = args.target.parent / f"{stem}_styled.pptx"

    try:
        apply_template_and_font(
            template_path=args.template,
            target_path=args.target,
            output_path=output,
            font_name=args.font,
        )
        print(f"Done. Output: {output}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
